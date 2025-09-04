import asyncio
import logging
import requests
import base64
import os
import re
import uuid
from email import message_from_bytes

from custom import CustomController
from aiosmtpd.smtp import AuthResult

from azure.identity import DefaultAzureCredential
from azure.data.tables import TableClient

import sslContext


# Load configuration from environment variables
def load_env(name, default=None, sanitize=lambda x: x, valid_values=None, convert=lambda x: x):
    value = sanitize(os.getenv(name, default))
    if valid_values and value not in valid_values:
        raise ValueError(f"Invalid {name}: {value}")
    return convert(value)

# Configuration
LOG_LEVEL = load_env(
    name='LOG_LEVEL',
    default='WARNING',
    valid_values=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
    sanitize=lambda x: x.upper()
)
TLS_SOURCE = load_env(
    name='TLS_SOURCE', 
    default='file', 
    valid_values=['off', 'file', 'keyvault'], 
    sanitize=lambda x: x.lower(),
)
REQUIRE_TLS = load_env(
    name='REQUIRE_TLS', 
    default='true', 
    valid_values=['true', 'false'], 
    sanitize=lambda x: x.lower(),
    convert=lambda x: x == 'true'
)
SERVER_GREETING = load_env(
    name='SERVER_GREETING', 
    default='Microsoft Graph SMTP OAuth Relay'
)
TLS_CERT_FILEPATH = load_env(
    name='TLS_CERT_FILEPATH',
    default='certs/cert.pem'
)
TLS_KEY_FILEPATH = load_env(
    name='TLS_KEY_FILEPATH',
    default='certs/key.pem'
)
USERNAME_DELIMITER = load_env(
    name='USERNAME_DELIMITER',
    default='@',
    valid_values=['@', ':', '|']
)
AZURE_KEY_VAULT_URL = load_env(
    name='AZURE_KEY_VAULT_URL',
    default=None,  # Make it optional
)
AZURE_KEY_VAULT_CERT_NAME = load_env(
    name='AZURE_KEY_VAULT_CERT_NAME',
    default=None,  # Make it optional
)
AZURE_TABLES_URL = load_env(
    name='AZURE_TABLES_URL',
    default=None,  # Make it optional
)
AZURE_TABLES_PARTITION_KEY = load_env(
    name='AZURE_TABLES_PARTITION_KEY',
    default='user'
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


def lookup_user(lookup_id: str) -> tuple[str, str, str|None]:
    """
    Search in Azure Table for user information based on the lookup_id (RowKey).
    Returns (tenant_id, client_id, from_email) or raises ValueError if not found.
    """
    if not AZURE_TABLES_URL:
        raise ValueError("AZURE_TABLES_URL environment variable not set")

    try:
        credential = DefaultAzureCredential()
        with TableClient.from_table_url(table_url=AZURE_TABLES_URL, credential=credential) as client: # pyright: ignore[reportArgumentType]
            entities = client.query_entities(query_filter=f"PartitionKey eq '{AZURE_TABLES_PARTITION_KEY}' and RowKey eq '{lookup_id}'")
            entity = None
            for i in entities:
                entity = i
                break
    except Exception as e:
        raise RuntimeError(f"Failed to query Azure Table: {str(e)}") from e

    if not entity:
        raise ValueError(f"No entity found for RowKey '{lookup_id}'")

    tenant_id = entity.get('tenant_id')
    client_id = entity.get('client_id')
    from_email = entity.get('from_email')

    if not tenant_id or not client_id:
        raise ValueError(f"Entity for RowKey '{lookup_id}' is missing tenant_id or client_id")

    return tenant_id, client_id, from_email


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
        return lookup_user(parts[0])

    # else return both parts decoded
    return decode_uuid_or_base64url(parts[0]), decode_uuid_or_base64url(parts[1]), None


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


def send_email(access_token: str, body: bytes, from_email: str) -> bool:
    url = f"https://graph.microsoft.com/v1.0/users/{from_email}/sendMail"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "text/plain"
    }
    
    try:
        data = base64.b64encode(body)
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
                
            login_str = auth_data.login.decode("utf-8")
            
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
        try:
            logging.info(f"Message from {envelope.mail_from} to {envelope.rcpt_tos}")

            if not hasattr(session, 'access_token'):
                logging.error("No access token available in session")
                return "530 5.7.0 Authentication required"

            if session.lookup_from_email:
                # some clients won't let you set a from address independent of the auth user. Issue: #36
                # replace from header in envelope if lookup_from_email is set
                envel = message_from_bytes(envelope.content)
                del envel['From']  # delete all occurrences of From header
                envel['From'] = session.lookup_from_email  # set new From header

                # Send email using Microsoft Graph API
                success = send_email(session.access_token, envel.as_bytes(), session.lookup_from_email)

            else:
                # Send email using Microsoft Graph API
                success = send_email(session.access_token, envelope.content, envelope.mail_from)

            if success:
                return "250 OK"
            else:
                return "554 Transaction failed"
                
        except Exception as e:
            logging.exception(f"Error handling DATA command: {str(e)}")
            return "554 Transaction failed"



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


    controller = None
    try:
        controller = CustomController(
            Handler(),
            hostname='',
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
