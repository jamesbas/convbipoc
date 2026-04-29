# UDX: Publishing a **Private** Azure AI Foundry Agent to **Microsoft 365 Copilot Chat** — Issues, Remedies, and Code Templates

> **Context (UDX current state):** The UDX Azure AI Foundry Project is deployed with **Public Network Access disabled** and uses **Private Endpoints** (network-isolated). This was discovered when attempting to publish the Foundry agent to **Microsoft 365 Copilot Chat** from the Foundry portal and receiving a warning that prevents publishing.

---

## 1) Problem Summary

### What you’re trying to do
Publish a Foundry agent so it can be used in **Microsoft 365 Copilot Chat**.

### What Foundry “Publish to Microsoft 365 Copilot” does
Publishing from the Foundry portal publishes an agent’s **stable endpoint** so users can discover and interact with the agent in **Microsoft 365 Copilot** and **Teams**. citeturn22search173

### Why it breaks in a private-only Foundry project
With network isolation, inbound access to the Foundry project is controlled by the **Public Network Access (PNA) flag**. When PNA is disabled, access requires a **private endpoint**. citeturn22search190

Because Microsoft 365 Copilot is a SaaS service outside your private VNet boundary, it typically cannot reach a private-only endpoint. So the publish flow that expects a reachable stable endpoint cannot complete successfully.

> **Important:** The sources describe what publishing is (stable endpoint) and how PNA/private endpoints control access. citeturn22search173turn22search190 The conclusion that M365 Copilot cannot reach private-only endpoints is an architectural implication of those constraints.

---

## 2) Root Cause (Technical)

Foundry network isolation is designed to:
- Control **inbound access** to Foundry via PNA (public vs private) citeturn22search190
- Support private endpoints / private networking setups for agent environments citeturn22search185turn22search190

Publishing to M365 requires an endpoint M365 can call. When Foundry is private-only, M365 can’t directly call it (it’s not on your VNet).

---

## 3) Solution Options (Simplest → Most Complex)

### Option 1 — Enable Foundry **Public Network Access** (Simplest)

**What:** Switch the Foundry project’s PNA from **Disabled** to **Enabled** (or equivalent), then publish from Foundry to M365 Copilot.

- Foundry supports controlling inbound access via the **PNA flag**, including an intermediate option of **Enabled from selected IP addresses** (where available). citeturn22search190
- Publishing from Foundry is supported in the portal workflow. citeturn22search173

**Benefits**
- Fastest path; minimal new components.
- Uses the built-in Foundry publishing workflow.

**Pros**
- Lowest implementation effort.
- No additional hosting layer to operate.

**Cons**
- Public exposure of the agent endpoint (even if secured with auth/RBAC).
- May not satisfy strict Tier 3/4 network isolation expectations.

**Best for**
- Rapid pilots where Cyber accepts a public endpoint protected by identity controls.

---

### Option 2 — “Public enabled from **selected IP addresses**” (Low complexity)

**What:** Keep Foundry generally private, but allow inbound access from selected IP ranges (where supported), and publish.

- Foundry documents an inbound setting between public and private: **Enabled from selected IP addresses**. citeturn22search190

**Benefits**
- Smaller exposure surface than fully public.

**Pros**
- Still relatively simple.

**Cons**
- Microsoft 365 Copilot traffic does not come from a small static set of customer IPs in most enterprise networks. In practice, IP allowlisting SaaS traffic can be challenging.
- May still fail if M365 calls originate from broader service ranges not allowlisted.

**Best for**
- Scenarios where you have a workable allowlist strategy and governance acceptance.

---

### Option 3 — **Bare-minimum Private Foundry** using Copilot Studio + Azure Function Proxy (**Recommended Minimal “Path B”**)

**What:** Keep Foundry private. Instead of using Foundry’s built-in publish, publish a **Copilot Studio** agent to Copilot Chat, and have it call a **public Azure Function** that forwards requests to the **private Foundry agent endpoint**.

**High-level flow**

```
M365 Copilot Chat
  → Copilot Studio agent (thin router)
    → Azure Function (public HTTPS endpoint)
      → Foundry agent endpoint (private endpoint)
        → Snowflake MCP tools (private)
```

**Why it works**
- Copilot Chat can reach public HTTPS endpoints.
- The Azure Function can be VNet-integrated so it can reach the private Foundry endpoint.

**Benefits**
- Preserves private networking posture for Foundry.
- Minimal additional moving parts compared to a full APIM + SDK stack.

**Pros**
- Smallest viable “private Foundry + Copilot Chat” architecture.
- Clear boundary-control story for security reviews.

**Cons**
- Not using Foundry’s one-click publish flow.
- Need to build/operate one lightweight Azure Function.

**Best for**
- UDX’s current state (private Foundry project) with the smallest “bridge” to Copilot Chat.

#### 3.1 Azure Function Proxy — Minimal Working Code

> This is the minimal proxy that forwards request bodies to Foundry. **For a production deployment**, add authentication (Entra JWT validation, OBO, etc.) and input validation.

**.NET 6 isolated Azure Function (single endpoint)**

`udx-agent-proxy.csproj`
```xml
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net6.0</TargetFramework>
    <AzureFunctionsVersion>v4</AzureFunctionsVersion>
  </PropertyGroup>
  <ItemGroup>
    <PackageReference Include="Microsoft.Azure.Functions.Worker" Version="1.16.0" />
    <PackageReference Include="Microsoft.Azure.Functions.Worker.Sdk" Version="1.16.0" OutputItemType="Analyzer" />
    <PackageReference Include="Microsoft.Azure.Functions.Worker.Extensions.Http" Version="3.1.0" />
  </ItemGroup>
</Project>
```

