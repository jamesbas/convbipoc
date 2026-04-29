# Boundary Storage Mechanism

## Foundry Agent Service, Cosmos DB, APIM Boundary Telemetry, Azure SQL DB, Fabric Mirroring, and Reporting Analytics

### Purpose

This document summarizes the recommended storage, telemetry, and reporting architecture for a Microsoft Azure AI Foundry project deployed as a custom/private project environment. The context is a Foundry Agent Service implementation where Microsoft-managed operational storage is deployed into the customer’s Azure environment, including Azure Cosmos DB.

The customer would prefer a familiar relational reporting database such as Azure SQL Database, but the Foundry project uses Azure Cosmos DB as part of its required operational architecture. The Comcast UDX architecture also uses Azure API Management (APIM) at both boundaries: inbound from Microsoft 365 Copilot / custom engine agent traffic into Foundry, and outbound from Foundry to the Snowflake MCP server.

This document explains what can and cannot be changed, how Cosmos DB data can be mirrored or projected into reporting platforms, how APIM can contribute boundary telemetry, and what kind of analytics can be built from the captured Foundry agent interaction data.

---

## 1. Executive Summary

Do **not** replace or turn off Azure Cosmos DB in a Microsoft Foundry Standard/custom/private project deployment.

Cosmos DB is part of the supported Foundry Agent Service operational storage pattern. It is used by Foundry to store agent conversation state, thread messages, system messages, model input/output data, and agent metadata. Azure SQL Database is not currently a supported drop-in replacement for that internal Foundry thread and agent state store.

The recommended Comcast UDX pattern is:

```text
Microsoft 365 Copilot / Custom Engine Agent
   ↓
Front-side APIM boundary telemetry
   ↓
Foundry Agent Service
   ↓
Required operational storage
Azure Cosmos DB
   ↓
Back-side APIM boundary telemetry for Snowflake MCP calls
   ↓
Snowflake MCP / Cortex Agent / semantic views

Reporting / analytics projection
   ↓
Azure SQL DB, Fabric, or both
```

The customer can still use Azure SQL Database, but it should be implemented as a **reporting, analytics, audit, and operational intelligence store**, not as the Foundry runtime state store. APIM can also be used as a **boundary telemetry collection point**, but it should not be treated as a replacement for Cosmos DB or Foundry/Application Insights observability.

The strongest reporting architecture combines four telemetry/data sources:

| Source | Role |
|---|---|
| Cosmos DB | Foundry operational conversation and agent state store. |
| APIM | Boundary telemetry, prompt/response capture if approved, MCP call telemetry, correlation IDs, HTTP status codes, gateway-observed latency. |
| Application Insights / Foundry tracing | Token usage, model/tool latency, tool execution, errors, success rates, evaluation outcomes. |
| Snowflake query history / MCP telemetry | Snowflake role validation, semantic-view usage, query correctness, warehouse/query performance. |

---

## 2. Key Decisions

### Can Azure SQL DB replace Cosmos DB for Foundry Agent Service storage?

**No.** Azure SQL DB should not be used as a replacement for the Cosmos DB storage that is deployed as part of the Foundry Standard/custom/private project.

### Can Cosmos DB be turned off?

**No.** Cosmos DB remains a required operational dependency for the Foundry Agent Service project. Turning it off, removing it, or breaking its network connectivity can break the agent runtime.

### Can Azure SQL DB be used for reporting over Foundry interactions?

**Yes.** Azure SQL DB can be added as a downstream reporting database that receives selected or transformed data from Cosmos DB, APIM, Application Insights / Azure Monitor, and Snowflake telemetry.

### Can Fabric Mirroring be used instead of a trigger-based copy process?

**Yes, if the goal is analytics over Cosmos DB data in Fabric.** Microsoft Fabric supports mirroring Azure Cosmos DB for NoSQL into OneLake. This gives SQL-style analytics access through Fabric, but it does **not** mirror Cosmos DB directly into Azure SQL DB.

### Can APIM write the user prompt, answer, and performance metadata to Azure SQL DB?

**Yes, but not directly as a SQL client.** APIM policies can emit request/response telemetry to Event Hubs, Service Bus, or a private HTTP telemetry collector. A downstream service such as Azure Functions, Logic Apps, Stream Analytics, Fabric Eventstream, or a small Container App should validate, redact, enrich, and write curated records to Azure SQL DB.

