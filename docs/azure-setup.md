# Azure/Entra ID Setup Guide

This guide walks you through setting up Microsoft Entra ID (formerly Azure AD) to work with the SMTP OAuth Relay.

## Table of Contents
- [Overview](#overview)
- [Creating an Application](#creating-an-application)
- [Configuring Permissions](#configuring-permissions)
- [Creating Client Secrets](#creating-client-secrets)
- [Restricting Sender Addresses](#restricting-sender-addresses)
- [PowerShell Setup Script](#powershell-setup-script)
- [Multiple Applications](#multiple-applications)

## Overview

The SMTP OAuth Relay uses OAuth 2.0 Client Credentials flow to authenticate with Microsoft Graph. Each application registration represents a set of credentials that can be used to send emails.

### Required Components

1. **Application Registration**: Represents the application in Entra ID
2. **Service Principal**: The application's identity in your tenant
3. **Application Permission**: `Mail.Send` permission to send emails
4. **Client Secret**: The password used for authentication
5. **Application Access Policy** (recommended): Restricts which mailboxes the app can send from

## Creating an Application

### Via Azure Portal

1. Sign in to the [Microsoft Entra admin center](https://portal.azure.com)

3. Select **App registrations** from the left menu

4. Click **New registration**

5. Configure the application:
   - **Name**: Enter a descriptive name (e.g., "SMTP OAuth Relay - Production")
   - **Supported account types**: Select "Accounts in this organizational directory only"
   - **Redirect URI**: Leave blank (not needed for client credentials flow)

6. Click **Register**

7. Note the following values from the Overview page:
   - **Application (client) ID**: This is your `client_id`
   - **Directory (tenant) ID**: This is your `tenant_id`

### Via PowerShell

```powershell
Connect-MgGraph -Scopes "Application.ReadWrite.All"

$app = New-MgApplication `
  -DisplayName "SMTP OAuth Relay" `
  -SignInAudience "AzureADMyOrg"

Write-Host "Application ID: $($app.AppId)"
Write-Host "Tenant ID: $((Get-MgContext).TenantId)"
```

## Configuring Permissions

The application needs the `Mail.Send` application permission to send emails on behalf of users.

### Via Azure Portal

1. In your app registration, select **API permissions**

2. Click **Add a permission**

3. Select **Microsoft Graph**

4. Select **Application permissions**

5. Search for and select **Mail.Send**

6. Click **Add permissions**

7. Click **Grant admin consent for [Your Organization]**
   - This step requires Global Administrator or Privileged Role Administrator privileges
   - The status should change to "Granted"

### Via PowerShell

```powershell
# Get the application
$app = Get-MgApplication -Filter "displayName eq 'SMTP OAuth Relay'"

# Get Microsoft Graph Service Principal
$graphSp = Get-MgServicePrincipal -Filter "appId eq '00000003-0000-0000-c000-000000000000'"

# Get Mail.Send permission ID
$mailSendPermission = $graphSp.AppRoles | Where-Object {$_.Value -eq "Mail.Send"}

# Add the permission to the application
Update-MgApplication `
  -ApplicationId $app.Id `
  -RequiredResourceAccess @{
    ResourceAppId = "00000003-0000-0000-c000-000000000000"
    ResourceAccess = @(
      @{
        Id = $mailSendPermission.Id
        Type = "Role"
      }
    )
  }

# Create service principal if it doesn't exist
$sp = Get-MgServicePrincipal -Filter "appId eq '$($app.AppId)'"
if (-not $sp) {
  $sp = New-MgServicePrincipal -AppId $app.AppId
}

# Grant admin consent
New-MgServicePrincipalAppRoleAssignment `
  -ServicePrincipalId $sp.Id `
  -PrincipalId $sp.Id `
  -ResourceId $graphSp.Id `
  -AppRoleId $mailSendPermission.Id
```

## Creating Client Secrets

### Via Azure Portal

1. In your app registration, select **Certificates & secrets**

2. Under **Client secrets**, click **New client secret**

3. Configure the secret:
   - **Description**: Enter a description (e.g., "Production secret 2025")
   - **Expires**: Select an appropriate expiration period
     - Recommended: 12 or 24 months for production
     - Note: You must rotate secrets before they expire

4. Click **Add**

5. **Important**: Copy the secret **Value** immediately
   - This is your `client_secret` (SMTP password)
   - It will never be shown again
   - Store it securely (e.g., in Azure Key Vault or a password manager)

### Via PowerShell

```powershell
$app = Get-MgApplication -Filter "displayName eq 'SMTP OAuth Relay'"

# Create a secret valid for 2 years
$passwordCred = Add-MgApplicationPassword `
  -ApplicationId $app.Id `
  -PasswordCredential @{
    DisplayName = "Secret created $(Get-Date -Format 'yyyy-MM-dd')"
    EndDateTime = (Get-Date).AddYears(2)
  }

Write-Host "Client Secret: $($passwordCred.SecretText)" -ForegroundColor Green
Write-Host "Save this value immediately - it cannot be retrieved later!"
```

### Secret Management Best Practices

- **Rotate secrets regularly**: Set calendar reminders before expiration
- **Use multiple secrets**: Create a new secret before deleting the old one to avoid downtime
- **Store securely**: Never commit secrets to source control
- **Use short expiration periods**: 12 months maximum for sensitive environments
- **Monitor expiration**: Use Azure Monitor or Microsoft 365 admin alerts

## Restricting Sender Addresses

By default, an application with `Mail.Send` permission can send email from any mailbox in the organization. You should restrict this using Application Access Policies.

### Prerequisites

- Exchange Online PowerShell module
- Exchange Administrator role

### Install Exchange Online Module

```powershell
Install-Module -Name ExchangeOnlineManagement -Scope CurrentUser
```

### Create an Application Access Policy

```powershell
# Connect to Exchange Online
Connect-ExchangeOnline

# Get your application ID
$appId = "your-application-client-id"

# Restrict to a single mailbox
New-ApplicationAccessPolicy `
  -AppId $appId `
  -PolicyScopeGroupId "sender@example.com" `
  -AccessRight RestrictAccess `
  -Description "SMTP Relay - Restrict to specific sender"
```

### Test the Policy

```powershell
# Test if a specific mailbox is allowed
Test-ApplicationAccessPolicy `
  -AppId $appId `
  -Identity "sender@example.com"

# Expected output:
# AccessCheckResult : Granted
# (or Denied if the mailbox is not allowed)
```

### List Existing Policies

```powershell
Get-ApplicationAccessPolicy | Format-Table AppId, PolicyScopeGroupId, AccessRight
```

### Remove a Policy

```powershell
Remove-ApplicationAccessPolicy -Identity "your-application-client-id"
```

## PowerShell Setup Script

Complete automated setup script:

```powershell
# Configuration
$appName = "SMTP OAuth Relay"
$appSecretEndDateTime = (Get-Date).AddYears(2) # More than 2 years is possible but not recommended
$senderAddress = "noreply@example.com"

# Connect to required services
Connect-MgGraph -Scopes "Application.ReadWrite.All" -NoWelcome
Connect-ExchangeOnline -ShowBanner:$false


# Create application
$application = New-MgApplication `
  -DisplayName $appName `
  -SignInAudience "AzureADMyOrg" `
  -PasswordCredentials @(@{
    DisplayName = "Secret $(Get-Date -Format 'yyyy-MM-dd')"
    EndDateTime = $appSecretEndDateTime
  }) `
  -RequiredResourceAccess @(@{
    ResourceAppId  = "00000003-0000-0000-c000-000000000000" # Microsoft Graph
    ResourceAccess = @(@{
        Id   = "b633e1c5-b582-4048-a93e-9f11b44c7e96" # Mail.Send
        Type = "Role"
      })
  })


# Create service principal
$servicePrincipal = New-MgServicePrincipal -AppId $application.AppId


# Grant tenant-wide admin consent
New-MgServicePrincipalAppRoleAssignment `
  -ServicePrincipalId $servicePrincipal.Id `
  -PrincipalId $servicePrincipal.Id `
  -ResourceId "7aeb2b66-3434-4d91-b79e-fe5f94c2634b" `
  -AppRoleId "b633e1c5-b582-4048-a93e-9f11b44c7e96" # Mail.Send


# Restrict the application to send emails only from specified sender addresses
New-ApplicationAccessPolicy `
  -AppId $application.appId `
  -PolicyScopeGroupId $senderAddress `
  -AccessRight RestrictAccess `
  -Description "Restrict the $appName application to send emails only from the specified sender addresses"


# Get tenant ID
$tenantId = (Get-MgContext).TenantId

# Display credentials
Write-Host "`n=== SMTP OAuth Relay Credentials ===" -ForegroundColor Cyan
Write-Host "Tenant ID: " -NoNewline
Write-Host $tenantId -ForegroundColor Green
Write-Host "Client ID: " -NoNewline
Write-Host $application.appId -ForegroundColor Green
Write-Host "Client Secret: " -NoNewline
Write-Host $application.passwordCredentials[0].secretText -ForegroundColor Green
Write-Host "`nSMTP Username: " -NoNewline
Write-Host "$($tenantId)@$($application.appId)" -ForegroundColor Yellow
Write-Host "SMTP Password: " -NoNewline
Write-Host $application.passwordCredentials[0].secretText -ForegroundColor Yellow
Write-Host "=== Save these credentials securely! ===" -ForegroundColor Cyan
```

## Multiple Applications

You can create multiple application registrations for different purposes:

### Use Cases

1. **Environment separation**: Different apps for dev, staging, production
2. **Department isolation**: Separate apps for different departments
3. **Sender restrictions**: Different apps for different sender addresses
4. **Security boundaries**: Separate apps for different security contexts

### Example: Multiple Departments

```powershell
# HR Department
$hrApp = New-MgApplication -DisplayName "SMTP Relay - HR"
# ...
New-ApplicationAccessPolicy `
  -AppId $hrApp.AppId `
  -PolicyScopeGroupId "hr@example.com" `
  -AccessRight RestrictAccess

# IT Department
$itApp = New-MgApplication -DisplayName "SMTP Relay - IT"
# ...
New-ApplicationAccessPolicy `
  -AppId $itApp.AppId `
  -PolicyScopeGroupId "it@example.com" `
  -AccessRight RestrictAccess
```

Each department uses their own credentials when connecting to the SMTP relay.

## Monitoring and Auditing

### View Sign-in Logs

1. Navigate to **Microsoft Entra ID** → **Sign-in logs**
2. Filter by your application name
3. Review authentication attempts and failures

### Enable Diagnostic Logs

```powershell
# Monitor Mail.Send API calls
# This requires Azure Monitor and Log Analytics workspace
```

### Set Up Alerts

1. Navigate to **Microsoft Entra ID** → **Monitoring** → **Alerts**
2. Create alerts for:
   - Failed authentication attempts
   - Expiring secrets (30 days before expiration)
   - Unusual sending patterns

## Troubleshooting

### "Admin consent required" Error

**Cause**: The `Mail.Send` permission requires admin consent.

**Solution**: A Global Administrator must grant consent in the Azure Portal.

### "AADSTS700016: Application not found"

**Cause**: The application ID doesn't exist or the service principal wasn't created.

**Solution**: Ensure both the application and service principal exist:
```powershell
Get-MgApplication -ApplicationId <app-object-id>
Get-MgServicePrincipal -Filter "appId eq '<client-id>'"
```

### Application Access Policy Not Working

**Cause**: Policy takes time to propagate or mailbox is not in the allowed group.

**Solution**: 
- Wait 15-30 minutes for policy propagation
- Test using `Test-ApplicationAccessPolicy`
- Verify mailbox is a member of the policy scope group

## Next Steps

- [Configure authentication format](authentication.md)
- [Set up SMTP clients](client-setup.md)
- [Configure the relay server](configuration.md)
