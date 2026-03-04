from __future__ import annotations

import logging
from email.utils import formataddr, getaddresses
from typing import TYPE_CHECKING

from addressing import lookup_to_failback_address
from config import FROM_REMAP_ADDRESSES, FROM_REMAP_DOMAINS, TO_REMAP_ADDRESSES, TO_REMAP_DOMAINS

if TYPE_CHECKING:
    from domain_settings import DomainSettings


def is_remap_enabled(
    domain: str,
    domain_settings: DomainSettings | None,
    from_address: str | None
) -> bool:
    # Env overrides win, then table-provided domain settings.
    if from_address and from_address.lower() in FROM_REMAP_ADDRESSES:
        return True
    if domain in FROM_REMAP_DOMAINS:
        return True
    if domain_settings and domain_settings.from_remap:
        return True
    return bool(
        domain_settings
        and from_address
        and from_address.lower() in domain_settings.remap_addresses
    )


def is_recipient_remap_enabled(address: str) -> bool:
    # Check remap config for either exact address or domain match.
    if "@" not in address:
        return False
    normalized = address.lower()
    if normalized in TO_REMAP_ADDRESSES:
        return True
    domain = normalized.split("@", 1)[-1]
    return domain in TO_REMAP_DOMAINS


def remap_recipient_address(address: str) -> str | None:
    # Translate a recipient to its configured failback, if enabled.
    if "@" not in address:
        return None
    if not is_recipient_remap_enabled(address):
        return None
    domain = address.split("@", 1)[-1].lower()
    failback = lookup_to_failback_address(domain)
    if not failback:
        logging.warning(
            "Recipient remapping requested for %s but no TO failback address is configured for %s",
            address,
            domain
        )
        return None
    return failback


def remap_recipient_headers(parsed_message) -> dict[str, str]:
    # Rewrite To/Cc/Bcc headers while deduplicating recipients.
    header_updates: dict[str, str] = {}
    for header_name in ("To", "Cc", "Bcc"):
        header_value = parsed_message.get(header_name)
        if not header_value:
            continue
        addresses = getaddresses([header_value])
        if not addresses:
            continue
        updated_addresses: list[str] = []
        seen: set[str] = set()
        header_changed = False
        for display_name, address in addresses:
            if not address:
                continue
            replacement = remap_recipient_address(address)
            if replacement:
                address = replacement
                header_changed = True
            address_key = address.lower()
            if address_key in seen:
                header_changed = True
                continue
            seen.add(address_key)
            if display_name:
                updated_addresses.append(formataddr((display_name, address)))
            else:
                updated_addresses.append(address)
        if header_changed:
            header_updates[header_name] = ", ".join(updated_addresses)
    return header_updates


def remap_recipient_list(addresses: list[str]) -> list[str]:
    # Rewrite envelope recipients and remove duplicates.
    updated: list[str] = []
    seen: set[str] = set()
    for address in addresses:
        replacement = remap_recipient_address(address)
        if replacement:
            address = replacement
        address_key = address.lower()
        if address_key in seen:
            continue
        seen.add(address_key)
        updated.append(address)
    return updated
