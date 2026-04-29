# Copilot Studio → Azure Function → Private Microsoft Foundry Agent

## Purpose

This document describes an alternative to using Azure API Management (APIM) as the public-to-private bridge between a Copilot Studio agent and a Microsoft Foundry Agent Service project deployed with private networking/private endpoints.

The target pattern is:

```text
User in Copilot Studio / Microsoft 365 Copilot experience
    → Copilot Studio agent tool / REST API action / custom connector
        → Public HTTPS Azure Function endpoint secured with Microsoft Entra ID
            → Azure Function outbound VNet integration
                → Private endpoint / private DNS path to Microsoft Foundry Agent Service
                    → Foundry agent
                        → MCP tool connection to Snowflake Cortex MCP, currently tested with PAT
```

This keeps the Foundry project private while giving Copilot Studio a callable public HTTPS endpoint. The Azure Function acts as a controlled bridge, request normalizer, identity/audit enricher, and Foundry invocation wrapper.

---

## Executive recommendation

For the UDX architecture, an Azure Function can replace APIM as the **inbound public-to-private bridge** from Copilot Studio to the private Foundry agent if the Function App is configured with:

1. **Public HTTPS ingress** that Copilot Studio can reach.
2. **Strong Microsoft Entra ID authentication** on the Function endpoint.
3. **Outbound VNet integration** from the Function App into the VNet that can resolve and reach the Foundry private endpoint.
4. **Managed identity authentication** from the Function App to Microsoft Foundry.
5. **A stable request/response contract** exposed to Copilot Studio through a REST API tool or Power Platform custom connector.
6. **Application Insights logging** and optional Azure SQL / Event Hub / Log Analytics capture for boundary telemetry.

The Function should not be treated as a simple pass-through proxy. It should own:

- Caller validation.
- Correlation ID creation.
- Conversation ID mapping.
- Foundry agent invocation.
- Timeout handling.
- Response shaping for Copilot Studio.
- Audit logging.
- Optional domain/role metadata forwarding.

---

## Key design decision

Because the Foundry project has public network access disabled, Copilot Studio cannot directly call the private Foundry endpoint from the public Microsoft 365/Copilot Studio service path unless a reachable intermediary exists.

The Azure Function becomes that intermediary:

```text
Copilot Studio can reach the Function App public endpoint.
The Function App can privately reach Foundry through VNet integration and private DNS.
```

This is a common bridge pattern for cloud-hosted services that must call into private Azure resources.

---

## Important security distinction

This pattern can preserve the **Copilot Studio user identity for auditing and application-level authorization**, but it does not automatically make Foundry or Snowflake execute as the end user.

There are two separate identities:

| Layer | Likely identity used | Notes |
|---|---|---|
| Copilot Studio → Azure Function | End-user delegated identity if using Entra/OBO; connector/service identity if configured that way | Use OBO/end-user auth when possible. |
| Azure Function → Foundry | Function managed identity | Recommended for production. Assign Azure AI User or equivalent invoke permissions. |
| Foundry → Snowflake MCP with PAT | PAT owner / service identity / configured Snowflake role | PAT does **not** provide per-user Snowflake RBAC. |

If Comcast UDX requires true Snowflake per-user RBAC, a PAT-based Snowflake MCP connection is likely a POC-only solution. In production, revisit OAuth identity passthrough, role-specific MCP connections, or a broker pattern that deterministically selects the appropriate Snowflake role outside the LLM.

---

## Recommended logical architecture

```text
+-----------------------------+
| User                        |
| Copilot Studio / M365 Chat  |
+--------------+--------------+
               |
               | Tool call / custom connector
               v
+--------------+--------------+
| Azure Function App          |
| Public HTTPS endpoint       |
| Entra ID protected          |
+--------------+--------------+
               |
               | Outbound VNet integration
               | Private DNS resolution
               v
+--------------+--------------+
| Microsoft Foundry Project   |
| Private endpoint enabled    |
| Public access disabled      |
| Foundry Agent Service       |
+--------------+--------------+
               |
               | MCP tool call from Foundry
               v
+--------------+--------------+
| Snowflake Cortex MCP Server |
| PAT initially / OAuth later |
+-----------------------------+
```

