import base64
import logging
import requests
from email import message_from_bytes, policy
from quopri import decodestring

from env import GRAPH_HTTP_TIMEOUT


class GraphClient:
    """Encapsulates all Microsoft Graph interactions for sending mail.

    An instance holds an OAuth access token and is passed around instead of
    the raw token, keeping all Graph-specific logic in one place.
    """

    def __init__(self, access_token: str):
        self.access_token = access_token

    @classmethod
    def from_credentials(cls, tenant_id: str, client_id: str, client_secret: str) -> "GraphClient":
        """Create a GraphClient by acquiring an access token via client credentials."""
        access_token = cls._request_access_token(tenant_id, client_id, client_secret)
        return cls(access_token)

    @staticmethod
    def _request_access_token(tenant_id: str, client_id: str, client_secret: str) -> str:
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
                headers=headers,
                timeout=GRAPH_HTTP_TIMEOUT
            )
            response.raise_for_status()
            return response.json().get("access_token")
        except requests.RequestException as e:
            logging.error(f"OAuth token request failed: {str(e)}")
            if hasattr(e, 'response') and e.response:
                logging.error(f"Response status: {e.response.status_code}, Response body: {e.response.text}")
            raise

    @staticmethod
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

    def send_email(self, body: bytes, from_email: str) -> bool:
        url = f"https://graph.microsoft.com/v1.0/users/{from_email}/sendMail"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "text/plain"
        }

        try:
            data = base64.b64encode(self._sanitize_mime_encoding(body))
            logging.debug(f"Sending email from {from_email}")

            response = requests.post(url, data=data, headers=headers, timeout=GRAPH_HTTP_TIMEOUT)
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
