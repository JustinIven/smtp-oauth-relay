# Entra ID Setup

The relay authenticates to Microsoft Graph with the OAuth 2.0 **client credentials** flow. You need one Entra ID application registration that provides:

| Component | Purpose |
|-----------|---------|
| Application (client) ID + Tenant ID | Form the SMTP **username** |
| Client secret | The SMTP **password** |
| `Application Mail.Send` role assignment, scoped to a mailbox (**recommended**) | Grants send rights *and* limits which mailboxes the app can send from |

!!! info "How send rights are granted"
    With **RBAC for Applications** (recommended) you do **not** add the `Mail.Send` Graph application permission to the app registration. Send rights come solely from the Exchange `New-ManagementRoleAssignment` below, scoped to a management scope — so the app can only send from the mailboxes in that scope.

    Only grant the tenant-wide `Mail.Send` Graph application permission if you deliberately want the app to send from **any** mailbox (the `-AllMailboxes` path).

## Recommended: the setup script

[`New-RelayEntraApp.ps1`](https://github.com/JustinIven/smtp-oauth-relay/blob/main/New-RelayEntraApp.ps1) performs the entire setup: registers the app, creates a secret and service principal, and grants scoped send rights via RBAC.

### Prerequisites

- PowerShell 5.1+
- Roles: **Application Administrator** (Graph) and **Exchange Administrator** (skip Exchange with `-AllMailboxes`)
- Modules and active sessions:

```powershell
Install-Module Microsoft.Graph -Scope CurrentUser
Install-Module ExchangeOnlineManagement -Scope CurrentUser   # not needed with -AllMailboxes

Connect-MgGraph -Scopes "Application.ReadWrite.All", "AppRoleAssignment.ReadWrite.All" -NoWelcome
Connect-ExchangeOnline -ShowBanner:$false
```

### Run it

```powershell
Invoke-WebRequest `
  -Uri "https://raw.githubusercontent.com/JustinIven/smtp-oauth-relay/main/New-RelayEntraApp.ps1" `
  -OutFile "New-RelayEntraApp.ps1"

# Restricted to one sender (recommended)
.\New-RelayEntraApp.ps1 -DisplayName "SMTP OAuth Relay" -SenderAddress "noreply@example.com"
```

??? example "Other invocations"
    ```powershell
    # Allow any mailbox — trusted/isolated tenants only (grants tenant-wide Mail.Send)
    .\New-RelayEntraApp.ps1 -DisplayName "SMTP OAuth Relay" -AllMailboxes

    # Capture the result for automation
    $app = .\New-RelayEntraApp.ps1 -DisplayName "SMTP Relay - HR" -SenderAddress "hr@example.com"
    $app.SmtpUsername
    $app.SmtpPassword
    ```

### Parameters

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `-DisplayName` | No | `SMTP OAuth Relay` | App registration display name |
| `-SenderAddress` | Yes* | – | Mailbox the app may send from. *Required unless `-AllMailboxes` |
| `-SecretValidYears` | No | `2` | Client secret lifetime in years (0–2) |
| `-AllMailboxes` | No | off | Skip sender restriction; grant tenant-wide `Mail.Send` |
| `-ScopeName` | No | `<DisplayName> mailbox scope` | Exchange management scope name |
| `-TenantId` | No | current session | Tenant ID used to build the SMTP username |
| `-DisableSummaryOutput` | No | off | Suppress printed summary (object still returned) |

The script prints the **SMTP username** (`tenant_id@client_id`) and **SMTP password** (client secret).

!!! danger "Save the secret now"
    The client secret is shown only at creation time and cannot be retrieved later.

## Manual setup (Azure Portal)

Use this only if you cannot run the script.

??? note "1. Register the application"
    1. [Entra admin center](https://entra.microsoft.com) → **App registrations** → **New registration**
    2. Name it, select **Accounts in this organizational directory only**, leave Redirect URI blank → **Register**
    3. From **Overview**, copy the **Application (client) ID** and **Directory (tenant) ID**

??? note "2. Create a client secret"
    1. **Certificates & secrets** → **New client secret**
    2. Set a description and expiry (12–24 months) → **Add**
    3. Copy the secret **Value** immediately — it is your SMTP password and cannot be retrieved later

After this, [grant scoped send rights](#restrict-the-sender-recommended). Do **not** add the `Mail.Send` API permission on the app registration — the management role assignment grants it instead.

### Restrict the sender (recommended)

Grant the app the `Application Mail.Send` role, scoped to a mailbox, with **RBAC for Applications** in Exchange Online. This is what gives the app permission to send — no app-level `Mail.Send` API permission or admin consent is required.

```powershell
Connect-ExchangeOnline

$appId = "<application-client-id>"

New-ManagementScope -Name "SMTP relay scope" `
  -RecipientRestrictionFilter "UserPrincipalName -eq 'noreply@example.com'"

New-ServicePrincipal -AppId $appId -ObjectId "<service-principal-object-id>" -DisplayName "SMTP OAuth Relay"

New-ManagementRoleAssignment -App $appId -Role "Application Mail.Send" `
  -CustomResourceScope "SMTP relay scope"
```

To allow a group of mailboxes, point `-RecipientRestrictionFilter` at a group membership filter, e.g. `MemberOfGroup -eq '<group-DN>'`.

!!! note
    Role assignments can take 15–30 minutes to propagate.

??? note "Legacy: Application Access Policy"
    Older tenants may still use Application Access Policies (superseded by RBAC for Applications). This approach **does** require the tenant-wide `Mail.Send` Graph application permission with admin consent, then restricts it:

    ```powershell
    New-ApplicationAccessPolicy -AppId $appId `
      -PolicyScopeGroupId "sender@example.com" `
      -AccessRight RestrictAccess `
      -Description "SMTP Relay - restrict sender"

    # Test
    Test-ApplicationAccessPolicy -AppId $appId -Identity "sender@example.com"

    # List / remove
    Get-ApplicationAccessPolicy | Format-Table AppId, PolicyScopeGroupId, AccessRight
    Remove-ApplicationAccessPolicy -Identity $appId
    ```

## Multiple applications

Create one app per environment, department, or sender to keep credentials and sending scopes isolated. Each app is a separate SMTP username/password pair.

## Next steps

- [Authentication formats](../authentication.md)
- [Client setup](../client-setup.md)
- [Configuration reference](../configuration.md)
