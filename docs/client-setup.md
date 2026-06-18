# Client Setup

## Settings every client needs

| Setting | Value |
|---------|-------|
| Server / Host | Your relay hostname or IP |
| Port | `8025` (or your configured port) |
| Security | STARTTLS (when `REQUIRE_TLS=true`) |
| Authentication | Required — `LOGIN` or `PLAIN` |
| Username | `tenant_id@client_id` ([formats](authentication.md)) |
| Password | Application client secret |
| From address | A mailbox the app is [allowed to send from](entra-id-setup/index.md#restrict-the-sender-recommended) |

!!! tip
    Use **STARTTLS** on port 8025, not implicit SSL/TLS. If a device has a short username field or cannot set a From address, use [Base64URL UUIDs or an Azure Tables lookup](authentication.md#azure-tables-lookup).

## Device examples

The field names vary, but the values are always those above.

=== "Printers (HP, Canon, Epson…)"

    In the printer's web interface under **Email / SMTP Settings**:

    - SMTP Server: `relay.example.com`, Port `8025`, Encryption STARTTLS/TLS
    - Authentication: enabled, Username `tenant_id@client_id`, Password client secret
    - From Address: a permitted mailbox

=== "Synology"

    **Control Panel → Notification → Email**: Service Provider *Other*, SMTP server + port `8025`, Security STARTTLS, Authentication required, then the username/password above.

=== "QNAP"

    **System Settings → Notification Center → SMTP Server**: SMTP server + port `8025`, Security TLS, Authentication enabled, then the username/password above.

=== "Firewalls / appliances"

    Any device with SMTP alerting: server `relay.example.com:8025`, authentication enabled, TLS/STARTTLS enabled, credentials as above.

!!! note
    Using a client that isn't listed? Open an issue or PR to add it.

## Troubleshooting

| Symptom | Check |
|---------|-------|
| Connection refused | Relay running and reachable; firewall; correct port (`8025`) |
| TLS/SSL errors | Client supports STARTTLS; certificate valid; for self-signed certs, disable verification (testing only) |
| Authentication fails | Username format; secret not expired; TLS enabled when `REQUIRE_TLS=true`; check relay logs |
| Email not delivered | Sender address [permitted](entra-id-setup/index.md#restrict-the-sender-recommended); check Message Trace; recipient spam folder |
| Username too long | Use [Base64URL UUIDs or Azure Tables lookup](authentication.md#azure-tables-lookup) |

## Next steps

- [Authentication formats](authentication.md)
- [Azure Tables integration](azure-tables.md)
- [Configuration reference](configuration.md)
