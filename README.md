# UDX Conversational BI POC

## Architecture
```
M365 Copilot Chat → Copilot Studio → APIM (public) → Foundry Agent (private) → APIM → Microsoft Learn MCP
```

## Key Design: Standalone Foundry (No Hub)

This POC uses the **new standalone Foundry project model** (`Microsoft.CognitiveServices/accounts` with `kind: AIServices` and `allowProjectManagement: true`). There is **no AI Hub, no Storage Account, and no Key Vault** — the Foundry resource and its child project are self-contained.

- **Foundry resource**: `Microsoft.CognitiveServices/accounts@2025-06-01` (kind `AIServices`)
- **Foundry project**: `Microsoft.CognitiveServices/accounts/projects@2025-06-01` (child resource)
- **Model deployment**: `gpt-41` (gpt-4.1), child of the Foundry account

## Project Structure
```
infra/
  main.bicep                  # All Azure infrastructure (IaC)
  main.parameters.json        # Deployment parameters (location=eastus2)
scripts/
  create_agent.py             # Creates Foundry agent via AzureOpenAI SDK
  update_apim_policy.py       # Updates APIM invoke-agent policy with agent ID
  configure_apim_vnet.ps1     # Post-deploy: APIM outbound VNet integration
  configure_vnet2.py          # Python alternative for VNet integration
docs/
  copilot-studio-setup.md     # Manual steps for Copilot Studio
```

## Deployed Resources (rgUDXConvBI, eastus2)
| Resource | Name | Type | Network |
|----------|------|------|---------|
| VNet (10.0.0.0/16) | udxcbi-vnet-* | Virtual Network | 2 subnets |
| NSG | udxcbi-apim-nsg-* | Network Security Group | APIM subnet |
| Foundry (AI Services) | udxcbi-foundry-* | CognitiveServices/accounts | Private (PNA disabled) |
| Foundry Project | udxcbi-proj-* | CognitiveServices/accounts/projects | Inherits from parent |
| gpt-4.1 Deployment | gpt-41 | Model deployment | — |
| APIM Standard v2 | udxcbi-apim-* | API Management | Public gateway |
| Private DNS Zone | privatelink.cognitiveservices.azure.com | DNS | Linked to VNet |
| Private DNS Zone | privatelink.openai.azure.com | DNS | Linked to VNet |
| Private Endpoint | udxcbi-foundry-pe-* | Network | Foundry (groupId: account) |
| RBAC Role Assignment | — | Cognitive Services OpenAI User | APIM MI → Foundry |

### Subnets
| Subnet | CIDR | Delegation | Purpose |
|--------|------|------------|---------|
| apim-integration-subnet | 10.0.1.0/24 | Microsoft.Web/serverFarms | APIM outbound VNet integration |
| private-endpoints-subnet | 10.0.2.0/24 | — | Private endpoints |

## Agent Details
- **Assistant ID**: `asst_DTDTErUlSCNAsdk9hyezeAjJ`
- **Model**: `gpt-41` (gpt-4.1)
- **Endpoint**: `https://udxcbi-foundry-rqtovkuobfzg2.openai.azure.com/`
- **APIM Endpoint**: `POST https://udxcbi-apim-rqtovkuobfzg2.azure-api.net/udx/foundry/invoke`
- **APIM routes** to Assistants API (`/openai/threads/runs`) using managed identity auth

## Deployment Steps

### 1. Deploy infrastructure
```bash
az deployment group create \
  --resource-group rgUDXConvBI \
  --template-file infra/main.bicep \
  --parameters infra/main.parameters.json \
  --name udxconvbi-deploy-v2b
```

### 2. Create the Foundry agent
Temporarily enable public network access, create the agent, then re-lock:
```bash
# Enable PNA
az resource update --ids "<foundry-resource-id>" \
  --set properties.networkAcls.defaultAction=Allow properties.publicNetworkAccess=Enabled \
  --api-version 2025-06-01

# Create agent
python scripts/create_agent.py

# Re-lock PNA
az resource update --ids "<foundry-resource-id>" \
  --set properties.networkAcls.defaultAction=Deny properties.publicNetworkAccess=Disabled \
  --api-version 2025-06-01
```

### 3. Update APIM policy with agent ID
Edit the assistant ID in `scripts/update_apim_policy.py`, then:
```bash
python scripts/update_apim_policy.py
```

### 4. Configure APIM VNet integration (optional)
```bash
python scripts/configure_vnet2.py
```

### 5. Copilot Studio (manual)
Follow [docs/copilot-studio-setup.md](docs/copilot-studio-setup.md).

## What's Automated vs Manual
| Component | Method |
|-----------|--------|
| All Azure infrastructure | Bicep IaC (`infra/main.bicep`) |
| Foundry agent creation | Python script (`scripts/create_agent.py`, AzureOpenAI SDK) |
| APIM APIs, backends, policies | Bicep IaC + Python script for policy update |
| APIM VNet integration | Post-deploy script (`scripts/configure_vnet2.py`) |
| Copilot Studio agent | **Manual** (no IaC/API available) |
