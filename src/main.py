import asyncio
import logging
import requests
import base64
import re
import uuid
from email import message_from_bytes, policy
from quopri import decodestring

from custom import CustomController
from aiosmtpd.smtp import AuthResult

import sslContext
import azure_table
from env import (
    LOG_LEVEL,
    TLS_SOURCE,
    REQUIRE_TLS,
    SERVER_GREETING,
    TLS_CERT_FILEPATH,
    TLS_KEY_FILEPATH,
    TLS_CIPHER_SUITE,
    USERNAME_DELIMITER,
    AZURE_KEY_VAULT_URL,
    AZURE_KEY_VAULT_CERT_NAME,
    AZURE_TABLES_FORCE_USAGE
)




def decode_uuid_or_base64url(input_str: str) -> str:
    """
    Checks if input is a UUID string, otherwise attempts to decode as base64url and convert to UUID string.
    Returns a decoded string in UUID format.
    """

    # check if the input is a UUID
    uuid_pattern = re.compile(r'^[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}$')
    if uuid_pattern.match(input_str):
        return input_str

    # Attempt to decode as base64url
    try:
        return str(uuid.UUID(bytes=base64.urlsafe_b64decode(input_str + '=' * (-len(input_str) % 4))))
    except Exception:
        raise ValueError(f"Invalid base64url encoding in input '{input_str}'")



def parse_username(username: str) -> tuple[str, str, str|None]:
    """
    Parse the username to extract tenant_id and client_id.
    The expected format is: tenant_id{USERNAME_DELIMITER}client_id{. optional_tld}
    """
    
    # remove the optional TLD if present
    if '.' in username:
        username = username.split('.')[0]

    # Check if username is valid
    if not username or USERNAME_DELIMITER not in username:
        raise ValueError(f"Invalid username format. Expected format: tenant_id{USERNAME_DELIMITER}client_id")
    
    # Split the username by the delimiter
    parts = username.split(USERNAME_DELIMITER)
    if len(parts) != 2:
        raise ValueError(f"Invalid username format. Expected exactly one '{USERNAME_DELIMITER}' character")
    
    # check if the second part hints a user stored in the lookup table
    if parts[1] == 'lookup':
        return azure_table.lookup_user(parts[0])

    # else return both parts decoded
    tenant_id = decode_uuid_or_base64url(parts[0])
    client_id = decode_uuid_or_base64url(parts[1])

    # If AZURE_TABLES_FORCE_USAGE is enabled, verify the user exists in the table
    if AZURE_TABLES_FORCE_USAGE:
        from_email = azure_table.verify_user_in_table(tenant_id, client_id)
        return tenant_id, client_id, from_email

    return tenant_id, client_id, None


def get_access_token(tenant_id: str, client_id: str, client_secret: str) -> str:
    data = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "https://graph.microsoft.com/.default"
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    
    try:
        response = requests.post(
            url=f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token", 
            data=data, 
            headers=headers
        )
        response.raise_for_status()
        return response.json().get("access_token")
    except requests.RequestException as e:
        logging.error(f"OAuth token request failed: {str(e)}")
        if hasattr(e, 'response') and e.response:
            logging.error(f"Response status: {e.response.status_code}, Response body: {e.response.text}")
        raise

def _sanitize_mime_encoding(raw_message: bytes) -> bytes:
    """
    Convert quoted-printable MIME parts to base64 before sending to Graph API.
    """

    def _convert_parts(msg, location: str = 'root') -> bool:
        modified = False
        if msg.is_multipart():
            for index, part in enumerate(msg.get_payload()):
                if _convert_parts(part, f"{location}.{index}"):
                    modified = True
        else:
            if msg.get('Content-Transfer-Encoding', '').lower().strip() == 'quoted-printable':
                logging.debug(
                    f"Converting quoted-printable MIME part at {location} "
                    f"(content-type={msg.get_content_type()})"
                )
                qp_payload = msg.get_payload(decode=False)
                if isinstance(qp_payload, str):
                    decoded = decodestring(qp_payload.encode('ascii', errors='surrogateescape'))
                else:
                    decoded = decodestring(qp_payload)
                msg.set_payload(base64.encodebytes(decoded).decode('ascii'))
                del msg['Content-Transfer-Encoding']
                msg['Content-Transfer-Encoding'] = 'base64'
                modified = True
        return modified

    try:
        msg = message_from_bytes(raw_message, policy=policy.compat32)
        if _convert_parts(msg):
            logging.info("Sanitized MIME encoding")
            return msg.as_bytes()
        logging.debug("No quoted-printable MIME parts found; message unchanged")
    except Exception:
        logging.exception("Failed to sanitize MIME encoding; sending original raw message")
    return raw_message


