#Requires -Version 5.1

<#
.SYNOPSIS
    Creates and configures a Microsoft Entra ID application for use with the
    SMTP OAuth Relay.

.DESCRIPTION
    Automates the Entra ID / Exchange Online setup required by the SMTP OAuth
    Relay:

        1. Registers an application (single-tenant) with a client secret.
        2. Creates the service principal (enterprise application).
        3. Restricts the application to a single sender mailbox using RBAC for
           Applications:
             - Creates an Exchange management scope.
             - Registers the service principal in Exchange.
             - Assigns the 'Application Mail.Send' role limited to that scope.
           When -AllMailboxes is specified, this restriction is skipped and the
           Microsoft Graph 'Mail.Send' application permission is granted tenant
           wide instead.

    The script returns a PSCustomObject containing the resulting credentials
    and identifiers, and (unless -DisableSummaryOutput is set) also prints a
    human readable summary to the host.

    A Microsoft Graph session (Connect-MgGraph) with the appropriate permissions 
    (Application.ReadWrite.All and AppRoleAssignment.ReadWrite.All) and, unless 
    -AllMailboxes is used, an Exchange Online session (Connect-ExchangeOnline) must 
    already be established before running this script.

.PARAMETER DisplayName
    Display name for the Entra ID application registration.
    Defaults to "SMTP OAuth Relay".

.PARAMETER SenderAddress
    The UserPrincipalName (e.g. noreply@example.com) the application is allowed
    to send from. Required unless -AllMailboxes is specified.

.PARAMETER SecretValidYears
    Number of years the generated client secret remains valid (0-2).
    Defaults to 2.

.PARAMETER AllMailboxes
    Switch. When set, the mailbox restriction is skipped and the application can
    send from any mailbox in the tenant. Use only in trusted, isolated
    environments.

.PARAMETER ScopeName
    Name of the Exchange management scope to create. This must be unique within the tenant or the script will fail.
    Defaults to "<DisplayName> mailbox scope". Ignored when -AllMailboxes is set.

.PARAMETER TenantId
    Tenant ID used when building the SMTP username. Defaults to the tenant of
    the current Microsoft Graph session.

.PARAMETER DisableSummaryOutput
    Switch. Suppresses the human readable summary printed to the host. The
    result object is still returned to the pipeline.

.EXAMPLE
    .\New-RelayEntraApp.ps1 -DisplayName "SMTP OAuth Relay" -SenderAddress "noreply@example.com"

    Creates an application that may only send from noreply@example.com.

.EXAMPLE
    $app = .\New-RelayEntraApp.ps1 -DisplayName "SMTP Relay - HR" -SenderAddress "hr@example.com" -SecretValidYears 1
    $app.SmtpUsername
    $app.SmtpPassword

    Captures the returned credential object for further automation.

.EXAMPLE
    .\New-RelayEntraApp.ps1 -DisplayName "SMTP Relay - Lab" -AllMailboxes

    Creates an application that can send from any mailbox in the tenant.

.NOTES
    Requires the following PowerShell modules:
        - Microsoft.Graph (Applications, ServicePrincipals)
        - ExchangeOnlineManagement (unless -AllMailboxes is used)

    Required roles:
        - Application.ReadWrite.All and AppRoleAssignment.ReadWrite.All (Graph)
        - Exchange Administrator (unless -AllMailboxes is used)

    The client secret is only available at creation time. Store the returned
    SmtpPassword securely; it cannot be retrieved later.
#>

