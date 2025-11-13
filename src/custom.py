from aiosmtpd.controller import Controller
from aiosmtpd.smtp import SMTP, Session
from typing import Any

# Custom logic to handle AUTH commands which are in lowercase (bug in aio-libs/aiosmtpd#542)
class CustomSMTP(SMTP):
    async def smtp_AUTH(self, arg: str) -> None:    
        args = arg.split()
        if len(args) == 2:
            args[0] = args[0].upper()
            arg = ' '.join(args)
        return await super().smtp_AUTH(arg)
    
    def _create_session(self) -> Session:
        return CustomSession(self.loop)
        

class CustomController(Controller):
    def factory(self) -> SMTP:
        return CustomSMTP(self.handler, **self.SMTP_kwargs)

# Custom Session class to remove deprecation warnings related to login_data attribute (bug in aio-libs/aiosmtpd#347)
class CustomSession(Session):
    @property
    def login_data(self) -> Any:
        return self._login_data

    @login_data.setter
    def login_data(self, value: Any) -> None:
        self._login_data = value
