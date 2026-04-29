"""Configure APIM VNet integration via REST API using azure-identity."""
import json, requests
from azure.identity import DefaultAzureCredential

SUB = "2678d36e-00a6-455f-8f47-d524ef09e674"
RG = "rgUDXConvBI"
APIM = "udxcbi-apim-rqtovkuobfzg2"
VNET = "udxcbi-vnet-rqtovkuobfzg2"

cred = DefaultAzureCredential()
token = cred.get_token("https://management.azure.com/.default").token

url = (
    f"https://management.azure.com/subscriptions/{SUB}/resourceGroups/{RG}"
    f"/providers/Microsoft.ApiManagement/service/{APIM}"
    f"/gateways/managed/configConnections/default?api-version=2024-06-01-preview"
)

body = {
    "properties": {
        "sourceId": f"/subscriptions/{SUB}/resourceGroups/{RG}/providers/Microsoft.ApiManagement/service/{APIM}/gateways/managed",
        "virtualNetworkConfiguration": {
            "subnetResourceId": f"/subscriptions/{SUB}/resourceGroups/{RG}/providers/Microsoft.Network/virtualNetworks/{VNET}/subnets/apim-integration-subnet"
        }
    }
}

r = requests.put(url, json=body, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
if r.status_code in (200, 201, 202):
    print(f"VNet integration configured! Status: {r.status_code}")
else:
    print(f"Failed ({r.status_code}): {r.text[:500]}")