Recommended ingestion choices:

1. Cosmos DB Change Feed to Azure Function to Azure SQL DB.
2. Azure Data Factory or Fabric Data Factory Copy Activity from Cosmos DB to Azure SQL DB.
3. APIM boundary telemetry to Event Hub / Service Bus / telemetry API, then to Azure SQL DB.
4. Application Insights / Azure Monitor export or query-based extraction to reporting tables.
5. A scheduled or event-driven ETL process that normalizes raw operational documents into curated SQL reporting tables.

### Can APIM replace Cosmos DB?

**No.** APIM can capture boundary traffic, but Cosmos DB remains the required Foundry operational store for threads, messages, and agent state.

---

## 3. Recommended Architecture

### 3.1 Platform Operational Store

```text
Microsoft 365 Copilot Chat or Foundry Client
        ↓
Foundry Agent Service
        ↓
Azure Cosmos DB
  - enterprise_memory database
  - thread-message-store container
  - system-thread-message-store container
  - agent-entity-store container
```

Cosmos DB remains the platform-owned operational store. Foundry expects this storage layer to be available and should be treated as part of the runtime service.

### 3.2 Reporting and Analytics Store

```text
Azure Cosmos DB
        ↓
Data projection mechanism
        ↓
Azure SQL DB and/or Microsoft Fabric
        ↓
Power BI, SQL queries, compliance reports, operational dashboards
```

The reporting layer should be modeled for analytics rather than as a raw replica of the Foundry storage containers.

### 3.3 APIM Boundary Telemetry Layer

Because Comcast UDX expects APIM on both sides of Foundry, APIM should be treated as a separate telemetry source. It can capture what crosses the API boundary, including user request metadata, request and response bodies when approved, correlation IDs, HTTP status codes, routing metadata, Snowflake MCP tool requests, and Snowflake MCP responses.

```text
M365 Copilot / custom engine agent
   ↓
Front-side APIM
   ├── validate caller / claims
   ├── stamp correlation ID
   ├── optionally capture user prompt
   └── route to Foundry private endpoint

Foundry Agent Service
   ├── Cosmos DB operational store
   ├── Application Insights / Foundry tracing
   └── MCP tool call

Back-side APIM
   ├── capture MCP tool name and request metadata
   ├── capture Snowflake role / domain hint if passed
   ├── capture MCP response metadata
   └── route to Snowflake MCP

Telemetry pipeline
   APIM events
      ↓
   Event Hub, Service Bus, or telemetry API
      ↓
   Azure Function / Logic App / Stream processor
      ↓
   Azure SQL DB reporting schema
```

APIM telemetry should be correlated with Cosmos DB conversation state and Application Insights / Foundry traces. APIM is best at **boundary telemetry**; Cosmos DB is best at **Foundry operational memory**; Application Insights is best at **runtime performance, latency, tool, token, and evaluation telemetry**.

---

## 4. What Data Exists in Cosmos DB?

In a Foundry Standard/custom/private deployment, the Cosmos DB database is typically named:

```text
enterprise_memory
```

The key containers are:

| Container | Purpose | Reporting usefulness |
|---|---|---|
| `thread-message-store` | Stores user and assistant conversation messages. | Primary source for user questions and model responses. |
| `system-thread-message-store` | Stores internal system messages and orchestration details. | Useful for troubleshooting, but may contain sensitive/internal platform details. |
| `agent-entity-store` | Stores agent metadata and model input/output records. | Useful for model behavior review, agent configuration analysis, and debugging. |

The exact document shape should be treated as platform-owned and subject to change. For reporting, use a conservative extraction approach:

1. Store the raw Cosmos DB document as JSON.
2. Extract stable fields into curated reporting columns.
3. Build downstream tables and views for analytics.
4. Do not depend on raw internal document shapes as a long-term reporting contract.

---

## 5. APIM Boundary Telemetry Pattern

### 5.1 When to use

Use the APIM boundary telemetry pattern when Comcast UDX wants to capture the API-layer view of the conversation and Snowflake tool path:

