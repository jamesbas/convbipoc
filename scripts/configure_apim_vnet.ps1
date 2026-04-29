# Post-deployment: Configure APIM Standard v2 outbound VNet integration
# This must be done after APIM is provisioned because Standard v2 doesn't support
# VNet integration at creation time via Bicep/ARM.

param(
    [string]$ResourceGroup = "rgUDXConvBI",
    [string]$DeploymentName = "udxconvbi-deploy"
)

$ErrorActionPreference = "Stop"

# Get deployment outputs
Write-Host "Fetching deployment outputs..."
$outputs = az deployment group show -g $ResourceGroup -n $DeploymentName --query "properties.outputs" -o json | ConvertFrom-Json

$apimName = $outputs.apimName.value
$vnetName = $outputs.vnetName.value
$subscriptionId = (az account show --query id -o tsv)

Write-Host "APIM: $apimName"
Write-Host "VNet: $vnetName"

# Get the APIM VNet integration subnet resource ID (Microsoft.Web/serverFarms delegation)
$subnetId = "/subscriptions/$subscriptionId/resourceGroups/$ResourceGroup/providers/Microsoft.Network/virtualNetworks/$vnetName/subnets/apim-integration-subnet"

Write-Host "Configuring APIM outbound VNet integration..."
Write-Host "Subnet: $subnetId"

# Configure the managed gateway with VNet integration
# Standard v2 uses PUT on the gateway configuration resource
$gatewayConfigUrl = "https://management.azure.com/subscriptions/$subscriptionId/resourceGroups/$ResourceGroup/providers/Microsoft.ApiManagement/service/$apimName/gateways/managed/configConnections/default?api-version=2024-06-01-preview"

$body = @{
    properties = @{
        sourceId = "/subscriptions/$subscriptionId/resourceGroups/$ResourceGroup/providers/Microsoft.ApiManagement/service/$apimName/gateways/managed"
        virtualNetworkConfiguration = @{
            subnetResourceId = $subnetId
        }
    }
} | ConvertTo-Json -Depth 5

Write-Host "Applying VNet integration via REST API..."
$result = az rest --method put --url $gatewayConfigUrl --body $body --output json 2>&1

if ($LASTEXITCODE -eq 0) {
    Write-Host "VNet integration configured successfully!" -ForegroundColor Green
} else {
    Write-Host "VNet integration configuration failed:" -ForegroundColor Yellow
    Write-Host $result
    Write-Host ""
    Write-Host "You may need to configure this manually in the Azure portal:" -ForegroundColor Yellow
    Write-Host "  APIM -> Deployment + infrastructure -> Network -> VNet integration" -ForegroundColor Yellow
}
