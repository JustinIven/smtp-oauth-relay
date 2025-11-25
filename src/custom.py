from aiosmtpd.controller import Controller
from aiosmtpd.smtp import SMTP, Session, TLSSetupException
from typing import Any
import logging


class CustomController(Controller):
    def factory(self) -> SMTP:
        return CustomSMTP(self.handler, **self.SMTP_kwargs)


class CustomSMTP(SMTP):
    AuthLoginUsernameChallenge = "Username:" # Some clients expect this format
    AuthLoginPasswordChallenge = "Password:"

    # Custom logic to handle AUTH commands which are in lowercase (bug in aio-libs/aiosmtpd#542)
    async def smtp_AUTH(self, arg: str) -> None:    
        args = arg.split()
        if len(args) == 2:
            args[0] = args[0].upper()
            arg = ' '.join(args)
        return await super().smtp_AUTH(arg)

    # Override STARTTLS to catch SSL handshake errors
    async def smtp_STARTTLS(self, arg: str) -> None:
        try:
            return await super().smtp_STARTTLS(arg)
        except TLSSetupException:
            if self.tls_context:
                logging.error(f"TLS handshake with client failed.")

    
    def _create_session(self) -> Session:
        return CustomSession(self.loop)
        
# Custom Session class to remove deprecation warnings related to login_data attribute (bug in aio-libs/aiosmtpd#347)
class CustomSession(Session):
    @property
    def login_data(self) -> Any:
        return self._login_data

    @login_data.setter
    def login_data(self, value: Any) -> None:
        self._login_data = value