---

## What Copilot Studio should call

Expose a single purpose-built Function endpoint such as:

```http
POST https://<function-app-name>.azurewebsites.net/api/foundry-chat
```

Recommended request body:

```json
{
  "message": "What was total sales last quarter by region?",
  "copilotConversationId": "{{conversation.id}}",
  "foundryConversationId": "optional-existing-foundry-conversation-id",
  "domainHint": "Sales",
  "user": {
    "id": "optional-user-object-id",
    "upn": "optional-user-upn",
    "displayName": "optional-display-name"
  },
  "metadata": {
    "channel": "CopilotStudio",
    "source": "UDX",
    "correlationId": "optional-correlation-id"
  }
}
```

Recommended response body:

```json
{
  "answer": "Total sales last quarter were ...",
  "foundryConversationId": "conv_abc123",
  "foundryResponseId": "resp_abc123",
  "correlationId": "8f1f4c1a-...",
  "status": "succeeded",
  "diagnostics": {
    "elapsedMs": 5240,
    "modelOrAgent": "UDX-Snowflake-Agent"
  }
}
```

Copilot Studio should use the `answer` field as the user-facing response and keep `foundryConversationId` available for the next turn if you want Foundry to maintain the multi-turn conversation.

---

## Copilot Studio implementation options

### Option A — REST API tool in Copilot Studio

Use Copilot Studio's REST API tool/action capability and provide an OpenAPI definition for the Function endpoint.

Use this when:

- You want a low-code setup.
- The Function endpoint has a simple request/response shape.
- You want the Copilot Studio generative orchestrator to select the tool when needed.

### Option B — Power Platform custom connector

Create a custom connector from an OpenAPI 2.0 definition and use it as a Copilot Studio tool.

Use this when:

- You want reusable connector governance.
- You want environment-level connection management.
- You need configured OAuth/Entra ID auth behavior.
- Other Power Platform assets might reuse the same Foundry bridge.

### Option C — Power Automate / Agent Flow wrapper

Create an agent flow that calls the Function and returns the answer to Copilot Studio.

Use this when:

- You want extra low-code orchestration.
- You need additional lookup/mapping logic before calling Foundry.
- You need approvals, notifications, or additional enrichment.

For this UDX scenario, **Option A or B is preferred**. Option C is workable but can add latency and service limits.

---

## Azure resources required

| Resource | Purpose |
|---|---|
| Azure Function App | Public endpoint callable by Copilot Studio; private outbound bridge to Foundry. |
| Function hosting plan | Flex Consumption, Premium, or Dedicated/App Service plan with VNet integration support. Premium or Dedicated is often safer for enterprise latency/control. |
| Storage account for Function App | Required by Azure Functions. Prefer private endpoint-secured storage where the plan supports it. |
| VNet integration subnet | Dedicated subnet used by Function App for outbound access into the private network. |
| Foundry private endpoint subnet | Existing subnet hosting Foundry private endpoint(s). |
| Private DNS zones | Must resolve Foundry service FQDNs to private IPs from the Function's VNet-integrated runtime. |
| Managed identity | Function App identity used to call Foundry without storing secrets. |
| Application Insights | Function telemetry, dependency calls, failures, duration, and correlation. |
| Optional Key Vault | Store non-identity configuration, Snowflake PAT if ever needed outside Foundry, or signing secrets. |
| Optional Azure SQL / Event Hub | Boundary telemetry/reporting destination. |

---

## Hosting plan guidance

Use a Function hosting plan that supports **outbound VNet integration**.

| Plan | Recommendation |
|---|---|
| Classic Consumption | Avoid for this scenario because it does not support the same VNet integration/private endpoint pattern needed for outbound private access. |
| Flex Consumption | Possible for some scenarios; supports VNet integration and private endpoints, but validate latency, cold start, network behavior, and enterprise controls. |
| Premium | Strong enterprise choice. Supports VNet integration, better warm instance behavior, and more predictable performance. |
| Dedicated/App Service Plan | Strong enterprise choice if the customer already standardizes on App Service networking and scaling. |
| App Service Environment | Highest isolation, more cost/ops overhead. Usually not necessary unless required by policy. |

