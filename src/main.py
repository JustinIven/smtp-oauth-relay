import asyncio
import contextlib
import logging
import sys
from email import message_from_bytes

from aiosmtpd.smtp import AuthResult

import sslContext
from azure_table import AzureTableStore
from custom import CustomController
from env import (
    AZURE_KEY_VAULT_CERT_NAME,
    AZURE_KEY_VAULT_URL,
    AZURE_TABLES_FORCE_USAGE,
    AZURE_TABLES_URL,
    LOG_LEVEL,
    REQUIRE_TLS,
    SERVER_GREETING,
    TLS_CERT_FILEPATH,
    TLS_CIPHER_SUITE,
    TLS_KEY_FILEPATH,
    TLS_RELOAD_INTERVAL,
    TLS_SOURCE,
)
from graph import GraphClient, close_http_session, start_http_session
from parsing import parse_username

logger = logging.getLogger(__name__)


class Authenticator:
    def __init__(self, table_store: AzureTableStore | None = None):
        self._table_store = table_store

    async def __call__(self, server, session, envelope, mechanism, auth_data):
        try:
            # Only support LOGIN and PLAIN mechanisms
            if mechanism not in ("LOGIN", "PLAIN"):
                logger.warning(f"Unsupported auth mechanism: {mechanism}")
                return AuthResult(
                    success=False,
                    handled=False,
                    message="504 5.7.4 Unsupported authentication mechanism",
                )

            # Check if authentication data is present
            if not auth_data or not auth_data.login or not auth_data.password:
                logger.warning("Missing authentication data")
                return AuthResult(
                    success=False,
                    handled=False,
                    message="535 5.7.8 Authentication credentials missing",
                )

            try:
                login_str = auth_data.login.decode("utf-8")
                client_secret = auth_data.password.decode("utf-8")
            except Exception as e:  # noqa: BLE001
                logger.error(f"Failed to decode credentials: {e!s}")
                return AuthResult(
                    success=False,
                    handled=False,
                    message="535 5.7.8 Invalid authentication credentials encoding",
                )

            # Parse tenant_id and client_id from login string using the configured format
            try:
                tenant_id, client_id, from_email = await parse_username(
                    login_str, self._table_store
                )
            except ValueError as e:
                logger.error(str(e))
                return AuthResult(
                    success=False, handled=False, message=f"535 5.7.8 {e!s}"
                )

            session.lookup_from_email = from_email

            try:
                session.graph_client = await GraphClient.from_credentials(
                    tenant_id, client_id, client_secret
                )
                return AuthResult(success=True)
            except Exception as e:  # noqa: BLE001
                logger.error(f"Authentication failed: {e!s}")
                return AuthResult(
                    success=False,
                    handled=False,
                    message="535 5.7.8 Authentication failed",
                )

        except Exception:
            logger.exception("Unexpected error during authentication")
            return AuthResult(
                success=False,
                handled=False,
                message="554 5.7.0 Unexpected error during authentication",
            )