- The user request as it enters the Foundry boundary.
- The Foundry response as it returns to the M365/custom engine agent boundary.
- The MCP tool request from Foundry toward Snowflake.
- The Snowflake MCP response, status code, and tool error metadata.
- The selected Snowflake role, domain, or semantic-view hint if those values are passed as headers, claims, or request fields.
- Gateway-observed latency and HTTP status codes.

### 5.2 Recommended APIM emission options

| APIM emission option | Best for | Notes |
|---|---|---|
| `log-to-eventhub` | High-volume analytics and near-real-time reporting | Strong default choice for boundary telemetry. |
| `send-service-bus-message` | Reliable enterprise messaging, queues, topics, dead-letter handling | Useful when audit events need stronger retry semantics; policy is documented as preview. |
| `send-one-way-request` | Fire-and-forget call to a private telemetry API | Good when a custom collector redacts, enriches, and validates records before SQL. |
| `send-request` | Synchronous enrichment or validation call | Use carefully; this waits for a response and can add user-facing latency. |

### 5.3 What APIM can capture well

APIM is a good source for:

- Correlation ID.
- User identity claims visible to APIM.
- API operation and route.
- HTTP method and path.
- Request timestamp.
- Response timestamp.
- Gateway-observed duration.
- HTTP status code.
- Request body, if logging full prompts is approved.
- Response body, if logging answers is approved.
- MCP request and response payloads.
- Snowflake MCP tool name.
- Snowflake role or domain hint if carried in headers/body.
- Policy outcomes such as authorization failure, rate limit, or routing decision.

### 5.4 What APIM does not replace

APIM is not a replacement for:

- Cosmos DB thread/message storage.
- Foundry internal run state.
- Full agent traces.
- Token counts, unless returned in headers/body or captured from Foundry telemetry.
- Model evaluation scores.
- Groundedness, correctness, or response quality assessments.
- Internal tool retries that never cross the APIM boundary.

Use Application Insights / Foundry observability for token usage, latency, tool execution, cost, retries, success rates, and evaluation outcomes.

### 5.5 Full-body logging caution

Full prompts, answers, and Snowflake MCP results may contain sensitive Finance, Sales, and HR data. Default to metadata logging and only enable full-body capture after security and privacy approval.

Recommended default APIM event payload:

```json
{
  "event_type": "foundry_request_or_response",
  "correlation_id": "...",
  "timestamp_utc": "...",
  "source_gateway": "front-apim-or-back-apim",
  "api_name": "...",
  "operation_name": "...",
  "user_id": "...",
  "agent_id": "...",
  "thread_id": "...",
  "domain": "Finance|Sales|HR|Other",
  "mcp_tool_name": "...",
  "snowflake_role": "...",
  "status_code": 200,
  "duration_ms": 1234,
  "payload_logged": false,
  "payload_hash": "...",
  "error_code": null,
  "error_message": null
}
```

Only add `request_body`, `response_body`, or `mcp_result_body` fields when explicitly approved and protected with encryption, RBAC, retention, masking, and audit controls.

### 5.6 APIM policy body handling gotcha

If an APIM policy reads the request or response body, use `preserveContent: true`. Without that setting, reading the body can consume it and affect downstream processing.

```xml
<set-variable name="requestBody"
  value="@(context.Request.Body.As<string>(preserveContent: true))" />

<set-variable name="responseBody"
  value="@(context.Response.Body.As<string>(preserveContent: true))" />
```

### 5.7 Example APIM to Event Hub policy

This is a conceptual example. It should be hardened before production use with redaction, truncation, allowlisting, error handling, and security review.

