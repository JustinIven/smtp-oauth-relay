# Installation and Deployment

This guide covers different methods to install and deploy the SMTP OAuth Relay.

## Table of Contents
- [Deploy to Azure](#deploy-to-azure)
- [Docker Deployment](#docker-deployment)
- [Docker Compose](#docker-compose)
- [Kubernetes Deployment](#kubernetes-deployment)
- [Azure Container Instances](#azure-container-instances)
- [Manual Installation](#manual-installation)

## Deploy to Azure

Click the button below to deploy the SMTP OAuth Relay to Azure Container Instances with a single click:

[![Deploy to Azure](https://aka.ms/deploytoazurebutton)](https://portal.azure.com/#create/Microsoft.Template/uri/https%3A%2F%2Fraw.githubusercontent.com%2FJustinIven%2Fsmtp-oauth-relay%2Fmain%2Fazure_deployment%2Fdeployment.json)

This will:
- Create an Azure Container Instance with the SMTP OAuth Relay
- Set up a managed identity for the container
- Create an Azure Storage Account and Table for configuration
- Assign Storage Table Data Reader to the managed identity
- Configure the relay with minimal settings and Azure Tables
- Optionally integrate with Azure Key Vault for TLS certificates

By default, the template disables TLS. To enable it, set `tlsSource=keyvault` and
provide `tlsCertKeyVaultUrl` and `tlsCertName`.

**Prerequisites:**
- An active Azure subscription
- Permissions to create resources in a resource group

**After deployment:**
1. Note the FQDN of the container instance
2. If using Key Vault for TLS, grant the managed identity access (`Key Vault Certificate User` or equivalent)
3. If you supplied `lookupTableUrl`, grant the managed identity `Storage Table Data Reader` on the target storage account
4. [Configure your Azure/Entra ID application](azure-setup.md)
5. [Configure your SMTP clients](client-setup.md)

For more control over the deployment, see the [Azure Container Instances](#azure-container-instances) section below.

## Docker Deployment

### Quick Start

The easiest way to run the SMTP OAuth Relay is via Docker:

```bash
docker run --name smtp-relay -p 8025:8025 \
  -v $(pwd)/certs:/usr/src/smtp-relay/certs \
  -e LOG_LEVEL=INFO \
  -e TLS_SOURCE=file \
  -e REQUIRE_TLS=true \
  ghcr.io/justiniven/smtp-oauth-relay:1
```

### With Environment File

Create an `.env` file with your configuration:

```bash
LOG_LEVEL=INFO
TLS_SOURCE=file
REQUIRE_TLS=true
SERVER_GREETING=My SMTP Relay
USERNAME_DELIMITER=@
```

Then run:

```bash
docker run --name smtp-relay -p 8025:8025 \
  -v $(pwd)/certs:/usr/src/smtp-relay/certs \
  --env-file .env \
  ghcr.io/justiniven/smtp-oauth-relay:1
```

### Building from Source

```bash
# Clone the repository
git clone https://github.com/justiniven/smtp-oauth-relay.git
cd smtp-oauth-relay

# Build the Docker image
docker build -t smtp-oauth-relay:local .

# Run the container
docker run --name smtp-relay -p 8025:8025 \
  -v $(pwd)/certs:/usr/src/smtp-relay/certs \
  -e LOG_LEVEL=INFO \
  smtp-oauth-relay:local
```

## Docker Compose

Create a `docker-compose.yml` file:

```yaml
version: '3.8'

services:
  smtp-relay:
    image: ghcr.io/justiniven/smtp-oauth-relay:1
    container_name: smtp-oauth-relay
    ports:
      - "8025:8025"
    volumes:
      - ./certs:/usr/src/smtp-relay/certs
    environment:
      - LOG_LEVEL=INFO
      - TLS_SOURCE=file
      - REQUIRE_TLS=true
      - SERVER_GREETING=Microsoft Graph SMTP OAuth Relay
      - USERNAME_DELIMITER=@
    restart: unless-stopped
```

Start the service:

```bash
docker-compose up -d
```

View logs:

```bash
docker-compose logs -f smtp-relay
```

## Azure Container Instances

Using Azure CLI:

```bash
# Create resource group
az group create --name smtp-relay-rg --location switzerlandnorth

# Create container instance with managed identity
az container create \
  --resource-group smtp-relay-rg \
  --name smtprelay-01-ci \
  --image ghcr.io/justiniven/smtp-oauth-relay:1 \
  --os-type Linux \
  --assign-identity [system] \
  --cpu 1 \
  --memory 1 \
  --ports 8025 \
  --protocol TCP \
  --dns-name-label smtprelay-01-ci \
  --ip-address Public \
  --environment-variables \
    LOG_LEVEL=INFO \
    TLS_SOURCE=keyvault \
    REQUIRE_TLS=true \
    AZURE_TABLES_URL=https://smtprelay1234.table.core.windows.net/users \
    AZURE_KEY_VAULT_URL=https://your-keyvault.vault.azure.net/ \
    AZURE_KEY_VAULT_CERT_NAME=smtp-relay-cert 
```

### Using Bicep Template

The repository includes Bicep templates for Azure deployment in the `azure_deployment/` directory:

```bash
# Deploy using the template
az deployment group create \
  --resource-group smtp-relay-rg \
  --template-file azure_deployment/deployment.bicep \
  --parameters location=switzerlandnorth

# Optional: use an existing table and enable TLS via Key Vault
# --parameters lookupTableUrl=https://storageaccount.table.core.windows.net/users \
#              tlsSource=keyvault \
#              tlsCertKeyVaultUrl=https://your-keyvault.vault.azure.net/ \
#              tlsCertName=smtp-relay-cert
```

## Kubernetes Deployment

### Basic Deployment

Create a `deployment.yaml`:

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: smtp-relay
---
apiVersion: v1
kind: Secret
metadata:
  name: smtp-relay-certs
  namespace: smtp-relay
type: Opaque
data:
  cert.pem: <base64-encoded-cert>
  key.pem: <base64-encoded-key>
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: smtp-relay-config
  namespace: smtp-relay
data:
  LOG_LEVEL: "INFO"
  TLS_SOURCE: "file"
  REQUIRE_TLS: "true"
  SERVER_GREETING: "Microsoft Graph SMTP OAuth Relay"
  USERNAME_DELIMITER: "@"
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: smtp-relay
  namespace: smtp-relay
spec:
  replicas: 2
  selector:
    matchLabels:
      app: smtp-relay
  template:
    metadata:
      labels:
        app: smtp-relay
    spec:
      containers:
      - name: smtp-relay
        image: ghcr.io/justiniven/smtp-oauth-relay:1
        ports:
        - containerPort: 8025
          name: smtp
        envFrom:
        - configMapRef:
            name: smtp-relay-config
        volumeMounts:
        - name: certs
          mountPath: /usr/src/smtp-relay/certs
          readOnly: true
        resources:
          requests:
            memory: "128Mi"
            cpu: "100m"
          limits:
            memory: "256Mi"
            cpu: "500m"
        livenessProbe:
          tcpSocket:
            port: 8025
          initialDelaySeconds: 10
          periodSeconds: 30
        readinessProbe:
          tcpSocket:
            port: 8025
          initialDelaySeconds: 5
          periodSeconds: 10
      volumes:
      - name: certs
        secret:
          secretName: smtp-relay-certs
---
apiVersion: v1
kind: Service
metadata:
  name: smtp-relay
  namespace: smtp-relay
spec:
  type: LoadBalancer
  ports:
  - port: 8025
    targetPort: 8025
    protocol: TCP
    name: smtp
  selector:
    app: smtp-relay
```

Deploy:

```bash
kubectl apply -f deployment.yaml
```

### With Azure Key Vault Integration

If using Azure Key Vault for TLS certificates:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: smtp-relay-config
  namespace: smtp-relay
data:
  LOG_LEVEL: "INFO"
  TLS_SOURCE: "keyvault"
  REQUIRE_TLS: "true"
  AZURE_KEY_VAULT_URL: "https://your-keyvault.vault.azure.net/"
  AZURE_KEY_VAULT_CERT_NAME: "smtp-relay-cert"
```

Ensure the pod has managed identity with Key Vault access:

```yaml
spec:
  template:
    metadata:
      labels:
        azure.workload.identity/use: "true"
    spec:
      serviceAccountName: smtp-relay-sa
```

## Manual Installation

### Prerequisites

- Python 3.11 or higher
- pip (Python package installer)
- OpenSSL (for certificate generation)

### Installation Steps

1. Clone the repository:

```bash
git clone https://github.com/justiniven/smtp-oauth-relay.git
cd smtp-oauth-relay
```

2. Create a virtual environment:

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Generate self-signed certificates (for testing):

```bash
mkdir -p certs
openssl req -x509 -newkey rsa:2048 -nodes \
  -keyout certs/key.pem -out certs/cert.pem -days 365 \
  -subj "/CN=localhost"
```

5. Set environment variables:

```bash
export LOG_LEVEL=INFO
export TLS_SOURCE=file
export REQUIRE_TLS=true
```

6. Run the server:

```bash
cd src
python main.py
```

### Running as a System Service (Linux)

Create a systemd service file at `/etc/systemd/system/smtp-relay.service`:

```ini
[Unit]
Description=SMTP OAuth Relay
After=network.target

[Service]
Type=simple
User=smtp-relay
WorkingDirectory=/opt/smtp-oauth-relay/src
Environment="LOG_LEVEL=INFO"
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

Enable and start the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable smtp-relay
sudo systemctl start smtp-relay
sudo systemctl status smtp-relay
```

## Next Steps

- [Configure the server](configuration.md)
- [Set up Azure/Entra ID](azure-setup.md)
- [Configure your SMTP clients](client-setup.md)