For UDX, start with **Premium** unless cost or serverless scaling drives you toward Flex Consumption.

---

## Network configuration

### 1. Confirm Foundry private endpoint configuration

The Foundry Standard/private deployment should already have public network access disabled and private endpoints configured. The Function needs network access to the same private endpoint path.

Private DNS zones commonly involved for Foundry private networking include:

```text
privatelink.cognitiveservices.azure.com
privatelink.openai.azure.com
privatelink.services.ai.azure.com
```

Validate the actual zones created in the UDX subscription and ensure the Function integration VNet can resolve them.

### 2. Enable outbound VNet integration on the Function App

Configure the Function App with regional VNet integration into a subnet that can reach the Foundry private endpoint.

Recommended subnet design:

```text
vnet-udx-foundry
  subnet-foundry-private-endpoints
  subnet-foundry-agent-service
  subnet-function-outbound-integration
```

The Function App integration subnet should be dedicated to App Service/Functions integration and sized for expected scale.

### 3. Link private DNS zones

The VNet used by the Function App for outbound integration must be linked to the relevant private DNS zones. If the Function is integrated with a peered VNet, confirm DNS resolution crosses the peering path or use custom DNS forwarding.

Validation command from a Function console/Kudu/diagnostic container equivalent:

```bash
nslookup <foundry-resource-name>.services.ai.azure.com
```

Expected result: private IP address associated with the private endpoint.

### 4. Validate outbound path

From the Function environment, test:

```bash
curl -I https://<foundry-resource-name>.services.ai.azure.com/api/projects/<project-name>
```

A `401` or `403` response can be a good sign that the private network path is reachable and authentication/authorization is now the remaining issue. DNS failures, timeouts, or public IP resolution indicate networking or DNS is not correct.

---

## Identity and authorization configuration

### Copilot Studio → Azure Function

Recommended production approach:

1. Register an Entra ID app for the Azure Function API.
2. Expose an API scope such as:

```text
api://<function-api-client-id>/Foundry.Chat.Invoke
```

3. Enable App Service Authentication / Easy Auth on the Function App.
4. Configure the Copilot Studio REST API tool or custom connector to use Microsoft Entra ID OAuth.
5. Use OBO/end-user authentication if the UX and tenant configuration support it.
6. Validate the user token in the Function through Easy Auth headers or manual JWT validation.

POC-only alternative:

- Function key or API key.

Avoid using Function keys for production because they do not give you per-user identity and are harder to govern than Entra ID.

### Azure Function → Microsoft Foundry

Recommended production approach:

1. Enable a system-assigned or user-assigned managed identity on the Function App.
2. Assign that identity the required Foundry role.
3. Start with **Azure AI User** on the Foundry project or published Agent Application invoke scope.
4. Use `DefaultAzureCredential` inside the Function.
5. The Function calls Foundry using Entra ID, not API keys.

For private Foundry agent invocation through Responses API, the Function identity must have permission to invoke the agent or access the project runtime.

### Foundry → Snowflake MCP

Current POC approach:

- Foundry MCP connection uses Snowflake PAT.

Production caution:

- PAT means Snowflake executes under the PAT-bound Snowflake identity/role, not the Copilot user.
- If per-user Snowflake RBAC is mandatory, replace PAT with OAuth/role-aware design before production.

---

## Azure Function application settings

Recommended settings:

```text
FOUNDRY_PROJECT_ENDPOINT=https://<foundry-resource-name>.services.ai.azure.com/api/projects/<project-name>
FOUNDRY_AGENT_NAME=UDX-Snowflake-Agent
AZURE_CLIENT_ID=<optional-user-assigned-managed-identity-client-id>
ALLOWED_TENANT_ID=<comcast-tenant-id>
ALLOWED_AUDIENCE=api://<function-api-client-id>
ENABLE_FULL_PROMPT_LOGGING=false
LOG_RESPONSE_BODY=false
DEFAULT_TIMEOUT_SECONDS=55
```

If using a user-assigned managed identity, set `AZURE_CLIENT_ID`. If using a system-assigned identity, omit it.

