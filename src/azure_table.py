from azure.identity import DefaultAzureCredential
from azure.data.tables import TableClient

from env import AZURE_TABLES_PARTITION_KEY, AZURE_TABLES_URL


def lookup_user(lookup_id: str) -> tuple[str, str, str|None]:
    """
    Search in Azure Table for user information based on the lookup_id (RowKey).
    Returns (tenant_id, client_id, from_email) or raises ValueError if not found.
    """
    if not AZURE_TABLES_URL:
        raise ValueError("AZURE_TABLES_URL environment variable not set")

    try:
        credential = DefaultAzureCredential()
        with TableClient.from_table_url(table_url=AZURE_TABLES_URL, credential=credential) as client: # pyright: ignore[reportArgumentType]
            entities = client.query_entities(query_filter=f"PartitionKey eq '{AZURE_TABLES_PARTITION_KEY}' and RowKey eq '{lookup_id}'")
            entity = None
            for i in entities:
                entity = i
                break
    except Exception as e:
        raise RuntimeError(f"Failed to query Azure Table: {str(e)}") from e

    if not entity:
        raise ValueError(f"No entity found for RowKey '{lookup_id}'")

    tenant_id = entity.get('tenant_id')
    client_id = entity.get('client_id')
    from_email = entity.get('from_email')

    if not tenant_id or not client_id:
        raise ValueError(f"Entity for RowKey '{lookup_id}' is missing tenant_id or client_id")

    return tenant_id, client_id, from_email


def verify_table_access():
    """
    Verify that the Azure Table is accessible.
    Raises RuntimeError if the table cannot be reached.
    """
    if not AZURE_TABLES_URL:
        raise ValueError("AZURE_TABLES_URL must be set when AZURE_TABLES_FORCE_USAGE is enabled")

    try:
        credential = DefaultAzureCredential()
        with TableClient.from_table_url(table_url=AZURE_TABLES_URL, credential=credential) as client: # pyright: ignore[reportArgumentType]
            entities = client.query_entities(
                query_filter=f"PartitionKey eq '{AZURE_TABLES_PARTITION_KEY}'",
                results_per_page=1
            )
            for _ in entities:
                break
    except Exception as e:
        raise RuntimeError(f"Failed to access Azure Table: {str(e)}") from e


def verify_user_in_table(tenant_id: str, client_id: str) -> str | None:
    """
    Verify that a user with the given tenant_id and client_id exists in Azure Table.
    Returns from_email if set, otherwise None.
    Raises ValueError if the user is not found.
    """
    if not AZURE_TABLES_URL:
        raise ValueError("AZURE_TABLES_URL environment variable not set")

    try:
        credential = DefaultAzureCredential()
        with TableClient.from_table_url(table_url=AZURE_TABLES_URL, credential=credential) as client: # pyright: ignore[reportArgumentType]
            entities = client.query_entities(
                query_filter=f"PartitionKey eq '{AZURE_TABLES_PARTITION_KEY}' and tenant_id eq '{tenant_id}' and client_id eq '{client_id}'"
            )
            entity = None
            for i in entities:
                entity = i
                break
    except Exception as e:
        raise RuntimeError(f"Failed to query Azure Table: {str(e)}") from e

    if not entity:
        raise ValueError(f"Sender not authorized: no entry found for tenant_id '{tenant_id}' and client_id '{client_id}'")

    return entity.get('from_email')
