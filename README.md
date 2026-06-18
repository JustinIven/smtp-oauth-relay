# SMTP OAuth Relay

A small, stateless SMTP server that lets legacy clients (printers, NAS, monitoring tools, line-of-business apps) send mail through **Microsoft 365** using **OAuth 2.0 client credentials** and the **Microsoft Graph API** — no Basic Authentication required.

- **OAuth 2.0 client credentials** — app credentials instead of user passwords
- **Microsoft Graph** — sends via the `sendMail` endpoint
- **SMTP compatible** — any client supporting `AUTH LOGIN`/`PLAIN` + STARTTLS
- **Stateless** — scale horizontally behind a load balancer
- **TLS** from file or Azure Key Vault
- **Azure Tables** — optional central credential lookup

📖 **Full documentation: https://justiniven.github.io/smtp-oauth-relay/**

## Quick start

Three steps. You need a Microsoft 365 tenant and permission to register an Entra ID application.

### 1. Create Entra ID credentials (PowerShell)

[`New-RelayEntraApp.ps1`](./New-RelayEntraApp.ps1) registers the app, creates a secret, and restricts it to a single sender mailbox.

```powershell
# Prerequisites: PowerShell 5.1+, Microsoft.Graph and ExchangeOnlineManagement modules
Connect-MgGraph -Scopes "Application.ReadWrite.All", "AppRoleAssignment.ReadWrite.All" -NoWelcome
Connect-ExchangeOnline -ShowBanner:$false

Invoke-WebRequest `
  -Uri "https://raw.githubusercontent.com/JustinIven/smtp-oauth-relay/main/New-RelayEntraApp.ps1" `
  -OutFile "New-RelayEntraApp.ps1"

.\New-RelayEntraApp.ps1 -DisplayName "SMTP OAuth Relay" -SenderAddress "noreply@example.com"
```

The script prints the **SMTP username** (`tenant_id@client_id`) and **SMTP password** (client secret). Save them — the secret cannot be retrieved later.

### 2. Run the relay

```bash
docker run --name smtp-relay -p 8025:8025 \
  -e TLS_SOURCE=off \
  -e REQUIRE_TLS=false \
  ghcr.io/justiniven/smtp-oauth-relay:latest
```

> [!WARNING]
> Only disable TLS for testing in a trusted network. Use `TLS_SOURCE=file` or `TLS_SOURCE=keyvault` in production.

Or deploy to Azure Container Instances:

[![Deploy to Azure](https://aka.ms/deploytoazurebutton)](https://portal.azure.com/#create/Microsoft.Template/uri/https%3A%2F%2Fraw.githubusercontent.com%2FJustinIven%2Fsmtp-oauth-relay%2Fmain%2Fazure_deployment%2Fdeployment.json)

### 3. Point your client at the relay

| Setting | Value |
|---------|-------|
| Server | Your relay hostname |
| Port | `8025` |
| Security | STARTTLS |
| Username | `tenant_id@client_id` (from step 1) |
| Password | Client secret (from step 1) |

Verify with PowerShell:

```powershell
$cred = Get-Credential   # User: tenant_id@client_id  Password: client_secret
Send-MailMessage -SmtpServer relay.example.com -Port 8025 `
  -Credential $cred `
  -From noreply@example.com -To you@example.com `
  -Subject 'Relay test' -Body 'Relay test'
```

Or with [swaks](https://github.com/jetmore/swaks):

```bash
swaks --server relay.example.com:8025 \
  --auth-user 'tenant_id@client_id' --auth-password 'client_secret' \
  --from noreply@example.com --to you@example.com --body 'Relay test'
```


## Documentation

- [Installation](docs/installation/index.md) — Docker, Azure, Kubernetes, manual
- [Entra ID setup](docs/entra-id-setup/index.md) — app registration and sender restrictions
- [Configuration](docs/configuration.md) — environment variable reference
- [Client setup](docs/client-setup.md) — printers, NAS, firewalls, apps
- [Authentication](docs/authentication.md) — username formats and encoding
- [Azure Tables](docs/azure-tables.md) — central credential lookup
- [Architecture](docs/architecture/index.md) · [FAQ](docs/faq.md)

## Known limitations

- The Microsoft Graph `user: sendMail` endpoint always sends from the primary mailbox; alias addresses are not honored ([#80](https://github.com/JustinIven/smtp-oauth-relay/issues/80)).

## Support

- Bugs and feature requests: [GitHub Issues](https://github.com/justiniven/smtp-oauth-relay/issues)
- Pull requests welcome.

## License

Apache License 2.0 — see [LICENSE](./LICENSE).

Built with [aiosmtpd](https://aiosmtpd.aio-libs.org/), the [Microsoft Graph API](https://learn.microsoft.com/en-us/graph/), and the [Microsoft Identity Platform](https://learn.microsoft.com/en-us/entra/identity-platform/).
