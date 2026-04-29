import json
import logging
import os
import time
import uuid
from typing import Any, Dict

import azure.functions as func
from azure.identity import DefaultAzureCredential, ManagedIdentityCredential
from openai import AzureOpenAI

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
AGENT_NAME = os.environ.get("FOUNDRY_AGENT_NAME", "UDX-Snowflake-Agent")
AGENT_ID = os.environ["FOUNDRY_AGENT_ID"]
AZURE_CLIENT_ID = os.getenv("AZURE_CLIENT_ID")
DEFAULT_TIMEOUT_SECONDS = int(os.getenv("DEFAULT_TIMEOUT_SECONDS", "55"))

# Use user-assigned managed identity if AZURE_CLIENT_ID is provided.
if AZURE_CLIENT_ID:
    credential = ManagedIdentityCredential(client_id=AZURE_CLIENT_ID)
else:
    credential = DefaultAzureCredential()

# AzureOpenAI client targeting the Foundry endpoint
openai_client = AzureOpenAI(
    azure_endpoint=PROJECT_ENDPOINT,
    azure_ad_token_provider=lambda: credential.get_token("https://cognitiveservices.azure.com/.default").token,
    api_version="2024-05-01-preview",
)


def _json_response(payload: Dict[str, Any], status_code: int = 200) -> func.HttpResponse:
    return func.HttpResponse(
        body=json.dumps(payload, ensure_ascii=False),
        status_code=status_code,
        mimetype="application/json",
    )


def _get_caller_info(req: func.HttpRequest) -> Dict[str, Any]:
    """
    Extract caller identity from Easy Auth headers injected by App Service Authentication.
    These headers are trustworthy when App Service Auth is enabled (not caller-supplied).
    """
    return {
        "principal_name": req.headers.get("x-ms-client-principal-name", ""),
        "principal_id": req.headers.get("x-ms-client-principal-id", ""),
        "principal_idp": req.headers.get("x-ms-client-principal-idp", ""),
    }


@app.route(route="foundry-chat", methods=["POST"])
def foundry_chat(req: func.HttpRequest) -> func.HttpResponse:
    """
    Public bridge endpoint: receives a user message from Copilot Studio,
    invokes the private Foundry agent, and returns the response.
    Entra ID authentication is enforced by Easy Auth before this code runs.
    """
    started = time.time()
    correlation_id = req.headers.get("x-correlation-id") or str(uuid.uuid4())

    try:
        # Parse request
        try:
            body = req.get_json()
        except ValueError:
            return _json_response(
                {"status": "failed", "correlationId": correlation_id, "error": "Request body must be valid JSON."},
                status_code=400,
            )

        message = body.get("message")
        if not message or not isinstance(message, str):
            return _json_response(
                {"status": "failed", "correlationId": correlation_id, "error": "The 'message' field is required and must be a string."},
                status_code=400,
            )

        # Extract caller identity (from Easy Auth, not from body)
        caller_info = _get_caller_info(req)

        # Optional metadata from Copilot Studio
        copilot_conversation_id = body.get("copilotConversationId")
        foundry_conversation_id = body.get("foundryConversationId")
        domain_hint = body.get("domainHint")

        # Create a thread+run in one call (Assistants API)
        run = openai_client.beta.threads.create_and_run(
            assistant_id=AGENT_ID,
            thread={
                "messages": [
                    {"role": "user", "content": message}
                ]
            },
        )

        # Poll for completion
        import time as _time
        deadline = _time.time() + DEFAULT_TIMEOUT_SECONDS
        while run.status in ("queued", "in_progress", "requires_action"):
            if _time.time() > deadline:
                return _json_response(
                    {"status": "failed", "correlationId": correlation_id, "error": "Agent response timed out."},
                    status_code=504,
                )
            _time.sleep(1)
            run = openai_client.beta.threads.runs.retrieve(thread_id=run.thread_id, run_id=run.id)

        if run.status != "completed":
            return _json_response(
                {"status": "failed", "correlationId": correlation_id, "error": f"Agent run ended with status: {run.status}"},
                status_code=502,
            )

        # Get the assistant's response messages
        messages = openai_client.beta.threads.messages.list(thread_id=run.thread_id, order="desc", limit=1)
        answer = ""
        if messages.data:
            for content_block in messages.data[0].content:
                if content_block.type == "text":
                    answer = content_block.text.value
                    break

        elapsed_ms = int((time.time() - started) * 1000)

        logging.info(
            "Foundry response succeeded",
            extra={
                "custom_dimensions": {
                    "correlation_id": correlation_id,
                    "elapsed_ms": elapsed_ms,
                    "thread_id": run.thread_id,
                    "domain_hint": domain_hint,
                    "caller_principal": caller_info.get("principal_name"),
                }
            },
        )

        return _json_response({
            "status": "succeeded",
            "correlationId": correlation_id,
            "answer": answer,
            "foundryConversationId": run.thread_id,
            "foundryResponseId": run.id,
            "diagnostics": {
                "elapsedMs": elapsed_ms,
                "agentName": AGENT_NAME,
            },
        })

    except Exception as exc:
        elapsed_ms = int((time.time() - started) * 1000)
        logging.exception("Foundry bridge failed", extra={"custom_dimensions": {"correlation_id": correlation_id}})

        return _json_response(
            {
                "status": "failed",
                "correlationId": correlation_id,
                "error": "The Foundry bridge encountered an error processing the request.",
                "diagnostics": {
                    "elapsedMs": elapsed_ms,
                    "agentName": AGENT_NAME,
                },
            },
            status_code=500,
        )


@app.route(route="health", methods=["GET"])
def health_check(req: func.HttpRequest) -> func.HttpResponse:
    """Simple health check endpoint."""
    return _json_response({"status": "healthy", "agent": AGENT_NAME})
