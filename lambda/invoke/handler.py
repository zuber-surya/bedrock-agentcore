"""API Gateway → AgentCore Runtime or campus_logic (Bedrock + tools).

Env:
  AGENT_RUNTIME_ARN — optional AgentCore runtime ARN
  USE_BEDROCK / BEDROCK_MODEL_ID — required when AgentCore ARN is unset
"""
from __future__ import annotations

import json
import logging
import os
import sys
import uuid
from typing import Any

CORS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Allow-Methods": "POST,OPTIONS",
    "Content-Type": "application/json",
}

LOG = logging.getLogger("campusassist.route")
if not LOG.handlers:
    _h = logging.StreamHandler(sys.stdout)
    _h.setFormatter(logging.Formatter("%(message)s"))
    LOG.addHandler(_h)
    LOG.setLevel(logging.INFO)
    LOG.propagate = False


def handler(event: dict[str, Any], _context: Any = None) -> dict[str, Any]:
    method = (
        (event.get("requestContext") or {}).get("http") or {}
    ).get("method") or event.get("httpMethod") or "POST"

    if method == "OPTIONS":
        return {"statusCode": 204, "headers": CORS, "body": ""}

    try:
        body = event.get("body") or "{}"
        if event.get("isBase64Encoded"):
            import base64

            body = base64.b64decode(body).decode("utf-8")
        if isinstance(body, str):
            payload = json.loads(body or "{}")
        else:
            payload = body
    except json.JSONDecodeError:
        return _resp(400, {"error": "Invalid JSON body"})

    message = (payload.get("message") or "").strip()
    session_id = payload.get("sessionId") or str(uuid.uuid4())
    if not message:
        return _resp(400, {"error": "message is required", "sessionId": session_id})

    agent_arn = (os.environ.get("AGENT_RUNTIME_ARN") or "").strip()
    if agent_arn:
        LOG.info(
            "[route] path=agentcore arn=%s qualifier=DEFAULT sessionId=%s message=%s",
            agent_arn,
            session_id,
            message.replace("\n", " ")[:200],
        )
        result = invoke_agentcore(message, session_id)
    else:
        LOG.info(
            "[route] path=in-lambda sessionId=%s message=%s",
            session_id,
            message.replace("\n", " ")[:200],
        )
        from campus_logic import run_campus_assist

        result = run_campus_assist(message, session_id)

    return _resp(200, result)


def _resp(status: int, body: dict[str, Any]) -> dict[str, Any]:
    return {"statusCode": status, "headers": CORS, "body": json.dumps(body)}


def invoke_agentcore(message: str, session_id: str) -> dict[str, Any]:
    """Invoke Bedrock AgentCore Runtime. Returns structured error on failure."""
    try:
        import boto3

        client = boto3.client("bedrock-agentcore")
        arn = os.environ["AGENT_RUNTIME_ARN"]
        # AgentCore requires runtimeSessionId length 33–100
        runtime_session = session_id
        if len(runtime_session) < 33:
            runtime_session = f"{runtime_session}-{uuid.uuid4()}"
        runtime_session = runtime_session[:100]
        LOG.info(
            "[route] invoke_agent_runtime runtimeSessionId=%s",
            runtime_session,
        )
        response = client.invoke_agent_runtime(
            agentRuntimeArn=arn,
            runtimeSessionId=runtime_session,
            qualifier="DEFAULT",
            payload=json.dumps({"prompt": message, "sessionId": session_id}),
        )
        raw = response.get("response")
        if hasattr(raw, "read"):
            text = raw.read().decode("utf-8")
        else:
            text = raw if isinstance(raw, str) else json.dumps(raw)
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict) and "reply" in parsed:
                parsed.setdefault("sessionId", session_id)
                LOG.info(
                    "[route] agentcore_ok mode=%s toolsUsed=%s citations=%s",
                    parsed.get("mode"),
                    parsed.get("toolsUsed"),
                    len(parsed.get("citations") or []),
                )
                return parsed
        except json.JSONDecodeError:
            pass
        return {
            "reply": text,
            "citations": [],
            "toolsUsed": [],
            "sessionId": session_id,
            "mode": "agentcore",
        }
    except Exception as exc:  # noqa: BLE001 — demo proxy should never 500 blankly
        LOG.info("[route] agentcore_error error=%s", exc)
        return {
            "reply": f"AgentCore invoke failed: {exc}",
            "citations": [],
            "toolsUsed": [],
            "sessionId": session_id,
            "mode": "error",
            "error": str(exc),
        }
