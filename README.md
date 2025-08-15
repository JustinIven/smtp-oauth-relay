# SMTP OAuth Relay

An SMTP relay that accepts SMTP submissions from legacy clients and forwards messages to Microsoft Graph using OAuth 2.0 client credentials.

This repository implements a small, stateless SMTP server that:
- Accepts SMTP connections on port 8025 (configurable)
- Authenticates clients using a special username format containing a tenant and client (application) id, plus the client secret as the password
- Acquires an application token from Microsoft Entra ID
- Sends messages through Microsoft Graph using the application's Mail.Send permission

The goal is to let SMTP-only clients send mail through Microsoft services without embedding user credentials.

## Table of Contents
- [Server configuration](#server-configuration)
  - [Getting started (Docker)](#getting-started-docker)
  - [Configuration (environment variables)](#configuration-environment-variables)
  - [TLS / certificates](#tls--certificates)
- [Client configuration](#client-configuration)
  - [Setting up Microsoft Entra ID application](#setting-up-microsoft-entra-id-application)
  - [SMTP username format](#smtp-username-format)
  - [SMTP client configuration](#smtp-client-configuration)
- [Additional](#additional)
  - [How it works](#how-it-works)
  - [Security considerations](#security-considerations)
  - [FAQ](#faq)
  - [License](#license)

---

## Server configuration

### Getting started (Docker)
The easiest way to run the SMTP OAuth Relay is via Docker:
```shell
docker run --name smtp-relay -p 8025:8025 \
  -v $(pwd)/certs:/usr/src/smtp-relay/certs \
  -e LOG_LEVEL=INFO \
  -e USE_TLS=True \
  -e REQUIRE_TLS=True \
  ghcr.io/justiniven/smtp-oauth-relay:latest
```

### Configuration (environment variables)

The server is configured via environment variables. Defaults shown below reflect the current implementation in `main.py`.

| Variable                 | Meaning / type                                  | Default                |
|--------------------------|--------------------------------------------------|------------------------|
| LOG_LEVEL                | Logging level (DEBUG, INFO, WARNING, ERROR)     | WARNING               |
| TLS_SOURCE               | TLS source: `off`, `file`, or `keyvault`        | file                  |
| REQUIRE_TLS              | Require TLS for authentication (true/false)     | true                  |
| SERVER_GREETING          | SMTP server ident / greeting string             | Microsoft Graph SMTP OAuth Relay |
| TLS_CERT_FILEPATH        | Path to TLS certificate (PEM)                   | certs/cert.pem        |
| TLS_KEY_FILEPATH         | Path to TLS private key (PEM)                   | certs/key.pem         |
| USERNAME_DELIMITER       | Delimiter between tenant_id and client_id       | @                     |
| AZURE_KEY_VAULT_URL      | (optional) Key Vault URL when TLS_SOURCE=keyvault | (none)              |
| AZURE_KEY_VAULT_CERT_NAME| (optional) Key Vault certificate name          | (none)                |

Notes:
- Boolean-like values are parsed case-insensitively (e.g. `true`, `True`, `false`).
- `USERNAME_DELIMITER` may be one of `@`, `:` or `|`.
- If `TLS_SOURCE` is `keyvault`, set `AZURE_KEY_VAULT_URL` and `AZURE_KEY_VAULT_CERT_NAME`.

### TLS / certificates

The server expects PEM-encoded certificate and private key files when `TLS_SOURCE=file`.

Generate a self-signed cert for local testing:

```bash
mkdir -p certs
openssl req -x509 -newkey rsa:2048 -nodes -keyout certs/key.pem -out certs/cert.pem -days 365 \
    -subj "/CN=localhost"
```

For production, provide a valid certificate chain and private key.

If you want to use Azure Key Vault for TLS material, set `TLS_SOURCE=keyvault` and provide `AZURE_KEY_VAULT_URL` and `AZURE_KEY_VAULT_CERT_NAME`.



## Client configuration
### Setting up Microsoft Entra ID application
1. Create an application (App Registration) in the Azure portal (or via Microsoft Graph / PowerShell).
2. Grant the application the application permission Mail.Send and grant admin consent for the tenant.
3. Create a client secret and record the value (this will be the SMTP password).
4. (Recommended) Restrict the app so it can only send on behalf of specific sender addresses using an Application Access Policy.

<details>
<summary>Create and restrict Application with PowerShell</summary>

```powershell
$appName = "SMTP Relay"
$appSecretEndDateTime = (Get-Date).AddYears(2)
$senderAddress = "test@example.com"


Connect-MgGraph -Scopes "Application.ReadWrite.All" -NoWelcome
Connect-ExchangeOnline -ShowBanner:$false


# create application
$application = Invoke-MgGraphRequest `
    -Method "POST" `
    -Uri "https://graph.microsoft.com/v1.0/applications" `
    -Body @{
        displayName = $AppName
        signInAudience = "AzureADMyOrg"
        passwordCredentials = @(
            @{
                displayName = "secret01"
                endDateTime = $appSecretEndDateTime
            }
        )
        requiredResourceAccess = @(
            @{
                resourceAppId = "00000003-0000-0000-c000-000000000000" # Microsoft Graph
                resourceAccess = @(
                    @{ 
                        id = "b633e1c5-b582-4048-a93e-9f11b44c7e96" # Mail.Send
                        type = "Role"
                    }
                )
            }
        )
    }


# create service principal
$servicePrincipal = Invoke-MgGraphRequest `
    -Method "POST" `
    -Uri "https://graph.microsoft.com/v1.0/servicePrincipals" `
    -Body @{
        appId = $application.appId
        tags = @(
            "WindowsAzureActiveDirectoryIntegratedApp"
            "HideApp"
        )
    }


# grant tenant-wide admin consent
Invoke-MgGraphRequest `
    -Method "POST" `
    -Uri "https://graph.microsoft.com/v1.0/servicePrincipals/$($servicePrincipal.id)/appRoleAssignments" `
    -Body @{
        principalId = $servicePrincipal.id
        resourceId = "7aeb2b66-3434-4d91-b79e-fe5f94c2634b" # Microsoft Graph Service Principal
        appRoleId = "b633e1c5-b582-4048-a93e-9f11b44c7e96" # Mail.Send
    }



# restrict the application to send emails only from the specified sender addresses
New-ApplicationAccessPolicy `
    -AppId $application.appId `
    -PolicyScopeGroupId $senderAddress `
    -AccessRight RestrictAccess `
    -Description "Restrict the SMTP Relay application to send emails only from the specified sender addresses"


# get tenant id
$tenantId = (Get-MgContext).TenantId


Write-Host "Username: " -NoNewline
Write-Host "$($tenantId):$($application.appId)" -ForegroundColor Green
Write-Host "Password: " -NoNewline
Write-Host "$($application.passwordCredentials[0].secretText)" -ForegroundColor Green
```

</details>

### SMTP username format

Authenticate with username and password where:

```
<tenant_id><delimiter><client_id>[.optional_tld]
```

- `tenant_id`: your Azure tenant ID. Either the UUID form or a base64url-encoded UUID.
- `client_id`: the application (client) ID. Either UUID or base64url-encoded UUID.
- `delimiter`: character defined by `USERNAME_DELIMITER` (default `@`).
- `optional_tld`: a dot and any characters after the client_id; this will be ignored by the server (useful for older clients that require an `@domain` on the username).

Examples:

- UUID form:

```
12345678-1234-1234-1234-123456789abc@abcdefab-1234-5678-abcd-abcdefabcdef
```

- base64url-encoded UUID form (how to generate):

```bash
# Replace the UUID below with your UUID
python - <<'PY'
import base64, uuid
u = uuid.UUID('12345678-1234-1234-1234-123456789abc')
print(base64.urlsafe_b64encode(u.bytes).decode().rstrip('='))
PY
```

You can then use the encoded value in the username, for example:

```
<base64url_tenant>@<base64url_client>.local
```

### SMTP Client Configuration
Configure your SMTP client with the following settings:

| Setting   | Value                      |
|-----------|----------------------------|
| Server    | Your SMTP OAuth Relay host |
| Port      | `8025`                     |
| SMTP-encryption | `STARTTLS` or no auth      |
| Username  | `tenant_id:client_id`      |
| Password  | `client_secret`            |

## Additional

### How it works
1. The SMTP server accepts connections on port 8025
2. Clients authenticate using tenant_id:client_id as username and client_secret as password
3. The server obtains an OAuth token from the Microsoft identity platform
4. When an email is received via SMTP, it's converted to a Microsoft Graph API request
5. The email is sent using the application's permissions

![Sequence diagram](docs/images/sequenceDiagram.svg)

### Security considerations
- Always use TLS in production environments
- Store client secrets securely and rotate them from time to time
- Restrict application permissions to only the necessary sender addresses using Application Access Policies
- Monitor logs for failed authentication or sending attempts

### FAQ
Q: Can I use this relay with any SMTP client? \
A: Yes, any SMTP client that supports AUTH PLAIN or AUTH LOGIN should work.

Q: Does this support multiple sender addresses? \
A: Yes, you can configure your Entra ID application to have permissions for multiple sender addresses.

Q: Can the relay be used with email addresses from different Microsoft tenants? \
A: Yes, since the service relies on the tenant ID in the username, it can be used with multiple tenants simultaneously.

Q: Is this relay suitable for high-volume email sending? \
A: This relay is designed for moderate email volumes. Exchange Online rate limits apply. For high-volume scenarios, consider Microsoft's native services like Azure Communication Services or Microsoft 365 High Volume Email.

Q: Can I run multiple instances for high availability? \
A: Yes, the relay is stateless and can be run in multiple instances behind a load balancer.

### License
This project is licensed under the Apache License 2.0 - see the [LICENSE](./LICENSE) file for details.
