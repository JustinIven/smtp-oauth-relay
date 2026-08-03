import base64
import re
import uuid

from azure_table import AzureTableStore
from env import (
    USERNAME_DELIMITER,
    AZURE_TABLES_FORCE_USAGE
)


UUID_PATTERN = re.compile(r'^[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}$')


def decode_uuid_or_base64url(input_str: str) -> str:
    """
    Checks if input is a UUID string, otherwise attempts to decode as base64url and convert to UUID string.
    Returns a decoded string in UUID format.
    """

    # check if the input is a UUID
    if UUID_PATTERN.match(input_str):
        return input_str

    # Attempt to decode as base64url
    try:
        return str(uuid.UUID(bytes=base64.urlsafe_b64decode(input_str + '=' * (-len(input_str) % 4))))
    except Exception:
        raise ValueError(f"Invalid base64url encoding in input '{input_str}'")


def parse_username(username: str, table_store: AzureTableStore | None = None) -> tuple[str, str, str|None]:
    """
    Parse the username to extract tenant_id and client_id.
    The expected format is: tenant_id{USERNAME_DELIMITER}client_id{. optional_tld}
    """

    # remove the optional TLD if present
    if '.' in username:
        username = username.split('.')[0]

    # Check if username is valid
    if not username or USERNAME_DELIMITER not in username:
        raise ValueError(f"Invalid username format. Expected format: tenant_id{USERNAME_DELIMITER}client_id")

    # Split the username by the delimiter
    parts = username.split(USERNAME_DELIMITER)
    if len(parts) != 2:
        raise ValueError(f"Invalid username format. Expected exactly one '{USERNAME_DELIMITER}' character")

    # check if the second part hints a user stored in the lookup table
    if parts[1] == 'lookup':
        if table_store is None:
            raise ValueError("User lookup requested but Azure Tables is not configured")
        return table_store.lookup_user(parts[0])

    # else return both parts decoded
    tenant_id = decode_uuid_or_base64url(parts[0])
    client_id = decode_uuid_or_base64url(parts[1])

    # If AZURE_TABLES_FORCE_USAGE is enabled, verify the user exists in the table
    if AZURE_TABLES_FORCE_USAGE:
        if table_store is None:
            raise ValueError("AZURE_TABLES_FORCE_USAGE is enabled but Azure Tables is not configured")
        from_email = table_store.verify_user_in_table(tenant_id, client_id)
        return tenant_id, client_id, from_email

    return tenant_id, client_id, None
