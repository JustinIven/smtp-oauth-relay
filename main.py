import asyncio
import logging
import requests
import base64

from aiosmtpd.controller import Controller
from aiosmtpd.smtp import AuthResult


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
    controller = None
    try:
        controller = Controller(
            Handler(),
            hostname='',
            port=8025,
            authenticator=Authenticator(),
            auth_require_tls=False,
            decode_data=False
        )
        controller.start()
        logging.info(f"SMTP OAuth relay server started on port 8025")
    except Exception as e:
        logging.exception(f"Failed to start SMTP server: {str(e)}")
        if controller:
            controller.stop()
        raise


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
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
