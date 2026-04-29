# UDX Architecture Note: M365 Copilot Chat → Copilot Studio → APIM → Foundry Agent (Private) → APIM → Snowflake Cortex MCP (AWS PrivateLink)

> **Purpose:** Document the UDX approach that enables **Microsoft 365 Copilot Chat** to use a **private (Private Endpoint / PNA disabled) Azure AI Foundry agent** and then reach **Snowflake on AWS via Snowflake’s managed Cortex AI MCP server**, using **Azure API Management (APIM) as the only network bridge** (no Azure Function).

> **UDX current constraint:** The Foundry project is deployed with **Public Network Access disabled** and uses **Private Endpoints**, which blocks direct publishing of the Foundry agent to M365 Copilot Chat from the Foundry portal.

---

## 1) Executive Summary

Because the UDX Foundry project is **private-only**, the Foundry portal’s **Publish to Microsoft 365 Copilot** flow can’t be used as-is. That publish flow exposes a **stable agent endpoint** for M365 Copilot/Teams users, and it assumes the endpoint is reachable by Microsoft 365 services. citeturn22search173  
Foundry network isolation is governed by the **Public Network Access (PNA) flag**; when PNA is disabled, access requires private endpoints. citeturn22search190

**Remedy:** Publish a *thin* Copilot Studio agent to M365 Copilot Chat, and have it call **APIM (public gateway)**. APIM then routes privately to:
1) the **private Foundry agent endpoint**, and
2) (optionally) the **Snowflake managed MCP endpoint** (AWS PrivateLink), with Foundry orchestrating tool calls.

This yields the required flow:

```
M365 Copilot Chat → Copilot Studio → APIM → Foundry Agent (Private) → APIM → Snowflake Cortex AI MCP (AWS PrivateLink) → Snowflake Data
```

---

## 2) Why Foundry “Publish to M365 Copilot” fails in a private-only project

- Foundry publishing publishes an agent’s **stable endpoint** for Microsoft 365 Copilot and Teams. citeturn22search173  
- Foundry inbound network isolation is controlled by **Public Network Access (PNA)**; when disabled, access requires private endpoint connectivity. citeturn22search190  

**Implication:** If the agent endpoint is private-only, Microsoft 365 SaaS callers won’t have line-of-sight to that endpoint, so the publish flow is blocked.

---

## 3) Why APIM-only is viable (Standard v2)

### 3.1 APIM can proxy to backends
APIM supports defining **backend entities** (HTTP services) and routing inbound API calls to those backends. citeturn32search206  

### 3.2 APIM Standard v2 can reach private backends
APIM **Standard v2** supports **virtual network integration for outbound requests**, allowing the APIM gateway (still publicly accessible) to call APIs hosted in a connected/peered VNet—i.e., network-isolated backends. citeturn32search222turn32search221  

### 3.3 Copilot Studio can call APIM via HTTP
Copilot Studio includes an **HTTP Request** node that can call external REST endpoints (GET/POST/etc.) and pass headers/body. citeturn32search201  

**Therefore:** Copilot Studio → APIM (public) is straightforward, and APIM → private Foundry is feasible with Standard v2 outbound VNet integration.

---

## 4) Reference Architecture (APIM-only bridge)

### 4.1 End-to-end flow

1. **User** asks a question in **M365 Copilot Chat**.
2. A **Copilot Studio agent** (thin router) receives the message.
3. Copilot Studio calls **APIM (public endpoint)** using an HTTP Request node.
4. APIM routes the call to the **Foundry agent endpoint** (private) as a backend.
5. The Foundry agent executes instructions and (when needed) calls tools.
6. For Snowflake access, Foundry calls **APIM** (again) to reach the **Snowflake managed MCP endpoint** (private connectivity required).
7. Snowflake MCP server invokes **Cortex Agent / Analyst semantic views** and queries Snowflake data.
8. Results return back through the chain to Copilot Chat.

### 4.2 Components and responsibilities

**Copilot Studio agent (thin router)**
- Hosts the agent inside M365 Copilot Chat.
- Calls APIM via HTTP node.
- Does *not* implement BI logic; Foundry does. citeturn32search201

**APIM (Standard v2)**
- Public gateway endpoint for Copilot Studio.
- Routes to private Foundry backend (requires outbound VNet integration). citeturn32search222turn32search221
- Optionally routes to Snowflake MCP endpoint (requires Azure↔AWS private connectivity + DNS).

**Foundry agent (private)**
- Contains the system instructions, orchestration, and tool calling.
- Private access controlled by PNA/private endpoints. citeturn22search190

**Snowflake managed MCP (AWS PrivateLink)**
- MCP server hosted by Snowflake.
- Executes Cortex Agent / Analyst / Search and queries Snowflake data.

---

## 5) Implementation — Minimal Build Steps

### 5.1 APIM setup (Standard v2)

1) **Deploy APIM Standard v2**
- Ensure you are on **Standard v2** so outbound VNet integration is available. citeturn32search222turn32search221

2) **Enable outbound VNet integration**
- Integrate APIM with the VNet that can resolve/reach the **Foundry private endpoint**. citeturn32search222turn32search221

3) **Configure backend: Foundry**
- Create an APIM **backend entity** that points to the Foundry agent endpoint (private FQDN). citeturn32search206

4) **(Optional) Configure backend: Snowflake MCP**
- Create an APIM backend that points to the Snowflake managed MCP endpoint.
- This requires that APIM has network reachability to Snowflake’s AWS PrivateLink endpoint (VPN/ER/peering + DNS).

5) **Create APIM API operations**
- `POST /udx/foundry/invoke` → Foundry backend
- `POST /udx/snowflake/mcp` → Snowflake MCP backend (optional; used if Foundry must route via APIM)

