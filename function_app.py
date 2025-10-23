import logging
import os
import json
import asyncio
from dotenv import load_dotenv
import azure.functions as func
from azure.ai.projects import AIProjectClient
from azure.identity import ClientSecretCredential

load_dotenv()

credential = ClientSecretCredential(
    # tenant_id=os.getenv("AI_AGENT_TENANT_ID"),
    client_id=os.getenv("AI_AGENT_CLIENT_ID"),
    client_secret=os.getenv("AI_AGENT_CLIENT_SECRET_VALUE")
)

project_client = AIProjectClient(
    endpoint=os.getenv("PROJECT_ENDPOINT"),
    credential=credential
)


func_app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)

@func_app.route(route="invoke_copilot_agent", methods=["POST"], auth_level=func.AuthLevel.FUNCTION)
async def invoke_copilot_agent(req: func.HttpRequest) -> func.HttpResponse:
    try:
        req_body = req.get_json()
        message = req_body.get("message")
        convo_thread_id = req_body.get("convo_thread_id")

        if not convo_thread_id:
            convo_thread_id = project_client.agents.threads.create().id

        # Add user message to thread
        try:
            project_client.agents.messages.create(
                thread_id=convo_thread_id,
                role="user",
                content=message
            )
        except Exception as msg_error:
            return func.HttpResponse(
                json.dumps({"error": f"Message creation failed: {str(msg_error)}"}),
                status_code=500,
                mimetype="application/json"
            )

        # Create run
        print(f"[DEBUG] Creating run...")
        try:
            run = project_client.agents.runs.create(
                thread_id=convo_thread_id,
                agent_id=os.getenv("COPILOT_AGENT_ID")
            )

            while run.status in ["queued", "in_progress"]:
                await asyncio.sleep(0.2)
                try:
                    run = project_client.agents.runs.get(
                        thread_id=convo_thread_id,
                        run_id=run.id
                    )
                except Exception as get_error:
                    return func.HttpResponse(
                        json.dumps({"error": f"Run retrieval failed: {str(get_error)}"}),
                        status_code=500,
                        mimetype="application/json"
                    )
                print(f"[DEBUG] Run status: {run.status}")

            if run.status == "completed":
                # Get latest messages from the thread
                msgs = project_client.agents.messages.list(thread_id=convo_thread_id)
                # Usually the last assistant message is the reply
                assistant_messages = [
                    m for m in msgs if m.role == "assistant"
                ]
                reply = assistant_messages[-1].content[0].text.value if assistant_messages else None

                logging.warning(reply)

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

        except Exception as run_error:
            return func.HttpResponse(
                json.dumps({"error": f"Run creation failed: {str(run_error)}"}),
                status_code=500,
                mimetype="application/json"
            )

    except Exception as e:
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            status_code=500,
            mimetype="application/json"
        )
 