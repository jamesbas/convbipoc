// UDX Conversational BI POC - Alternative Path: Azure Function Bridge
// M365 Copilot Chat → Copilot Studio → Azure Function (Public, Entra ID Auth) → Private Foundry Agent
//
// This Bicep deploys the Azure Function App as an alternative to APIM for the
// public-to-private bridge between Copilot Studio and the private Foundry Agent.
// Deploy AFTER main.bicep (requires existing VNet, Foundry, and private DNS zones).

targetScope = 'resourceGroup'

@description('Azure region for all resources')
param location string = 'eastus2'

@description('Unique suffix for resource names')
param uniqueSuffix string = uniqueString(resourceGroup().id)

@description('Name prefix for resources')
param namePrefix string = 'udxcbi'

@description('Entra ID tenant ID for authentication')
param tenantId string = subscription().tenantId

@description('Entra ID client ID (app registration) for the Function App')
param functionAppClientId string

@description('Foundry agent name for invocation')
param foundryAgentName string = 'UDX-Snowflake-Agent'

// --- Variables ---
var vnetName = '${namePrefix}-vnet-${uniqueSuffix}'
var foundryName = '${namePrefix}-foundry-${uniqueSuffix}'
var functionAppName = '${namePrefix}-func-${uniqueSuffix}'
var appServicePlanName = '${namePrefix}-asp-${uniqueSuffix}'
var storageAccountName = '${namePrefix}st${uniqueSuffix}'
var appInsightsName = '${namePrefix}-ai-${uniqueSuffix}'
var logAnalyticsName = '${namePrefix}-law-${uniqueSuffix}'
var functionSubnetName = 'function-integration-subnet'

// --- Reference existing VNet ---
resource vnet 'Microsoft.Network/virtualNetworks@2024-01-01' existing = {
  name: vnetName
}

// --- Reference existing Foundry resource ---
resource foundry 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = {
  name: foundryName
}

// --- Add Function App integration subnet to existing VNet ---
resource functionSubnet 'Microsoft.Network/virtualNetworks/subnets@2024-01-01' = {
  parent: vnet
  name: functionSubnetName
  properties: {
    addressPrefix: '10.0.3.0/24'
    delegations: [
      {
        name: 'func-delegation'
        properties: {
          serviceName: 'Microsoft.Web/serverFarms'
        }
      }
    ]
  }
}

// --- Log Analytics Workspace (for App Insights) ---
resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: logAnalyticsName
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

// --- Application Insights ---
resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: appInsightsName
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalytics.id
  }
}

// --- Storage Account (required by Azure Functions) ---
resource storageAccount 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageAccountName
  location: location
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    supportsHttpsTrafficOnly: true
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
  }
}

// --- App Service Plan (Premium for VNet integration) ---
resource appServicePlan 'Microsoft.Web/serverfarms@2023-12-01' = {
  name: appServicePlanName
  location: location
  sku: {
    name: 'EP1'
    tier: 'ElasticPremium'
  }
  kind: 'elastic'
  properties: {
    maximumElasticWorkerCount: 5
    reserved: true // Linux
  }
}

// --- Azure Function App ---
resource functionApp 'Microsoft.Web/sites@2023-12-01' = {
  name: functionAppName
  location: location
  kind: 'functionapp,linux'
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    serverFarmId: appServicePlan.id
    httpsOnly: true
    virtualNetworkSubnetId: functionSubnet.id
    siteConfig: {
      pythonVersion: '3.11'
      linuxFxVersion: 'PYTHON|3.11'
      ftpsState: 'Disabled'
      minTlsVersion: '1.2'
      vnetRouteAllEnabled: true // Route all outbound through VNet
      appSettings: [
        {
          name: 'AzureWebJobsStorage'
          value: 'DefaultEndpointsProtocol=https;AccountName=${storageAccount.name};EndpointSuffix=${environment().suffixes.storage};AccountKey=${storageAccount.listKeys().keys[0].value}'
        }
        {
          name: 'FUNCTIONS_EXTENSION_VERSION'
          value: '~4'
        }
        {
          name: 'FUNCTIONS_WORKER_RUNTIME'
          value: 'python'
        }
        {
          name: 'APPINSIGHTS_INSTRUMENTATIONKEY'
          value: appInsights.properties.InstrumentationKey
        }
        {
          name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
          value: appInsights.properties.ConnectionString
        }
        {
          name: 'FOUNDRY_PROJECT_ENDPOINT'
          value: 'https://${foundryName}.openai.azure.com'
        }
        {
          name: 'FOUNDRY_AGENT_NAME'
          value: foundryAgentName
        }
        {
          name: 'FOUNDRY_AGENT_ID'
          value: 'asst_DTDTErUlSCNAsdk9hyezeAjJ'
        }
        {
          name: 'ALLOWED_TENANT_ID'
          value: tenantId
        }
        {
          name: 'ALLOWED_AUDIENCE'
          value: 'api://${functionAppClientId}'
        }
        {
          name: 'DEFAULT_TIMEOUT_SECONDS'
          value: '55'
        }
        {
          name: 'SCM_DO_BUILD_DURING_DEPLOYMENT'
          value: 'true'
        }
      ]
    }
  }
}

// --- Entra ID Authentication (Easy Auth) ---
resource functionAuthSettings 'Microsoft.Web/sites/config@2023-12-01' = {
  parent: functionApp
  name: 'authsettingsV2'
  properties: {
    globalValidation: {
      requireAuthentication: true
      unauthenticatedClientAction: 'Return401'
    }
    identityProviders: {
      azureActiveDirectory: {
        enabled: true
        registration: {
          openIdIssuer: 'https://sts.windows.net/${tenantId}/v2.0'
          clientId: functionAppClientId
        }
        validation: {
          allowedAudiences: [
            'api://${functionAppClientId}'
            functionAppClientId
          ]
          defaultAuthorizationPolicy: {
            allowedPrincipals: {}
          }
        }
      }
    }
    login: {
      tokenStore: {
        enabled: true
      }
    }
  }
}

// --- RBAC: Function MI → Cognitive Services OpenAI User on Foundry ---
resource functionCognitiveRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(functionApp.id, foundry.id, '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd')
  scope: foundry
  properties: {
    principalId: functionApp.identity.principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd') // Cognitive Services OpenAI User
    principalType: 'ServicePrincipal'
  }
}

// --- Outputs ---
output functionAppName string = functionApp.name
output functionAppUrl string = 'https://${functionApp.properties.defaultHostName}'
output functionEndpoint string = 'https://${functionApp.properties.defaultHostName}/api/foundry-chat'
output functionAppPrincipalId string = functionApp.identity.principalId
output appInsightsName string = appInsights.name
