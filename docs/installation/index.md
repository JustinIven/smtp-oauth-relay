# Installation

Pick the deployment method that fits your environment. All methods run the same container/image and read the same [environment variables](../configuration.md).

| Method | Best for | Complexity |
|--------|----------|------------|
| [Docker](docker.md) | Quick setup, small deployments | Low |
| [Azure](azure.md) | Azure-native, one-click deploy | Low–Medium |
| [Kubernetes](kubernetes.md) | Scalable production workloads | Medium |
| [Manual](manual.md) | Full control, custom hosts | Medium |

## Requirements

**Required**

- Docker, Kubernetes, or Python 3.11+ (manual)
- Outbound network access to `login.microsoftonline.com` and `graph.microsoft.com`
- An [Entra ID application](../entra-id-setup/index.md) (client secret + scoped send rights)
- A TLS certificate for production

**Optional**

- Azure Key Vault — TLS certificate storage ([config](../configuration.md#tls))
- Azure Table Storage — central credential lookup ([guide](../azure-tables.md))
- Managed Identity — passwordless access to the Azure services above

## After installing

1. [Set up Entra ID](../entra-id-setup/index.md)
2. [Configure the relay](../configuration.md)
3. [Configure your SMTP clients](../client-setup.md)
