# FAQ

## What does it do?

Lets legacy SMTP-only clients send mail through Microsoft 365 using OAuth 2.0 (client credentials) and the Microsoft Graph API, instead of deprecated Basic Authentication. The relay obtains a token from Entra ID and posts the message to Graph `sendMail`. It is a community open-source project that uses official Microsoft APIs — not a Microsoft product.

## Compatibility

**Which clients work?** Anything that speaks SMTP (RFC 5321) with `AUTH LOGIN` or `AUTH PLAIN` and STARTTLS.

**Which mail backends?** Microsoft 365 / Exchange Online only. It does **not** work with Gmail, Outlook.com, or on-premises Exchange.

**Shared mailboxes?** Yes, if the app has `Mail.Send`, an RBAC role assignment grants access to the mailbox (Application Access Policies don't cover this), and you send from the shared mailbox address.

**External recipients?** Yes, if your tenant allows external mail.

## Configuration

**Change the port from 8025?** Remap it at the container/host level, e.g. `docker run -p 587:8025 …`.

**Different username delimiter?** Set `USERNAME_DELIMITER` to `:` or `|`.

**Run without TLS?** Only for local development (`TLS_SOURCE=off`, `REQUIRE_TLS=false`). Never in production — credentials would be sent in clear text.

**How many client apps?** Unlimited. Use one app per device, department, or environment as needed.

**Restrict who can send?** Yes — use [RBAC for Applications](entra-id-setup/index.md#restrict-the-sender-recommended) to scope an app to specific mailboxes.

## Azure Tables

**What is it?** Optional [credential lookup](azure-tables.md) so devices use a short `id@lookup` username instead of full UUIDs.

**Are secrets stored there?** No. The table holds only tenant and client IDs. The client secret is still the SMTP password.

**Do I need it?** No — use it for short usernames, central management, or sender-address overrides.

## Security

**Is it secure?** With TLS enabled and secrets protected: credentials travel encrypted, no user passwords are involved, tokens are short-lived, and all sign-ins are audited in Entra ID.

**If a client secret leaks?** Rotate it in Azure, update legitimate clients, and review sign-in/audit logs. Create a new app if needed.

**Self-signed certificates?** Testing only. Use a CA-issued certificate (e.g. Let's Encrypt) in production.

## Operations

**Throughput?** Roughly 100–200 emails/minute per instance; bounded by Graph API (~10,000 requests / 10 min per app) and Exchange Online sending limits. Use multiple apps for higher volume.

**Run multiple instances?** Yes — the relay is stateless. Scale horizontally behind a load balancer (see [Kubernetes](installation/kubernetes.md)).

**Run on-premises?** Yes, with outbound access to `login.microsoftonline.com` and `graph.microsoft.com`, plus an inbound public port (default 8025).

**Enable debug logging?** `LOG_LEVEL=DEBUG`. Debug logs may contain sensitive data — don't use in production or share unredacted.

## Cost & license

**Cost?** Free and self-hosted; uses your existing Microsoft 365 licenses. If hosted on Azure you pay for the chosen services (Container Instances/Apps, optional Key Vault and Table Storage).

**License?** Apache 2.0 — free for commercial use; attribution appreciated but not required.

## Getting help

Read these docs, then open a [GitHub issue](https://github.com/justiniven/smtp-oauth-relay/issues) for bugs or feature requests (include environment details, redacted config, errors, and repro steps). Pull requests are welcome.

## Next steps

- [Install](installation/index.md)
- [Set up Entra ID](entra-id-setup/index.md)
- [Configure your clients](client-setup.md)
