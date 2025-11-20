# Configuration Reference

This document provides a comprehensive reference for all configuration options available in the SMTP OAuth Relay.

## Table of Contents
- [Environment Variables](#environment-variables)
- [TLS Configuration](#tls-configuration)
- [Authentication Configuration](#authentication-configuration)
- [Azure Integration](#azure-integration)
- [Logging Configuration](#logging-configuration)

## Environment Variables

All configuration is done through environment variables. Below is a complete reference:

### General Settings

#### LOG_LEVEL
- **Type**: String
- **Default**: `WARNING`
- **Valid Values**: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` (case-insensitive)
- **Description**: Controls the verbosity of logging output.

**Examples**:
```bash
# Development - verbose logging
LOG_LEVEL=DEBUG

# Production - minimal logging
LOG_LEVEL=WARNING

# Troubleshooting - informational messages
LOG_LEVEL=INFO
```

#### SERVER_GREETING
- **Type**: String
- **Default**: `Microsoft Graph SMTP OAuth Relay`
- **Description**: The identification string sent to clients when they connect (SMTP banner).

**Example**:
```bash
SERVER_GREETING="My Company SMTP Relay"
```

### TLS Configuration

#### TLS_SOURCE
- **Type**: String
- **Default**: `file`
- **Valid Values**: `off`, `file`, `keyvault` (case-insensitive)
- **Description**: Specifies where TLS certificates are loaded from.
  - `off`: TLS disabled (not recommended for production)
  - `file`: Load certificates from filesystem
  - `keyvault`: Load certificates from Azure Key Vault

**Examples**:
```bash
# Load from filesystem (default)
TLS_SOURCE=file

# Use Azure Key Vault
TLS_SOURCE=keyvault

# Disable TLS (development only)
TLS_SOURCE=off
```

#### REQUIRE_TLS
- **Type**: Boolean
- **Default**: `true`
- **Valid Values**: `true`, `false` (case-insensitive)
- **Description**: Whether to require TLS encryption for authentication. When `true`:
  - Clients must use STARTTLS before authenticating
  - Authentication attempts without TLS are rejected
  
**Security Note**: Should always be `true` in production environments.

**Examples**:
```bash
# Require TLS (recommended)
REQUIRE_TLS=true

# Allow unencrypted connections (development only)
REQUIRE_TLS=false
```

#### TLS_CERT_FILEPATH
- **Type**: String (file path)
- **Default**: `certs/cert.pem`
- **Description**: Path to PEM-encoded TLS certificate file. Only used when `TLS_SOURCE=file`.

**Example**:
```bash
TLS_CERT_FILEPATH=/etc/smtp-relay/certs/fullchain.pem
```

#### TLS_KEY_FILEPATH
- **Type**: String (file path)
- **Default**: `certs/key.pem`
- **Description**: Path to PEM-encoded TLS private key file. Only used when `TLS_SOURCE=file`.

**Example**:
```bash
TLS_KEY_FILEPATH=/etc/smtp-relay/certs/privkey.pem
```

#### TLS_CIPHER_SUITE
- **Type**: String
- **Default**: None (uses system defaults)
- **Description**: Specifies the TLS cipher suite to use for secure connections. Follows [OpenSSL cipher string format](https://docs.openssl.org/3.0/man1/openssl-ciphers/#cipher-list-format). See the following table for all [ciphers](https://wiki.mozilla.org/Security/Cipher_Suites). The used cipher suites will be logged on startup.

> [!NOTE]  
> Note that the TLS 1.3 cipher suites cannot be disabled or modified.



**Example**:
```bash
TLS_CIPHER_SUITE=DHE-RSA-AES128-GCM-SHA256:DHE-RSA-AES256-GCM-SHA384:DHE-RSA-CHACHA20-POLY1305
```

### Authentication Configuration

#### USERNAME_DELIMITER
- **Type**: String (single character)
- **Default**: `@`
- **Valid Values**: `@`, `:`, `|`
- **Description**: Character used to separate tenant ID and client ID in the username.

**Examples**:
```bash
# Using @ delimiter (default)
USERNAME_DELIMITER=@
# Username format: tenant_id@client_id

# Using colon delimiter
USERNAME_DELIMITER=:
# Username format: tenant_id:client_id

# Using pipe delimiter
USERNAME_DELIMITER=|
# Username format: tenant_id|client_id
```

**Why change the delimiter?**
- Some email clients may have restrictions on allowed characters
- The `@` symbol is commonly expected in email usernames
- Use `:` or `|` if your client has issues with `@`

### Azure Integration

#### AZURE_KEY_VAULT_URL
- **Type**: String (URL)
- **Default**: None (optional)
- **Required When**: `TLS_SOURCE=keyvault`
- **Description**: The URL of the Azure Key Vault containing TLS certificates.

**Example**:
```bash
AZURE_KEY_VAULT_URL=https://my-keyvault.vault.azure.net/
```

**Requirements**:
- The application must have a managed identity
- The identity must have `Get Secret` and `Get Certificate` permissions on the Key Vault
- Certificate must be imported in PKCS#12 format

#### AZURE_KEY_VAULT_CERT_NAME
- **Type**: String
- **Default**: None (optional)
- **Required When**: `TLS_SOURCE=keyvault`
- **Description**: The name of the certificate in Azure Key Vault.

**Example**:
```bash
AZURE_KEY_VAULT_CERT_NAME=smtp-relay-certificate
```

#### AZURE_TABLES_URL
- **Type**: String (URL)
- **Default**: None (optional)
- **Description**: The URL of an Azure Table for user lookup functionality. Enables storing credentials centrally.

**Example**:
```bash
AZURE_TABLES_URL=https://mystorageaccount.table.core.windows.net/users
```

**Table Schema**:
| Column | Type | Description |
|--------|------|-------------|
| PartitionKey | String | User partition (configurable via `AZURE_TABLES_PARTITION_KEY`) |
| RowKey | String | Lookup ID used in username |
| tenant_id | String | Azure tenant ID (UUID) |
| client_id | String | Application client ID (UUID) |
| from_email | String (optional) | Email address to use as sender |

See [Azure Tables Integration](azure-tables.md) for detailed setup.

#### AZURE_TABLES_PARTITION_KEY
- **Type**: String
- **Default**: `user`
- **Description**: The partition key to use when querying the Azure Table.

**Example**:
```bash
AZURE_TABLES_PARTITION_KEY=smtp-users
```

## Configuration Examples

### Production Configuration (File-based TLS)

```bash
LOG_LEVEL=WARNING
TLS_SOURCE=file
REQUIRE_TLS=true
TLS_CERT_FILEPATH=/etc/letsencrypt/live/smtp.example.com/fullchain.pem
TLS_KEY_FILEPATH=/etc/letsencrypt/live/smtp.example.com/privkey.pem
USERNAME_DELIMITER=@
SERVER_GREETING=Example Corp SMTP Relay
```

### Production Configuration (Key Vault TLS)

```bash
LOG_LEVEL=WARNING
TLS_SOURCE=keyvault
REQUIRE_TLS=true
AZURE_KEY_VAULT_URL=https://prod-keyvault.vault.azure.net/
AZURE_KEY_VAULT_CERT_NAME=smtp-relay-cert
USERNAME_DELIMITER=@
SERVER_GREETING=Example Corp SMTP Relay
```

### Development Configuration

```bash
LOG_LEVEL=DEBUG
TLS_SOURCE=file
REQUIRE_TLS=false
TLS_CERT_FILEPATH=certs/cert.pem
TLS_KEY_FILEPATH=certs/key.pem
USERNAME_DELIMITER=@
```

### Configuration with Azure Tables

```bash
LOG_LEVEL=INFO
TLS_SOURCE=keyvault
REQUIRE_TLS=true
AZURE_KEY_VAULT_URL=https://my-keyvault.vault.azure.net/
AZURE_KEY_VAULT_CERT_NAME=smtp-cert
AZURE_TABLES_URL=https://mystorageaccount.table.core.windows.net/users
AZURE_TABLES_PARTITION_KEY=smtp-users
USERNAME_DELIMITER=@
```

## Validation

The server validates configuration on startup and will fail with clear error messages if:
- Required variables are missing
- Values are outside valid ranges
- File paths don't exist (when `TLS_SOURCE=file`)
- Key Vault is inaccessible (when `TLS_SOURCE=keyvault`)

## Next Steps

- [Set up Azure/Entra ID](azure-setup.md)
- [Configure TLS certificates](installation.md#tls--certificates)
- [Configure SMTP clients](client-setup.md)
- [Set up Azure Tables](azure-tables.md)
