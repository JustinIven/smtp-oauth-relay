# Kubernetes Deployment

The relay is stateless — run multiple replicas behind a `LoadBalancer` service. The manifest below includes a namespace, a TLS cert `Secret`, a config `ConfigMap`, a `Deployment`, and a `Service`. Adjust values to your environment.

## Basic deployment

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

## Optional: Azure Key Vault for TLS

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

## Next steps

- [Configure the relay](../configuration.md)
- [Set up Entra ID](../entra-id-setup/index.md)
- [Configure your SMTP clients](../client-setup.md)
