// UDX Conversational BI POC - Main Bicep Template
// M365 Copilot Chat → Copilot Studio → APIM → Foundry Agent (Private) → APIM → Microsoft Learn MCP
//
// Uses the new standalone Foundry model (Microsoft.CognitiveServices/accounts + /projects)
// — no AI Hub, no Storage Account, no Key Vault dependencies.

targetScope = 'resourceGroup'

@description('Azure region for all resources')
param location string = 'eastus2'

@description('Unique suffix for resource names')
param uniqueSuffix string = uniqueString(resourceGroup().id)

@description('Name prefix for resources')
param namePrefix string = 'udxcbi'

// --- Variables ---
var vnetName = '${namePrefix}-vnet-${uniqueSuffix}'
var apimName = '${namePrefix}-apim-${uniqueSuffix}'
var foundryName = '${namePrefix}-foundry-${uniqueSuffix}'
var projectName = '${namePrefix}-proj-${uniqueSuffix}'

// --- NSG for APIM VNet Integration Subnet ---
resource apimNsg 'Microsoft.Network/networkSecurityGroups@2024-01-01' = {
  name: '${namePrefix}-apim-nsg-${uniqueSuffix}'
  location: location
  properties: {
    securityRules: [
      {
        name: 'AllowStorageOutbound'
        properties: {
          priority: 100
          direction: 'Outbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourceAddressPrefix: 'VirtualNetwork'
          sourcePortRange: '*'
          destinationAddressPrefix: 'Storage'
          destinationPortRange: '443'
        }
      }
      {
        name: 'AllowKeyVaultOutbound'
        properties: {
          priority: 110
          direction: 'Outbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourceAddressPrefix: 'VirtualNetwork'
          sourcePortRange: '*'
          destinationAddressPrefix: 'AzureKeyVault'
          destinationPortRange: '443'
        }
      }
    ]
  }
}

// --- VNet ---
resource vnet 'Microsoft.Network/virtualNetworks@2024-01-01' = {
  name: vnetName
  location: location
  properties: {
    addressSpace: {
      addressPrefixes: [
        '10.0.0.0/16'
      ]
    }
    subnets: [
      {
        name: 'apim-integration-subnet'
        properties: {
          addressPrefix: '10.0.1.0/24'
          networkSecurityGroup: {
            id: apimNsg.id
          }
          delegations: [
            {
              name: 'webapp-delegation'
              properties: {
                serviceName: 'Microsoft.Web/serverFarms'
              }
            }
          ]
        }
      }
      {
        name: 'private-endpoints-subnet'
        properties: {
          addressPrefix: '10.0.2.0/24'
        }
      }
    ]
  }
}

// --- Foundry Resource (AIServices — standalone, no hub) ---
resource foundry 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: foundryName
  location: location
  kind: 'AIServices'
  identity: {
    type: 'SystemAssigned'
  }
  sku: {
    name: 'S0'
  }
  properties: {
    allowProjectManagement: true
    customSubDomainName: foundryName
    publicNetworkAccess: 'Disabled'
    networkAcls: {
      defaultAction: 'Deny'
    }
    disableLocalAuth: false
  }
}

// --- Foundry Project (child of Foundry resource) ---
resource foundryProject 'Microsoft.CognitiveServices/accounts/projects@2025-06-01' = {
  name: projectName
  parent: foundry
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {}
}

// --- Model Deployment: gpt-4.1 ---
resource gpt41Deployment 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = {
  parent: foundry
  name: 'gpt-41'
  sku: {
    name: 'Standard'
    capacity: 10
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-4.1'
      version: '2025-04-14'
    }
  }
}

// --- Private DNS Zones ---
var privateDnsZones = [
  'privatelink.cognitiveservices.azure.com'
  'privatelink.openai.azure.com'
]

resource dnsZones 'Microsoft.Network/privateDnsZones@2024-06-01' = [
  for zone in privateDnsZones: {
    name: zone
    location: 'global'
  }
]

resource dnsZoneLinks 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = [
  for (zone, i) in privateDnsZones: {
    parent: dnsZones[i]
    name: '${namePrefix}-link-${i}'
    location: 'global'
    properties: {
      virtualNetwork: {
        id: vnet.id
      }
      registrationEnabled: false
    }
  }
]

// --- Foundry Private Endpoint ---
resource foundryPe 'Microsoft.Network/privateEndpoints@2024-01-01' = {
  name: '${foundryName}-pe'
  location: location
  dependsOn: [
    gpt41Deployment
    foundryProject
  ]
  properties: {
    subnet: {
      id: vnet.properties.subnets[1].id
    }
    privateLinkServiceConnections: [
      {
        name: '${foundryName}-plsc'
        properties: {
          privateLinkServiceId: foundry.id
          groupIds: [
            'account'
          ]
        }
      }
    ]
  }
}

resource foundryPeDnsGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-01-01' = {
  parent: foundryPe
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'cognitive'
        properties: {
          privateDnsZoneId: dnsZones[0].id // privatelink.cognitiveservices.azure.com
        }
      }
      {
        name: 'openai'
        properties: {
          privateDnsZoneId: dnsZones[1].id // privatelink.openai.azure.com
        }
      }
    ]
  }
}

// --- APIM Standard v2 ---
resource apim 'Microsoft.ApiManagement/service@2023-09-01-preview' = {
  name: apimName
  location: location
  sku: {
    name: 'StandardV2'
    capacity: 1
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    publisherEmail: 'udx-admin@contoso.com'
    publisherName: 'UDX Conv BI'
    virtualNetworkType: 'None' // Outbound VNet integration configured post-deployment via REST API
  }
}

