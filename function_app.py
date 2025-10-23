import logging
import os
import json
import asyncio
import azure.functions as func
from azure.ai.projects import AIProjectClient
from azure.identity import ClientSecretCredential

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)

@app.route(route="invoke_copilot_agent", methods=["POST"], auth_level=func.AuthLevel.FUNCTION)
async def invoke_copilot_agent(req: func.HttpRequest) -> func.HttpResponse:
    try:
        # Initialize client inside function to avoid startup errors
        credential = ClientSecretCredential(
            tenant_id=os.getenv("AI_AGENT_TENANT_ID"),
            client_id=os.getenv("AI_AGENT_CLIENT_ID"),
            client_secret=os.getenv("AI_AGENT_CLIENT_SECRET_VALUE")
        )
        
        project_client = AIProjectClient(
            endpoint=os.getenv("PROJECT_ENDPOINT"),
            credential=credential
        )
        
        req_body = req.get_json()
        message = req_body.get("message")
        convo_thread_id = req_body.get("convo_thread_id")

        if not convo_thread_id:
            convo_thread_id = project_client.agents.threads.create().id

        project_client.agents.messages.create(
            thread_id=convo_thread_id,
            role="user",
            content=message
        )

        run = project_client.agents.runs.create(
            thread_id=convo_thread_id,
            agent_id=os.getenv("COPILOT_AGENT_ID")
        )

        while run.status in ["queued", "in_progress"]:
            await asyncio.sleep(0.2)
            run = project_client.agents.runs.get(
                thread_id=convo_thread_id,
                run_id=run.id
            )

        if run.status == "completed":
            msgs = project_client.agents.messages.list(thread_id=convo_thread_id)
            assistant_messages = [m for m in msgs if m.role == "assistant"]
            reply = assistant_messages[-1].content[0].text.value if assistant_messages else None

            return func.HttpResponse(
                json.dumps({
                    "convo_thread_id": convo_thread_id,
                    "response": reply
                }),
                status_code=200,
                mimetype="application/json"
            )
        else:
            return func.HttpResponse(
                json.dumps({
                    "convo_thread_id": convo_thread_id,
                    "error": f"Run did not complete. Status: {run.status}"
                }),
                status_code=500,
                mimetype="application/json"
            )

    except Exception as e:
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            status_code=500,
            mimetype="application/json"
        )
