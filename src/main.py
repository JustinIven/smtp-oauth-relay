import asyncio
import logging
from email import policy
from email.parser import BytesParser

from aiosmtpd.smtp import MISSING

import addressing
import config
import config_resolver
import graph_client
import message_utils
import rate_limiter
import relay_logging
import remap
import sslContext
from auth import Authenticator
from constants import (
    SMTP_ACTION_ABORTED,
    SMTP_AUTH_REQUIRED,
    SMTP_MALFORMED_ADDRESS,
    SMTP_OK,
    SMTP_RATE_LIMITED,
    SMTP_TRANSACTION_FAILED,
    SMTP_USER_NOT_LOCAL,
)
from custom import CustomController


# Handler implements the SMTP callbacks invoked by aiosmtpd.
class Handler:
    async def handle_MAIL(self, server, session, envelope, address, mail_options):
        if not addressing.is_valid_smtp_mailbox(address, allow_null=True):
            relay_logging.log_rejected_mail_from(address)
            return SMTP_MALFORMED_ADDRESS
        return MISSING

    async def handle_RCPT(self, server, session, envelope, address, rcpt_options):
        if not addressing.is_valid_smtp_mailbox(address, allow_null=False):
            relay_logging.log_rejected_rcpt_to(address)
            return SMTP_MALFORMED_ADDRESS
        return MISSING

    async def handle_DATA(self, server, session, envelope):
        try:
            relay_logging.log_message_received(envelope.mail_from, envelope.rcpt_tos)

            if not hasattr(session, 'access_token'):
                relay_logging.log_missing_access_token()
                return SMTP_AUTH_REQUIRED

            # Parse the message once and reuse for header inspection and validation.
            raw_message = envelope.content
            parsed_message = BytesParser(policy=policy.SMTP).parsebytes(raw_message)
            x_sender_raw = parsed_message.get('X-Sender')
            x_sender_address = addressing.parse_email_address(x_sender_raw)

            return_path_raw = parsed_message.get('Return-Path')
            return_path_address = addressing.parse_email_address(return_path_raw)
            from_header_raw = parsed_message.get('From')
            from_header_address = addressing.parse_email_address(from_header_raw)
            from_header_valid = from_header_address is not None
            from_email = from_header_address
            header_updates: dict[str, str | None] = {}
            header_change_reasons: list[str] = []

            # Ensure replies go back to the original valid From when clients omit Reply-To.
            if from_header_valid and not parsed_message.get('Reply-To'):
                header_updates['Reply-To'] = from_header_raw
                header_change_reasons.append("inserted Reply-To from From header")

            # Normalize invalid X-Sender so downstream routing has a usable sender.
            if x_sender_raw is not None and not x_sender_address:
                replacement_sender = from_header_address or return_path_address
                if replacement_sender:
                    header_updates['X-Sender'] = replacement_sender
                    x_sender_address = replacement_sender
                    header_change_reasons.append("normalized invalid X-Sender")
                message_utils.log_invalid_x_sender(
                    x_sender_raw,
                    replacement_sender,
                    return_path_address,
                    from_header_address,
                )

            # Resolve domain-level settings with env-first precedence.
            domain_context = config_resolver.resolve_domain_context(
                x_sender_raw,
                return_path_raw,
                from_header_raw,
                envelope.mail_from,
                *(envelope.rcpt_tos or [])
            )
            domain_hint = domain_context.domain
            settings = domain_context.settings

            rfc5322_error = message_utils.validate_rfc5322_message(
                raw_message,
                parsed_message=parsed_message,
                # Allow missing/invalid From if a domain failback is configured.
                allow_invalid_from=bool(domain_context.failback_address),
            )
            if rfc5322_error:
                message_utils.log_rfc5322_validation_failed(rfc5322_error)
                return rfc5322_error

            # Apply recipient remapping for both headers and envelope recipients.
            recipient_header_updates = remap.remap_recipient_headers(parsed_message)
            if recipient_header_updates:
                header_updates.update(recipient_header_updates)
                message_utils.log_recipient_header_remap()
                header_change_reasons.append("remapped recipient headers")
            if envelope.rcpt_tos:
                remapped_recipients = remap.remap_recipient_list(envelope.rcpt_tos)
                if remapped_recipients != envelope.rcpt_tos:
                    envelope.rcpt_tos = remapped_recipients
                    message_utils.log_envelope_recipient_remap()

            # If we still don't have a sender, fall back to the domain failback.
            if not from_email:
                failback_address = domain_context.failback_address
                if failback_address:
                    message_utils.log_failback_sender_used(domain_hint)
                    from_email = failback_address
                    header_updates['From'] = failback_address
                    if not addressing.parse_email_address(parsed_message.get('X-Sender')):
                        header_updates['X-Sender'] = failback_address
                    header_change_reasons.append("applied failback sender")
                else:
                    message_utils.log_failback_sender_missing()
                    return SMTP_TRANSACTION_FAILED

            # Domain-level From remapping uses failback sender + Reply-To preservation.
            if domain_hint and from_header_raw and remap.is_remap_enabled(
                domain_hint,
                settings,
                from_header_address
            ):
                failback_address = domain_context.failback_address
                if failback_address:
                    header_updates['From'] = failback_address
                    if from_header_valid:
                        header_updates['Reply-To'] = message_utils.build_reply_to_value(
                            parsed_message.get('Reply-To'),
                            from_header_raw
                        )
                    from_email = failback_address
                    message_utils.log_from_remap_applied(domain_hint, failback_address)
                    header_change_reasons.append("remapped From header")
                else:
                    message_utils.log_from_remap_missing(domain_hint)

            if session.lookup_from_email:
                # Some clients won't let you set a from address independent of the auth user.
                # Issue: #36
                # Replace from header in envelope if lookup_from_email is set.
                header_updates['From'] = session.lookup_from_email
                from_email = session.lookup_from_email
                header_change_reasons.append("overrode From header from lookup user")

            # Apply header updates once with consistent logging.
            if header_updates:
                raw_message = message_utils.apply_header_updates(
                    raw_message,
                    parsed_message,
                    header_updates,
                    header_change_reasons,
                )

            # Rate-limit and send email using Microsoft Graph API.
            limiter = await rate_limiter.try_acquire_mailbox(from_email)
            if not limiter:
                relay_logging.log_rate_limited(from_email)
                return SMTP_RATE_LIMITED
            try:
                success, error_detail, status_code = graph_client.send_email(
                    session.access_token,
                    raw_message,
                    from_email
                )
            finally:
                # Always release limiter capacity even on send failures.
                await limiter.release()

            if success:
                return SMTP_OK

            # Retry with a domain failback sender when Graph returns 404.
            if status_code == 404 and config.GRAPH_FAILBACK_ON_404:
                failback_address = domain_context.failback_address
                if failback_address and failback_address != from_email:
                    relay_logging.log_graph_failback_retry(from_email, failback_address)
                    fallback_updates = {"From": failback_address}
                    raw_message = message_utils.apply_header_updates(
                        raw_message,
                        BytesParser(policy=policy.SMTP).parsebytes(raw_message),
                        fallback_updates,
                        ["applied failback sender after Graph 404"],
                    )
                    limiter = await rate_limiter.try_acquire_mailbox(failback_address)
                    if not limiter:
                        relay_logging.log_rate_limited(failback_address)
                        return SMTP_RATE_LIMITED
                    try:
                        success, error_detail, status_code = graph_client.send_email(
                            session.access_token,
                            raw_message,
                            failback_address
                        )
                    finally:
                        await limiter.release()
                    if success:
                        return SMTP_OK
                elif not failback_address:
                    relay_logging.log_graph_failback_missing(domain_hint)
            # Optionally emit a failure notification if configured for the domain.
            failure_notification = domain_context.failure_notification
            if failure_notification:
                notification_sender = domain_context.failback_address or from_email
                if notification_sender:
                    graph_client.send_failure_notification(
                        access_token=session.access_token,
                        from_email=notification_sender,
                        notification_address=failure_notification,
                        parsed_message=parsed_message,
                        envelope=envelope,
                        error_detail=error_detail
                    )
                else:
                    message_utils.log_failure_notification_missing_sender(domain_hint)
            await asyncio.sleep(0.5)
            if status_code == 404:
                return SMTP_USER_NOT_LOCAL
            return SMTP_ACTION_ABORTED

        except Exception as e:
            relay_logging.log_data_handler_exception(e)
            return SMTP_TRANSACTION_FAILED


