"""
Create a Foundry Agent (OpenAI Assistant) in the UDX Azure OpenAI resource.

NOTE: The OpenAI resource must have public network access temporarily enabled
for this script to work from outside the VNet. After creation, re-lock with:
  az resource update --ids <openai-resource-id> \
    --set properties.networkAcls.defaultAction=Deny properties.publicNetworkAccess=Disabled \
    --api-version 2024-10-01

Agent ID created: asst_DTDTErUlSCNAsdk9hyezeAjJ
"""
from openai import AzureOpenAI
from azure.identity import DefaultAzureCredential, get_bearer_token_provider

AZURE_OPENAI_ENDPOINT = "https://udxcbi-foundry-rqtovkuobfzg2.openai.azure.com/"
API_VERSION = "2024-05-01-preview"

token_provider = get_bearer_token_provider(
    DefaultAzureCredential(), "https://cognitiveservices.azure.com/.default"
)
client = AzureOpenAI(
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
    api_version=API_VERSION,
    azure_ad_token_provider=token_provider,
)

print("Creating Foundry assistant/agent...")
assistant = client.beta.assistants.create(
    model="gpt-41",
    name="UDX-ConvBI-POC-Agent",
    instructions="""You are a helpful assistant for UDX Conversational BI.
You can search Microsoft Learn documentation to answer questions about Microsoft technologies.
When a user asks about Microsoft products, Azure services, or technical documentation,
use the available tools to search for relevant information.
Always cite your sources when providing information from Microsoft Learn.""",
)

print(f"Agent created: {assistant.id}")
print(f"Agent name: {assistant.name}")
print(f"Agent model: {assistant.model}")
