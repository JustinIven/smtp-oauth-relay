from aiosmtpd.controller import UnthreadedController
from aiosmtpd.smtp import SMTP, AuthResult, Session, TLSSetupException
from typing import Any, List
import inspect
import logging


class CustomController(UnthreadedController):
    def factory(self) -> SMTP:
        return CustomSMTP(self.handler, **self.SMTP_kwargs)


class CustomSMTP(SMTP):
    AuthLoginUsernameChallenge = "Username:" # Some clients expect this format
    AuthLoginPasswordChallenge = "Password:"

    # aiosmtpd invokes the authenticator synchronously, so an async authenticator's coroutine
    # arrives here unawaited; smtp_AUTH would otherwise treat it as a successful legacy login.
    @staticmethod
    async def _resolve_auth(result: Any) -> Any:
        if inspect.isawaitable(result):
            return await result
        return result

    async def auth_PLAIN(self, _: SMTP, args: List[str]) -> AuthResult:
        return await self._resolve_auth(await super().auth_PLAIN(_, args))

    async def auth_LOGIN(self, _: SMTP, args: List[str]) -> AuthResult:
        return await self._resolve_auth(await super().auth_LOGIN(_, args))

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