[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [Parameter(Mandatory = $false)]
    [ValidateNotNullOrEmpty()]
    [string]$DisplayName = "SMTP OAuth Relay",

    [Parameter(Mandatory = $false)]
    [ValidatePattern('^[^@\s]+@[^@\s]+\.[^@\s]+$')]
    [string]$SenderAddress,

    [Parameter(Mandatory = $false)]
    [ValidateRange(0, 2)]
    [int]$SecretValidYears = 2,

    [Parameter(Mandatory = $false)]
    [switch]$AllMailboxes,

    [Parameter(Mandatory = $false)]
    [string]$ScopeName = "$DisplayName mailbox scope",

    [Parameter(Mandatory = $false)]
    [string]$TenantId = (Get-MgContext).TenantId,

    [Parameter(Mandatory = $false)]
    [switch]$DisableSummaryOutput
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Well-known identifiers for Microsoft Graph.
$GraphAppId        = '00000003-0000-0000-c000-000000000000'
$MailSendAppRoleId = 'b633e1c5-b582-4048-a93e-9f11b44c7e96' # Mail.Send (application)

# Validate parameter combination.
if (-not $AllMailboxes -and [string]::IsNullOrWhiteSpace($SenderAddress)) {
    throw "SenderAddress is required unless -AllMailboxes is specified."
}



# Create the application registration with a client secret
Write-Verbose "Creating application registration '$DisplayName'..."
$secretEndDate = (Get-Date).AddYears($SecretValidYears)

$application = New-MgApplication `
    -DisplayName $DisplayName `
    -SignInAudience 'AzureADMyOrg' `
    -PasswordCredentials @(@{
        DisplayName = "Secret $(Get-Date -Format 'yyyy-MM-dd')"
        EndDateTime = $secretEndDate
    })

$clientSecret = $application.PasswordCredentials[0].SecretText


# Create the service principal (enterprise application)
Write-Verbose "Creating service principal..."
$servicePrincipal = New-MgServicePrincipal -AppId $application.AppId




if ($allMailboxes) {
    Write-Verbose "Skipping RBAC restriction; application can send from any mailbox."

    # Add Microsoft Graph 'Mail.Send' application permission to the app registration.
    Update-MgApplication `
        -ApplicationId $application.id `
        -RequiredResourceAccess @(@{
            ResourceAppId  = $GraphAppId
            ResourceAccess = @(@{
                Id   = $MailSendAppRoleId
                Type = 'Role'
            })
        })

    # 3. Grant tenant-wide admin consent for Mail.Send
    Write-Verbose "Granting admin consent for Mail.Send..."
    $graphServicePrincipalId = (Get-MgServicePrincipal -Filter "appId eq '$GraphAppId'").Id

    New-MgServicePrincipalAppRoleAssignment `
        -ServicePrincipalId $servicePrincipal.Id `
        -PrincipalId $servicePrincipal.Id `
        -ResourceId $graphServicePrincipalId `
        -AppRoleId $MailSendAppRoleId | Out-Null

} else {
    Write-Verbose "Restricting application to sender '$SenderAddress' via RBAC..."

    Start-Sleep -Seconds 10 # Wait for service principal to propagate in Exchange Online

    # Create a management scope limited to the sender address.
    New-ManagementScope `
        -Name $ScopeName `
        -RecipientRestrictionFilter "UserPrincipalName -eq '$SenderAddress'" | Out-Null
    
    # Register the application's service principal in Exchange.
    New-ServicePrincipal `
        -AppId $servicePrincipal.AppId `
        -ObjectId $servicePrincipal.Id `
        -DisplayName $DisplayName | Out-Null

    # Grant the Application Mail.Send role limited to the management scope.
    New-ManagementRoleAssignment `
        -App $servicePrincipal.AppId `
        -Role 'Application Mail.Send' `
        -CustomResourceScope $ScopeName | Out-Null
}



# Build result object
$result = [PSCustomObject]@{
    DisplayName        = $DisplayName
    TenantId           = $TenantId
    ClientId           = $application.AppId
    ClientSecret       = $clientSecret
    ApplicationObjectId      = $application.Id
    ServicePrincipalObjectId = $servicePrincipal.Id
    SmtpUsername       = "$($TenantId)@$($application.AppId)"
    SmtpPassword       = $clientSecret
    SenderAddress      = if ($AllMailboxes) { '(any mailbox)' } else { $SenderAddress }
    ManagementScope    = if ($AllMailboxes) { $null } else { $ScopeName }
    SecretExpires      = $secretEndDate
}

if (-not $DisableSummaryOutput) {
    # Human readable summary
    Write-Host "`n=== SMTP OAuth Relay Credentials ===" -ForegroundColor Cyan
    Write-Host "Display Name:   " -NoNewline; Write-Host $result.DisplayName -ForegroundColor Green
    Write-Host "Tenant ID:      " -NoNewline; Write-Host $result.TenantId -ForegroundColor Green
    Write-Host "Client ID:      " -NoNewline; Write-Host $result.ClientId -ForegroundColor Green
    Write-Host "Client Secret:  " -NoNewline; Write-Host $result.ClientSecret -ForegroundColor Green
    Write-Host "Secret Expires: " -NoNewline; Write-Host $result.SecretExpires.ToString('yyyy-MM-dd') -ForegroundColor Green
    Write-Host "Sender:         " -NoNewline; Write-Host $result.SenderAddress -ForegroundColor Green

    Write-Host "`n--- SMTP Settings ---" -ForegroundColor Cyan
    Write-Host "SMTP Username:  " -NoNewline; Write-Host $result.SmtpUsername -ForegroundColor Yellow
    Write-Host "SMTP Password:  " -NoNewline; Write-Host $result.SmtpPassword -ForegroundColor Yellow
    Write-Host "=== Save these credentials securely - the secret cannot be retrieved later! ===`n" -ForegroundColor Cyan
}


return $result
