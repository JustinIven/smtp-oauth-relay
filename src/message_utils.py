import logging
import re
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import getaddresses, parsedate_to_datetime

from constants import (
    SMTP_BARE_LF,
    SMTP_INVALID_DATE,
    SMTP_INVALID_FROM,
    SMTP_MISSING_DATE,
    SMTP_MISSING_FROM,
)

BARE_LF_PATTERN = re.compile(br"(?<!\r)\n")


def validate_rfc5322_message(
    raw_message: bytes,
    *,
    parsed_message: EmailMessage | None = None,
    allow_invalid_from: bool = False
) -> str | None:
    if BARE_LF_PATTERN.search(raw_message):
        return SMTP_BARE_LF

    if parsed_message is None:
        parsed_message = BytesParser(policy=policy.SMTP).parsebytes(raw_message)
    from_header = parsed_message.get("From")
    date_header = parsed_message.get("Date")
    if not from_header and not allow_invalid_from:
        return SMTP_MISSING_FROM
    if not date_header:
        return SMTP_MISSING_DATE

    if from_header:
        addresses = [addr for _, addr in getaddresses([from_header]) if addr]
        if (not allow_invalid_from) and (
            not addresses or any("@" not in addr for addr in addresses)
        ):
            return SMTP_INVALID_FROM

    try:
        if parsedate_to_datetime(date_header) is None:
            return SMTP_INVALID_DATE
    except (TypeError, ValueError):
        return SMTP_INVALID_DATE
    return None


def split_raw_message(raw_message: bytes) -> tuple[bytes, bytes, bytes]:
    header_end = raw_message.find(b"\r\n\r\n")
    separator = b"\r\n\r\n"
    if header_end == -1:
        header_end = raw_message.find(b"\n\n")
        separator = b"\n\n"
    if header_end == -1:
        if raw_message.startswith(b"\r\n"):
            return b"", b"\r\n", raw_message[len(b"\r\n"):]
        if raw_message.startswith(b"\n"):
            return b"", b"\n", raw_message[len(b"\n"):]
        return raw_message, b"", b""
    header_bytes = raw_message[:header_end]
    body_bytes = raw_message[header_end + len(separator):]
    return header_bytes, separator, body_bytes


def update_raw_headers(raw_message: bytes, updates: dict[str, str | None]) -> bytes:
    header_bytes, separator, body_bytes = split_raw_message(raw_message)
    line_ending = b"\r\n" if b"\r\n" in header_bytes else b"\n"

    updated_keys = {key.lower() for key in updates}
    new_lines: list[bytes] = []
    skip_header = False

    for line in header_bytes.splitlines(keepends=True):
        if line.startswith((b" ", b"\t")):
            if skip_header:
                continue
            new_lines.append(line)
            continue

        header_name = line.split(b":", 1)[0].decode("utf-8", "replace").strip().lower()
        skip_header = header_name in updated_keys
        if skip_header:
            continue
        new_lines.append(line)

    has_new_headers = any(value is not None for value in updates.values())
    # Ensure appended headers don't get glued to the last existing header line.
    if new_lines and has_new_headers and not new_lines[-1].endswith(line_ending):
        new_lines[-1] = new_lines[-1] + line_ending

    for header_name, header_value in updates.items():
        if header_value is None:
            continue
        new_lines.append(f"{header_name}: {header_value}".encode() + line_ending)

    rebuilt_headers = b"".join(new_lines)
    if separator:
        return rebuilt_headers + separator + body_bytes
    if body_bytes:
        return rebuilt_headers + (line_ending + line_ending) + body_bytes
    return rebuilt_headers


def apply_header_updates(
    raw_message: bytes,
    parsed_message: EmailMessage,
    updates: dict[str, str | None],
    reasons: list[str],
) -> bytes:
    # Centralize update logging + rewrite so callers stay focused on flow.
    if not updates:
        return raw_message

    if logging.getLogger().isEnabledFor(logging.DEBUG):
        for header_name in sorted(updates.keys()):
            old_value = parsed_message.get(header_name)
            new_value = updates[header_name]
            if new_value is None:
                logging.debug(
                    "Header update: %s removed (was %r)",
                    header_name,
                    old_value
                )
            else:
                logging.debug(
                    "Header update: %s %r -> %r",
                    header_name,
                    old_value,
                    new_value
                )

    logging.info(
        "Message headers updated: %s; reasons=%s",
        ", ".join(sorted(updates.keys())),
        ", ".join(reasons) if reasons else "unspecified"
    )
    return update_raw_headers(raw_message, updates)


def build_reply_to_value(existing_reply_to: str | None, original_from: str) -> str:
    if not existing_reply_to:
        return original_from
    existing_addresses = {
        addr.lower() for _, addr in getaddresses([existing_reply_to]) if addr
    }
    original_addresses = [addr for _, addr in getaddresses([original_from]) if addr]
    if not original_addresses:
        return existing_reply_to
    if any(addr.lower() not in existing_addresses for addr in original_addresses):
        return f"{existing_reply_to}, {original_from}"
    return existing_reply_to


def log_invalid_x_sender(
    original_value: str,
    replacement_sender: str | None,
    return_path: str | None,
    from_header: str | None,
) -> None:
    if replacement_sender:
        logging.debug(
            "Normalized invalid X-Sender %r -> %r",
            original_value,
            replacement_sender,
        )
    else:
        logging.debug(
            "Invalid X-Sender %r with no replacement (Return-Path=%r, From=%r)",
            original_value,
            return_path,
            from_header,
        )


def log_recipient_header_remap() -> None:
    logging.info("Remapped recipient headers based on TO remap settings.")


def log_envelope_recipient_remap() -> None:
    logging.info("Remapped SMTP recipients based on TO remap settings.")


def log_failback_sender_used(domain_hint: str | None) -> None:
    logging.warning(
        "Using failback sender address for malformed message (domain hint: %s)",
        domain_hint,
    )


def log_failback_sender_missing() -> None:
    logging.error("Unable to determine sender address and no failback configured.")


def log_from_remap_applied(domain_hint: str, failback_address: str) -> None:
    logging.info(
        "Remapped From header for domain %s using failback address %s",
        domain_hint,
        failback_address,
    )


def log_from_remap_missing(domain_hint: str) -> None:
    logging.warning(
        "From remapping requested for domain %s but no failback address is configured",
        domain_hint,
    )


def log_failure_notification_missing_sender(domain_hint: str | None) -> None:
    logging.warning(
        "Failure notification configured for domain %s but no sender address is available",
        domain_hint,
    )


def log_rfc5322_validation_failed(error_message: str) -> None:
    logging.error("RFC 5322 validation failed: %s", error_message)
