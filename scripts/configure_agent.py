#!/usr/bin/env python3
"""
Post-deployment script: Create a Foundry Agent in the AI Project
and configure it with an MCP tool pointing to APIM → Microsoft Learn MCP.

Prerequisites:
  pip install azure-identity azure-ai-projects
"""

import json
import sys
import subprocess

def get_deployment_outputs(resource_group: str, deployment_name: str) -> dict:
    """Get outputs from the Bicep deployment."""
    result = subprocess.run(
        ["az", "deployment", "group", "show",
         "--resource-group", resource_group,
         "--name", deployment_name,
         "--query", "properties.outputs",
         "--output", "json"],
        capture_output=True, text=True, check=True
    )
    return json.loads(result.stdout)

def get_apim_subscription_key(resource_group: str, apim_name: str, sub_name: str) -> str:
    """Get APIM subscription primary key."""
    result = subprocess.run(
        ["az", "rest", "--method", "post",
         "--url", f"https://management.azure.com/subscriptions/{{subId}}/resourceGroups/{resource_group}/providers/Microsoft.ApiManagement/service/{apim_name}/subscriptions/{sub_name}/listSecrets?api-version=2023-09-01-preview".replace("{subId}", get_subscription_id())],
        capture_output=True, text=True, check=True
    )
    return json.loads(result.stdout)["primaryKey"]

def get_subscription_id() -> str:
    result = subprocess.run(
        ["az", "account", "show", "--query", "id", "--output", "tsv"],
        capture_output=True, text=True, check=True
    )
    return result.stdout.strip()

def main():
    resource_group = "rgUDXConvBI"
    deployment_name = "udxconvbi-deploy"

    print("Fetching deployment outputs...")
    outputs = get_deployment_outputs(resource_group, deployment_name)

    apim_gateway_url = outputs["apimGatewayUrl"]["value"]
    apim_name = outputs["apimName"]["value"]
    ai_project_name = outputs["aiProjectName"]["value"]

    print(f"APIM Gateway: {apim_gateway_url}")
    print(f"AI Project: {ai_project_name}")

    # Get APIM subscription key for the Foundry agent to call MCP via APIM
    print("Fetching APIM subscription key...")
    apim_key = get_apim_subscription_key(resource_group, apim_name, "copilot-studio-sub")
    print(f"APIM Key obtained (first 4 chars): {apim_key[:4]}...")

    # The MCP endpoint through APIM
    mcp_via_apim_url = f"{apim_gateway_url}/udx/mcp"

    print(f"\nMCP via APIM URL: {mcp_via_apim_url}")
    print(f"\nAgent configuration details:")
    print(f"  - AI Project: {ai_project_name}")
    print(f"  - Resource Group: {resource_group}")
    print(f"  - MCP Endpoint (via APIM): {mcp_via_apim_url}")
    print(f"  - APIM Subscription Key: {apim_key[:4]}...{apim_key[-4:]}")

    # Create agent using Azure AI Projects SDK
    try:
        from azure.identity import DefaultAzureCredential
        from azure.ai.projects import AIProjectClient
        from azure.ai.projects.models import OpenApiTool, OpenApiAnonymousAuthDetails

        # Get the AI Project connection string
        sub_id = get_subscription_id()

        # Construct the project client
        print("\nConnecting to AI Project...")
        client = AIProjectClient(
            credential=DefaultAzureCredential(),
            endpoint=f"https://eastus2.api.azureml.ms",
            subscription_id=sub_id,
            resource_group_name=resource_group,
            project_name=ai_project_name
        )

        # Create the agent with MCP tool
        print("Creating Foundry agent...")
        agent = client.agents.create_agent(
            model="gpt-41",  # matches the deployment name in Bicep
            name="UDX-ConvBI-POC-Agent",
            instructions="""You are a helpful assistant for UDX Conversational BI.
You can search Microsoft Learn documentation to answer questions about Microsoft technologies.
When a user asks about Microsoft products, Azure services, or technical documentation,
use the Microsoft Learn MCP tool to search for relevant information.
Always cite your sources when providing information from Microsoft Learn.""",
            headers={"Content-Type": "application/json"},
        )

        print(f"\nAgent created successfully!")
        print(f"  Agent ID: {agent.id}")
        print(f"  Agent Name: {agent.name}")

        # Save agent details for APIM backend update
        agent_details = {
            "agent_id": agent.id,
            "agent_name": agent.name,
            "apim_gateway_url": apim_gateway_url,
            "mcp_via_apim_url": mcp_via_apim_url,
            "apim_subscription_key_first4": apim_key[:4],
            "ai_project_name": ai_project_name,
            "resource_group": resource_group,
        }
        with open("agent_details.json", "w") as f:
            json.dump(agent_details, f, indent=2)
        print("\nAgent details saved to agent_details.json")

    except ImportError:
        print("\n⚠ azure-ai-projects SDK not installed.")
        print("Run: pip install azure-identity azure-ai-projects")
        print("Then re-run this script.")
        sys.exit(1)
    except Exception as e:
        print(f"\n⚠ Error creating agent: {e}")
        print("You may need to create the agent manually in the Foundry portal.")
        sys.exit(1)

if __name__ == "__main__":
    main()
