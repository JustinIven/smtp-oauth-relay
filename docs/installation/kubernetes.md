# Kubernetes Deployment

The relay is stateless — run multiple replicas behind a `LoadBalancer` service. Deploy it with the [Helm chart](#helm-chart-recommended) or with [plain manifests](#plain-manifests).

The image runs as the unprivileged user `smtp-relay` (pinned UID/GID `10001`), so it works unchanged under a `restricted` Pod Security Standard.

## Helm chart (recommended)

The chart is published as an OCI artifact to `oci://ghcr.io/justiniven/charts/smtp-oauth-relay`. Each chart version matches the relay release. See the [chart README](https://github.com/JustinIven/smtp-oauth-relay/tree/main/charts/smtp-oauth-relay) for all values.

The chart needs a TLS certificate source. Choose one of the options below.

### TLS with cert-manager

Requires [cert-manager](https://cert-manager.io/) and an existing `Issuer` or `ClusterIssuer`. The chart creates a `Certificate`, mounts the issued secret, and the relay [reloads the renewed certificate](../configuration.md#tls) automatically.

`values.yaml`:

```yaml
tls:
  source: file
  certManager:
    enabled: true
    issuerRef:
      name: letsencrypt-prod
      kind: ClusterIssuer
    dnsNames:
      - smtp.example.com
```

```bash
helm install smtp-relay oci://ghcr.io/justiniven/charts/smtp-oauth-relay \
  --namespace smtp-relay --create-namespace -f values.yaml
```

!!! note "ACME issuers"
    SMTP is not HTTP, so Let's Encrypt issuers must use the **DNS-01** challenge to issue a certificate for the relay's hostname.

### TLS with an existing secret

```yaml
tls:
  source: file
  existingSecret:
    name: smtp-relay-certs
    certKey: tls.crt   # use cert.pem / key.pem for the secret from the manifest below
    keyKey: tls.key
```

### TLS from Key Vault with Azure Workload Identity

Requires [Azure Workload Identity](https://azure.github.io/azure-workload-identity/) on the cluster (on AKS, enable the OIDC issuer and workload identity). The same identity can also read [Azure Tables](../azure-tables.md).

1. Create a user-assigned managed identity and grant it `Key Vault Secrets User` (and `Storage Table Data Reader` if you use Azure Tables).
2. Add a federated credential for the service account:

    ```bash
    az identity federated-credential create \
      --name smtp-relay \
      --identity-name <identity-name> \
      --resource-group <resource-group> \
      --issuer "$(az aks show -n <cluster> -g <resource-group> --query oidcIssuerProfile.issuerUrl -o tsv)" \
      --subject system:serviceaccount:smtp-relay:smtp-relay-smtp-oauth-relay \
      --audiences api://AzureADTokenExchange
    ```

    The subject is `system:serviceaccount:<namespace>:<service account name>`. By default the service account is named `<release>-smtp-oauth-relay`; set `serviceAccount.name` to choose a different name.

3. Install with:

    ```yaml
    tls:
      source: keyvault
    azure:
      keyVault:
        url: https://my-keyvault.vault.azure.net/
        certName: smtp-relay-cert
    azureWorkloadIdentity:
      enabled: true
      clientId: <managed-identity-client-id>
    ```

The chart annotates the service account with `azure.workload.identity/client-id` and labels the pods with `azure.workload.identity/use: "true"`. New Key Vault certificate versions are picked up automatically.

### Common settings

```yaml
replicaCount: 3
config:
  logLevel: INFO
  serverGreeting: Example Corp SMTP Relay
service:
  type: LoadBalancer
  port: 25
  externalTrafficPolicy: Local   # preserve client IPs
  loadBalancerSourceRanges:
    - 10.0.0.0/8
  annotations:
    service.beta.kubernetes.io/azure-load-balancer-internal: "true"
extraEnv:
  - name: HTTPS_PROXY
    value: http://proxy.example.com:3128
```

Upgrade or uninstall:

```bash
helm upgrade smtp-relay oci://ghcr.io/justiniven/charts/smtp-oauth-relay -n smtp-relay -f values.yaml
helm uninstall smtp-relay -n smtp-relay
```

## Plain manifests

The manifest below includes a namespace, a TLS cert `Secret`, a config `ConfigMap`, a `Deployment`, and a `Service`. Adjust values to your environment.

### Basic deployment

`deployment.yaml`:

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
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        runAsGroup: 10001
        fsGroup: 10001
        seccompProfile:
          type: RuntimeDefault
      containers:
      - name: smtp-relay
        image: ghcr.io/justiniven/smtp-oauth-relay:1
        securityContext:
          allowPrivilegeEscalation: false
          readOnlyRootFilesystem: true
          capabilities:
            drop: ["ALL"]
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

### Optional: Azure Key Vault for TLS

To load TLS certificates from Key Vault instead of a `Secret`, update the ConfigMap:

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

Ensure the pod has managed identity with Key Vault access. With `readOnlyRootFilesystem: true`, also mount a writable `/tmp`, where the relay briefly writes the certificate it loads from Key Vault:

```yaml
spec:
  template:
    metadata:
      labels:
        azure.workload.identity/use: "true"
    spec:
      serviceAccountName: smtp-relay-sa
      containers:
      - name: smtp-relay
        volumeMounts:
        - name: tmp
          mountPath: /tmp
      volumes:
      - name: tmp
        emptyDir:
          medium: Memory
```

## Next steps

- [Configure the relay](../configuration.md)
- [Set up Entra ID](../entra-id-setup/index.md)
- [Configure your SMTP clients](../client-setup.md)
