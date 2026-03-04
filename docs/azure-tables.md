# Azure Tables Integration

The SMTP OAuth Relay supports storing credentials in Azure Table Storage for centralized credential management. This allows you to use short, memorable usernames instead of long UUID-based credentials.

## Table of Contents
- [Overview](#overview)
- [Benefits](#benefits)
- [Setup](#setup)
- [Table Schema](#table-schema)
- [Usage](#usage)
- [Management](#management)
- [Security Considerations](#security-considerations)

## Overview

Azure Tables integration enables a lookup mechanism where:
- Users authenticate with a short lookup ID (e.g., `app1@lookup`)
- The server queries Azure Table Storage to retrieve the actual tenant_id and client_id
- Optionally overrides the sender email address

This is useful for:
- Overriding sender addresses for clients that don't allow custom From addresses
- Simplifying credentials for devices with limited input
- Centralizing credential management

## Benefits

### Simplified Credentials

**Traditional format**:
```
Username: 12345678-1234-1234-1234-123456789abc@abcdefab-1234-5678-abcd-abcdefabcdef
Password: very-long-client-secret-string
```

**With Azure Tables**:
```
Username: app1@lookup
Password: very-long-client-secret-string
```

### Centralized Management

- Update credentials in one place
- Rotate client IDs without reconfiguring clients
- Manage multiple applications centrally
- Audit who has access

### Sender Address Override

Some clients (like certain network printers) don't allow setting a custom From address. Azure Tables can override this:

```python
# Table entry includes: from_email = "printer@example.com"
# Email is sent from "printer@example.com" regardless of client's From header
```

## Setup

### Prerequisites

- Azure Storage Account
- Azure Table created in the storage account
- Managed Identity or credentials for the relay to access the table

### Create Storage Account and Table

#### Using Azure Portal

1. Navigate to **Storage accounts** in Azure Portal
2. Click **Create**
3. Configure:
   - **Resource group**: Select or create
   - **Storage account name**: `smtprelaystorageXXXX` (must be unique)
   - **Region**: Choose appropriate region
   - **Performance**: Standard
   - **Redundancy**: LRS or higher based on needs
4. Click **Review + create** → **Create**
5. Once created, go to the storage account
6. Navigate to **Tables** under **Data storage**
7. Click **+ Table**
8. Name: `users` (or your preferred name)
9. Click **OK**

#### Using Azure CLI

```bash
# Variables
RESOURCE_GROUP="smtp-relay-rg"
LOCATION="switzerlandnorth"
STORAGE_ACCOUNT="smtprelay$(openssl rand -hex 4)"
TABLE_NAME="users"

# Create storage account
az storage account create \
  --name $STORAGE_ACCOUNT \
  --resource-group $RESOURCE_GROUP \
  --location $LOCATION \
  --sku Standard_LRS

# Create table
az storage table create \
  --name $TABLE_NAME \
  --account-name $STORAGE_ACCOUNT

# Get table URL
STORAGE_URL=$(az storage account show \
  --name $STORAGE_ACCOUNT \
  --query "primaryEndpoints.table" \
  --output tsv)

echo "Table URL: ${STORAGE_URL}${TABLE_NAME}"
```

#### Using PowerShell

```powershell
# Variables
$resourceGroup = "smtp-relay-rg"
$location = "switzerlandnorth"
$storageAccount = "smtprelay$(Get-Random -Maximum 9999)"
$tableName = "users"

# Create storage account
New-AzStorageAccount `
  -ResourceGroupName $resourceGroup `
  -Name $storageAccount `
  -Location $location `
  -SkuName Standard_LRS

# Get context
$ctx = New-AzStorageContext `
  -StorageAccountName $storageAccount `
  -UseConnectedAccount

# Create table
New-AzStorageTable `
  -Name $tableName `
  -Context $ctx

# Get table URL
$tableUrl = "https://$storageAccount.table.core.windows.net/$tableName"
Write-Host "Table URL: $tableUrl"
```

### Configure Relay

Add environment variables to your relay configuration:

```bash
AZURE_TABLES_URL=https://smtprelay1234.table.core.windows.net/users
AZURE_TABLES_PARTITION_KEY=user
```

Per-domain From remapping and failure notifications also use the same table. Configure `DOMAIN_SETTINGS_TABLES_PARTITION_KEY` (default `domain`) and add one row per sender domain. You can optionally add address-level remapping by providing a comma-separated list of addresses.

### Domain Settings Resolution Order

When both environment variables and Azure Table domain settings are present, the relay resolves
values in this order:

1. Environment variables (for example, `<DOMAIN>_FROM_FAILBACK`, `<DOMAIN>_FAILURE_NOTIFICATION`)
2. Azure Table domain settings (PartitionKey from `DOMAIN_SETTINGS_TABLES_PARTITION_KEY`)

This lets you keep steady-state settings in Azure Tables while still allowing quick overrides
via environment variables when needed.

### Grant Permissions

The relay needs permissions to read from the table. Internally, it uses DefaultAzureCredential to authenticate to Azure so you can use multiple methods to provide the necessary credentials. More details on DefaultAzureCredential can be found [here](https://learn.microsoft.com/en-us/dotnet/api/azure.identity.defaultazurecredential).

#### Using Managed Identity (Recommended)

1. Ensure the relay has a managed identity assigned
2. Grant the identity "Storage Table Data Reader" role:

```bash
# Get relay's managed identity principal ID (Azure Container Instances)
PRINCIPAL_ID=$(az container show \
  --name smtp-relay \
  --resource-group smtp-relay-rg \
  --query identity.principalId \
  --output tsv)

# If you're using Azure Container Apps instead:
# PRINCIPAL_ID=$(az containerapp show \
#   --name smtp-relay \
#   --resource-group smtp-relay-rg \
#   --query identity.principalId \
#   --output tsv)

# Grant role
az role assignment create \
  --assignee $PRINCIPAL_ID \
  --role "Storage Table Data Reader" \
  --scope /subscriptions/<subscription-id>/resourceGroups/smtp-relay-rg/providers/Microsoft.Storage/storageAccounts/smtprelay1234
```

#### Using Environment Variables
If you cannot use Managed Identity or prefer client credentials, set the following environment variables:

```bash
AZURE_TENANT_ID=<your-tenant-id>
AZURE_CLIENT_ID=<your-client-id>
AZURE_CLIENT_SECRET=<your-client-secret>
```

For an extensive list of environment variables supported by DefaultAzureCredential (e.g. signing in with a certificate), refer to the [official documentation](https://learn.microsoft.com/en-us/dotnet/api/azure.identity.environmentcredential).


## Table Schema

### Required Columns

| Column | Type | Description | Example |
|--------|------|-------------|---------|
| PartitionKey | String | Partition key for the entity | `user` |
| RowKey | String | Unique identifier (lookup ID) | `app1`, `printer-01` |
| tenant_id | String | Azure tenant UUID | `12345678-1234-1234-1234-123456789abc` |
| client_id | String | Application client UUID | `abcdefab-1234-5678-abcd-abcdefabcdef` |
| from_email | String | Override sender email address (optional) | `app1@example.com` |
| description | String | Human-readable description (not used by relay) | `Application 1 credentials` |

### Optional Domain Settings Columns (PartitionKey = `domain`)

| Column | Type | Description | Example |
|--------|------|-------------|---------|
| PartitionKey | String | Domain settings partition key (set by `DOMAIN_SETTINGS_TABLES_PARTITION_KEY`) | `domain` |
| RowKey | String | Sender domain | `example.com` |
| from_remap | Boolean/String | Enable From remapping for this domain | `true` |
| from_remap_addresses | String | Comma-separated list of sender addresses to remap | `accounting@example.com,ops@example.com` |
| failure_notification | String | Email address that receives failure notifications | `mail-ops@example.com` |

## Usage

### Authentication

To use Azure Tables lookup:

**Username format**: `<lookup_id>@lookup`

**Example**:
```
Username: app1@lookup
Password: client-secret
```

The server will:
1. Detect `@lookup` in the username
2. Extract `app1` as the RowKey
3. Query Azure Table for PartitionKey=`user` and RowKey=`app1`
4. Retrieve `tenant_id` and `client_id`
5. Request OAuth token using retrieved credentials

### Sender Address Override

If the table entity includes `from_email`:

```json
{
  "RowKey": "app1",
  "tenant_id": "...",
  "client_id": "...",
  "from_email": "noreply@example.com"
}
```

Then all emails sent will use `noreply@example.com` as the sender, regardless of what the client specifies in the MAIL FROM command or From header.

This is useful for:
- Clients that can't set a custom From address
- Enforcing consistent sender addresses
- Printers and devices with limited configuration

## Management

### Adding Entries

#### Azure Portal

1. Navigate to your storage account → **Tables** → Select your table
2. Click **+ Add entity**
3. Fill in:
   - **PartitionKey**: `user`
   - **RowKey**: Your lookup ID (e.g., `app1`)
4. Click **Add property** for each field:
   - **tenant_id** (String): Your tenant UUID
   - **client_id** (String): Your client UUID
   - **from_email** (String, optional): Sender email
5. Click **Insert**

#### Using Azure CLI

```bash
az storage entity insert \
  --account-name smtprelay1234 \
  --table-name users \
  --entity PartitionKey=user RowKey=app1 \
    tenant_id=12345678-1234-1234-1234-123456789abc \
    client_id=abcdefab-1234-5678-abcd-abcdefabcdef \
    from_email=app1@example.com
```

## Troubleshooting

### "No entity found for RowKey"

**Cause**: The lookup ID doesn't exist in the table.

**Solution**:
- Verify the username is correct (should be `lookupid@lookup`)
- Check the table contains an entity with that RowKey
- Verify PartitionKey matches `AZURE_TABLES_PARTITION_KEY`

### "Failed to query Azure Table"

**Cause**: Permission or connectivity issues.

**Solution**:
- Verify `AZURE_TABLES_URL` is correct
- Check managed identity has proper role assignment
- Verify network connectivity to Azure Storage
- Check firewall rules on storage account

### "Entity is missing tenant_id or client_id"

**Cause**: Table entity doesn't have required columns.

**Solution**:
- Verify entity has `tenant_id` column (String type)
- Verify entity has `client_id` column (String type)
- Check column names are exactly `tenant_id` and `client_id` (case-sensitive)

### Lookup is Slow

**Cause**: Azure Tables queries can have latency.

**Solution**:
- Ensure proper indexing (PartitionKey + RowKey)
- Consider caching frequently-used credentials (future feature)
- Use direct UUID format for high-performance scenarios

## Next Steps

- [Authentication guide](authentication.md)
- [Client configuration](client-setup.md)
- [FAQ](faq.md)