class Handler:
    async def handle_DATA(self, server, session, envelope):
        logger.debug(
            f"SMTP envelope: mail_from={envelope.mail_from}, rcpt_tos={envelope.rcpt_tos}"
        )

        if not hasattr(session, "graph_client"):
            logger.error("No Graph client available in session")
            return "530 5.7.0 Authentication required"

        try:
            raw_envelope = message_from_bytes(envelope.content)
        except Exception:
            logger.exception("Failed to parse incoming message bytes")
            return "554 Transaction failed"

        # apply any necessary fixes for known issues
        fixes_applied = False
        fixes_applied |= self._fix_missing_bcc(raw_envelope, envelope.rcpt_tos)
        override_applied, mail_from = self._apply_from_override(
            raw_envelope, session, envelope.mail_from
        )
        fixes_applied |= override_applied

        if fixes_applied:
            logger.debug("Applied fixes to email headers before sending")
            success = await session.graph_client.send_email(
                raw_envelope.as_bytes(), mail_from
            )
        else:
            success = await session.graph_client.send_email(
                envelope.content, envelope.mail_from
            )

        if success:
            logger.info("DATA command processed successfully")
            return "250 OK"

        logger.error("DATA command failed during send_email")
        return "554 Transaction failed"

    def _fix_missing_bcc(self, raw_envelope, rcpt_tos) -> bool:
        """Ensure Bcc header contains any recipients missing from To/Cc.
        Return True if a fix was applied, False otherwise.

        Issue #82: some clients do not include Bcc recipients in the headers
        at all, which causes Graph to drop them. The workaround is to compute
        which rcpt_tos are not already in To/Cc and add them as a Bcc header.
        """

        to_headers = raw_envelope.get_all("To", [])
        cc_headers = raw_envelope.get_all("Cc", [])
        total_headers = len(to_headers) + len(cc_headers)
        logger.debug(f"Headers count - To: {len(to_headers)}, Cc: {len(cc_headers)}")

        if len(rcpt_tos) <= total_headers:
            logger.debug("No missing recipients detected; skipping Bcc fixup")
            return False

        header_recipients = set(to_headers + cc_headers)
        missing = set(rcpt_tos) - header_recipients
        if not missing:
            logger.debug(
                "Mismatch between rcpt_tos and headers, but no missing recipients"
            )
            return False

        logger.info(f"Adding Bcc header for missing recipients: {sorted(missing)}")
        # preserve any existing Bcc header by appending if present
        existing_bcc = raw_envelope.get_all("Bcc", [])
        combined = list(existing_bcc) + sorted(missing)
        raw_envelope["Bcc"] = ", ".join(combined)
        return True

    def _apply_from_override(
        self, raw_envelope, session, default_mail_from
    ) -> tuple[bool, str]:
        """When lookup_from_email is configured replace the From header.
        Returns a a tuple of (was_overridden, new_mail_from). If no override was applied, returns (False, default_mail_from).

        Some SMTP clients (issue #36) do not allow the From address to differ
        from the authenticated user.  We drop any existing From headers and
        insert the value stored in ``session.lookup_from_email`` if set.
        Returns the mail_from value that should be supplied to Graph.
        """

        if not getattr(session, "lookup_from_email", None):
            logger.debug("No from-override configured; using envelope.mail_from")
            return False, default_mail_from

        new_from = session.lookup_from_email
        logger.info(
            f"Overriding From header to '{new_from}' per lookup_from_email setting"
        )

        # remove all existing From headers
        while "From" in raw_envelope:
            del raw_envelope["From"]

        raw_envelope["From"] = new_from
        return True, new_from


# noinspection PyShadowingNames
def create_certificate_source():
    match TLS_SOURCE:
        case "file":
            return sslContext.FileCertificateSource(
                TLS_CERT_FILEPATH, TLS_KEY_FILEPATH, TLS_CIPHER_SUITE
            )

        case "keyvault":
            if not AZURE_KEY_VAULT_URL or not AZURE_KEY_VAULT_CERT_NAME:
                logger.error(
                    "Azure Key Vault URL and Certificate Name must be set when TLS_SOURCE is 'keyvault'"
                )
                raise ValueError("Azure Key Vault URL and Certificate Name must be set")
            return sslContext.KeyVaultCertificateSource(
                AZURE_KEY_VAULT_URL, AZURE_KEY_VAULT_CERT_NAME, TLS_CIPHER_SUITE
            )

        case "off":
            return None

        case _:
            logger.error(f"Invalid TLS_SOURCE: {TLS_SOURCE}")
            raise ValueError(f"Invalid TLS_SOURCE: {TLS_SOURCE}")


