import asyncio
import logging
import requests
import base64

from aiosmtpd.controller import Controller
from aiosmtpd.smtp import AuthResult


def get_access_token(tenant_id , client_id, client_secret):
    data = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "https://graph.microsoft.com/.default"
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    
    response = requests.post( f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token", data=data, headers=headers)
    response.raise_for_status()  # Raise error if request fails
    return response.json().get("access_token")


def send_email(access_token, body, from_email):
    url = f"https://graph.microsoft.com/v1.0/users/{from_email}/sendMail"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "text/plain"
    }
    data = base64.b64encode(body)
    print(data)
    
    response = requests.post(url, data=data, headers=headers)
    if response.status_code == 202:
        print("Email sent successfully!")
    else:
        print(f"Failed to send email: {response.text}")



class Authenticator:
    def __call__(self, server, session, envelope, mechanism, auth_data):
        fail_nothandled = AuthResult(success=False, handled=False)
        
        tenant_id, client_id = auth_data.login.decode("utf-8").split(':')
        client_secret = auth_data.password

        session.access_token = get_access_token(tenant_id, client_id, client_secret)

        return AuthResult(success=True)


class Handler:
    async def handle_DATA(self, server, session, envelope):
        logging.info(f"Message from {envelope.mail_from} to {envelope.rcpt_tos}")

        # Send email using Microsoft Graph API
        send_email(session.access_token, envelope.content, envelope.mail_from)

        return "250 OK"


# noinspection PyShadowingNames
async def amain():
    cont = Controller(
        Handler(),
        hostname='',
        port=8025,
        authenticator=Authenticator(),
        auth_require_tls=False,
        decode_data=False
    )
    cont.start()


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.create_task(amain())  # type: ignore[unused-awaitable]
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        print("User abort indicated")