```xml
<policies>
  <inbound>
    <base />

    <set-variable name="correlationId" value="@(Guid.NewGuid().ToString())" />
    <set-variable name="requestBody"
      value="@(context.Request.Body.As<string>(preserveContent: true))" />

    <set-header name="x-correlation-id" exists-action="override">
      <value>@((string)context.Variables["correlationId"])</value>
    </set-header>

    <log-to-eventhub logger-id="foundry-boundary-eventhub">
      @{ 
        return Newtonsoft.Json.JsonConvert.SerializeObject(new {
          event_type = "foundry_inbound_request",
          correlation_id = (string)context.Variables["correlationId"],
          timestamp_utc = DateTime.UtcNow.ToString("o"),
          api_name = context.Api?.Name,
          operation_name = context.Operation?.Name,
          request_url = context.Request.Url.ToString(),
          method = context.Request.Method,
          user_id = context.User?.Id,
          subscription_id = context.Subscription?.Id,
          client_ip = context.Request.IpAddress,
          request_body = (string)context.Variables["requestBody"]
        });
      }
    </log-to-eventhub>
  </inbound>

  <backend>
    <base />
  </backend>

  <outbound>
    <base />

    <set-variable name="responseBody"
      value="@(context.Response.Body.As<string>(preserveContent: true))" />

    <log-to-eventhub logger-id="foundry-boundary-eventhub">
      @{ 
        return Newtonsoft.Json.JsonConvert.SerializeObject(new {
          event_type = "foundry_outbound_response",
          correlation_id = (string)context.Variables["correlationId"],
          timestamp_utc = DateTime.UtcNow.ToString("o"),
          status_code = context.Response.StatusCode,
          response_body = (string)context.Variables["responseBody"]
        });
      }
    </log-to-eventhub>
  </outbound>

  <on-error>
    <base />

    <log-to-eventhub logger-id="foundry-boundary-eventhub">
      @{ 
        var correlationId = context.Variables.ContainsKey("correlationId")
          ? (string)context.Variables["correlationId"]
          : Guid.NewGuid().ToString();

        return Newtonsoft.Json.JsonConvert.SerializeObject(new {
          event_type = "foundry_boundary_error",
          correlation_id = correlationId,
          timestamp_utc = DateTime.UtcNow.ToString("o"),
          error_message = context.LastError?.Message,
          error_source = context.LastError?.Source,
          error_reason = context.LastError?.Reason
        });
      }
    </log-to-eventhub>
  </on-error>
</policies>
```

---

## 6. Azure SQL Reporting Store Pattern

### 6.1 When to use

Use Azure SQL DB when the customer explicitly wants:

- A familiar relational database for audit and reporting.
- SQL Server-style tables, views, stored procedures, and security models.
- Existing SQL-based reporting skills and operational support.
- A reporting store that can be queried outside of Fabric.

### 6.2 Architecture

```text
Foundry Agent Service
   ↓
Azure Cosmos DB
   ↓
Cosmos DB Change Feed / Azure Function / Data Factory
   ↓
Azure SQL Database
   ↓
Power BI / SQL reports / operational dashboards

APIM
   ↓
Event Hub / Service Bus / telemetry API
   ↓
Azure Function / Logic App / Container App
   ↓
Azure SQL Database
```

### 6.3 Recommended reporting schema

Suggested SQL tables:

| Table | Purpose |
|---|---|
| `foundry_audit.raw_agent_events` | Raw Cosmos DB records retained as JSON for audit/schema drift protection. |
| `foundry_audit.fact_agent_message` | One row per user/assistant/system/tool message. |
| `foundry_audit.fact_agent_turn` | One row per user question and assistant answer pair. |
| `foundry_boundary.raw_apim_event` | Raw APIM boundary event as JSON. |
| `foundry_boundary.fact_mcp_tool_call` | One row per Snowflake MCP tool call captured at the back-side APIM boundary. |
| `foundry_audit.fact_agent_evaluation` | Automated or human evaluation scores. |
| `foundry_audit.dim_agent_user` | User, department, business unit, role metadata. |
| `foundry_audit.dim_agent_domain` | Finance, Sales, HR, semantic view, and data owner metadata. |

Example APIM raw event table:

```sql
CREATE SCHEMA foundry_boundary;
GO

CREATE TABLE foundry_boundary.raw_apim_event (
    event_id            bigint IDENTITY(1,1) PRIMARY KEY,
    event_type          nvarchar(100) NOT NULL,
    correlation_id      nvarchar(100) NULL,
    event_time_utc      datetime2 NOT NULL,
    source_gateway      nvarchar(100) NULL,
    api_name            nvarchar(256) NULL,
    operation_name      nvarchar(256) NULL,
    user_id             nvarchar(512) NULL,
    client_ip           nvarchar(100) NULL,
    status_code         int NULL,
    duration_ms         int NULL,
    raw_json            nvarchar(max) NOT NULL,
    ingested_time_utc   datetime2 NOT NULL DEFAULT SYSUTCDATETIME()
);
GO
```

