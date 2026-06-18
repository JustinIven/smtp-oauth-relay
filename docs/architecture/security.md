# Security Architecture

This document describes the security model and threat mitigations of the SMTP OAuth Relay.

## Defense in Depth

The relay implements multiple layers of security:

1. **TLS Encryption**: Protects credentials in transit
2. **OAuth Authentication**: No user passwords stored or transmitted
3. **Application Permissions**: Centrally managed in Azure
4. **Application Access Policies**: Restrict sender addresses
5. **Managed Identities**: No stored credentials for Azure services

## Attack Surface

**Exposed**:

- SMTP port (8025)
- TLS certificate

**Protected**:

- Client secrets (known only to administrators and clients)
- OAuth tokens (short-lived, never logged)
- Azure credentials (managed identities)

## Threat Model

| Threat | Mitigation |
|--------|-----------|
| Credential theft | TLS encryption, no credentials in logs |
| Token theft | Short-lived tokens, TLS encryption |
| Unauthorized sending | RBAC for Applications |
| DoS attacks | Rate limiting (external), connection limits |
| MITM attacks | TLS with valid certificates |

## Best Practices

- :lock: **Always enable TLS** in production (`REQUIRE_TLS=true`)
- :key: **Rotate client secrets** before they expire
- :shield: **Use RBAC for Applications** to restrict sender addresses
- :cloud: **Use Managed Identities** for Azure Key Vault and Table Storage access
- :mag: **Monitor sign-in logs** in Microsoft Entra ID for anomalies
- :no_entry: **Never set `LOG_LEVEL=DEBUG`** in production — debug logs may contain sensitive information

## Next Steps

- [Design Decisions](design-decisions.md)
- [Architecture Overview](index.md)
- [Entra ID Setup — Restrict the sender](../entra-id-setup/index.md#restrict-the-sender-recommended)
