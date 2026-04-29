"""Update APIM policy for the invoke-agent operation via Azure REST API."""
import json
import requests
from azure.identity import DefaultAzureCredential

credential = DefaultAzureCredential()
token = credential.get_token("https://management.azure.com/.default").token

policy = (
    '<policies>'
    '<inbound>'
    '<base />'
    '<set-backend-service backend-id="foundry-backend" />'
    '<authentication-managed-identity resource="https://cognitiveservices.azure.com" />'
    '<set-header name="Content-Type" exists-action="override">'
    '<value>application/json</value>'
    '</set-header>'
    '<rewrite-uri template="/threads/runs?api-version=2024-05-01-preview" />'
    '<set-body>@{var body = context.Request.Body.As&lt;JObject&gt;();'
    'var userMessage = body["message"]?.ToString() ?? body["query"]?.ToString() ?? "";'
    'var result = new JObject('
    'new JProperty("assistant_id", "asst_DTDTErUlSCNAsdk9hyezeAjJ"),'
    'new JProperty("thread", new JObject('
    'new JProperty("messages", new JArray('
    'new JObject('
    'new JProperty("role", "user"),'
    'new JProperty("content", userMessage)'
    '))))));'
    'return result.ToString();}'
    '</set-body>'
    '</inbound>'
    '<backend><base /></backend>'
    '<outbound><base /></outbound>'
    '<on-error><base /></on-error>'
    '</policies>'
)

url = (
    "https://management.azure.com/subscriptions/2678d36e-00a6-455f-8f47-d524ef09e674"
    "/resourceGroups/rgUDXConvBI/providers/Microsoft.ApiManagement/service/udxcbi-apim-rqtovkuobfzg2"
    "/apis/udx-foundry-api/operations/invoke-agent/policies/policy"
    "?api-version=2023-09-01-preview"
)

body = {"properties": {"format": "xml", "value": policy}}

resp = requests.put(
    url,
    json=body,
    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
)
print(f"Status: {resp.status_code}")
if resp.status_code >= 400:
    print(resp.text)
else:
    print("Policy updated successfully")