// --- APIM Backend: Foundry Agent ---
resource apimFoundryBackend 'Microsoft.ApiManagement/service/backends@2023-09-01-preview' = {
  parent: apim
  name: 'foundry-backend'
  properties: {
    protocol: 'http'
    url: 'https://${foundryName}.openai.azure.com/openai'
    description: 'Foundry Agent (Private) Backend — Azure OpenAI Assistants API'
    tls: {
      validateCertificateChain: true
      validateCertificateName: true
    }
  }
}

// --- APIM Backend: Microsoft Learn MCP ---
resource apimMcpBackend 'Microsoft.ApiManagement/service/backends@2023-09-01-preview' = {
  parent: apim
  name: 'mslearn-mcp-backend'
  properties: {
    protocol: 'http'
    url: 'https://learn.microsoft.com/api/mcp'
    description: 'Microsoft Learn MCP Server Backend'
    tls: {
      validateCertificateChain: true
      validateCertificateName: true
    }
  }
}

// --- APIM API: Foundry Agent ---
resource apimFoundryApi 'Microsoft.ApiManagement/service/apis@2023-09-01-preview' = {
  parent: apim
  name: 'udx-foundry-api'
  properties: {
    displayName: 'UDX Foundry Agent API'
    path: 'udx/foundry'
    protocols: [
      'https'
    ]
    subscriptionRequired: true
    subscriptionKeyParameterNames: {
      header: 'Ocp-Apim-Subscription-Key'
      query: 'subscription-key'
    }
  }
}

resource apimFoundryInvokeOp 'Microsoft.ApiManagement/service/apis/operations@2023-09-01-preview' = {
  parent: apimFoundryApi
  name: 'invoke-agent'
  properties: {
    displayName: 'Invoke Foundry Agent'
    method: 'POST'
    urlTemplate: '/invoke'
  }
}

resource apimFoundryInvokePolicy 'Microsoft.ApiManagement/service/apis/operations/policies@2023-09-01-preview' = {
  parent: apimFoundryInvokeOp
  name: 'policy'
  properties: {
    format: 'xml'
    value: '''
<policies>
  <inbound>
    <base />
    <set-backend-service backend-id="foundry-backend" />
    <authentication-managed-identity resource="https://cognitiveservices.azure.com" />
    <set-header name="Content-Type" exists-action="override">
      <value>application/json</value>
    </set-header>
    <rewrite-uri template="/threads/runs?api-version=2024-05-01-preview" />
    <set-body>@{
      var body = context.Request.Body.As&lt;JObject&gt;();
      var userMessage = body["message"]?.ToString() ?? body["query"]?.ToString() ?? "";
      var result = new JObject(
        new JProperty("assistant_id", "asst_DTDTErUlSCNAsdk9hyezeAjJ"),
        new JProperty("thread", new JObject(
          new JProperty("messages", new JArray(
            new JObject(
              new JProperty("role", "user"),
              new JProperty("content", userMessage)
            )
          ))
        ))
      );
      return result.ToString();
    }</set-body>
  </inbound>
  <backend>
    <base />
  </backend>
  <outbound>
    <base />
  </outbound>
  <on-error>
    <base />
  </on-error>
</policies>
'''
  }
}

// --- APIM API: Microsoft Learn MCP ---
resource apimMcpApi 'Microsoft.ApiManagement/service/apis@2023-09-01-preview' = {
  parent: apim
  name: 'udx-mcp-api'
  properties: {
    displayName: 'UDX MCP Proxy API'
    path: 'udx/mcp'
    protocols: [
      'https'
    ]
    subscriptionRequired: true
    subscriptionKeyParameterNames: {
      header: 'Ocp-Apim-Subscription-Key'
      query: 'subscription-key'
    }
  }
}

resource apimMcpInvokeOp 'Microsoft.ApiManagement/service/apis/operations@2023-09-01-preview' = {
  parent: apimMcpApi
  name: 'invoke-mcp'
  properties: {
    displayName: 'Invoke MCP Server'
    method: 'POST'
    urlTemplate: '/*'
  }
}

resource apimMcpInvokePolicy 'Microsoft.ApiManagement/service/apis/operations/policies@2023-09-01-preview' = {
  parent: apimMcpInvokeOp
  name: 'policy'
  properties: {
    format: 'xml'
    value: '''
<policies>
  <inbound>
    <base />
    <set-backend-service backend-id="mslearn-mcp-backend" />
    <set-header name="Content-Type" exists-action="override">
      <value>application/json</value>
    </set-header>
  </inbound>
  <backend>
    <base />
  </backend>
  <outbound>
    <base />
  </outbound>
  <on-error>
    <base />
  </on-error>
</policies>
'''
  }
}

// --- APIM Subscription for Copilot Studio ---
resource apimSubscription 'Microsoft.ApiManagement/service/subscriptions@2023-09-01-preview' = {
  parent: apim
  name: 'copilot-studio-sub'
  properties: {
    displayName: 'Copilot Studio Subscription'
    scope: '/apis'
    state: 'active'
  }
}

// --- RBAC: APIM MI → Cognitive Services OpenAI User on Foundry ---
resource apimCognitiveRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(apim.id, foundry.id, '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd')
  scope: foundry
  properties: {
    principalId: apim.identity.principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd') // Cognitive Services OpenAI User
    principalType: 'ServicePrincipal'
  }
}

// --- Outputs ---
output apimGatewayUrl string = apim.properties.gatewayUrl
output apimName string = apim.name
output foundryName string = foundry.name
output foundryEndpoint string = foundry.properties.endpoint
output projectName string = foundryProject.name
output vnetName string = vnet.name
output resourceGroupName string = resourceGroup().name
