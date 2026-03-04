import logging
from dataclasses import dataclass

from azure.data.tables import TableClient
from azure.identity import DefaultAzureCredential

from addressing import normalize_bool, parse_email_address
from config import AZURE_TABLES_URL, DOMAIN_SETTINGS_TABLES_PARTITION_KEY


@dataclass(frozen=True)
class DomainSettings:
    from_remap: bool
    remap_addresses: set[str]
    failure_notification: str | None


def lookup_domain_settings(domain: str) -> DomainSettings | None:
    if not AZURE_TABLES_URL:
        return None

    try:
        credential = DefaultAzureCredential()
        with TableClient.from_table_url(
            table_url=AZURE_TABLES_URL,
            credential=credential
        ) as client:  # pyright: ignore[reportArgumentType]
            entities = client.query_entities(
                query_filter=(
                    f"PartitionKey eq '{DOMAIN_SETTINGS_TABLES_PARTITION_KEY}' "
                    f"and RowKey eq '{domain}'"
                )
            )
            entity = None
            for item in entities:
                entity = item
                break
    except Exception as exc:
        logging.error("Failed to query domain settings from Azure Table: %s", exc)
        return None

    if not entity:
        return None

    from_remap = normalize_bool(entity.get("from_remap")) or False
    remap_addresses_value = entity.get("from_remap_addresses")
    remap_addresses = {
        item.strip().lower()
        for item in str(remap_addresses_value).split(",")
        if remap_addresses_value and item.strip()
    }
    failure_notification = parse_email_address(entity.get("failure_notification"))
    return DomainSettings(
        from_remap=from_remap,
        remap_addresses=remap_addresses,
        failure_notification=failure_notification
    )