# noinspection PyShadowingNames
async def amain():
    # Choose TLS configuration based on source and settings.
    match config.TLS_SOURCE:
        case 'file':
            context = sslContext.from_file(config.TLS_CERT_FILEPATH, config.TLS_KEY_FILEPATH)
            sslContext.log_loaded_certificate_from_file(config.TLS_CERT_FILEPATH)

        case 'keyvault':
            if not config.AZURE_KEY_VAULT_URL or not config.AZURE_KEY_VAULT_CERT_NAME:
                sslContext.log_missing_keyvault_config()
                raise ValueError("Azure Key Vault URL and Certificate Name must be set")
            context = sslContext.from_keyvault(
                config.AZURE_KEY_VAULT_URL,
                config.AZURE_KEY_VAULT_CERT_NAME
            )
            sslContext.log_loaded_certificate_from_keyvault(config.AZURE_KEY_VAULT_CERT_NAME)

        case 'off':
            context = None

        case _:
            sslContext.log_invalid_tls_source(config.TLS_SOURCE)
            raise ValueError(f"Invalid TLS_SOURCE: {config.TLS_SOURCE}")

    # Configure TLS cipher suite if specified, then log the actual ciphers.
    if context:
        if config.TLS_CIPHER_SUITE:
            context.set_ciphers(config.TLS_CIPHER_SUITE)

        cipher_names = ", ".join([cipher["name"] for cipher in context.get_ciphers()])
        sslContext.log_tls_cipher_suites(cipher_names)

    # Build and start the SMTP server with authentication and TLS settings.
    controller = None
    try:
        controller = CustomController(
            Handler(),
            hostname='',  # bind dual-stack on all interfaces
            port=8025,
            ident=config.SERVER_GREETING,
            authenticator=Authenticator(),
            auth_required=True,
            auth_require_tls=config.REQUIRE_TLS,
            require_starttls=config.REQUIRE_TLS,
            tls_context=context
        )
        controller.start()
        relay_logging.log_server_started()
    except Exception as e:
        relay_logging.log_server_start_failed(e)
        if controller:
            controller.stop()
        raise


if __name__ == '__main__':
    # Setup logging
    logging.basicConfig(
        level=config.LOG_LEVEL,
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
        relay_logging.log_shutdown_requested()
    except Exception as e:
        relay_logging.log_unexpected_error(e)
    finally:
        relay_logging.log_shutting_down()
        tasks = asyncio.all_tasks(loop)
        for task in tasks:
            task.cancel()
        loop.close()
