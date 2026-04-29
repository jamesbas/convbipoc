import json

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
    'new JProperty("assistant_id", "asst_xOxiUjOpWmuxdp9sr3mJWBwG"),'
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

body = {"properties": {"format": "xml", "value": policy}}
with open("e:/Code/udx-conv-bi/temp_policy.json", "w", encoding="utf-8") as f:
    json.dump(body, f)
print("Policy JSON written")