---

## Azure Function implementation draft

The following is a Python Azure Functions v2-style implementation sketch. It uses the Microsoft Foundry Project client and the Responses API with an `agent_reference`.

### `requirements.txt`

```text
azure-functions
azure-identity
azure-ai-projects>=2.0.0
applicationinsights
opencensus-ext-azure
```

Adjust package versions to Comcast's approved dependency baseline.

### `function_app.py`

```python
import json
import logging
import os
import time
import uuid
from typing import Any, Dict, Optional

import azure.functions as func
from azure.identity import DefaultAzureCredential, ManagedIdentityCredential
from azure.ai.projects import AIProjectClient

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
AGENT_NAME = os.environ["FOUNDRY_AGENT_NAME"]
AZURE_CLIENT_ID = os.getenv("AZURE_CLIENT_ID")
DEFAULT_TIMEOUT_SECONDS = int(os.getenv("DEFAULT_TIMEOUT_SECONDS", "55"))

# Use user-assigned managed identity if AZURE_CLIENT_ID is provided.
# Otherwise DefaultAzureCredential will use the system-assigned managed identity in Azure.
if AZURE_CLIENT_ID:
    credential = ManagedIdentityCredential(client_id=AZURE_CLIENT_ID)
else:
    credential = DefaultAzureCredential()

project_client = AIProjectClient(
    endpoint=PROJECT_ENDPOINT,
    credential=credential,
)
openai_client = project_client.get_openai_client()


def _json_response(payload: Dict[str, Any], status_code: int = 200) -> func.HttpResponse:
    return func.HttpResponse(
        body=json.dumps(payload, ensure_ascii=False),
        status_code=status_code,
        mimetype="application/json",
    )


def _get_easy_auth_claims(req: func.HttpRequest) -> Dict[str, Any]:
    """
    If App Service Authentication / Easy Auth is enabled, Azure App Service can
    pass authenticated principal information in x-ms-client-principal headers.

    Production implementations should validate the expected auth mode and avoid
    trusting caller-supplied identity headers unless injected by App Service Auth.
    """
    principal = req.headers.get("x-ms-client-principal")
    if not principal:
        return {}

    # The header is base64 encoded JSON in App Service Authentication.
    # Keep this as a placeholder to avoid accidental fragile parsing in sample code.
    # Production code should decode and validate this structure carefully.
    return {"raw_x_ms_client_principal_present": True}


def _get_request_json(req: func.HttpRequest) -> Dict[str, Any]:
    try:
        return req.get_json()
    except ValueError:
        raise ValueError("Request body must be valid JSON.")


@app.route(route="foundry-chat", methods=["POST"])
def foundry_chat(req: func.HttpRequest) -> func.HttpResponse:
    started = time.time()
    correlation_id = req.headers.get("x-correlation-id") or str(uuid.uuid4())

    try:
        body = _get_request_json(req)
        message = body.get("message")
        if not message or not isinstance(message, str):
            return _json_response(
                {
                    "status": "failed",
                    "correlationId": correlation_id,
                    "error": "The 'message' field is required and must be a string."
                },
                status_code=400,
            )

        # Identity can come from the signed-in user token / Easy Auth claims,
        # explicit Copilot payload, or both. Treat request body user fields as
        # convenience metadata, not as proof of identity.
        easy_auth_claims = _get_easy_auth_claims(req)
        supplied_user = body.get("user") or {}
        domain_hint = body.get("domainHint")
        copilot_conversation_id = body.get("copilotConversationId")
        foundry_conversation_id = body.get("foundryConversationId")

        # Create a Foundry conversation if Copilot did not send an existing one.
        # For production, store a mapping:
        # Copilot conversation ID -> Foundry conversation ID.
        if not foundry_conversation_id:
            conversation = openai_client.conversations.create()
            foundry_conversation_id = conversation.id

        # Build agent reference request.
        # User metadata is added for traceability, not security enforcement.
        response = openai_client.responses.create(
            conversation=foundry_conversation_id,
            input=message,
            extra_body={
                "agent_reference": {
                    "name": AGENT_NAME,
                    "type": "agent_reference",
                },
                "metadata": {
                    "correlation_id": correlation_id,
                    "copilot_conversation_id": copilot_conversation_id,
                    "domain_hint": domain_hint,
                    "supplied_user_id": supplied_user.get("id"),
                    "supplied_user_upn": supplied_user.get("upn"),
                    "source": "CopilotStudio-AzureFunction-Bridge",
                }
            },
            timeout=DEFAULT_TIMEOUT_SECONDS,
        )

        elapsed_ms = int((time.time() - started) * 1000)

        logging.info(
            "Foundry response succeeded",
            extra={
                "correlation_id": correlation_id,
                "elapsed_ms": elapsed_ms,
                "foundry_conversation_id": foundry_conversation_id,
                "domain_hint": domain_hint,
            },
        )

        return _json_response({
            "status": "succeeded",
            "correlationId": correlation_id,
            "answer": getattr(response, "output_text", None) or "",
            "foundryConversationId": foundry_conversation_id,
            "foundryResponseId": getattr(response, "id", None),
            "diagnostics": {
                "elapsedMs": elapsed_ms,
                "agentName": AGENT_NAME,
            }
        })

    except Exception as exc:
        elapsed_ms = int((time.time() - started) * 1000)
        logging.exception("Foundry bridge failed", extra={"correlation_id": correlation_id})

        return _json_response(
            {
                "status": "failed",
                "correlationId": correlation_id,
                "error": "The Foundry bridge failed while processing the request.",
                "details": str(exc),
                "diagnostics": {
                    "elapsedMs": elapsed_ms,
                    "agentName": AGENT_NAME,
                }
            },
            status_code=500,
        )
```

