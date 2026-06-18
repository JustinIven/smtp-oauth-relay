# Configuration Reference

All configuration is via environment variables. Defaults are safe for a TLS-enabled file-based setup.

## General

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_LEVEL` | `WARNING` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` (case-insensitive). Avoid `DEBUG` in production — logs may contain secrets. |
| `SERVER_GREETING` | `Microsoft Graph SMTP OAuth Relay` | SMTP banner sent to clients. |
| `USERNAME_DELIMITER` | `@` | Character separating tenant and client ID in the username. One of `@`, `:`, `|`. Use `:` or `|` if a client rejects `@`. |

## TLS

| Variable | Default | Required when | Description |
|----------|---------|---------------|-------------|
| `TLS_SOURCE` | `file` | — | `off`, `file`, or `keyvault`. `off` disables TLS (dev only). |
| `REQUIRE_TLS` | `true` | — | Reject authentication before STARTTLS. Keep `true` in production. |
| `TLS_CERT_FILEPATH` | `certs/cert.pem` | `TLS_SOURCE=file` | PEM certificate path. |
| `TLS_KEY_FILEPATH` | `certs/key.pem` | `TLS_SOURCE=file` | PEM private key path. |
| `TLS_CIPHER_SUITE` | system default | — | [OpenSSL cipher string](https://docs.openssl.org/3.0/man1/openssl-ciphers/#cipher-list-format); see [Mozilla cipher list](https://wiki.mozilla.org/Security/Cipher_Suites). Active ciphers are logged at startup. TLS 1.3 suites cannot be changed. |

## Azure integration (optional)

| Variable | Default | Required when | Description |
|----------|---------|---------------|-------------|
| `AZURE_KEY_VAULT_URL` | – | `TLS_SOURCE=keyvault` | Key Vault URL holding the TLS certificate (PKCS#12). |
| `AZURE_KEY_VAULT_CERT_NAME` | – | `TLS_SOURCE=keyvault` | Certificate name in Key Vault. |
| `AZURE_TABLES_URL` | – | Table lookup used | Azure Table URL for [credential lookup](azure-tables.md). |
| `AZURE_TABLES_PARTITION_KEY` | `user` | — | PartitionKey used when querying the table. |
| `AZURE_TABLES_FORCE_USAGE` | `false` | — | Require every sender to exist in the table (acts as an allowlist). Needs `AZURE_TABLES_URL`. |

!!! note "Key Vault / Table access"
    The relay authenticates to Azure with `DefaultAzureCredential` (managed identity recommended). The identity needs `Key Vault Certificate User` / `Get Secret` for Key Vault and `Storage Table Data Reader` for Table Storage.

## Examples

=== "Production (file TLS)"

    ```bash
    LOG_LEVEL=WARNING
    TLS_SOURCE=file
    REQUIRE_TLS=true
    TLS_CERT_FILEPATH=/etc/letsencrypt/live/smtp.example.com/fullchain.pem
    TLS_KEY_FILEPATH=/etc/letsencrypt/live/smtp.example.com/privkey.pem
    SERVER_GREETING=Example Corp SMTP Relay
    ```

=== "Production (Key Vault TLS)"

    ```bash
    LOG_LEVEL=WARNING
    TLS_SOURCE=keyvault
    REQUIRE_TLS=true
    AZURE_KEY_VAULT_URL=https://prod-keyvault.vault.azure.net/
    AZURE_KEY_VAULT_CERT_NAME=smtp-relay-cert
    ```

=== "With Azure Tables"

    ```bash
    TLS_SOURCE=keyvault
    REQUIRE_TLS=true
    AZURE_KEY_VAULT_URL=https://my-keyvault.vault.azure.net/
    AZURE_KEY_VAULT_CERT_NAME=smtp-cert
    AZURE_TABLES_URL=https://mystorageaccount.table.core.windows.net/users
    AZURE_TABLES_PARTITION_KEY=smtp-users
    AZURE_TABLES_FORCE_USAGE=true
    ```

=== "Development (no TLS)"

    ```bash
    LOG_LEVEL=DEBUG
    TLS_SOURCE=off
    REQUIRE_TLS=false
    ```

The relay validates configuration at startup and fails with a clear error if required variables are missing, values are invalid, cert files are missing (`TLS_SOURCE=file`), or Key Vault is unreachable (`TLS_SOURCE=keyvault`).

## Next steps

- [Set up Entra ID](entra-id-setup/index.md)
- [Configure SMTP clients](client-setup.md)
- [Azure Tables integration](azure-tables.md)
