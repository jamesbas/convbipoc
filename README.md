# UDX Conversational BI POC

## Architecture

### Path A — APIM Bridge (original)
```
M365 Copilot Chat → Copilot Studio → APIM (public) → Foundry Agent (private) → APIM → Microsoft Learn MCP
```

### Path B — Azure Function Bridge (alternative)
```
M365 Copilot Chat → Copilot Studio → Azure Function (public, Entra ID auth) → Foundry Agent (private)
```

## Key Design: Standalone Foundry (No Hub)

This POC uses the **new standalone Foundry project model** (`Microsoft.CognitiveServices/accounts` with `kind: AIServices` and `allowProjectManagement: true`). There is **no AI Hub, no Storage Account, and no Key Vault** — the Foundry resource and its child project are self-contained.

- **Foundry resource**: `Microsoft.CognitiveServices/accounts@2025-06-01` (kind `AIServices`)
- **Foundry project**: `Microsoft.CognitiveServices/accounts/projects@2025-06-01` (child resource)
- **Model deployment**: `gpt-41` (gpt-4.1), child of the Foundry account

## Project Structure
```
infra/
  main.bicep                  # Path A: APIM + Foundry infrastructure (IaC)
  main.parameters.json        # Parameters for main.bicep (location=eastus2)
  function-app.bicep          # Path B: Azure Function bridge infrastructure (IaC)
  function-app.parameters.json # Parameters for function-app.bicep
function-app/
  function_app.py             # Azure Function: Foundry bridge endpoint
  requirements.txt            # Python dependencies
  host.json                   # Functions runtime config
  local.settings.json         # Local dev settings
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
| function-integration-subnet | 10.0.3.0/24 | Microsoft.Web/serverFarms | Function App outbound VNet integration (Path B) |

## Agent Details
- **Assistant ID**: `asst_DTDTErUlSCNAsdk9hyezeAjJ`
- **Model**: `gpt-41` (gpt-4.1)
- **Endpoint**: `https://udxcbi-foundry-rqtovkuobfzg2.openai.azure.com/`
- **APIM Endpoint**: `POST https://udxcbi-apim-rqtovkuobfzg2.azure-api.net/udx/foundry/invoke`
- **APIM routes** to Assistants API (`/openai/threads/runs`) using managed identity auth

---

## Path B — Azure Function Bridge

An alternative to APIM that uses an Azure Function App as the public-to-private bridge with **Entra ID pass-through authentication**.

### Why use the Function approach?
- Richer request/response shaping (correlation IDs, conversation mapping, timeout handling)
- Native Entra ID Easy Auth — caller identity flows through to the Function code
- Simpler VNet integration (no gateway configConnections API issues)
- Built-in Application Insights telemetry

### Additional Resources (Path B only)
| Resource | Name | Type |
|----------|------|------|
| App Service Plan | udxcbi-asp-* | Elastic Premium (EP1, Linux) |
| Function App | udxcbi-func-* | Python 3.11, VNet-integrated |
| Storage Account | udxcbist* | Required by Functions runtime |
| Application Insights | udxcbi-ai-* | Telemetry |
| Log Analytics | udxcbi-law-* | App Insights backend |
| RBAC | — | Cognitive Services OpenAI User (Function MI → Foundry) |

### Authentication Flow
```
Copilot Studio → Entra ID token (OAuth) → Function App Easy Auth validates → Function code runs
  → Function MI authenticates to Foundry (DefaultAzureCredential) → Private Foundry Agent
```

- **Inbound**: Entra ID Easy Auth enforces authentication; unauthenticated requests get `401`
- **Outbound**: Function system-assigned managed identity calls Foundry (no secrets stored)
- **Caller identity**: Available in `x-ms-client-principal-*` headers for audit/logging

### Function Endpoint
```
POST https://<udxcbi-func-*.azurewebsites.net>/api/foundry-chat
```

**Request:**
```json
{
  "message": "What was total sales last quarter by region?",
  "copilotConversationId": "optional-copilot-conv-id",
  "foundryConversationId": "optional-for-multi-turn",
  "domainHint": "Sales"
}
```

**Response:**
```json
{
  "status": "succeeded",
  "correlationId": "8f1f4c1a-...",
  "answer": "Total sales last quarter were ...",
  "foundryConversationId": "thread_abc123",
  "foundryResponseId": "run_abc123",
  "diagnostics": { "elapsedMs": 5240, "agentName": "UDX-Snowflake-Agent" }
}
```

### Deploy Path B

#### Prerequisites
1. Create an Entra ID app registration with identifier URI `api://<client-id>`
2. Note the client ID for the parameter below

#### Deploy
```bash
az deployment group create \
  --resource-group rgUDXConvBI \
  --template-file infra/function-app.bicep \
  --parameters infra/function-app.parameters.json \
  --parameters functionAppClientId="<your-app-registration-client-id>" \
  --name udxconvbi-func-deploy
```

#### Deploy Function code
```bash
cd function-app
func azure functionapp publish <udxcbi-func-name>
```

---

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
| All Azure infrastructure (Path A) | Bicep IaC (`infra/main.bicep`) |
| Azure Function infrastructure (Path B) | Bicep IaC (`infra/function-app.bicep`) |
| Foundry agent creation | Python script (`scripts/create_agent.py`, AzureOpenAI SDK) |
| APIM APIs, backends, policies | Bicep IaC + Python script for policy update |
| APIM VNet integration | Post-deploy script (`scripts/configure_vnet2.py`) |
| Function App code deployment | Azure Functions Core Tools (`func azure functionapp publish`) |
| Entra ID app registration (Path B) | **Manual** (portal or `az ad app create`) |
| Copilot Studio agent | **Manual** (no IaC/API available) |