### Notes on the sample

- `http_auth_level=ANONYMOUS` is intentional if App Service Authentication / Easy Auth handles authentication before the function code runs.
- Do not trust user identity values provided in the JSON body. Treat them as convenience metadata unless validated against the token claims.
- In production, fully decode and validate Easy Auth claims or manually validate JWTs.
- Use managed identity for Foundry authentication.
- Return compact JSON to Copilot Studio. Avoid returning raw Foundry traces or Snowflake payloads unless explicitly needed.
- Consider adding a persistence layer to map Copilot conversation IDs to Foundry conversation IDs.

---

## Conversation state handling

There are three ways to handle multi-turn memory.

### Option 1 — Copilot passes the Foundry conversation ID

The Function returns `foundryConversationId`; Copilot Studio stores it in a conversation variable and sends it back on the next call.

Pros:

- Simple.
- Minimal server-side storage.

Cons:

- Requires careful Copilot Studio variable handling.
- Users could potentially tamper with the conversation ID if not protected.

### Option 2 — Function stores the mapping

The Function stores:

```text
copilotConversationId → foundryConversationId
```

in Azure Table Storage, Azure SQL DB, Cosmos DB, or Redis.

Pros:

- Cleaner Copilot Studio contract.
- Better control and auditability.

Cons:

- Requires a small persistence store.

### Option 3 — Stateless calls only

Each Function call creates a new Foundry conversation.

Pros:

- Simplest.

Cons:

- Poor multi-turn experience.
- Follow-up questions like “what about last quarter?” may fail.

Recommended UDX approach: **Option 2** for production, Option 1 for POC.

---

## OpenAPI definition for Copilot Studio / custom connector

Copilot Studio and Power Platform custom connectors commonly require OpenAPI 2.0/Swagger definitions. Use this as a starting point and customize host, auth, schemas, and descriptions.

