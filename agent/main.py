"""CampusAssist agent for Amazon Bedrock AgentCore Runtime (direct code deploy).

Entrypoint returns JSON: { reply, citations, toolsUsed, sessionId }.
Uses Bedrock Converse when credentials/model available; otherwise deterministic mock tools+KB.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

# Local imports for ZIP layout
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent / "lambda" / "tools"))

from campus_logic import run_campus_assist  # noqa: E402

try:
    from bedrock_agentcore.runtime import BedrockAgentCoreApp

    app = BedrockAgentCoreApp()
except ImportError:
    # Local / unit-test fallback without the AgentCore SDK installed
    class BedrockAgentCoreApp:  # type: ignore
        def entrypoint(self, fn):
            self._fn = fn
            return fn

        def run(self):
            pass

    app = BedrockAgentCoreApp()


@app.entrypoint
def invoke(payload: dict[str, Any]):
    message = (
        payload.get("prompt")
        or payload.get("message")
        or payload.get("inputText")
        or ""
    )
    if isinstance(message, dict):
        message = message.get("text") or json.dumps(message)
    session_id = payload.get("sessionId") or payload.get("session_id") or "local-session"
    result = run_campus_assist(str(message), str(session_id))
    return result


def main():
    # CLI smoke: python -m agent.main "What is minimum attendance?"
    msg = sys.argv[1] if len(sys.argv) > 1 else "What is the minimum attendance for semester exams?"
    print(json.dumps(run_campus_assist(msg, "cli"), indent=2))


if __name__ == "__main__":
    if os.environ.get("AGENTCORE_RUNTIME") == "1":
        app.run()
    else:
        main()
