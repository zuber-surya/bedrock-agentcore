"""Campus Placement agent for Amazon Bedrock AgentCore Runtime (direct code deploy).

Entrypoint returns JSON: { reply, citations, toolsUsed, sessionId, agent }.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


_load_dotenv(ROOT.parent / ".env")
os.environ.setdefault("USE_BEDROCK", "true")
os.environ.setdefault("BEDROCK_MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001-v1:0")
os.environ.setdefault("BEDROCK_FALLBACK_MODEL_ID", "us.amazon.nova-lite-v1:0")

from placement_logic import run_placement_assist  # noqa: E402
from bedrock_agentcore.runtime import BedrockAgentCoreApp

app = BedrockAgentCoreApp()


def _extract_message(payload: dict[str, Any]) -> tuple[str, str]:
    if not isinstance(payload, dict):
        return "", "local-session"
    inner = payload.get("input") if isinstance(payload.get("input"), dict) else payload
    message = (
        inner.get("prompt")
        or inner.get("message")
        or inner.get("inputText")
        or ""
    )
    if isinstance(message, dict):
        message = message.get("text") or json.dumps(message)
    session_id = (
        inner.get("sessionId")
        or inner.get("session_id")
        or payload.get("sessionId")
        or payload.get("session_id")
        or "local-session"
    )
    return str(message), str(session_id)


@app.entrypoint
def invoke(payload: dict[str, Any]):
    if isinstance(payload, (str, bytes)):
        try:
            payload = json.loads(payload)
        except Exception:  # noqa: BLE001
            payload = {"prompt": str(payload)}
    if not isinstance(payload, dict):
        payload = {}
    message, session_id = _extract_message(payload)
    print(
        f"[agent] entrypoint=agent-placement/main.py:invoke "
        f"runtime={os.environ.get('AGENTCORE_RUNTIME', '')} "
        f"sessionId={session_id} message={message.replace(chr(10), ' ')[:200]}",
        flush=True,
    )
    return run_placement_assist(message, session_id)


def main():
    msg = sys.argv[1] if len(sys.argv) > 1 else "Am I eligible for campus placement?"
    print(json.dumps(run_placement_assist(msg, "cli"), indent=2))


if __name__ == "__main__":
    if len(sys.argv) > 1 and os.environ.get("AGENTCORE_RUNTIME") != "1":
        main()
    else:
        app.run()