async def reload_tls_context(controller, source, fingerprint, interval):
    """
    Periodically check the certificate source and swap in a new TLS context when it
    changes. aiosmtpd creates an SMTP instance per connection from SMTP_kwargs, so only
    new connections use the new context. On failure the current context is kept.
    """
    failed_fingerprint = None
    while True:
        await asyncio.sleep(interval)
        new_fingerprint = None
        try:
            new_fingerprint = await asyncio.to_thread(source.fingerprint)
            if new_fingerprint == fingerprint:
                continue
            context = await asyncio.to_thread(source.load)
        except Exception as e:
            message = f"Failed to reload TLS certificate from {source}; keeping the current certificate"
            # Avoid a traceback on every check while the same broken certificate is in place
            if new_fingerprint is not None and new_fingerprint == failed_fingerprint:
                logger.warning(f"{message}: {e!s}")
            else:
                logger.exception(message)
            failed_fingerprint = new_fingerprint
            continue
        failed_fingerprint = None
        controller.SMTP_kwargs["tls_context"] = context
        fingerprint = new_fingerprint
        logger.info(f"Reloaded TLS certificate from {source}")


# noinspection PyShadowingNames
async def amain(loop):
    source = create_certificate_source()
    context = None
    fingerprint = None
    if source is not None:
        # Fingerprint before loading so a change during startup is picked up by the next check
        fingerprint = source.fingerprint()
        context = source.load()
        logger.info(f"Loaded certificate from {source}")
        logger.info(
            f"TLS cipher suites used: {', '.join([i['name'] for i in context.get_ciphers()])}"
        )

    # Create a shared Azure Table store when configured
    table_store = AzureTableStore() if AZURE_TABLES_URL else None

    # If AZURE_TABLES_FORCE_USAGE is enabled, verify table access at startup
    if AZURE_TABLES_FORCE_USAGE:
        if table_store is None:
            raise ValueError(
                "AZURE_TABLES_URL must be set when AZURE_TABLES_FORCE_USAGE is enabled"
            )
        await table_store.verify_table_access()
        logger.info("Azure Table access verified (AZURE_TABLES_FORCE_USAGE=true)")

    # Share a single HTTP session, created on the loop that serves SMTP
    await start_http_session()

    controller = CustomController(
        Handler(),
        hostname="",  # bind dual-stack on all interfaces
        port=8025,
        loop=loop,
        ident=SERVER_GREETING,
        authenticator=Authenticator(table_store),
        auth_required=True,
        auth_require_tls=REQUIRE_TLS,
        require_starttls=REQUIRE_TLS,
        tls_context=context,
    )

    reload_task = None
    if source is not None and TLS_RELOAD_INTERVAL > 0:
        reload_task = loop.create_task(
            reload_tls_context(controller, source, fingerprint, TLS_RELOAD_INTERVAL)
        )
        logger.info(
            f"Checking TLS certificate for changes every {TLS_RELOAD_INTERVAL} seconds"
        )

    return controller, table_store, reload_task


async def ashutdown(controller, table_store, reload_task):
    if reload_task is not None:
        reload_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await reload_task
    if controller is not None and controller.server is not None:
        await controller.finalize()
    await close_http_session()
    if table_store is not None:
        await table_store.close()


if __name__ == "__main__":
    # Setup logging
    logging.basicConfig(
        level=LOG_LEVEL, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Create event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    controller = None
    table_store = None
    reload_task = None
    exit_code = 0
    try:
        controller, table_store, reload_task = loop.run_until_complete(amain(loop))
        # begin() drives the loop itself, so it has to run before run_forever()
        controller.begin()
        logger.info("SMTP OAuth relay server started on port 8025")
        loop.run_forever()
    except KeyboardInterrupt:
        logger.info("Shutdown requested via keyboard interrupt")
    except Exception:
        logger.exception("Unexpected error")
        exit_code = 1
    finally:
        logger.info("Shutting down...")
        loop.run_until_complete(ashutdown(controller, table_store, reload_task))
        for task in asyncio.all_tasks(loop):
            task.cancel()
        loop.close()
        sys.exit(exit_code)
