"""Delete old resources from rgUDXConvBI that are no longer needed."""
import requests
from azure.identity import DefaultAzureCredential

credential = DefaultAzureCredential()
token = credential.get_token("https://management.azure.com/.default").token
headers = {"Authorization": f"Bearer {token}"}

SUB = "2678d36e-00a6-455f-8f47-d524ef09e674"
RG = "rgUDXConvBI"
BASE = f"https://management.azure.com/subscriptions/{SUB}/resourceGroups/{RG}/providers"

# Resources to delete (order matters - children first)
to_delete = [
    # ML workspaces (project first, then hub)
    (f"{BASE}/Microsoft.MachineLearningServices/workspaces/udxcbi-aiproj-rqtovkuobfzg2", "2024-04-01"),
    (f"{BASE}/Microsoft.MachineLearningServices/workspaces/udxcbi-aihub-rqtovkuobfzg2", "2024-04-01"),
    # Old OpenAI
    (f"{BASE}/Microsoft.CognitiveServices/accounts/udxcbi-oai-rqtovkuobfzg2", "2024-04-01-preview"),
    # Key Vault (purge protection may apply)
    (f"{BASE}/Microsoft.KeyVault/vaults/udxcbikvrqtovkuobfzg2", "2023-07-01"),
    # Storage
    (f"{BASE}/Microsoft.Storage/storageAccounts/udxcbistrqtovkuobfzg2", "2023-05-01"),
    # Log Analytics
    (f"{BASE}/Microsoft.OperationalInsights/workspaces/udxcbi-law-rqtovkuobfzg2", "2023-09-01"),
    # DNS zone links to delete
    (f"{BASE}/Microsoft.Network/privateDnsZones/privatelink.api.azureml.ms/virtualNetworkLinks/udxcbi-link-0", "2024-06-01"),
    (f"{BASE}/Microsoft.Network/privateDnsZones/privatelink.notebooks.azure.net/virtualNetworkLinks/udxcbi-link-1", "2024-06-01"),
    (f"{BASE}/Microsoft.Network/privateDnsZones/privatelink.cognitiveservices.azure.com/virtualNetworkLinks/udxcbi-link-2", "2024-06-01"),
    (f"{BASE}/Microsoft.Network/privateDnsZones/privatelink.openai.azure.com/virtualNetworkLinks/udxcbi-link-3", "2024-06-01"),
    (f"{BASE}/Microsoft.Network/privateDnsZones/privatelink.vaultcore.azure.net/virtualNetworkLinks/udxcbi-link-4", "2024-06-01"),
    (f"{BASE}/Microsoft.Network/privateDnsZones/privatelink.blob.core.windows.net/virtualNetworkLinks/udxcbi-link-5", "2024-06-01"),
    # DNS zones to remove
    (f"{BASE}/Microsoft.Network/privateDnsZones/privatelink.api.azureml.ms", "2024-06-01"),
    (f"{BASE}/Microsoft.Network/privateDnsZones/privatelink.notebooks.azure.net", "2024-06-01"),
    (f"{BASE}/Microsoft.Network/privateDnsZones/privatelink.vaultcore.azure.net", "2024-06-01"),
    (f"{BASE}/Microsoft.Network/privateDnsZones/privatelink.blob.core.windows.net", "2024-06-01"),
]

for url_base, api_ver in to_delete:
    url = f"{url_base}?api-version={api_ver}"
    name = url_base.split("/")[-1]
    resp = requests.delete(url, headers=headers)
    status = "OK" if resp.status_code < 300 else f"FAIL({resp.status_code})"
    print(f"  {status}: {name}")

# Keep: privatelink.cognitiveservices.azure.com and privatelink.openai.azure.com
print("\nDone. Kept: VNet, NSG, APIM, and 2 DNS zones (cognitiveservices, openai)")
