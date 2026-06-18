# Azure Tables Integration

*Optional.* Store credential mappings in Azure Table Storage so clients authenticate with a short ID (`app1@lookup`) instead of full UUIDs. The table never stores client secrets — those remain the SMTP password.

Use it to:

- Give devices with short username fields a simple lookup ID.
- Override the sender address for clients that can't set a custom From.
- Centralize credential mappings.
- Restrict who may use the relay (with `AZURE_TABLES_FORCE_USAGE=true`).

```text
# Without Azure Tables
Username: 12345678-…-789abc@abcdefab-…-abcdef

# With Azure Tables
Username: app1@lookup
```

!!! info "Enforce an allowlist"
    With `AZURE_TABLES_FORCE_USAGE=true` the relay verifies it can reach the table at startup and rejects any sender (lookup **or** direct `tenant_id@client_id`) that has no matching entry.

## Setup

### 1. Create a storage account and table

=== "Azure CLI"

    ```bash
    RESOURCE_GROUP="smtp-relay-rg"
    STORAGE_ACCOUNT="smtprelay$(openssl rand -hex 4)"
    TABLE_NAME="users"

    az storage account create --name $STORAGE_ACCOUNT \
      --resource-group $RESOURCE_GROUP --location switzerlandnorth --sku Standard_LRS
    az storage table create --name $TABLE_NAME --account-name $STORAGE_ACCOUNT
    echo "https://$STORAGE_ACCOUNT.table.core.windows.net/$TABLE_NAME"
    ```

=== "PowerShell"

    ```powershell
    $storageAccount = "smtprelay$(Get-Random -Maximum 9999)"
    New-AzStorageAccount -ResourceGroupName "smtp-relay-rg" -Name $storageAccount `
      -Location switzerlandnorth -SkuName Standard_LRS
    $ctx = New-AzStorageContext -StorageAccountName $storageAccount -UseConnectedAccount
    New-AzStorageTable -Name "users" -Context $ctx
    "https://$storageAccount.table.core.windows.net/users"
    ```

=== "Portal"

    **Storage accounts → Create** (Standard, LRS), then **Data storage → Tables → + Table**, name it `users`.

### 2. Configure the relay

```bash
AZURE_TABLES_URL=https://smtprelay1234.table.core.windows.net/users
AZURE_TABLES_PARTITION_KEY=user
```

### 3. Grant read access

The relay authenticates with `DefaultAzureCredential`. Prefer a **managed identity** with the `Storage Table Data Reader` role:

```bash
az role assignment create \
  --assignee <relay-managed-identity-principal-id> \
  --role "Storage Table Data Reader" \
  --scope <storage-account-resource-id>
```

??? note "Alternative: service principal via environment variables"
    ```bash
    AZURE_TENANT_ID=<tenant-id>
    AZURE_CLIENT_ID=<client-id>
    AZURE_CLIENT_SECRET=<client-secret>
    ```
    See the [`DefaultAzureCredential` docs](https://learn.microsoft.com/en-us/dotnet/api/azure.identity.defaultazurecredential) for all supported methods.

## Table schema

| Column | Required | Description | Example |
|--------|----------|-------------|---------|
| `PartitionKey` | Yes | Must match `AZURE_TABLES_PARTITION_KEY` | `user` |
| `RowKey` | Yes | Lookup ID used in the username | `app1`, `printer-01` |
| `tenant_id` | Yes | Azure tenant UUID | `12345678-…` |
| `client_id` | Yes | Application client UUID | `abcdefab-…` |
| `from_email` | No | Overrides the sender address | `app1@example.com` |
| `description` | No | Free-text note (ignored by the relay) | `App 1` |

## Usage

Authenticate with `<lookup_id>@lookup` and the client secret as the password. The relay reads `PartitionKey`/`RowKey`, retrieves `tenant_id` and `client_id`, and requests the token.

If the entry sets `from_email`, **all** messages for that user are sent from that address regardless of the client's `MAIL FROM` / `From` header — useful for devices that can't set a custom From.

### Add an entry

```bash
az storage entity insert \
  --account-name smtprelay1234 --table-name users \
  --entity PartitionKey=user RowKey=app1 \
    tenant_id=12345678-1234-1234-1234-123456789abc \
    client_id=abcdefab-1234-5678-abcd-abcdefabcdef \
    from_email=app1@example.com
```

In the Portal: **Tables → your table → + Add entity**, set `PartitionKey`/`RowKey` and add the columns above as String properties.

## Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| `No entity found for RowKey` | Lookup ID not in table | Verify username is `lookupid@lookup`; check `RowKey` and `PartitionKey` |
| `Failed to query Azure Table` | Permissions or connectivity | Check `AZURE_TABLES_URL`, role assignment, storage firewall |
| `Entity is missing tenant_id or client_id` | Missing/misnamed columns | Add `tenant_id` and `client_id` as String (case-sensitive) |

## Next steps

- [Authentication formats](authentication.md)
- [Client setup](client-setup.md)
- [Configuration reference](configuration.md)
