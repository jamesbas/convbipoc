# Copilot Studio Setup (Manual Steps)

> Copilot Studio agent creation cannot be automated via IaC. Follow these steps after infrastructure deployment completes.

## Prerequisites
- Infrastructure deployment to `rgUDXConvBI` is complete
- You have access to [Copilot Studio](https://copilotstudio.microsoft.com)
- You have the APIM gateway URL and subscription key (from deployment outputs)

## Steps

### 1. Get APIM Details
Run this to get your APIM gateway URL and subscription key:
```bash
# Get gateway URL
az deployment group show --resource-group rgUDXConvBI --name udxconvbi-deploy --query "properties.outputs.apimGatewayUrl.value" -o tsv

# Get subscription key
az rest --method post --url "https://management.azure.com$(az apim show -n $(az deployment group show -g rgUDXConvBI -n udxconvbi-deploy --query 'properties.outputs.apimName.value' -o tsv) -g rgUDXConvBI --query id -o tsv)/subscriptions/copilot-studio-sub/listSecrets?api-version=2023-09-01-preview" --query primaryKey -o tsv
```

### 2. Create Copilot Studio Agent
1. Go to [Copilot Studio](https://copilotstudio.microsoft.com)
2. Click **Create** → **New agent**
3. Name it: `UDX Conversational BI POC`
4. Description: `Routes user queries to Azure AI Foundry agent via APIM for the UDX Conversational BI POC`

### 3. Add HTTP Request Action (Topic)
1. Create a new **Topic** (e.g., `Route to Foundry`)
2. Set trigger: **On message received** (catch-all)
3. Add an **HTTP Request** node:
   - **Method:** POST
   - **URL:** `https://<APIM_GATEWAY_URL>/udx/foundry/invoke`
   - **Headers:**
     - `Content-Type`: `application/json`
     - `Ocp-Apim-Subscription-Key`: `<YOUR_APIM_KEY>`
   - **Body:**
     ```json
     {
       "userQuery": "{x]Topic.MessageText}",
       "channel": "M365CopilotChat",
       "tenant": "UDX"
     }
     ```
4. Add a **Message** node after the HTTP request to return the response body to the user.

### 4. Publish to M365 Copilot Chat
1. Go to **Channels** in the left nav
2. Select **Microsoft 365 Copilot (Preview)**
3. Click **Publish**
4. Wait for admin approval in the Microsoft 365 admin center if required

### 5. Test
1. Open Microsoft 365 Copilot Chat
2. Find the `UDX Conversational BI POC` agent
3. Ask a question like "What is Azure AI Foundry?"
4. Verify the response comes back through the full chain
