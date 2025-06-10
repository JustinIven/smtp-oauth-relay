import asyncio
import logging
import requests
import base64
import ssl
import os
import re
import uuid

from custom import CustomController
from aiosmtpd.smtp import AuthResult


# Load configuration from environment variables
def load_env(name, default=None, sanitize=lambda x: x, valid_values=None, convert=lambda x: x):
    value = sanitize(os.getenv(name, default))
    if valid_values and value not in valid_values:
        raise ValueError(f"Invalid {name}: {value}")
    return convert(value)

# Configuration
LOG_LEVEL = load_env(
    name='LOG_LEVEL',
    default='INFO',
    valid_values=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
    sanitize=lambda x: x.upper()
)
USE_TLS = load_env(
    name='USE_TLS', 
    default='true', 
    valid_values=['true', 'false'], 
    sanitize=lambda x: x.lower(),
    convert=lambda x: x == 'true'
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



def parse_username(username):
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
    
    # check if parts have a UUID-like format or else base64url decode them
    uuid_pattern = re.compile(r'^[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}$')
    decoded_parts = []
    for part in parts:
        if uuid_pattern.match(part):
            decoded_parts.append(part)
            continue  # valid UUID format, no need to decode

        # Attempt to decode as base64url
        try:
            decoded_parts.append(str(uuid.UUID(bytes=base64.urlsafe_b64decode(part + '=' * (-len(part) % 4)))))
        except Exception as e:
            raise ValueError(f"Invalid base64url encoding in part '{part}'")

    return decoded_parts[0], decoded_parts[1]


def get_access_token(tenant_id, client_id, client_secret):
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


def send_email(access_token, body, from_email):
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
                tenant_id, client_id = parse_username(login_str)
            except ValueError as e:
                logging.error(str(e))
                return AuthResult(success=False, handled=False, message=f"535 5.7.8 {str(e)}")
                
            client_secret = auth_data.password

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

    # load ssl context
    context = None
    if USE_TLS:
        # check if cert and key files exist
        if not os.path.exists(path=TLS_CERT_FILEPATH) or not os.path.exists(path=TLS_KEY_FILEPATH):
            logging.error("Certificate or key not found")
            raise FileNotFoundError("Certificate or key not found")

        # load default context
        context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)

        # load cert and key
        try:
            context.load_cert_chain(certfile=TLS_CERT_FILEPATH, keyfile=TLS_KEY_FILEPATH)
        except ssl.SSLError as e:
            logging.error(f"Failed to load Certificate or key: {str(e)}")
            raise
        except FileNotFoundError as e:
            logging.error(f"Certificate or key not found: {str(e)}")


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
