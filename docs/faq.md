# Frequently Asked Questions (FAQ)

Common questions and answers about the SMTP OAuth Relay.

## General Questions

### What is the SMTP OAuth Relay?

The SMTP OAuth Relay is a bridge that allows legacy SMTP-only clients (printers, scanners, applications, etc.) to send email through Microsoft 365 / Exchange Online using OAuth 2.0 authentication instead of traditional username/password credentials.

### Why do I need this?

Microsoft is deprecating Basic Authentication (username/password) for SMTP. Legacy devices and applications that can't support OAuth directly need a relay to continue sending email through Microsoft 365.

### How does it work?

1. Your legacy client connects via SMTP with special credentials (tenant ID + client ID + client secret)
2. The relay obtains an OAuth token from Microsoft Entra ID
3. The relay sends your email via Microsoft Graph API
4. Exchange Online delivers the email normally

See [Architecture](architecture.md) for detailed explanation.

### Is this an official Microsoft product?

No, this is an open-source community project. It uses official Microsoft APIs (Microsoft Graph and Microsoft Identity Platform).

### What are the alternatives?

- **Native OAuth support**: Upgrade clients to support OAuth (best option, not always possible)
- **Microsoft 365 High Volume Email**: Designed for high-volume scenarios, but has specific requirements and limitations (still in preview)
- **Azure Communication Services**: Azure Service for sending emails programmatically, has its own pricing and setup
- **SendGrid/other services**: Third-party email services
- **Exchange Hybrid**: Complex on-premises setup

## Compatibility

### What SMTP clients are supported?

Any client that supports:
- SMTP protocol (RFC 5321)
- AUTH LOGIN or AUTH PLAIN authentication
- STARTTLS / TLS (recommended)

### Can I use this with Gmail, Outlook.com, or other providers?

No. This relay is specifically designed for Microsoft 365 / Exchange Online using Microsoft Graph API. It only works with:
- Microsoft 365 (Office 365)
- Exchange Online
- Microsoft Entra ID (Azure AD) authenticated tenants

### Does this work with on-premises Exchange?

No. This requires Exchange Online and Microsoft Graph API. On-premises Exchange should use native SMTP relay.

### What about shared mailboxes?

Yes, shared mailboxes work if:
1. The application has Mail.Send permission
2. An Application Access Policy grants access to the shared mailbox
3. You specify the shared mailbox address as the sender

### Can I send to external recipients?

Yes, as long as:
- Your Exchange Online tenant allows external email
- Recipient addresses are valid
- Your tenant's spam filters allow the message

## Configuration

### Can I change the port from 8025?

Yes, but requires modifying the code or container port mapping:

```bash
# Docker port mapping (external:internal)
docker run -p 587:8025 ... smtp-relay

# Or modify main.py to change internal port
```

### Can I use a different delimiter instead of `@`?

Yes, set `USERNAME_DELIMITER` to `:` or `|`:

```bash
USERNAME_DELIMITER=:
# Username format becomes: tenant_id:client_id
```

### Can I use this without TLS?

Not recommended for production, but for development:

```bash
TLS_SOURCE=off
REQUIRE_TLS=false
```

**Never disable TLS in production** - credentials would be sent unencrypted.

### How many client applications can I have?

Unlimited. You can:
- Create multiple Entra ID applications (one per department, device, etc.)
- Use the same application for multiple devices
- Mix and match based on your security requirements

### Can I restrict which addresses can send?

Yes, using Application Access Policies in Exchange Online:

```powershell
New-ApplicationAccessPolicy `
  -AppId <your-app-id> `
  -PolicyScopeGroupId "allowed-senders@example.com" `
  -AccessRight RestrictAccess
