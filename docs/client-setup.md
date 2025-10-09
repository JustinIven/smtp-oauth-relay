# Client Setup Guide

This guide shows how to configure various SMTP clients to work with the SMTP OAuth Relay.

## Table of Contents
- [General Configuration](#general-configuration)
- [Email Clients](#email-clients)
- [Programming Languages](#programming-languages)
- [Network Devices](#network-devices)
- [Applications](#applications)
- [Testing Tools](#testing-tools)

## General Configuration

All SMTP clients need these settings:

| Setting | Value |
|---------|-------|
| **Server/Host** | Your SMTP relay hostname or IP |
| **Port** | `8025` (or your configured port) |
| **Security** | STARTTLS / TLS (if `REQUIRE_TLS=true`) |
| **Authentication** | Required (LOGIN or PLAIN) |
| **Username** | `tenant_id@client_id` (see [Authentication Guide](authentication.md)) |
| **Password** | Your application's client secret |

### Important Notes

1. **Use STARTTLS, not SSL/TLS**: Most clients should use STARTTLS on port 8025, not implicit SSL/TLS
2. **Authentication is required**: The server always requires authentication
3. **Sender address restrictions**: May be enforced via Application Access Policies in Azure

## Network Devices

### Printers (HP, Canon, Epson, etc.)

Most network printers support SMTP for scan-to-email features:

1. Access printer's web interface (usually http://printer-ip)
2. Navigate to **Email/SMTP Settings**
3. Configure:
   - **SMTP Server**: smtp.example.com
   - **Port**: 8025
   - **Authentication**: Required/Enabled
   - **Username**: `tenant_id@client_id`
   - **Password**: client_secret
   - **Encryption**: TLS/STARTTLS
   - **From Address**: printer@example.com

**Note**: Some printers have limited username field length. Consider using base64url-encoded UUIDs or Azure Tables lookup if needed.

### NAS Devices (Synology, QNAP, etc.)

#### Synology

1. Go to **Control Panel** → **Notification** → **Email**
2. Configure:
   - **Service Provider**: Other
   - **SMTP Server**: smtp.example.com
   - **SMTP Port**: 8025
   - **Security**: STARTTLS
   - **Authentication Required**: Yes
   - **Username**: `tenant_id@client_id`
   - **Password**: client_secret

#### QNAP

1. Go to **System Settings** → **Notification Center** → **SMTP Server**
2. Configure:
   - **SMTP Server**: smtp.example.com
   - **Port**: 8025
   - **Security**: TLS
   - **Authentication**: Yes
   - **Username**: `tenant_id@client_id`
   - **Password**: client_secret

### Firewalls and Security Devices

Many firewalls send alert emails via SMTP. Configuration is similar:

- **Server**: smtp.example.com:8025
- **Authentication**: Enabled
- **TLS/STARTTLS**: Enabled
- **Credentials**: As described above

> [!NOTE]
> If you use the SMTP OAuth Relay with a client that is not on the list and you'd like to add it, please open an issue or submit a pull request. Help is always appreciated!

## Troubleshooting

### Connection Refused

- Verify the relay is running and accessible
- Check firewall rules
- Verify the port (default: 8025)

### TLS/SSL Errors

- Ensure client supports STARTTLS
- Verify certificate is valid (not expired, correct CN)
- For self-signed certificates, disable certificate verification in testing

### Authentication Failures

- Verify username format: `tenant_id@client_id`
- Check client secret hasn't expired
- Ensure TLS is enabled if `REQUIRE_TLS=true`
- Check server logs for detailed error messages

### Email Not Delivered

- Verify the sender address is allowed (check Application Access Policy)
- Check Microsoft Graph API permissions
- Review Exchange Online logs in Microsoft 365 admin center
- Check recipient's spam folder

### Client Doesn't Support Long Usernames

- Use base64url-encoded UUIDs (shorter)
- Or use Azure Tables lookup with short lookup IDs

## Next Steps

- [Authentication details](authentication.md)
- [Azure Tables integration](azure-tables.md)