```yaml
swagger: '2.0'
info:
  title: UDX Foundry Agent Bridge
  description: Calls the private Microsoft Foundry Agent through an Azure Function bridge.
  version: '1.0'
host: <function-app-name>.azurewebsites.net
basePath: /api
schemes:
  - https
consumes:
  - application/json
produces:
  - application/json
paths:
  /foundry-chat:
    post:
      summary: Ask the UDX Foundry Agent
      description: Sends a user question to the UDX Foundry Agent and returns the agent response.
      operationId: AskFoundryAgent
      parameters:
        - name: body
          in: body
          required: true
          schema:
            $ref: '#/definitions/FoundryChatRequest'
      responses:
        '200':
          description: Successful response from Foundry agent.
          schema:
            $ref: '#/definitions/FoundryChatResponse'
        '400':
          description: Invalid request.
        '401':
          description: Unauthorized.
        '500':
          description: Bridge or Foundry processing error.
definitions:
  FoundryChatRequest:
    type: object
    required:
      - message
    properties:
      message:
        type: string
        description: The user's natural language question.
      copilotConversationId:
        type: string
        description: The Copilot Studio conversation ID.
      foundryConversationId:
        type: string
        description: Existing Foundry conversation ID for multi-turn continuity.
      domainHint:
        type: string
        description: Optional domain hint such as Finance, Sales, or HR.
      user:
        type: object
        properties:
          id:
            type: string
          upn:
            type: string
          displayName:
            type: string
      metadata:
        type: object
        additionalProperties:
          type: string
  FoundryChatResponse:
    type: object
    properties:
      status:
        type: string
      answer:
        type: string
      foundryConversationId:
        type: string
      foundryResponseId:
        type: string
      correlationId:
        type: string
      diagnostics:
        type: object
```

Authentication can be configured in the connector UI or embedded into the OpenAPI definition depending on the selected connector path and tenant standards. For production, prefer Microsoft Entra ID OAuth over API key authentication.

---

## Step-by-step implementation plan

### Phase 1 — Validate the Function can reach private Foundry

1. Create or identify the Foundry private endpoint deployment.
2. Confirm Foundry public network access is disabled.
3. Create a Function App on Premium or another VNet-capable plan.
4. Enable Function App managed identity.
5. Enable outbound VNet integration to the subnet that can reach Foundry.
6. Link the Foundry private DNS zones to the VNet used by the Function.
7. Assign the Function identity **Azure AI User** or equivalent runtime invoke permission on the Foundry project or Agent Application resource.
8. Add app settings for `FOUNDRY_PROJECT_ENDPOINT` and `FOUNDRY_AGENT_NAME`.
9. Deploy a simple test Function that gets an Entra token and calls Foundry.
10. Validate DNS resolution and HTTP connectivity from the Function runtime.

### Phase 2 — Build the Foundry bridge endpoint

1. Implement `/api/foundry-chat` HTTP POST endpoint.
2. Validate JSON body.
3. Create or resolve Foundry conversation ID.
4. Call Foundry Responses API with `agent_reference`.
5. Return only the needed response fields to Copilot Studio.
6. Add structured logging and correlation IDs.
7. Add timeout handling.
8. Add retry logic only for transient network or 429/5xx errors; do not blindly retry non-idempotent operations.

### Phase 3 — Secure the Function endpoint

1. Register an Entra app for the Function API.
2. Expose an API scope.
3. Enable App Service Authentication on the Function App.
4. Require authenticated requests.
5. Configure allowed audiences and issuers.
6. Confirm Copilot Studio/custom connector can obtain and send a valid token.
7. Validate that unauthenticated requests fail.
8. Add rate limiting inside code or via another approved edge control if APIM is not used.

### Phase 4 — Connect Copilot Studio

1. Create a REST API tool or custom connector using the OpenAPI definition.
2. Configure authentication to the Function API.
3. Add the tool to the Copilot Studio agent.
4. Provide a clear tool description:

```text
Use this tool when the user asks a question about UDX curated Snowflake data or business metrics in Finance, Sales, or HR. The tool sends the question to the approved Microsoft Foundry agent, which has access to governed Snowflake Cortex MCP tools.
```

5. Test with simple non-sensitive prompts.
6. Test follow-up questions to validate conversation continuity.
7. Test unauthorized users.
8. Test Foundry failures and ensure Copilot Studio receives user-safe error messages.

### Phase 5 — Operationalize

1. Enable Application Insights on the Function App.
2. Log correlation ID, caller, domain hint, elapsed time, Foundry conversation ID, response ID, status, and error category.
3. Decide whether to log full prompts/responses. Default should be no for HR/Finance unless approved.
4. Add alerts for 401/403 spikes, 5xx errors, Foundry timeout, and latency.
5. Add Azure SQL/Event Hub reporting if required.
6. Add Key Vault references for any secrets that cannot be replaced with managed identity.
7. Document support/runbook steps.

