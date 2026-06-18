# Manual Installation

For running directly on a host without containers.

**Prerequisites:** Python 3.11+, `pip`, and OpenSSL (for test certificates).

## Steps

```bash
# 1. Clone and enter the repo
git clone https://github.com/justiniven/smtp-oauth-relay.git
cd smtp-oauth-relay

# 2. Create a virtual environment
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run the server
cd src
TLS_SOURCE=file REQUIRE_TLS=true python main.py
```

### Generate a self-signed certificate (testing)

```bash
mkdir -p certs
openssl req -x509 -newkey rsa:2048 -nodes \
  -keyout certs/key.pem -out certs/cert.pem -days 365 \
  -subj "/CN=localhost"
```

!!! warning
    Self-signed certificates are for testing only. Use a CA-issued certificate (e.g. Let's Encrypt) in production.

## Run as a systemd service (Linux)

`/etc/systemd/system/smtp-relay.service`:

```ini
[Unit]
Description=SMTP OAuth Relay
After=network.target

[Service]
Type=simple
User=smtp-relay
WorkingDirectory=/opt/smtp-oauth-relay/src
Environment="TLS_SOURCE=file"
Environment="REQUIRE_TLS=true"
Environment="TLS_CERT_FILEPATH=/opt/smtp-oauth-relay/certs/cert.pem"
Environment="TLS_KEY_FILEPATH=/opt/smtp-oauth-relay/certs/key.pem"
ExecStart=/opt/smtp-oauth-relay/venv/bin/python main.py
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now smtp-relay
sudo systemctl status smtp-relay
```

## Next steps

- [Configure the relay](../configuration.md)
- [Set up Entra ID](../entra-id-setup/index.md)
- [Configure your SMTP clients](../client-setup.md)