`Program.cs`
```csharp
using Microsoft.Extensions.Hosting;

var host = new HostBuilder()
    .ConfigureFunctionsWorkerDefaults()
    .Build();

host.Run();
```

`ProxyFunction.cs`
```csharp
using System.Net;
using System.Net.Http.Headers;
using Microsoft.Azure.Functions.Worker;
using Microsoft.Azure.Functions.Worker.Http;

public class ProxyFunction
{
    private readonly HttpClient _client = new HttpClient();

    [Function("proxy")]
    public async Task<HttpResponseData> Run(
        [HttpTrigger(AuthorizationLevel.Function, "post")] HttpRequestData req)
    {
        string requestBody = await new StreamReader(req.Body).ReadToEndAsync();
        var foundryEndpoint = Environment.GetEnvironmentVariable("FOUNDRY_ENDPOINT");

        var request = new HttpRequestMessage(HttpMethod.Post, foundryEndpoint)
        {
            Content = new StringContent(requestBody)
        };
        request.Content.Headers.ContentType = new MediaTypeHeaderValue("application/json");

        // PoC: forward as-is.
        // Production: validate Entra JWT from Copilot Studio, then do OBO/Managed Identity before calling Foundry.

        var response = await _client.SendAsync(request);
        var responseContent = await response.Content.ReadAsStringAsync();

        var output = req.CreateResponse(HttpStatusCode.OK);
        output.Headers.Add("Content-Type", "application/json");
        await output.WriteStringAsync(responseContent);
        return output;
    }
}
```

`local.settings.json` (for local test)
```json
{
  "IsEncrypted": false,
  "Values": {
    "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    "FUNCTIONS_WORKER_RUNTIME": "dotnet-isolated",
    "FOUNDRY_ENDPOINT": "https://<PRIVATE-FOUNDRY-ENDPOINT>"
  }
}
```

**Networking requirements (minimal)**
- Function must be able to resolve and reach the **private Foundry endpoint**.
- If Foundry uses Private Link / private endpoints, configure **VNet integration** for the Function and ensure appropriate **private DNS** resolution.

**References for private networking setup concepts**
- Foundry network isolation and private endpoint usage citeturn22search190
- Private networking setup for Foundry Agent Service (standard private networking) citeturn22search185

#### 3.2 Copilot Studio “Thin Router” Configuration (Conceptual)

Copilot Studio’s job in this pattern is **not to be the brain**. Foundry remains the brain.

- Copilot Studio receives the user message in M365 Copilot Chat.
- Copilot Studio calls the HTTP tool (Azure Function).
- Azure Function forwards to Foundry.

**Conceptual HTTP tool definition** (Copilot Studio is UI-driven; this shows the equivalent intent)
```json
{
  "tool": {
    "name": "Call UDX Foundry Finance Agent",
    "type": "http",
    "method": "POST",
    "url": "https://<your-function>.azurewebsites.net/api/proxy",
    "headers": {"Content-Type": "application/json"},
    "body": {"query": "{{user_input}}"}
  }
}
```

**Pros**
- Copilot Studio stays minimal.

**Cons**
- Copilot Studio setup is mostly via UI; export formats vary by environment.

---

### Option 4 — Add **APIM** in front of the Function (More secure, more ops)

**What:** Keep Option 3, but put Azure API Management in front of the Function.

```
Copilot Studio → APIM (public) → Function → Private Foundry
```

**Benefits**
- Centralized controls (rate limiting, request validation, auth enforcement, logging).

**Pros**
- Strong “boundary control” story.

**Cons**
- More infrastructure and policies to manage.

---

### Option 5 — Replace Copilot Studio with a **Custom Copilot Agent** using Microsoft 365 Agents SDK (Most control)

**What:** Build a code-based agent with the M365 Agents SDK and have it call your proxy endpoint.

```
M365 Copilot Chat → Custom Agent (SDK) → APIM/Function → Private Foundry
```

**Benefits**
- Maximum control over identity, OBO delegation, telemetry, and error handling.

**Pros**
- Most flexible for enterprise requirements.

**Cons**
- Highest engineering lift.

---

## 4) “Selected Outbound Access” vs “Ports to open”

In Foundry network isolation, **outbound access** controls what the Foundry environment (agent compute/tooling) can reach outside, while **inbound access** is governed by the **Public Network Access flag** and private endpoint rules. citeturn22search190

- **Selected outbound** is primarily about **allowed destinations** and network egress policy.
- It is **not** equivalent to simply opening a port for inbound SaaS services.

If your issue is **Copilot → Foundry inbound reachability**, outbound settings alone will not fix publishing.

---

## 5) Recommendation for UDX (Private Foundry, Minimum Build)

Given UDX’s current private endpoint posture, the minimum viable path is:

1. **Copilot Studio agent** (thin router) published to M365 Copilot Chat.
2. **Azure Function proxy** (public) with VNet integration.
3. Function forwards to the **private Foundry agent endpoint**.

This keeps Foundry private while allowing Copilot Chat access with minimal components.

---

## 6) Implementation Checklist (Minimal “Path B”)

- [ ] Confirm Foundry agent endpoint is reachable from within the VNet (private endpoint works).
- [ ] Deploy Azure Function (public), enable VNet integration to reach private Foundry.
- [ ] Configure private DNS so Function can resolve Foundry’s private endpoint name.
- [ ] Configure Copilot Studio HTTP tool to call the Function.
- [ ] Publish Copilot Studio agent to M365 Copilot Chat.
- [ ] Add basic security hardening (next step): Entra JWT validation, request limits, logging.

---

## 7) Links / Sources

- Publish agents to Microsoft 365 Copilot and Teams (Foundry) citeturn22search173
- Configure network isolation / private link and PNA flag options (Foundry) citeturn22search190
- Set up private networking for Foundry Agent Service (standard private networking) citeturn22search185
