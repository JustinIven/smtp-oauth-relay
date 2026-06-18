# Azure Deployment

## One-click deploy

[![Deploy to Azure](https://aka.ms/deploytoazurebutton)](https://portal.azure.com/#create/Microsoft.Template/uri/https%3A%2F%2Fraw.githubusercontent.com%2FJustinIven%2Fsmtp-oauth-relay%2Fmain%2Fazure_deployment%2Fdeployment.json)

Deploys an **Azure Container Instance** running the relay with a system-assigned managed identity. Optionally wires up Key Vault (TLS) and Table Storage (credential lookup).

**Prerequisites:** an Azure subscription and permission to create resources in a resource group.

After deployment:

1. Note the container instance **FQDN** — this is your relay hostname.
2. If you use Key Vault or Table Storage, grant the managed identity the matching role: `Key Vault Certificate User` and/or `Storage Table Data Reader`.
3. [Set up the Entra ID application](../entra-id-setup/index.md) and [configure your clients](../client-setup.md).

## Azure CLI

=== "Container instance"

    ```bash
    az group create --name smtp-relay-rg --location switzerlandnorth

    az container create \
      --resource-group smtp-relay-rg \
      --name smtprelay-01-ci \
      --image ghcr.io/justiniven/smtp-oauth-relay:1 \
      --os-type Linux \
      --assign-identity [system] \
      --ports 8025 --protocol TCP \
      --dns-name-label smtprelay-01-ci \
      --ip-address Public \
      --environment-variables \
        TLS_SOURCE=keyvault \
        REQUIRE_TLS=true \
        AZURE_KEY_VAULT_URL=https://your-keyvault.vault.azure.net/ \
        AZURE_KEY_VAULT_CERT_NAME=smtp-relay-cert
    ```

=== "Bicep"

    ```bash
    az deployment group create \
      --resource-group smtp-relay-rg \
      --template-file azure_deployment/deployment.bicep \
      --parameters location=switzerlandnorth
    ```

## Next steps

- [Configure the relay](../configuration.md)
- [Set up Entra ID](../entra-id-setup/index.md)
- [Configure your SMTP clients](../client-setup.md)
