# smtp-oauth-relay Helm chart

Deploys [SMTP OAuth Relay](https://github.com/JustinIven/smtp-oauth-relay), an SMTP relay that sends mail through Microsoft Graph using OAuth 2.0.

Full documentation: <https://justiniven.github.io/smtp-oauth-relay/installation/kubernetes/>

## Install

```bash
helm install smtp-relay oci://ghcr.io/justiniven/charts/smtp-oauth-relay \
  --namespace smtp-relay --create-namespace -f values.yaml
```

A TLS certificate source is required. Set `tls.source` and configure one of:

| `tls.source` | Configure | Notes |
|--------------|-----------|-------|
| `file` | `tls.certManager.enabled: true` | Creates a cert-manager `Certificate` from an existing `Issuer`/`ClusterIssuer`. |
| `file` | `tls.existingSecret.name` | Mounts an existing secret (default keys `tls.crt` / `tls.key`). |
| `keyvault` | `azure.keyVault.url`, `azure.keyVault.certName` | Typically combined with `azureWorkloadIdentity`. |
| `"off"` | — | Development only. Quote `"off"` in YAML. |

The certificate secret is mounted as a directory, so renewed certificates reach the pod. The relay reloads them every `config.tlsReloadInterval` seconds without a restart.

## Examples

cert-manager:

```yaml
tls:
  source: file
  certManager:
    enabled: true
    issuerRef:
      name: letsencrypt-prod   # must use a DNS-01 solver
      kind: ClusterIssuer
    dnsNames:
      - smtp.example.com
```

Key Vault with Azure Workload Identity:

```yaml
tls:
  source: keyvault
azure:
  keyVault:
    url: https://my-keyvault.vault.azure.net/
    certName: smtp-relay-cert
azureWorkloadIdentity:
  enabled: true
  clientId: 00000000-0000-0000-0000-000000000000
```

Create a federated credential on the identity with subject
`system:serviceaccount:<namespace>:<release>-smtp-oauth-relay`, or the value of `serviceAccount.name`.

More combinations are in [`ci/`](ci/).

## Values

| Key | Default | Description |
|-----|---------|-------------|
| `replicaCount` | `2` | Number of replicas. |
| `image.repository` | `ghcr.io/justiniven/smtp-oauth-relay` | Image repository. |
| `image.tag` | chart `appVersion` | Image tag. |
| `image.pullPolicy` | `IfNotPresent` | Image pull policy. |
| `imagePullSecrets` | `[]` | Pull secrets. |
| `nameOverride` / `fullnameOverride` | `""` | Override resource names. |
| `config.logLevel` | `WARNING` | `LOG_LEVEL`. |
| `config.serverGreeting` | `Microsoft Graph SMTP OAuth Relay` | `SERVER_GREETING`. |
| `config.usernameDelimiter` | `@` | `USERNAME_DELIMITER` (`@`, `:`, `\|`). |
| `config.requireTls` | `true` | `REQUIRE_TLS`. |
| `config.graphHttpTimeout` | `30` | `GRAPH_HTTP_TIMEOUT`. |
| `config.tlsCipherSuite` | `""` | `TLS_CIPHER_SUITE`. |
| `config.tlsReloadInterval` | `300` | `TLS_RELOAD_INTERVAL`; `0` disables certificate reloading. |
| `azure.keyVault.url` / `certName` | `""` | Key Vault certificate (`tls.source: keyvault`). |
| `azure.tables.url` | `""` | `AZURE_TABLES_URL`. |
| `azure.tables.partitionKey` | `user` | `AZURE_TABLES_PARTITION_KEY`. |
| `azure.tables.forceUsage` | `false` | `AZURE_TABLES_FORCE_USAGE`. |
| `tls.source` | `file` | `file`, `keyvault` or `"off"`. |
| `tls.mountPath` | `/etc/smtp-relay/tls` | Mount path of the certificate secret. |
| `tls.certManager.enabled` | `false` | Create a cert-manager `Certificate`. |
| `tls.certManager.issuerRef` | `{name: "", kind: ClusterIssuer, group: cert-manager.io}` | Existing issuer reference. |
| `tls.certManager.commonName` | `""` | Optional common name. |
| `tls.certManager.dnsNames` | `[]` | DNS names (at least one required). |
| `tls.certManager.ipAddresses` | `[]` | Optional IP SANs. |
| `tls.certManager.duration` / `renewBefore` | `""` | Certificate lifetime settings (cert-manager defaults). |
| `tls.certManager.privateKey` | `{algorithm: RSA, size: 2048, rotationPolicy: Always}` | Private key settings. |
| `tls.certManager.secretName` | `<fullname>-tls` | Name of the issued secret. |
| `tls.certManager.secretTemplate` | `{}` | Labels/annotations for the issued secret. |
| `tls.certManager.annotations` | `{}` | Annotations on the `Certificate`. |
| `tls.existingSecret.name` | `""` | Existing secret with the certificate and key. |
| `tls.existingSecret.certKey` / `keyKey` | `tls.crt` / `tls.key` | Keys inside the existing secret. |
| `serviceAccount.create` | `true` | Create a service account. |
| `serviceAccount.name` | `""` | Service account name. |
| `serviceAccount.annotations` | `{}` | Service account annotations. |
| `serviceAccount.automountServiceAccountToken` | `false` | Mount the Kubernetes API token. |
| `azureWorkloadIdentity.enabled` | `false` | Annotate the service account and label pods for Azure Workload Identity. |
| `azureWorkloadIdentity.clientId` | `""` | Managed identity / app registration client ID. |
| `azureWorkloadIdentity.tenantId` | `""` | Optional tenant ID. |
| `service.type` | `LoadBalancer` | `ClusterIP`, `NodePort` or `LoadBalancer`. |
| `service.port` | `8025` | Service port. |
| `service.annotations` / `labels` | `{}` | Service metadata. |
| `service.loadBalancerIP` | `""` | Static load balancer IP. |
| `service.loadBalancerSourceRanges` | `[]` | Allowed client CIDRs. |
| `service.externalTrafficPolicy` | `""` | `Local` preserves client source IPs. |
| `service.nodePort` | `null` | Fixed node port. |
| `gateway.enabled` | `false` | Expose the relay via Gateway API: creates a `ListenerSet` (TCP) and a `TCPRoute`. Requires the Gateway API CRDs and a Gateway that allows ListenerSets. Use with `service.type: ClusterIP`. |
| `gateway.parentRef.name` / `namespace` | `""` | Gateway to attach to (name required; namespace defaults to the release namespace). |
| `gateway.listener.name` / `port` | `smtp` / `8025` | Listener name and the port opened on the Gateway. |
| `gateway.annotations` | `{}` | Annotations on the `ListenerSet` and `TCPRoute`. |
| `podAnnotations` / `podLabels` | `{}` | Extra pod metadata. |
| `podSecurityContext` | UID/GID `10001`, `runAsNonRoot`, `RuntimeDefault` seccomp | Pod security context. |
| `securityContext` | read-only root FS, no privilege escalation, drop `ALL` | Container security context. |
| `resources` | `100m`/`128Mi` requests, `500m`/`256Mi` limits | Container resources. |
| `livenessProbe` / `readinessProbe` | TCP on `smtp` | Probes. |
| `nodeSelector` / `tolerations` / `affinity` | empty | Scheduling. |
| `priorityClassName` | `""` | Priority class. |
| `terminationGracePeriodSeconds` | `30` | Grace period. |
| `extraEnv` / `extraEnvFrom` | `[]` | Additional environment for the container. |
| `extraVolumes` / `extraVolumeMounts` | `[]` | Additional volumes and mounts. |
