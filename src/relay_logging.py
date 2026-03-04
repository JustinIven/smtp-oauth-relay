# Shared logging helpers to keep main/auth modules focused on flow.

import logging


def log_rejected_mail_from(address: str) -> None:
    logging.warning("Rejected malformed MAIL FROM address: %s", address)


def log_rejected_rcpt_to(address: str) -> None:
    logging.warning("Rejected malformed RCPT TO address: %s", address)


def log_message_received(mail_from: str, rcpt_tos: list[str] | None) -> None:
    logging.info("Message from %s to %s", mail_from, rcpt_tos)


def log_missing_access_token() -> None:
    logging.error("No access token available in session")


def log_data_handler_exception(exc: Exception) -> None:
    logging.exception("Error handling DATA command: %s", exc)


def log_server_started() -> None:
    logging.info("SMTP OAuth relay server started on port 8025")


def log_server_start_failed(exc: Exception) -> None:
    logging.exception("Failed to start SMTP server: %s", exc)


def log_shutdown_requested() -> None:
    logging.info("Shutdown requested via keyboard interrupt")


def log_unexpected_error(exc: Exception) -> None:
    logging.exception("Unexpected error: %s", exc)


def log_shutting_down() -> None:
    logging.info("Shutting down...")


def log_oauth_token_request_failed(exc: Exception) -> None:
    logging.error("OAuth token request failed: %s", exc)


def log_oauth_token_response_details(status_code: int, response_body: str) -> None:
    logging.error("Response status: %s, Response body: %s", status_code, response_body)


def log_unsupported_auth_mechanism(mechanism: str) -> None:
    logging.warning("Unsupported auth mechanism: %s", mechanism)


def log_missing_auth_data() -> None:
    logging.warning("Missing authentication data")


def log_auth_login_decode_failed(exc: Exception) -> None:
    logging.error("Failed to decode login string: %s", exc)


def log_auth_parse_failed(message: str) -> None:
    logging.error("%s", message)


def log_authentication_failed(exc: Exception) -> None:
    logging.error("Authentication failed: %s", exc)


def log_auth_unexpected_error(exc: Exception) -> None:
    logging.exception("Unexpected error during authentication: %s", exc)


def log_rate_limited(mailbox: str) -> None:
    logging.warning("Rate limit exceeded for mailbox %s", mailbox)


def log_graph_failback_retry(original_sender: str, failback_sender: str) -> None:
    logging.warning(
        "Graph returned 404 for sender %s; retrying with failback sender %s",
        original_sender,
        failback_sender,
    )


def log_graph_failback_missing(domain_hint: str | None) -> None:
    logging.warning(
        "Graph returned 404 but no failback sender is configured (domain hint: %s)",
        domain_hint,
    )