---

## Copilot Studio instruction guidance

Add this kind of instruction to the Copilot Studio agent so it knows when to call the Function tool:

```text
You are the Comcast UDX conversational business intelligence assistant. When a user asks a question about curated UDX business data, metrics, or analysis for Finance, Sales, or HR, use the AskFoundryAgent tool. The tool sends the user's question to the approved Microsoft Foundry agent that is connected to Snowflake Cortex MCP tools.

Do not invent numbers, metrics, or business facts. If the tool returns an answer, summarize it clearly and concisely for the user. If the tool indicates that data is unavailable, the user lacks access, or the request is ambiguous, explain that clearly and ask a focused follow-up question.

Treat user identity, domain hints, and Snowflake role information as security-sensitive metadata. Do not ask the user to manually provide privileged role names. Do not claim that a user has access to HR, Finance, or Sales data unless the tool confirms it.
```

---

## Function-level prompt/metadata guidance

The Azure Function should avoid adding large hidden prompt instructions that conflict with the Foundry agent instructions. The Foundry agent should remain the primary reasoning/orchestration layer.

The Function can pass metadata such as:

```json
{
  "correlation_id": "...",
  "caller_upn": "...",
  "domain_hint": "Finance",
  "copilot_conversation_id": "...",
  "source": "CopilotStudio"
}
```

Do not use caller-supplied JSON metadata as a security decision. Authorization should come from validated token claims, group/role lookups, or governed connection configuration.

---

## Telemetry and reporting

Even without APIM, the Function can emit boundary telemetry.

Recommended telemetry fields:

```text
correlation_id
copilot_conversation_id
foundry_conversation_id
foundry_response_id
caller_object_id
caller_upn
agent_name
domain_hint
request_timestamp_utc
response_timestamp_utc
elapsed_ms
status
error_category
http_status_code
```

Optional sensitive fields, only if approved:

```text
user_prompt_text
assistant_answer_text
snowflake_domain/tool metadata
```

Default stance: log metadata and metrics, not full HR/Finance/Sales content, unless security and compliance approve retention and access controls.

---

## Gotchas and watch areas

### 1. The Function is now the security boundary

If APIM is removed, the Function must handle security capabilities that APIM might have provided:

- Authentication enforcement.
- Request validation.
- Rate limiting or throttling.
- Payload size limits.
- Logging and correlation.
- Error shaping.
- Abuse protection.

Consider Azure Front Door, App Service access restrictions, Defender for Cloud, or code-level throttling if the customer needs APIM-like controls without APIM.

### 2. VNet integration is outbound only

Function App VNet integration lets the Function reach private resources. It does not automatically make the Function itself private. That is acceptable here because Copilot Studio needs a public endpoint, but the endpoint must be strongly authenticated.

### 3. DNS is usually the hardest part

The Function may be correctly integrated with the VNet but still fail to reach Foundry if private DNS zones are not linked correctly. Always validate that the Foundry endpoint resolves to the private IP from the Function runtime.

### 4. Classic Consumption plan is usually the wrong choice

Use Flex Consumption, Premium, or Dedicated for VNet integration. Premium is often the safest enterprise default.

### 5. PAT-based Snowflake MCP is not per-user authorization

If Foundry uses a Snowflake PAT for MCP, Snowflake sees the PAT identity/role. Use this for POC only unless Comcast accepts a service-role security model.

### 6. Copilot Studio timeout behavior matters

Copilot Studio tools expect reasonably fast responses. Keep the Function and Foundry response path optimized. For long-running analytics, consider an asynchronous pattern, but that is usually less conversational.

### 7. Do not return raw tool errors to the user

Map internal exceptions to user-safe responses.

Example:

```text
I could not complete the data request because the analytics service was unavailable. Please try again later or contact the UDX support team with correlation ID ...
```

### 8. Function-managed identity must have Foundry runtime permission

A common failure mode is successful network connectivity but `403 Forbidden` from Foundry because the Function identity lacks the required Foundry role.

### 9. Conversation mapping is required for good multi-turn behavior

