import asyncio
import logging
import requests
import base64
import ssl
import os

from aiosmtpd.controller import Controller
from aiosmtpd.smtp import AuthResult


# Load configuration from environment variables
if (log_level := os.getenv('LOG_LEVEL', 'INFO')).upper() in ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']:
    LOG_LEVEL = log_level.upper()
else:
    raise ValueError(f"Invalid LOG_LEVEL: {log_level}")

if (use_tls := os.getenv('USE_TLS', 'true')).lower() in ['true', 'false']:
    USE_TLS = use_tls.lower() == 'true'
else:
    raise ValueError(f"Invalid USE_TLS: {use_tls}")

if (require_tls := os.getenv('REQUIRE_TLS', 'true')).lower() in ['true', 'false']:
    REQUIRE_TLS = require_tls.lower() == 'true'
else:
    raise ValueError(f"Invalid REQUIRE_TLS: {require_tls}")

if (server_greeting := os.getenv('SERVER_GREETING', 'Microsoft Graph SMTP OAuth Relay')).strip():
    SERVER_GREETING = server_greeting
else:
    raise ValueError(f"Invalid SERVER_GREETING: {server_greeting}")





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
            
            # Extract tenant_id and client_id from login string
            try:
                tenant_id, client_id = login_str.split(':')
            except ValueError:
                logging.error(f"Invalid login format: Expected 'tenant_id:client_id', got '{login_str}'")
                return AuthResult(success=False, handled=False, message="535 5.7.8 Invalid login format: Expected 'tenant_id:client_id'")
                
            client_secret = auth_data.password

            try:
                session.access_token = get_access_token(tenant_id, client_id, client_secret)
                return AuthResult(success=True)
            except Exception as e:
                logging.error(f"Authentication failed: {str(e)}")
                return AuthResult(success=False, handled=False, message="535 5.7.8 Authentication failed")
                
        except Exception as e:
            logging.exception(f"Unexpected error during authentication: {str(e)}")
            return AuthResult(success=False, handled=False)


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
        if not os.path.exists('certs/cert.pem') or not os.path.exists('certs/key.pem'):
            logging.error("Certificate or key not found")
            raise FileNotFoundError("Certificate or key not found")

        # load default context
        context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)

        # load cert and key
        try:
            context.load_cert_chain(certfile='certs/cert.pem', keyfile='certs/key.pem')
        except ssl.SSLError as e:
            logging.error(f"Failed to load Certificate or key: {str(e)}")
            raise
        except FileNotFoundError as e:
            logging.error(f"Certificate or key not found: {str(e)}")

    
    # check if REQUIRE_TLS is set to True and USE_TLS is set to False
    if REQUIRE_TLS and not USE_TLS:
        logging.warning("REQUIRE_TLS is set to True but USE_TLS is set to False; TLS won't be enforced")


    controller = None
    try:
        controller = Controller(
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