Example MCP tool-call table:

```sql
CREATE TABLE foundry_boundary.fact_mcp_tool_call (
    tool_call_id            bigint IDENTITY(1,1) PRIMARY KEY,
    correlation_id          nvarchar(100) NOT NULL,
    user_id                 nvarchar(512) NULL,
    mcp_tool_name           nvarchar(256) NULL,
    snowflake_role          nvarchar(256) NULL,
    semantic_view_name      nvarchar(256) NULL,
    request_time_utc        datetime2 NULL,
    response_time_utc       datetime2 NULL,
    duration_ms             int NULL,
    status_code             int NULL,
    error_code              nvarchar(100) NULL,
    error_message           nvarchar(max) NULL,
    request_summary         nvarchar(max) NULL,
    response_summary        nvarchar(max) NULL,
    created_time_utc        datetime2 NOT NULL DEFAULT SYSUTCDATETIME()
);
GO
```

---

## 7. Fabric Mirroring Pattern

Use Fabric Mirroring when the customer wants:

- Near-real-time analytics over Cosmos DB data.
- SQL-style querying without building a custom ingestion service.
- Power BI reporting through Fabric and OneLake.
- A lakehouse-style analytics pattern.

Architecture:

```text
Foundry Agent Service
   ↓
Azure Cosmos DB
   ↓
Microsoft Fabric Mirroring
   ↓
OneLake Delta Tables
   ↓
Fabric SQL Analytics Endpoint / Power BI / Notebooks
```

Gotchas:

- Fabric Mirroring does not create an Azure SQL Database copy.
- Mirrored data lands in Fabric OneLake, not Azure SQL DB.
- The Cosmos DB account may need compatible continuous backup settings.
- Private networking and OneLake security requirements must be reviewed carefully.
- This is an analytics pattern, not a replacement for Foundry operational storage.

---

## 8. What the Customer Can Analyze

The customer wants to understand how users are interacting with the Foundry agent. The reporting layer should support the following types of analysis.

### 8.1 Usage Analytics

- How many questions were asked?
- How many active users are using the agent?
- Who is asking the most questions?
- What are the busiest days and times?
- Which business domains are most frequently queried?
- Are users asking Finance, Sales, HR, or general questions?
- Which users or departments have the highest adoption?

### 8.2 Performance Analytics

- Average response time.
- P50 / P90 / P95 latency.
- Front-side APIM observed latency.
- Back-side APIM Snowflake MCP latency.
- Foundry model latency from Application Insights.
- Tool-call duration.
- Snowflake MCP duration.
- Error rate.
- Timeout rate.
- Token usage.
- Cost estimate by user/domain/agent.

### 8.3 Quality Analytics

- Did the answer cite or explain the metric correctly?
- Was the answer grounded in Snowflake results?
- Did the model make unsupported claims?
- Did the agent call the correct Finance, Sales, or HR semantic view?
- Did the model ask a clarifying question when the user request was ambiguous?
- Was the answer complete, relevant, and useful?

### 8.4 Data Source Improvement Analytics

- Questions with no matching semantic view.
- Questions where users rephrased multiple times.
- Questions that caused tool errors.
- Questions where the model said data was unavailable.
- Most requested metrics not currently covered.
- Semantic view usage by domain.
- Snowflake role or permission failures.

---

## 9. Quality Evaluation Framework

Cosmos DB and APIM can show **what was asked and answered**. They do not prove whether the answer was correct. To evaluate quality, build a separate evaluation layer.

Recommended evaluation approach:

1. Create golden question sets for Finance, Sales, and HR.
2. Define the expected semantic view and approved SQL or Snowflake result for each test question.
3. Capture the actual tool call and response.
4. Compare the assistant answer to the expected result.
5. Score groundedness, correctness, completeness, relevance, and safety.
6. Send low-confidence or sensitive responses to a human review queue.

Example golden question structure:

```text
Question: What was revenue last quarter by region?
Expected domain: Finance
Expected semantic view: FINANCE_REVENUE_SEMANTIC_VIEW
Expected filters: Last fiscal quarter
Expected output fields: Region, Revenue
Validation SQL: Approved deterministic SQL
Tolerance: Exact or defined variance threshold
```