If Copilot Studio does not send back the Foundry conversation ID, follow-up questions may lose context. Store or return the mapping explicitly.

### 10. Avoid putting security decisions in prompts

The LLM can help classify the topic, but it should not determine whether the user is allowed to access HR, Finance, or Sales data. Use deterministic identity/role checks.

---

## POC test plan

### Test 1 — Function public authentication

- Call the Function without a token.
- Expected: 401/403.

### Test 2 — Function with valid token

- Call the Function through the custom connector or Postman with Entra token.
- Expected: 200 or controlled Foundry response.

### Test 3 — Function to Foundry private endpoint

- Use a simple prompt.
- Expected: Foundry agent response.
- Validate that DNS resolves to private IP.

### Test 4 — Copilot Studio tool call

- Ask Copilot Studio: “Ask the UDX Foundry agent what data domains it can answer questions about.”
- Expected: Tool is called and response is returned to the user.

### Test 5 — Multi-turn continuity

1. “What were sales last quarter by region?”
2. “Which region had the biggest increase?”

Expected: second answer understands the prior context.

### Test 6 — Unauthorized access

- Test with a user not allowed to call the Function.
- Expected: access denied before Foundry is invoked.

### Test 7 — Snowflake MCP PAT role behavior

- Ask a question that requires Snowflake MCP.
- Check Snowflake query/access history.
- Confirm which Snowflake user/role executed.
- If it is the PAT/service identity, document that this does not meet per-user RBAC.

---

## Production checklist

- [ ] Function App hosted on Premium/Dedicated/Flex with VNet integration.
- [ ] Function public endpoint protected by Entra ID.
- [ ] Function App managed identity enabled.
- [ ] Function identity assigned Azure AI User or equivalent Foundry invoke permission.
- [ ] Foundry private DNS zones linked to Function integration VNet.
- [ ] Foundry endpoint resolves to private IP from Function runtime.
- [ ] Copilot Studio REST API tool or custom connector created from OpenAPI definition.
- [ ] Connector authentication tested with target users.
- [ ] Conversation ID mapping implemented.
- [ ] Application Insights enabled.
- [ ] Logs avoid secrets, tokens, and sensitive HR/Finance data by default.
- [ ] User-safe error handling implemented.
- [ ] Timeout/retry policy implemented.
- [ ] Snowflake PAT security model accepted for POC only or replaced for production.
- [ ] POC validates Snowflake observed identity/role.

---

## References

- Copilot Studio custom agents can be extended with tools, including REST API/custom connector-based tools: https://learn.microsoft.com/en-us/microsoft-copilot-studio/add-tools-custom-agent
- Copilot Studio REST API tool creation flow: https://learn.microsoft.com/en-us/microsoft-copilot-studio/agent-extend-action-rest-api
- Power Platform custom connectors wrap REST APIs for Copilot Studio, Power Automate, Power Apps, and Logic Apps: https://learn.microsoft.com/en-us/connectors/custom-connectors/
- Custom connectors can be created from OpenAPI definitions; OpenAPI 2.0 is commonly required: https://learn.microsoft.com/en-us/connectors/custom-connectors/define-openapi-definition
- Copilot Studio custom connector OBO authentication: https://learn.microsoft.com/en-us/microsoft-copilot-studio/advanced-custom-connector-on-behalf-of
- Azure Functions networking options and VNet/private endpoint support: https://learn.microsoft.com/en-us/azure/azure-functions/functions-networking-options
- Azure Functions with private endpoints/VNet tutorial: https://learn.microsoft.com/en-us/azure/azure-functions/functions-create-vnet
- Microsoft Foundry private networking for Agent Service: https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/virtual-networks
- Microsoft Foundry private link and DNS behavior: https://learn.microsoft.com/en-us/azure/foundry/how-to/configure-private-link
- Microsoft Foundry authentication and authorization: https://learn.microsoft.com/en-us/azure/foundry/concepts/authentication-authorization-foundry
- Microsoft Foundry RBAC roles: https://learn.microsoft.com/en-us/azure/foundry/concepts/rbac-foundry
- Microsoft Foundry runtime components, conversations, and responses: https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/runtime-components
