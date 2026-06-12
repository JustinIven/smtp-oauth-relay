# Azure/Entra ID Setup Guide

This guide explains how to set up Microsoft Entra ID (formerly Azure AD) for the
SMTP OAuth Relay using the provided `New-RelayEntraApp.ps1` script.

## Table of Contents
- [What the Script Does](#what-the-script-does)
- [Prerequisites](#prerequisites)
- [Running the Script](#running-the-script)
- [Parameters](#parameters)
- [Output](#output)
- [Next Steps](#next-steps)

## What the Script Does

The SMTP OAuth Relay uses the OAuth 2.0 Client Credentials flow to authenticate
with Microsoft Graph. The `New-RelayEntraApp.ps1` script automates the full
Entra ID and Exchange Online setup required to obtain a set of SMTP credentials:

1. **Registers an application** (single-tenant) in Entra ID with a client secret.
2. **Creates the service principal** (enterprise application) for that app.
3. **Restricts the sender address** so the application can only send from a
   single mailbox, using RBAC for Applications:
   - Creates an Exchange management scope limited to the sender address.
   - Registers the service principal in Exchange.
   - Assigns the `Application Mail.Send` role limited to that scope.

When run with `-AllMailboxes`, the restriction is skipped and the application is
granted the tenant-wide Microsoft Graph `Mail.Send` permission instead, allowing
it to send from any mailbox in the organization.

The script prints the resulting credentials and also returns them as an object
for further automation.

## Prerequisites

- **PowerShell** 5.1 or later
- **PowerShell modules**:
  - `Microsoft.Graph`
  - `ExchangeOnlineManagement` (not required when using `-AllMailboxes`)

  ```powershell
  Install-Module -Name Microsoft.Graph -Scope CurrentUser
  Install-Module -Name ExchangeOnlineManagement -Scope CurrentUser
  ```

- **Roles**:
  - Application Administrator or Global Administrator (Microsoft Graph)
  - Exchange Administrator (not required when using `-AllMailboxes`)

- **Active sessions** before running the script:

  ```powershell
  Connect-MgGraph -Scopes "Application.ReadWrite.All", "AppRoleAssignment.ReadWrite.All" -NoWelcome
  Connect-ExchangeOnline -ShowBanner:$false
  ```

## Running the Script

Download the script:

```powershell
Invoke-WebRequest `
  -Uri "https://raw.githubusercontent.com/JustinIven/smtp-oauth-relay/refs/heads/main/New-RelayEntraApp.ps1" `
  -OutFile "New-RelayEntraApp.ps1"
```

Run it with a restricted sender address (recommended):

```powershell
.\New-RelayEntraApp.ps1 -DisplayName "SMTP OAuth Relay" -SenderAddress "noreply@example.com"
```

Allow sending from any mailbox in the tenant (use only in trusted environments):

```powershell
.\New-RelayEntraApp.ps1 -DisplayName "SMTP OAuth Relay" -AllMailboxes
```

Capture the result for automation:

```powershell
$app = .\New-RelayEntraApp.ps1 -DisplayName "SMTP Relay - HR" -SenderAddress "hr@example.com"
$app.SmtpUsername
$app.SmtpPassword
```

## Parameters

| Parameter | Required | Default | Description |
| --- | --- | --- | --- |
| `-DisplayName` | No | `SMTP OAuth Relay` | Display name for the Entra ID application registration. |
| `-SenderAddress` | Yes* | – | UserPrincipalName the application is allowed to send from. *Required unless `-AllMailboxes` is specified. |
| `-SecretValidYears` | No | `2` | Number of years the client secret is valid (0–2). |
| `-AllMailboxes` | No | off | Skip the sender restriction and allow sending from any mailbox in the tenant. |
| `-ScopeName` | No | `<DisplayName> mailbox scope` | Name of the Exchange management scope. Ignored with `-AllMailboxes`. |
| `-TenantId` | No | current Graph session tenant | Tenant ID used when building the SMTP username. |
| `-DisableSummaryOutput` | No | off | Suppress the printed summary; the result object is still returned. |

## Output

The script prints a summary of the credentials and returns a `PSCustomObject`
with the following properties:

- `DisplayName`
- `TenantId`
- `ClientId`
- `ClientSecret`
- `ApplicationObjectId`
- `ServicePrincipalObjectId`
- `SmtpUsername`
- `SmtpPassword`
- `SenderAddress`
- `ManagementScope`
- `SecretExpires`

> **Important**: The client secret (`SmtpPassword`) is only available at creation
> time. Store it securely — it cannot be retrieved later.

## Next Steps

- [Configure authentication format](authentication.md)
- [Set up SMTP clients](client-setup.md)
- [Configure the relay server](configuration.md)
