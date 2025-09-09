from aiosmtpd.controller import Controller
from aiosmtpd.smtp import SMTP

# Custom logic to handle AUTH commands which are in lowercase (bug in aiosmtpd aio-libs/aiosmtpd#542)
class CustomSMTP(SMTP):
    async def smtp_AUTH(self, arg: str) -> None:    
        args = arg.split()
        if len(args) == 2:
            args[0] = args[0].upper()
            arg = ' '.join(args)
        return await super().smtp_AUTH(arg)
        

class CustomController(Controller):
    def factory(self) -> SMTP:
        return CustomSMTP(self.handler, **self.SMTP_kwargs)