def send_email(access_token: str, body: bytes, from_email: str) -> bool:
    url = f"https://graph.microsoft.com/v1.0/users/{from_email}/sendMail"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "text/plain"
    }
    
    try:
        data = base64.b64encode(_sanitize_mime_encoding(body))
        logging.debug(f"Sending email from {from_email}")
        
        response = requests.post(url, data=data, headers=headers)
        if response.status_code == 202:
            logging.info("Email sent successfully!")
            return True
        else:
            logging.error(f"Failed to send email: Status code {response.status_code}")
            logging.error(f"Response body: {response.text}")
            return False
    except Exception as e:
        logging.exception(f"Exception while sending email: {str(e)}")
        return False



class Authenticator:
    def __call__(self, server, session, envelope, mechanism, auth_data):
        try:
            # Only support LOGIN and PLAIN mechanisms
            if mechanism not in ('LOGIN', 'PLAIN'):
                logging.warning(f"Unsupported auth mechanism: {mechanism}")
                return AuthResult(success=False, handled=False, message="504 5.7.4 Unsupported authentication mechanism")
                
            # Check if authentication data is present
            if not auth_data or not auth_data.login or not auth_data.password:
                logging.warning("Missing authentication data")
                return AuthResult(success=False, handled=False, message="535 5.7.8 Authentication credentials missing")
                
            try:
                login_str = auth_data.login.decode("utf-8")
            except Exception as e:
                logging.error(f"Failed to decode login string: {str(e)}")
                return AuthResult(success=False, handled=False, message="535 5.7.8 Invalid authentication credentials encoding")
            
            # Parse tenant_id and client_id from login string using the configured format
            try:
                tenant_id, client_id, from_email = parse_username(login_str)
            except ValueError as e:
                logging.error(str(e))
                return AuthResult(success=False, handled=False, message=f"535 5.7.8 {str(e)}")
                
            client_secret = auth_data.password
            session.lookup_from_email = from_email

            try:
                session.access_token = get_access_token(tenant_id, client_id, client_secret)
                return AuthResult(success=True)
            except Exception as e:
                logging.error(f"Authentication failed: {str(e)}")
                return AuthResult(success=False, handled=False, message="535 5.7.8 Authentication failed")
                
        except Exception as e:
            logging.exception(f"Unexpected error during authentication: {str(e)}")
            return AuthResult(success=False, handled=False, message="554 5.7.0 Unexpected error during authentication")


class Handler:
    async def handle_DATA(self, server, session, envelope):
        logging.debug(f"SMTP envelope: mail_from={envelope.mail_from}, rcpt_tos={envelope.rcpt_tos}")

        if not hasattr(session, 'access_token'):
            logging.error("No access token available in session")
            return "530 5.7.0 Authentication required"

        try:
            raw_envelope = message_from_bytes(envelope.content)
        except Exception as e:
            logging.exception("Failed to parse incoming message bytes")
            return "554 Transaction failed"

        # apply any necessary fixes for known issues
        fixes_applied = False
        fixes_applied |= self._fix_missing_bcc(raw_envelope, envelope.rcpt_tos)
        override_applied, mail_from = self._apply_from_override(raw_envelope, session, envelope.mail_from)
        fixes_applied |= override_applied

        if fixes_applied:
            logging.debug("Applied fixes to email headers before sending")
            success = send_email(session.access_token, raw_envelope.as_bytes(), mail_from)
        else:
            success = send_email(session.access_token, envelope.content, envelope.mail_from)

        if success:
            logging.info("DATA command processed successfully")
            return "250 OK"

        logging.error("DATA command failed during send_email")
        return "554 Transaction failed"

    def _fix_missing_bcc(self, raw_envelope, rcpt_tos) -> bool:
        """Ensure Bcc header contains any recipients missing from To/Cc.
        Return True if a fix was applied, False otherwise.

        Issue #82: some clients do not include Bcc recipients in the headers
        at all, which causes Graph to drop them. The workaround is to compute
        which rcpt_tos are not already in To/Cc and add them as a Bcc header.
        """

        to_headers = raw_envelope.get_all('To', [])
        cc_headers = raw_envelope.get_all('Cc', [])
        total_headers = len(to_headers) + len(cc_headers)
        logging.debug(f"Headers count - To: {len(to_headers)}, Cc: {len(cc_headers)}")

        if len(rcpt_tos) <= total_headers:
            logging.debug("No missing recipients detected; skipping Bcc fixup")
            return False

        header_recipients = set(to_headers + cc_headers)
        missing = set(rcpt_tos) - header_recipients
        if not missing:
            logging.debug("Mismatch between rcpt_tos and headers, but no missing recipients")
            return False
        
        logging.info(f"Adding Bcc header for missing recipients: {sorted(missing)}")
        # preserve any existing Bcc header by appending if present
        existing_bcc = raw_envelope.get_all('Bcc', [])
        combined = list(existing_bcc) + sorted(missing)
        raw_envelope['Bcc'] = ", ".join(combined)
        return True

    def _apply_from_override(self, raw_envelope, session, default_mail_from) -> tuple[bool, str]:
        """When lookup_from_email is configured replace the From header.
        Returns a a tuple of (was_overridden, new_mail_from). If no override was applied, returns (False, default_mail_from).

        Some SMTP clients (issue #36) do not allow the From address to differ
        from the authenticated user.  We drop any existing From headers and
        insert the value stored in ``session.lookup_from_email`` if set.
        Returns the mail_from value that should be supplied to Graph.
        """

        if not getattr(session, 'lookup_from_email', None):
            logging.debug("No from-override configured; using envelope.mail_from")
            return False, default_mail_from

        new_from = session.lookup_from_email
        logging.info(f"Overriding From header to '{new_from}' per lookup_from_email setting")

        # remove all existing From headers
        while 'From' in raw_envelope:
            del raw_envelope['From']

        raw_envelope['From'] = new_from
        return True, new_from



