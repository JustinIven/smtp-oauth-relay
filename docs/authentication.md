# Authentication Guide

This guide explains how authentication works with the SMTP OAuth Relay and how to format credentials.

## Table of Contents
- [Authentication Flow](#authentication-flow)
- [Username Format](#username-format)
- [UUID Encoding](#uuid-encoding)
- [Azure Tables Lookup](#azure-tables-lookup)
- [Supported AUTH Mechanisms](#supported-auth-mechanisms)
- [Security Considerations](#security-considerations)

## Authentication Flow

The SMTP OAuth Relay uses a unique authentication model:

```
1. Client connects to SMTP server
2. Client initiates STARTTLS (if TLS is required)
3. Client sends AUTH command with credentials
4. Server parses username to extract tenant_id and client_id
5. Server requests OAuth token from Microsoft identity platform
6. If successful, server accepts connection
7. Client sends email via DATA command
8. Server forwards email via Microsoft Graph API
```

### Sequence Diagram

![Authentication Flow](images/sequenceDiagram.svg)

## Username Format

The username encodes the Azure tenant and application information needed to obtain an OAuth token.

### Basic Format

```
<tenant_id><delimiter><client_id>
```

**Components**:
- `tenant_id`: Your Azure tenant UUID
- `delimiter`: Configured separator character (default: `@`)
- `client_id`: Your application's client UUID

### With Optional TLD

To satisfy clients that require an `@domain.tld` format:

```
<tenant_id><delimiter><client_id>.tld
```

The `.tld` portion (anything after the first dot) is ignored by the server.

### Examples

With `@` delimiter (default):
```
12345678-1234-1234-1234-123456789abc@abcdefab-1234-5678-abcd-abcdefabcdef
```

With `.local` TLD for compatibility:
```
12345678-1234-1234-1234-123456789abc@abcdefab-1234-5678-abcd-abcdefabcdef.local
```

With `:` delimiter:
```
12345678-1234-1234-1234-123456789abc:abcdefab-1234-5678-abcd-abcdefabcdef
```

### Password

The password is always the **client secret** created in Entra ID.

## UUID Encoding

The server accepts UUIDs in two formats:

### 1. Standard UUID Format

Standard hyphenated UUID string:
```
12345678-1234-1234-1234-123456789abc
```

**Advantages**:
- Human-readable
- Standard format
- Easy to copy from Azure Portal

**Disadvantages**:
- Longer (36 characters)
- Contains hyphens that some clients may not handle well

### 2. Base64URL Encoded Format

UUIDs can be encoded to a shorter, URL-safe format:

```
EjRWeBI0EjQSNBI0VnirzQ
```

**Advantages**:
- Shorter (22 characters)
- No special characters except safe ones
- More compact for storage

**Disadvantages**:
- Not human-readable
- Requires encoding/decoding

### Generating Base64URL Encoded UUIDs

#### Python

```python
import base64
import uuid

# Your UUID from Azure
tenant_uuid = uuid.UUID('12345678-1234-1234-1234-123456789abc')
client_uuid = uuid.UUID('abcdefab-1234-5678-abcd-abcdefabcdef')

# Encode to base64url (remove padding)
tenant_b64 = base64.urlsafe_b64encode(tenant_uuid.bytes).decode().rstrip('=')
client_b64 = base64.urlsafe_b64encode(client_uuid.bytes).decode().rstrip('=')

print(f"Tenant: {tenant_b64}")
print(f"Client: {client_b64}")
print(f"Username: {tenant_b64}@{client_b64}")
```

#### Bash (one-liner)

```bash
# Replace with your tenant UUID
python -c "import base64, uuid; u = uuid.UUID('12345678-1234-1234-1234-123456789abc'); print(base64.urlsafe_b64encode(u.bytes).decode().rstrip('='))"
```

### Decoding

The server automatically detects and decodes base64url-encoded UUIDs. No special configuration is needed.

## Azure Tables Lookup

For simplified credential management, you can use Azure Tables to store credentials centrally. This is particularly useful for devices or applications that have a restriction on username length or don't allow for a separate sender address.

### Lookup Username Format

```
<lookup_id>@lookup
```

When the server sees `@lookup` as the client portion, it queries Azure Tables for the actual credentials.

### Example

**Azure Table Entry**:
| PartitionKey | RowKey | tenant_id | client_id | from_email |
|--------------|---------|-----------|-----------|------------|
| user | app1 | 12345678-... | abcdefab-... | app1@example.com |

**SMTP Username**: `app1@lookup`

**SMTP Password**: Client secret (as usual)

When authenticating:
1. Server sees `app1@lookup`
2. Server queries Azure Tables for RowKey=`app1`
3. Server retrieves `tenant_id` and `client_id`
4. Server requests OAuth token using retrieved values

See [Azure Tables Integration](azure-tables.md) for setup details.

## Supported AUTH Mechanisms

The server supports two SMTP authentication mechanisms:

### AUTH PLAIN

Simple authentication mechanism where credentials are sent base64-encoded in a single string.

**Client Example**:
```
AUTH PLAIN AGFwcDFAbG9va3VwAG15LXNlY3JldA==
```

Where the base64 decodes to: `\0app1@lookup\0my-secret`

### AUTH LOGIN

Interactive authentication where username and password are requested separately.

**Client Exchange**:
```
C: AUTH LOGIN
S: 334 VXNlcm5hbWU6
C: YXBwMUBsb29rdXA=
S: 334 UGFzc3dvcmQ6
C: bXktc2VjcmV0
S: 235 2.7.0 Authentication successful
```

### Not Supported

- **AUTH CRAM-MD5**: Not supported (requires shared secret)
- **AUTH DIGEST-MD5**: Not supported (deprecated)
- **AUTH XOAUTH2**: Not needed (the relay handles OAuth internally)

## Security Considerations

### TLS Requirement

By default, the server requires TLS before accepting authentication (`REQUIRE_TLS=true`).

**Without TLS**:
```
C: AUTH PLAIN AGFwcDFAbG9va3VwAG15LXNlY3JldA==
S: 530 5.7.0 Must issue a STARTTLS command first
```

**With TLS**:
```
C: STARTTLS
S: 220 Ready to start TLS
[TLS negotiation]
C: AUTH PLAIN AGFwcDFAbG9va3VwAG15LXNlY3JldA==
S: 235 2.7.0 Authentication successful
```

### Client Secret Protection

- **Never hardcode secrets** in application code
- **Use environment variables** or secure configuration storage
- **Rotate secrets regularly** (before expiration)
- **Use different secrets** for different environments

### Username Privacy

The username (tenant_id@client_id) is not particularly sensitive:
- Tenant IDs are often public knowledge
- Client IDs are visible in many Azure resources
- The client secret is what must be protected

However, using base64url encoding adds a layer of obfuscation if desired.

### Authentication Failures

Failed authentication attempts are logged (level depends on `LOG_LEVEL`):

```
WARNING - Unsupported auth mechanism: CRAM-MD5
ERROR - Invalid username format. Expected format: tenant_id@client_id
ERROR - Authentication failed: AADSTS700016: Application not found
```

### Rate Limiting

The server does not implement rate limiting itself, but:
- Microsoft identity platform has rate limits on token requests
- Exchange Online has rate limits on email sending

## Testing Authentication

### Using OpenSSL

```bash
# Connect to server
openssl s_client -starttls smtp -connect smtp.example.com:8025

# After connection
EHLO test.local

# Start authentication
AUTH LOGIN
# Server responds with: 334 VXNlcm5hbWU6
# Send base64-encoded username
YXBwMUBsb29rdXA=
# Server responds with: 334 UGFzc3dvcmQ6
# Send base64-encoded password
bXktc2VjcmV0
# Server responds with: 235 2.7.0 Authentication successful
```

### Using Python

```python
import smtplib

# Configuration
smtp_host = 'smtp.example.com'
smtp_port = 8025
username = 'tenant_id@client_id'
password = 'client_secret'

# Connect and authenticate
with smtplib.SMTP(smtp_host, smtp_port) as server:
    server.starttls()
    server.login(username, password)
    print("Authentication successful!")
```

### Using swaks

```bash
# Install swaks (Swiss Army Knife for SMTP)
apt-get install swaks  # Debian/Ubuntu
brew install swaks      # macOS

# Test authentication
swaks \
  --to recipient@example.com \
  --from sender@example.com \
  --server smtp.example.com:8025 \
  --auth-user 'tenant_id@client_id' \
  --auth-password 'client_secret' \
  --tls \
  --body 'Test email'
```

## Troubleshooting

### "Invalid username format"

**Cause**: Username doesn't contain the delimiter or is malformed.

**Solution**: 
- Check delimiter configuration (`USERNAME_DELIMITER`)
- Ensure format is: `tenant_id@client_id`
- Verify no extra spaces or characters

### "Authentication failed: AADSTS700016"

**Cause**: Application (client) ID doesn't exist or isn't in the specified tenant.

**Solution**:
- Verify tenant ID is correct
- Verify client ID is correct
- Ensure application exists in the tenant
- Check if service principal was created

### "Authentication failed: AADSTS7000215"

**Cause**: Invalid client secret.

**Solution**:
- Verify the client secret hasn't expired
- Check for typos in the secret
- Create a new secret if needed

### "Must issue a STARTTLS command first"

**Cause**: `REQUIRE_TLS=true` but client didn't initiate TLS.

**Solution**:
- Configure client to use STARTTLS or TLS
- Or set `REQUIRE_TLS=false` (not recommended for production)

### Base64URL Decoding Fails

**Cause**: Invalid base64url encoding or non-UUID data.

**Solution**:
- Verify the UUID was encoded correctly
- Check for padding characters (should not have `=`)
- Ensure using `urlsafe_b64encode`, not standard base64

## Next Steps

- [Configure SMTP clients](client-setup.md)
- [Set up Azure Tables](azure-tables.md)
- [FAQ](faq.md)