---

## 10. Implementation Steps

### Step 1 — Keep Cosmos DB in place

Validate the Foundry-created Cosmos DB database and containers:

```text
enterprise_memory
  - thread-message-store
  - system-thread-message-store
  - agent-entity-store
```

Do not remove Cosmos DB, disable it, or attempt to point Foundry thread storage to Azure SQL DB.

### Step 2 — Create Azure SQL DB reporting store

Create an Azure SQL logical server and Azure SQL Database. For private environments, configure:

- Private endpoint.
- Private DNS zone.
- Public access disabled, if required.
- Microsoft Entra authentication.
- Auditing and Defender settings, if required by the customer.

### Step 3 — Define correlation IDs

Create or accept a correlation ID at the first APIM boundary and pass it through:

```text
M365 custom engine agent → APIM → Foundry → APIM → Snowflake MCP
```

Recommended headers or fields:

```text
x-correlation-id
x-foundry-session-id
x-agent-id
x-business-domain
x-snowflake-role
```

### Step 4 — Configure APIM telemetry emission

Choose the right telemetry sink:

```text
Preferred analytics path:
APIM log-to-eventhub → Event Hub → Azure Function/Stream Analytics/Fabric Eventstream → Azure SQL DB

Preferred reliability path:
APIM send-service-bus-message → Service Bus → Azure Function → Azure SQL DB

Preferred custom-control path:
APIM send-one-way-request → Private telemetry API → Azure SQL DB
```

### Step 5 — Configure APIM managed identity

Use managed identity where possible.

For Event Hub:

- Enable system-assigned or user-assigned managed identity on APIM.
- Grant the identity the required Event Hubs sender permissions.
- Configure the APIM logger to use managed identity.

For Service Bus:

- Enable managed identity on APIM.
- Grant the identity `Azure Service Bus Data Sender` on the queue or topic.
- Configure the `send-service-bus-message` policy.

For a private telemetry API:

- Protect the telemetry API with Entra ID.
- Use APIM managed identity authentication to call the API.
- Keep the telemetry API private where possible.

### Step 6 — Build the ingestion service

The ingestion service should:

- Validate the event schema.
- Reject or quarantine malformed events.
- Redact sensitive fields.
- Truncate large fields.
- Hash or tokenize prompt/response text if full-text retention is not allowed.
- Enrich events with domain, agent name, environment, and route metadata.
- Write raw JSON to `foundry_boundary.raw_apim_event`.
- Write curated rows to `fact_agent_turn` and `fact_mcp_tool_call`.

### Step 7 — Ingest Cosmos DB data

For Cosmos-to-SQL reporting, choose one or more of the following:

- Cosmos DB Change Feed to Azure Function to Azure SQL DB.
- Azure Data Factory Copy Activity.
- Fabric Data Factory pipeline.
- Fabric Mirroring if the target is Fabric/OneLake instead of Azure SQL DB.

### Step 8 — Enable Foundry/Application Insights telemetry

Use Foundry observability and Application Insights to capture:

- Token usage.
- Latency.
- Success rates.
- Tool usage.
- Tool errors.
- Evaluation outcomes.
- Runtime exceptions.

### Step 9 — Join APIM, Cosmos, Application Insights, and Snowflake telemetry

Use the curated model to join:

```text
APIM boundary telemetry
   + Cosmos DB thread/message data
   + Application Insights / Foundry traces
   + Snowflake query history / MCP response metadata
```

This combined view supports the customer’s most important questions:

- What did users ask?
- What answer did they receive?
- Which domain was involved?
- Which Snowflake role and semantic view were used?
- How long did the overall request take?
- How long did the Snowflake MCP call take?
- Did the tool call fail?
- Was the answer grounded and correct?

### Step 10 — Test failure cases

Test and validate:

- APIM logging does not break the user request if Event Hub, Service Bus, telemetry API, or SQL is unavailable.
- Body logging does not consume the request/response payload.
- Sensitive headers are not logged.
- Large responses are truncated or summarized safely.
- Correlation IDs appear in all relevant systems.
- APIM can reach private Foundry and private Snowflake/APIM backends according to the selected APIM networking tier.