# noinspection PyShadowingNames
async def amain():
    match TLS_SOURCE:
        case 'file':
            context = sslContext.from_file(TLS_CERT_FILEPATH, TLS_KEY_FILEPATH)
            logging.info(f"Loaded certificate from file: {TLS_CERT_FILEPATH}")
            
        case 'keyvault':
            if not AZURE_KEY_VAULT_URL or not AZURE_KEY_VAULT_CERT_NAME:
                logging.error("Azure Key Vault URL and Certificate Name must be set when TLS_SOURCE is 'keyvault'")
                raise ValueError("Azure Key Vault URL and Certificate Name must be set")
            context = sslContext.from_keyvault(AZURE_KEY_VAULT_URL, AZURE_KEY_VAULT_CERT_NAME)
            logging.info(f"Loaded certificate from Azure Key Vault: {AZURE_KEY_VAULT_CERT_NAME}")
            
        case 'off':
            context = None

        case _:
            logging.error(f"Invalid TLS_SOURCE: {TLS_SOURCE}")
            raise ValueError(f"Invalid TLS_SOURCE: {TLS_SOURCE}")

    # Configure TLS cipher suite if specified
    if context:
        if TLS_CIPHER_SUITE:
            context.set_ciphers(TLS_CIPHER_SUITE)

        logging.info(f"TLS cipher suites used: {', '.join([i['name'] for i in context.get_ciphers()])}")

    # If AZURE_TABLES_FORCE_USAGE is enabled, verify table access at startup
    if AZURE_TABLES_FORCE_USAGE:
        azure_table.verify_table_access()
        logging.info("Azure Table access verified (AZURE_TABLES_FORCE_USAGE=true)")

    controller = None
    try:
        controller = CustomController(
            Handler(),
            hostname='', # bind dual-stack on all interfaces
            port=8025,
            ident=SERVER_GREETING,
            authenticator=Authenticator(),
            auth_required=True,
            auth_require_tls=REQUIRE_TLS,
            require_starttls=REQUIRE_TLS,
            tls_context=context
        )
        controller.start()
        logging.info(f"SMTP OAuth relay server started on port 8025")
    except Exception as e:
        logging.exception(f"Failed to start SMTP server: {str(e)}")
        if controller:
            controller.stop()
        raise


if __name__ == '__main__':
    # Setup logging
    logging.basicConfig(
        level=LOG_LEVEL,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Create event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    # Run main function
    try:
        loop.create_task(amain())
        loop.run_forever()
    except KeyboardInterrupt:
        logging.info("Shutdown requested via keyboard interrupt")
    except Exception as e:
        logging.exception(f"Unexpected error: {str(e)}")
    finally:
        logging.info("Shutting down...")
        tasks = asyncio.all_tasks(loop)
        for task in tasks:
            task.cancel()
        loop.close()