```

See [Azure Setup Guide](azure-setup.md) for details.

## Azure Tables

### What is Azure Tables integration?

Optional feature that lets you store credential mappings in Azure Table Storage, allowing short, memorable usernames instead of long UUIDs.

**Without Azure Tables**:
```
Username: 12345678-1234-1234-1234-123456789abc@abcdefab-1234-5678-abcd-abcdefabcdef
```

**With Azure Tables**:
```
Username: printer1@lookup
```

See [Azure Tables Integration](azure-tables.md) for setup.

### Do I need Azure Tables?

No, it's optional. Use it if:
- Your devices have username length limits
- You want centralized credential management
- You need to override sender addresses

### Are client secrets stored in Azure Tables?

No. The table only stores tenant IDs and client IDs (not secrets). The client secret is still provided as the SMTP password.

## Security

### Is this secure?

Yes, when configured properly:
- **TLS encryption**: Protects credentials in transit
- **OAuth authentication**: No user passwords involved
- **Application permissions**: Centrally managed in Azure
- **Short-lived tokens**: Tokens expire quickly
- **Audit logging**: All activity logged in Azure

### Can someone steal my credentials?

Client secrets should be protected like passwords:
- Store in secure vaults
- Never commit to source control
- Rotate regularly
- Use TLS for transmission

### What if my client secret is compromised?

1. Immediately rotate the secret in Azure
2. Update all legitimate clients
3. Review audit logs for unauthorized activity
4. Consider creating a new application

### Should I use self-signed certificates?

Only for development/testing. Production should use certificates from a trusted Certificate Authority (Let's Encrypt, DigiCert, etc.).

## Performance

### How many emails can I send?

Limited by:
1. **Graph API rate limits**: ~10,000 requests per 10 minutes per application
2. **Exchange Online limits**: Varies by license (typically 10,000/day per mailbox)
3. **Relay performance**: Handles 200+ emails/minute per instance

For high volume, use multiple applications or consider Azure Communication Services.

### Is there any delay in email delivery?

Small overhead (~1-2 seconds) for:
- OAuth token acquisition (~500ms)
- Graph API call (~500ms)
- Network latency

After the relay accepts the email, delivery time depends on Exchange Online (typically seconds to minutes).

### Can I run multiple instances?

Yes! The relay is stateless and can be:
- Scaled horizontally behind a load balancer
- Run in multiple regions
- Deployed in Kubernetes with multiple replicas

## Troubleshooting

### Why am I getting "Authentication failed"?

Common causes:
1. **Wrong credentials**: Verify tenant ID, client ID, and client secret
2. **Expired secret**: Check expiration date in Azure
3. **Missing permissions**: Ensure Mail.Send permission granted
4. **No service principal**: Create service principal for the application

### Why aren't emails being delivered?

Check:
1. **Application Access Policy**: May be blocking sender
2. **Spam folder**: Email might be filtered
3. **Exchange Online limits**: May have hit sending limits
4. **Server logs**: Check for error messages

Use Microsoft 365 Message Trace to track emails.

### Why is authentication slow?

OAuth token acquisition takes ~500ms. If using Azure Tables, add query time. Consider:
- Using direct UUID format (bypass Azure Tables)
- Deploying closer to Azure region
- Implementing token caching (future feature)

### How do I enable debug logging?

```bash
LOG_LEVEL=DEBUG
```

**Warning**: Debug logs may contain sensitive information. Never share publicly without redacting secrets.

## Cost

### How much does this cost to run?

**Azure costs** (if using Azure services):
- **Container Apps**: ~$30-50/month for small instance
- **Key Vault**: ~$0.03 per 10,000 operations
- **Table Storage**: ~$0.05/GB/month + $0.00015 per 10k transactions
- **Bandwidth**: Typically minimal for email

**Self-hosted costs**: Only infrastructure (Docker host, certificates, etc.)

**Microsoft 365**: No additional cost, uses existing licenses

### Is there a free tier?

**Azure**: Free tier available for some services, but typically need paid tier for production

**Self-hosted**: Run on any infrastructure (Docker, VM, on-premises)

**Microsoft 365**: Included with existing licenses

## Deployment

### Can I run this on-premises?

Yes, as long as it can reach:
- Microsoft Identity Platform (login.microsoftonline.com)
- Microsoft Graph API (graph.microsoft.com)
- Azure services (if using Key Vault or Tables)

An inbound internet access and a public port (default: 8025) are required.

### Can I run in Kubernetes?

Yes, see [Installation Guide](installation.md) for Kubernetes examples.

### What about high availability?

Options:
1. **Multiple replicas**: Run 2+ instances behind load balancer
2. **Auto-scaling**: Scale based on connection count
3. **Multiple regions**: Deploy in different Azure regions
4. **Health checks**: Implement liveness/readiness probes

The relay is stateless, making HA easy.

### Can I use Docker Compose?

Yes, see [Installation Guide](installation.md) for docker-compose example.

## Monitoring

### How do I monitor the relay?

**Application logs**:
```bash
docker logs smtp-relay -f
```

**Azure Monitor**:
- Sign-in logs in Entra ID
- Graph API logs
- Container metrics

**Metrics to track**:
- Authentication success/failure rate
- Email send volume
- Response times
- Error rates

### How do I know if emails are being sent?

1. **Server logs**: Look for "Email sent successfully" messages
2. **Azure AD sign-in logs**: Check application sign-ins
3. **Message Trace**: Use Microsoft 365 admin center
4. **Test emails**: Send to known address

### Can I get alerts for failures?

Yes, set up Azure Monitor alerts for:
- High authentication failure rate
- Email send failures
- Certificate expiration
- High error rates

## Compliance

### Is this HIPAA/SOC2/ISO27001 compliant?

The relay itself doesn't store or log sensitive data. Compliance depends on your deployment:
- Use TLS for encryption
- Deploy in compliant infrastructure
- Follow security best practices
- Implement proper access controls

### What about GDPR?

The relay:
- Doesn't store personal data
- Doesn't log email content
- Processes email addresses transiently
- Can be deployed in EU regions

### Are emails encrypted?

- **In transit to relay**: TLS encryption (if enabled)
- **In transit to Microsoft**: HTTPS (always)
- **At rest in Exchange**: Microsoft's encryption

## Customization

### Can I modify the code?

Yes! It's open source (Apache 2.0 license). Fork and customize as needed.

### Can I add custom authentication?

Yes, modify the `Authenticator` class in `main.py`.

### Can I support other email providers?

Possible, but requires significant changes to use different APIs (not just Graph API).

### Can I add custom logging?

Yes, Python's logging framework is used. Add custom handlers as needed.

## Support

### Where can I get help?

1. **Documentation**: Read these docs thoroughly
2. **GitHub Issues**: Report bugs or ask questions

### How do I report a bug?

Create an issue on GitHub with:
- Environment details
- Configuration (redact secrets)
- Error messages
- Steps to reproduce

### How do I request a feature?

Create a GitHub issue with:
- Use case description
- Expected behavior
- Why it's useful

### Can I contribute?

Yes! Contributions welcome:
- Bug fixes
- New features
- Documentation improvements
- Testing

## Future Plans

### What features are planned?

Potential future enhancements:
- Built-in rate limiting
- Prometheus metrics endpoint
- Multiple Graph API endpoint support

### Will there be breaking changes?

The project follows semantic versioning:
- **Major versions** (X.0.0): May have breaking changes
- **Minor versions** (0.X.0): New features, backwards compatible
- **Patch versions** (0.0.X): Bug fixes

### How stable is this?

The project is actively maintained and used in production. It's based on stable Microsoft APIs (Graph API, Identity Platform).

## License

### What license is this under?

Apache License 2.0 - free to use, modify, and distribute.

### Can I use this commercially?

Yes, Apache 2.0 allows commercial use.

### Do I need to credit the project?

Not required, but appreciated!

## Next Steps

- [Get started with installation](installation.md)
- [Set up Azure/Entra ID](azure-setup.md)
- [Configure your clients](client-setup.md)