---

## 11. Security and Privacy Considerations

### 11.1 Sensitive Content

Conversation data may contain sensitive business information. HR and Finance questions are especially sensitive.

Controls to apply:

- Restrict access to raw message tables.
- Mask or redact sensitive text where appropriate.
- Separate raw audit data from business-friendly reporting views.
- Apply row-level security for department or domain-based reporting.
- Avoid exposing system messages broadly.
- Avoid logging OAuth tokens, authorization headers, cookies, client secrets, or connection strings.

### 11.2 Raw JSON Handling

Store raw JSON for auditability and schema drift protection, but control access carefully.

Recommended pattern:

```text
Raw Cosmos/APIM data → restricted technical/audit access only
Curated reporting tables → analytics team access
Aggregated dashboards → business stakeholder access
```

### 11.3 Identity and RBAC

For user-level reporting, confirm which identity is stored in Cosmos DB, which identity is visible at APIM, and which identity appears in Application Insights traces.

Validate:

- User ID.
- UPN or object ID.
- Agent ID.
- Thread ID.
- Snowflake role used, if available from APIM, tool telemetry, or Snowflake query history.

### 11.4 Private Networking

If the Foundry project is private, the reporting ingestion layer must also respect the private architecture.

Validate private connectivity for:

- Cosmos DB private endpoint.
- Azure SQL DB private endpoint.
- APIM inbound private endpoint and/or VNet mode, depending on tier.
- Function App / Container App / Logic App network integration.
- DNS resolution from the integration runtime or function runtime.
- Application Insights ingestion strategy, if private monitoring is required.

---

## 12. Gotchas and Watch Areas

| Gotcha | Why it matters | Recommendation |
|---|---|---|
| Cosmos DB cannot be replaced by Azure SQL DB | Foundry depends on Cosmos DB for operational state. | Keep Cosmos DB as the system of record for Foundry runtime. |
| Cosmos DB cannot be replaced by APIM | APIM can capture HTTP boundary events, not internal Foundry state. | Use APIM as boundary telemetry only. |
| APIM should not synchronously depend on SQL | SQL outages could impact user-facing agent calls. | Emit to Event Hub, Service Bus, or a telemetry API and write to SQL asynchronously. |
| APIM body logging can consume payloads | Reading request/response bodies in policy can affect downstream processing if not preserved. | Use `preserveContent: true` whenever reading bodies in APIM policies. |
| APIM telemetry is boundary-only | APIM cannot see internal Foundry run steps that do not cross the gateway. | Combine APIM telemetry with Cosmos DB and Foundry/Application Insights tracing. |
| APIM diagnostic payload limits may truncate body content | Large prompts/responses can exceed logging limits. | Use custom Event Hub events, controlled truncation, hashing, and summarization. |
| Cosmos document schema may evolve | Direct reporting on raw containers may break. | Store raw JSON and build curated projection tables. |
| Cosmos DB is not full observability | It stores conversation data, not all runtime metrics. | Combine with Application Insights / Azure Monitor. |
| Full prompt/answer logging is sensitive | HR, Finance, and Sales prompts may contain regulated or confidential data. | Default to metadata logging and require explicit approval for full-content capture. |
| Response quality cannot be proven from Cosmos alone | Cosmos shows the answer, not whether it was correct. | Use automated evaluations and golden question test sets. |
| Latency is better captured in telemetry | Message timestamps may only approximate response time. | Use Application Insights traces and APIM boundary timing. |
| Role and identity mapping may be incomplete | Need to know which user and Snowflake role were used. | Join Cosmos data with App Insights, APIM back-side telemetry, and Snowflake query history. |
| Fabric Mirroring does not create Azure SQL DB | It mirrors to OneLake/Fabric, not Azure SQL DB. | Use mirroring for Fabric analytics; use ETL for Azure SQL DB. |
| Private networking can complicate ingestion | Functions/Data Factory/APIM must reach private endpoints. | Validate VNet integration, private DNS, and APIM tier capabilities. |

---

## 13. Recommended Comcast UDX Pattern

For Comcast UDX, the strongest pattern is:

```text
M365 Copilot / custom engine agent
   ↓
Front-side APIM
   ↓
Foundry Agent Service
   ↓
Cosmos DB operational store
   ↓
Back-side APIM
   ↓
Snowflake MCP / Cortex Agent / semantic views

Reporting projections:

Cosmos DB
   ↓
Conversation analytics projection
   ↓
Azure SQL DB or Fabric

APIM boundary telemetry
   ↓
Event Hub / Service Bus / telemetry API
   ↓
Azure SQL DB or Fabric

Application Insights / Azure Monitor
   ↓
Operational telemetry projection
   ↓
Azure SQL DB or Fabric

Snowflake Query History / MCP telemetry
   ↓
Data correctness, role validation, and tool performance analytics
```

Use Cosmos DB for the conversation record, APIM for boundary telemetry and correlation, Application Insights for operational telemetry, and Snowflake query history for data access validation.

---

## 14. Final Recommendation

The recommended approach is:

1. Keep Cosmos DB as the required Foundry operational store.
2. Do not attempt to replace Cosmos DB with Azure SQL DB or APIM.
3. Add Azure SQL DB only as a downstream reporting and analytics database if the customer requires SQL Server-style access.
4. Use APIM as a boundary telemetry and correlation mechanism on both sides of Foundry.
5. Send APIM telemetry asynchronously to Event Hub, Service Bus, or a private telemetry API, then into Azure SQL DB.
6. Consider Fabric Mirroring if the customer is comfortable with Fabric and wants low-code analytics over Cosmos DB.
7. Combine Cosmos DB data with APIM telemetry and Application Insights telemetry to measure both what users asked and how the agent performed.
8. Build a quality evaluation layer to determine whether model responses were correct, grounded, and useful.
9. Protect raw prompts, responses, Snowflake results, and system messages as sensitive operational data.

In short:

```text
Cosmos DB = Foundry operational memory and conversation state
APIM = boundary telemetry, correlation, request/response and MCP-path audit
Azure SQL DB = optional curated reporting and audit projection
Fabric Mirroring = optional low-code analytics path
Application Insights = performance, token, tool, evaluation, and observability source
Snowflake Query History = data access and correctness validation source
```

---

## 15. Reference Links

The following Microsoft documentation areas are relevant to this design:

- Azure AI Foundry standard agent setup: https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/standard-agent-setup
- Azure Cosmos DB integration with Foundry Agent Service: https://learn.microsoft.com/en-us/azure/cosmos-db/gen-ai/azure-agent-service
- BYO thread storage containers for Foundry Agent Service: https://devblogs.microsoft.com/cosmosdb/azure-ai-foundry-connection-for-azure-cosmos-db-and-byo-thread-storage-in-azure-ai-agent-service/
- Azure AI Foundry observability concepts: https://learn.microsoft.com/en-us/azure/foundry/concepts/observability
- Foundry Agent Monitoring Dashboard: https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/how-to-monitor-agents-dashboard
- APIM `log-to-eventhub` policy: https://learn.microsoft.com/en-us/azure/api-management/log-to-eventhub-policy
- APIM Event Hub logging setup with managed identity: https://learn.microsoft.com/en-us/azure/api-management/api-management-howto-log-event-hubs
- APIM `send-one-way-request` policy: https://learn.microsoft.com/en-us/azure/api-management/send-one-way-request-policy
- APIM `send-service-bus-message` policy: https://learn.microsoft.com/en-us/azure/api-management/send-service-bus-message-policy
- APIM `send-request` policy: https://learn.microsoft.com/en-us/azure/api-management/send-request-policy
- APIM `set-body` policy and `preserveContent`: https://learn.microsoft.com/en-us/azure/api-management/set-body-policy
- APIM monitoring and gateway log limits: https://learn.microsoft.com/en-us/azure/api-management/monitor-api-management
- APIM virtual network concepts: https://learn.microsoft.com/en-us/azure/api-management/virtual-network-concepts
- APIM inbound private endpoint: https://learn.microsoft.com/en-us/azure/api-management/private-endpoint
- Azure SQL Database private endpoint overview: https://learn.microsoft.com/en-us/azure/azure-sql/database/private-endpoint-overview
- Azure Private Endpoint overview: https://learn.microsoft.com/en-us/azure/private-link/private-endpoint-overview
