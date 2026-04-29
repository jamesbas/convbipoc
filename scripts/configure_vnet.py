"""Configure APIM VNet integration via REST API."""
import json, subprocess

SUB = "2678d36e-00a6-455f-8f47-d524ef09e674"
RG = "rgUDXConvBI"
APIM = "udxcbi-apim-rqtovkuobfzg2"
VNET = "udxcbi-vnet-rqtovkuobfzg2"

url = (
    f"https://management.azure.com/subscriptions/{SUB}/resourceGroups/{RG}"
    f"/providers/Microsoft.ApiManagement/service/{APIM}"
    f"/gateways/managed/configConnections/default?api-version=2024-06-01-preview"
)

body = json.dumps({
    "properties": {
        "sourceId": f"/subscriptions/{SUB}/resourceGroups/{RG}/providers/Microsoft.ApiManagement/service/{APIM}/gateways/managed",
        "virtualNetworkConfiguration": {
            "subnetResourceId": f"/subscriptions/{SUB}/resourceGroups/{RG}/providers/Microsoft.Network/virtualNetworks/{VNET}/subnets/apim-integration-subnet"
        }
    }
})

r = subprocess.run(f'az rest --method put --url "{url}" --body "{body.replace(chr(34), chr(92)+chr(34))}"', capture_output=True, text=True, shell=True)
if r.returncode == 0:
    print("VNet integration configured successfully!")
    print(r.stdout[:200])
else:
    print(f"Failed: {r.stderr[:500]}")