6) **Policies**
- Add request/response limits, logging, auth.
- (Optional) Inject headers required by Foundry or Snowflake MCP.


### 5.2 Copilot Studio setup (thin router)

1) Create Copilot Studio agent and publish it to **M365 Copilot Chat**.
2) Add an **HTTP Request** node to call APIM endpoint:
   - Method: POST
   - URL: `https://<apim-gateway-host>/udx/foundry/invoke`
   - Body: JSON with the user query

Copilot Studio HTTP Request node is a documented extension point for calling REST APIs. citeturn32search201

### 5.3 Foundry setup (private)

1) Keep Foundry project private (PNA disabled).
2) Ensure the Foundry agent endpoint is reachable from APIM’s integrated VNet.
3) Configure the Foundry agent to use MCP tools as normal.
4) If Foundry must call Snowflake MCP via APIM, register APIM Snowflake endpoint as an MCP server endpoint (depending on your tool wiring).

---

## 6) Configuration Templates (Copy/Paste)

> **Note:** Exact Foundry agent REST paths can vary by agent configuration. The templates below show the **pattern** for APIM routing, not a promise of a specific Foundry URL shape.

### 6.1 Copilot Studio HTTP Request node — request body template

Use a minimal JSON payload so Foundry can interpret the user message:

```json
{
  "userQuery": "{{System.Activity.Text}}",
  "channel": "M365CopilotChat",
  "tenant": "UDX"
}
```

### 6.2 APIM backend definition (conceptual)

Create backends in APIM for:
- `foundry-backend` → `https://<private-foundry-endpoint>`
- `snowflake-mcp-backend` → `https://<snowflake-mcp-endpoint>`

APIM backends encapsulate backend info and are reused across APIs. citeturn32search206

### 6.3 APIM policy (inbound) — validate JWT (optional)

```xml
<policies>
  <inbound>
    <base />
    <!-- Optional: validate JWT from Copilot Studio / Entra -->
    <validate-jwt header-name="Authorization" failed-validation-httpcode="401" failed-validation-error-message="Unauthorized">
      <openid-config url="https://login.microsoftonline.com/<TENANT_ID>/v2.0/.well-known/openid-configuration" />
      <required-claims>
        <claim name="aud">
          <value><YOUR_APP_ID_URI_OR_CLIENT_ID></value>
        </claim>
      </required-claims>
    </validate-jwt>
  </inbound>
  <backend>
    <base />
  </backend>
  <outbound>
    <base />
  </outbound>
  <on-error>
    <base />
  </on-error>
</policies>
```

### 6.4 APIM policy — route to Foundry backend

```xml
<policies>
  <inbound>
    <base />
    <set-backend-service backend-id="foundry-backend" />
    <set-header name="Content-Type" exists-action="override">
      <value>application/json</value>
    </set-header>
  </inbound>
  <backend>
    <base />
  </backend>
  <outbound>
    <base />
  </outbound>
</policies>
```

### 6.5 APIM policy — route to Snowflake MCP backend (optional)

```xml
<policies>
  <inbound>
    <base />
    <set-backend-service backend-id="snowflake-mcp-backend" />
    <set-header name="Content-Type" exists-action="override">
      <value>application/json</value>
    </set-header>
  </inbound>
  <backend>
    <base />
  </backend>
  <outbound>
    <base />
  </outbound>
</policies>
```

---

## 7) Networking Notes (Private Foundry + AWS PrivateLink)

### 7.1 Foundry private endpoint reachability
- Foundry private endpoint access is required when PNA is disabled. citeturn22search190
- APIM Standard v2 outbound VNet integration must be connected to a VNet that can resolve/reach that endpoint. citeturn32search222turn32search221

### 7.2 Snowflake PrivateLink reachability
Snowflake MCP on AWS PrivateLink generally implies:
- Private connectivity between Azure network (where APIM/Foundry live) and AWS VPC (where Snowflake private endpoint lives), typically via VPN/ER and DNS integration.

(These details depend on UDX networking standards and are not specified in the cited sources; treat them as design considerations rather than hard requirements.)

---

## 8) Benefits / Tradeoffs

### Benefits
- Keeps Foundry private (aligns to stricter Tier 3/4 posture).
- Uses a single gateway control plane (APIM) for:
  - inbound (Copilot Studio)
  - outbound to private backends.

### Tradeoffs
- More networking complexity than “enable public Foundry” approach.
- Requires correct DNS for private endpoints.
- Adding APIM between Foundry and Snowflake MCP adds hop latency and requires cross-cloud private connectivity.

---

## 9) Alternatives (for completeness)

### A) Enable Foundry public access (simplest)
- Use Foundry portal publish directly.
- Conflicts with strict private endpoint posture.

### B) Copilot Studio + Azure Function proxy
- Same pattern as APIM-only but swaps APIM backend routing for custom code.
- Often easier to debug but adds another runtime.

---

## 10) Validation Checklist

1) Copilot Studio HTTP Request node successfully calls APIM. citeturn32search201
2) APIM successfully routes to Foundry backend and returns a response (requires APIM outbound VNet integration). citeturn32search222turn32search206
3) Foundry tool calls succeed (Snowflake MCP calls return data).
4) If using APIM between Foundry and Snowflake MCP:
   - Foundry can reach APIM Snowflake route
   - APIM can reach Snowflake PrivateLink endpoint

---

## 11) References

- Foundry publish to M365 Copilot/Teams publishes stable endpoint citeturn22search173
- Foundry inbound network isolation / PNA flag and private endpoint requirement citeturn22search190
- Copilot Studio HTTP Request node for calling external REST APIs citeturn32search201
- APIM backends (routing to backend HTTP services) citeturn32search206
- APIM Standard v2 outbound VNet integration to reach network-isolated backends citeturn32search222turn32search221
