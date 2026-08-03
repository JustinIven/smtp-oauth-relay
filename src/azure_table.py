from azure.identity import DefaultAzureCredential
from azure.data.tables import TableClient

from env import AZURE_TABLES_PARTITION_KEY, AZURE_TABLES_URL


class AzureTableStore:
    """Provides Azure Table access using a shared credential and table client.

    A single instance reuses one ``DefaultAzureCredential`` (and its token
    cache) and one ``TableClient`` for the process lifetime, instead of
    recreating them on every query.
    """

    def __init__(self, table_url: str | None = AZURE_TABLES_URL, partition_key: str = AZURE_TABLES_PARTITION_KEY):
        if not table_url:
            raise ValueError("AZURE_TABLES_URL environment variable not set")
        self._partition_key = partition_key
        self._credential = DefaultAzureCredential()
        self._client = TableClient.from_table_url(table_url=table_url, credential=self._credential)  # pyright: ignore[reportArgumentType]

    def lookup_user(self, lookup_id: str) -> tuple[str, str, str|None]:
        """
        Search in Azure Table for user information based on the lookup_id (RowKey).
        Returns (tenant_id, client_id, from_email) or raises ValueError if not found.
        """
        try:
            entities = self._client.query_entities(
                query_filter=f"PartitionKey eq '{self._partition_key}' and RowKey eq '{lookup_id}'"
            )
            entity = next(iter(entities), None)
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

    def verify_table_access(self) -> None:
        """
        Verify that the Azure Table is accessible.
        Raises RuntimeError if the table cannot be reached.
        """
        try:
            entities = self._client.query_entities(
                query_filter=f"PartitionKey eq '{self._partition_key}'",
                results_per_page=1
            )
            next(iter(entities), None)
        except Exception as e:
            raise RuntimeError(f"Failed to access Azure Table: {str(e)}") from e

    def verify_user_in_table(self, tenant_id: str, client_id: str) -> str | None:
        """
        Verify that a user with the given tenant_id and client_id exists in Azure Table.
        Returns from_email if set, otherwise None.
        Raises ValueError if the user is not found.
        """
        try:
            entities = self._client.query_entities(
                query_filter=f"PartitionKey eq '{self._partition_key}' and tenant_id eq '{tenant_id}' and client_id eq '{client_id}'"
            )
            entity = next(iter(entities), None)
        except Exception as e:
            raise RuntimeError(f"Failed to query Azure Table: {str(e)}") from e

        if not entity:
            raise ValueError(f"Sender not authorized: no entry found for tenant_id '{tenant_id}' and client_id '{client_id}'")

        return entity.get('from_email')
