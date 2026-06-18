# Authentication

How the relay maps SMTP credentials to an OAuth token.

## Flow

1. Client connects and issues `STARTTLS` (required when `REQUIRE_TLS=true`).
2. Client sends `AUTH LOGIN` or `AUTH PLAIN`.
3. The relay parses the username into `tenant_id` and `client_id`.
4. The relay requests an OAuth token from Microsoft Entra ID using the client secret (the SMTP password).
5. On success it accepts the message and forwards it via Microsoft Graph `sendMail`.

![Authentication Flow](images/sequenceDiagram.svg)

## Username format

```
<tenant_id><delimiter><client_id>
```

- **delimiter** — `@` by default ([`USERNAME_DELIMITER`](configuration.md#general)); also `:` or `|`.
- **password** — always the application **client secret**.
- **optional TLD** — anything after the first `.` is ignored, so `client_id.local` works for clients that demand an `@domain.tld` username.

```text
# Standard UUIDs
12345678-1234-1234-1234-123456789abc@abcdefab-1234-5678-abcd-abcdefabcdef

# With a .local suffix for picky clients
12345678-1234-1234-1234-123456789abc@abcdefab-1234-5678-abcd-abcdefabcdef.local
```

## UUID encoding

The relay accepts each ID as either a standard hyphenated UUID (36 chars) or a **Base64URL-encoded** form (22 chars, no padding) for clients with short username fields. Decoding is automatic — no configuration needed.

=== "Generate (Python)"

    ```python
    import base64, uuid
    u = uuid.UUID('12345678-1234-1234-1234-123456789abc')
    print(base64.urlsafe_b64encode(u.bytes).decode().rstrip('='))
    # -> EjRWeBI0EjQSNBI0VnirzQ
    ```

=== "Generate (Bash)"

    ```bash
    python -c "import base64,uuid;print(base64.urlsafe_b64encode(uuid.UUID('12345678-1234-1234-1234-123456789abc').bytes).decode().rstrip('='))"
    ```

## Azure Tables lookup

For devices with username length limits or no custom From address, store credentials in Azure Tables and authenticate with a short ID:

```text
Username: app1@lookup
Password: <client secret>
```

The relay detects `@lookup`, queries the table for `RowKey=app1`, and uses the stored `tenant_id`/`client_id`. See [Azure Tables Integration](azure-tables.md).

## Supported AUTH mechanisms

| Mechanism | Supported | Notes |
|-----------|-----------|-------|
| `AUTH LOGIN` | :material-check: | Username/password requested separately |
| `AUTH PLAIN` | :material-check: | Base64 `\0user\0pass` |
| `CRAM-MD5` / `DIGEST-MD5` | :material-close: | Require a shared secret |
| `XOAUTH2` | :material-close: | Not needed — the relay handles OAuth internally |

!!! note "TLS first"
    With `REQUIRE_TLS=true`, authentication before `STARTTLS` is rejected with `530 5.7.0 Must issue a STARTTLS command first`.

## Test authentication

=== "Python"

    ```python
    import smtplib
    with smtplib.SMTP('smtp.example.com', 8025) as s:
        s.starttls()
        s.login('tenant_id@client_id', 'client_secret')
        print('OK')
    ```

=== "swaks"

    ```bash
    swaks --server smtp.example.com:8025 --tls \
      --auth-user 'tenant_id@client_id' --auth-password 'client_secret' \
      --from sender@example.com --to recipient@example.com --body 'Test'
    ```

=== "openssl"

    ```bash
    openssl s_client -starttls smtp -connect smtp.example.com:8025
    # then: EHLO test.local / AUTH LOGIN / base64(username) / base64(password)
    ```

## Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| `Invalid username format` | Missing/duplicate delimiter | Match `USERNAME_DELIMITER`; format `tenant_id@client_id` |
| `AADSTS700016: Application not found` | Wrong tenant/client ID or no service principal | Verify IDs; ensure the service principal exists |
| `AADSTS7000215: Invalid client secret` | Wrong or expired secret | Recreate the client secret |
| `Must issue a STARTTLS command first` | `REQUIRE_TLS=true`, no TLS | Enable STARTTLS on the client |
| Base64URL decode fails | Bad encoding | Use `urlsafe_b64encode`, strip `=` padding |

## Next steps

- [Configure SMTP clients](client-setup.md)
- [Azure Tables integration](azure-tables.md)
- [FAQ](faq.md)
