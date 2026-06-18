# Design Decisions

| Decision | Chosen | Why |
|----------|--------|-----|
| SMTP server library | [aiosmtpd](https://aiosmtpd.readthedocs.io/) | Async, Python-native (matches the Graph integration), lightweight, easy to extend |
| OAuth flow | Client credentials | Server-to-server, no user interaction, application permissions, no redirect URIs or refresh tokens |
| State | Stateless | Trivial horizontal scaling and HA; trade-off is a token request per connection (no caching yet) |
| Graph payload | MIME via `sendMail` | Preserves all headers and formatting; works with any SMTP client |
| UUID encoding | UUID **and** Base64URL | Base64URL (22 chars) fits short username fields; standard UUID stays human-readable |

## Next steps

- [Security](security.md)
- [Architecture overview](index.md)
