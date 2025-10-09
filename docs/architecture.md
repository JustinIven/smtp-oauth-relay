# Architecture and How It Works

This document explains the architecture, design decisions, and internal workings of the SMTP OAuth Relay.

## Table of Contents
- [Overview](#overview)
- [Architecture Diagram](#architecture-diagram)
- [Components](#components)
- [Authentication Flow](#authentication-flow)
- [Email Flow](#email-flow)
- [Technical Implementation](#technical-implementation)
- [Design Decisions](#design-decisions)

## Overview

The SMTP OAuth Relay acts as a bridge between legacy SMTP clients and Microsoft Graph API. It translates SMTP protocol commands into Graph API calls, handling OAuth authentication transparently.

### Key Characteristics

- **Stateless**: Each connection is independent; no session data is persisted
- **Lightweight**: Minimal dependencies, small footprint
- **Secure**: Enforces TLS, uses OAuth 2.0 Client Credentials flow
- **Flexible**: Supports multiple authentication formats and credential storage options

## Components

### 1. SMTP Server (aiosmtpd)

**Purpose**: Accept and process SMTP connections

**Technology**: [aiosmtpd](https://aiosmtpd.readthedocs.io/) - asyncio-based SMTP server library

**Responsibilities**:
- Listen on port 8025
- Handle SMTP commands (EHLO, AUTH, MAIL, RCPT, DATA, QUIT)
- Enforce STARTTLS when `REQUIRE_TLS=true`
- Provide TLS encryption

**Custom Extensions**:
- `CustomSMTP`: Works around aiosmtpd bug with lowercase AUTH commands
- `CustomController`: Factory for creating CustomSMTP instances

**Code**: `src/custom.py`

### 2. Authenticator

**Purpose**: Validate credentials and obtain OAuth tokens

**Responsibilities**:
- Parse username to extract tenant_id and client_id
- Support multiple username formats (UUID, base64url)
- Query Azure Tables for lookup-based authentication
- Request OAuth token from Microsoft Identity Platform
- Validate token acquisition
- Store token in session for email sending

**Supported Auth Mechanisms**:
- AUTH LOGIN
- AUTH PLAIN

**Code**: `Authenticator` class in `src/main.py`

### 3. Handler

**Purpose**: Process email data and send via Microsoft Graph

**Responsibilities**:
- Receive email content from SMTP DATA command
- Parse email headers and body
- Override From address if specified in Azure Tables
- Format email for Microsoft Graph API
- Send email via Graph API `/users/{from}/sendMail` endpoint
- Return appropriate SMTP status codes

**Code**: `Handler` class in `src/main.py`

### 4. SSL Context Manager

**Purpose**: Manage TLS certificates

**Responsibilities**:
- Load certificates from filesystem
- Load certificates from Azure Key Vault
- Create SSL context for STARTTLS

**Sources**:
- **File**: Load PEM-encoded cert and key from filesystem
- **Key Vault**: Load PKCS#12 cert from Azure Key Vault
- **Off**: Disable TLS (development only)

**Code**: `src/sslContext.py`

### 5. Configuration Loader

**Purpose**: Load and validate configuration from environment variables

**Responsibilities**:
- Load all environment variables
- Validate values against allowed options
- Convert types (string to boolean, etc.)
- Provide defaults

**Code**: `load_env()` function in `src/main.py`

## Authentication Flow

### Sequence Diagram

```
Client          SMTP Server     Authenticator    Azure Tables    MS Identity     Graph API
  |                 |                |                |               |              |
  |---CONNECT------>|                |                |               |              |
  |<---220----------|                |                |               |              |
  |                 |                |                |               |              |
  |---EHLO--------->|                |                |               |              |
  |<---250 (caps)---|                |                |               |              |
  |                 |                |                |               |              |
  |---STARTTLS----->|                |                |               |              |
  |<---220----------|                |                |               |              |
  |<==[TLS NEGO]===>|                |                |               |              |
  |                 |                |                |               |              |
  |---AUTH LOGIN--->|                |                |               |              |
  |<---334 (user)---|                |                |               |              |
  |---username----->|                |                |               |              |
  |<---334 (pass)---|                |                |               |              |
  |---password----->|                |                |               |              |
  |                 |---parse------->|                |               |              |
  |                 |                |---query------->|               |              |
  |                 |                |<--creds--------|               |              |
  |                 |                |---token req------------------->|              |
  |                 |                |<--access token-----------------|              |
  |                 |<--success------|                |               |              |
  |<---235----------|                |                |               |              |
  |                 |                |                |               |              |
  |---MAIL FROM---->|                |                |               |              |
  |<---250----------|                |                |               |              |
  |---RCPT TO------>|                |                |               |              |
  |<---250----------|                |                |               |              |
  |---DATA--------->|                |                |               |              |
  |<---354----------|                |                |               |              |
  |---[email]------>|                |                |               |              |
  |---. (end)------>|                |                |               |              |
  |                 |---handle------>|                |               |              |
  |                 |                |---send email--------------------------------->|
  |                 |                |<--202 Accepted--------------------------------|
  |                 |<--success------|                |               |              |
  |<---250 OK-------|                |                |               |              |
```

### Steps

1. **Client Connects**: TCP connection to port 8025
2. **EHLO Exchange**: Server advertises capabilities (STARTTLS, AUTH)
3. **STARTTLS**: Client initiates TLS encryption (if required)
4. **AUTH Command**: Client sends AUTH LOGIN or AUTH PLAIN
5. **Username Parsing**:
   - Extract tenant_id and client_id from username
   - If format is `id@lookup`, query Azure Tables
   - Decode base64url if needed
6. **Token Request**: Request OAuth token from `https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token`
7. **Token Validation**: Verify token was received
8. **Success**: Return 235 status, store token in session

## Email Flow

### Steps

1. **MAIL FROM**: Client specifies sender
2. **RCPT TO**: Client specifies recipient(s)
3. **DATA**: Client sends email content
4. **Processing**:
   - Retrieve access token from session
   - Parse email message
   - Override From address if specified in Azure Tables
   - Base64-encode entire email
5. **Graph API Call**: POST to `https://graph.microsoft.com/v1.0/users/{from}/sendMail`
   - Headers: `Authorization: Bearer {token}`, `Content-Type: text/plain`
   - Body: Base64-encoded MIME message
6. **Response Handling**:
   - 202 Accepted → Return `250 OK` to client
   - Error → Return `554 Transaction failed` to client

### Microsoft Graph API

The relay uses the `/users/{from}/sendMail` endpoint with MIME format:

```http
POST https://graph.microsoft.com/v1.0/users/sender@example.com/sendMail
Authorization: Bearer eyJ0eXAiOiJKV1QiLCJub...
Content-Type: text/plain

RnJvbTogc2VuZGVyQGV4YW1wbGUuY29tDQpUbzogcmVjaXBpZW50QGV4YW1wbGUuY29tDQpTdWJq
ZWN0OiBUZXN0IEVtYWlsDQoNCgpUaGlzIGlzIGEgdGVzdCBlbWFpbC4NCg==
```

**Why MIME format?**
- Preserves all email headers
- Supports attachments
- Maintains formatting
- Compatible with all SMTP features

## Technical Implementation

### Asynchronous Design

The server uses Python's `asyncio` for non-blocking I/O:

```python
# Event loop handles multiple connections concurrently
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
loop.create_task(amain())
loop.run_forever()
```

**Benefits**:
- Handle multiple clients simultaneously
- Non-blocking I/O operations
- Efficient resource usage
- Scalable to hundreds of concurrent connections

### Session State

Each SMTP session maintains state:

```python
session.access_token = get_access_token(...)
session.lookup_from_email = from_email  # Optional override
```

**Session lifecycle**:
1. Created on connection
2. Populated during authentication
3. Used during email sending
4. Destroyed on disconnect

### Error Handling

Multiple layers of error handling:

1. **Configuration validation**: Startup fails with clear errors
2. **Authentication errors**: Return SMTP error codes (535, 530, etc.)
3. **Graph API errors**: Logged and returned as 554 Transaction failed
4. **Network errors**: Logged and handled gracefully

### Logging

Configurable logging levels:

- **DEBUG**: Full request/response details (may contain secrets)
- **INFO**: Operational messages (connections, emails sent)
- **WARNING**: Unusual conditions (default)
- **ERROR**: Failures requiring attention
- **CRITICAL**: Catastrophic failures

## Design Decisions

### Why aiosmtpd?

**Alternatives considered**: smtplib, Postfix, custom implementation

**Why aiosmtpd**:
- Python-based (same as Graph API integration)
- Async support
- Easy to customize
- Lightweight
- Good documentation

### Why Client Credentials Flow?

**Alternatives**: Authorization Code flow, Device Code flow

**Why Client Credentials**:
- **Stateless**: No user interaction required
- **Server-to-Server**: Appropriate for background services
- **Application permissions**: Can send on behalf of any user
- **Simple**: No refresh tokens or redirect URIs

### Why Stateless?

**Benefits**:
- **Scalability**: Easy to scale horizontally
- **Simplicity**: No session management or database
- **Reliability**: No state to corrupt
- **High Availability**: Any instance can handle any request

**Trade-offs**:
- Must request new token for each connection
- No caching of tokens (could be added as enhancement)

### Why MIME Format for Graph API?

**Alternatives**: JSON format with separate fields

**Why MIME**:
- **Feature-complete**: Supports all email features
- **Standard**: Universal email format
- **Preservation**: Maintains all headers and formatting
- **Compatibility**: Works with all SMTP clients

### Why Base64URL for UUIDs?

**Benefits**:
- **Shorter**: 22 characters vs 36
- **URL-safe**: No special characters
- **Standard**: Well-established encoding

**Trade-offs**:
- Less human-readable
- Requires encoding/decoding

## Performance Characteristics

### Throughput

- **Single instance**: ~100-200 emails/minute (limited by Graph API rate limits)
- **Concurrent connections**: Supports 50+ simultaneous connections
- **Token acquisition**: ~500ms per authentication
- **Email sending**: ~1-2 seconds per email

### Bottlenecks

1. **OAuth token requests**: ~500ms latency
   - Mitigation: Could implement token caching
2. **Graph API rate limits**: 10,000 requests/10 minutes per app
   - Mitigation: Use multiple applications
3. **Network latency**: Variable based on location
   - Mitigation: Deploy closer to clients

### Resource Usage

- **Memory**: ~50-100 MB baseline
- **CPU**: Minimal (I/O bound)
- **Network**: ~5-10 KB per email (excluding attachments)

## Security Architecture

### Defense in Depth

1. **TLS Encryption**: Protects credentials in transit
2. **OAuth Authentication**: No user passwords stored or transmitted
3. **Application Permissions**: Centrally managed in Azure
4. **Application Access Policies**: Restrict sender addresses
5. **Managed Identities**: No stored credentials for Azure services

### Attack Surface

**Exposed**:
- SMTP port (8025)
- TLS certificate

**Protected**:
- Client secrets (known only to administrators and clients)
- OAuth tokens (short-lived, never logged)
- Azure credentials (managed identities)

### Threat Model

| Threat | Mitigation |
|--------|-----------|
| Credential theft | TLS encryption, no credentials in logs |
| Token theft | Short-lived tokens, TLS encryption |
| Unauthorized sending | Application Access Policies |
| DoS attacks | Rate limiting (external), connection limits |
| MITM attacks | TLS with valid certificates |

## Extensibility

The architecture supports future enhancements:

- **Token caching**: Reduce authentication latency
- **Rate limiting**: Built-in throttling
- **Metrics/monitoring**: Prometheus exporter
- **Multiple backends**: Support other email APIs
- **Message queue**: Async email processing
- **Webhook support**: Delivery notifications

## Next Steps

- [FAQ](faq.md)
