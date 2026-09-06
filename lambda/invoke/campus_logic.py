"""Shared CampusAssist reasoning: tools + KB context + Bedrock reply."""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
# Lambda package layout: campus_logic.py + handlers.py + kb/ beside each other
# Repo layout: agent/campus_logic.py with ../lambda/tools and ../docs/kb
if (HERE / "handlers.py").exists():
    sys.path.insert(0, str(HERE))
    KB_ROOT = HERE / "kb" if (HERE / "kb").exists() else HERE.parents[1] / "docs" / "kb"
else:
    sys.path.insert(0, str(HERE.parents[1] / "lambda" / "tools"))
    KB_ROOT = HERE.parents[1] / "docs" / "kb"

from handlers import create_ticket, get_admission_deadline, get_exam_schedule  # noqa: E402

SYSTEM = """You are CampusAssist for Demo Institute of Technology.
Answer ONLY using college knowledge (admission, exams, regulations, fees) and tool results.
Always cite document titles when using knowledge base snippets.
If the question is off-topic, politely refuse.
Keep answers concise for a live demo."""


def run_campus_assist(message: str, session_id: str) -> dict[str, Any]:
    message = (message or "").strip()
    if not message:
        return {
            "reply": "Please ask a question about admission, exams, regulations, or fees.",
            "citations": [],
            "toolsUsed": [],
            "sessionId": session_id,
            "mode": "error",
        }

    context = gather_context(message)
    if context.get("offTopic"):
        return {
            "reply": context["refuse"],
            "citations": [],
            "toolsUsed": [],
            "sessionId": session_id,
            "mode": "off-topic",
        }

    use_bedrock = os.environ.get("USE_BEDROCK", "").lower() == "true"
    model_id = os.environ.get("BEDROCK_MODEL_ID", "").strip()
    if not (use_bedrock and model_id):
        return {
            "reply": (
                "Bedrock is required. Set USE_BEDROCK=true and BEDROCK_MODEL_ID "
                "(mock and hardcoded replies were removed)."
            ),
            "citations": context["citations"],
            "toolsUsed": context["toolsUsed"],
            "sessionId": session_id,
            "mode": "error",
        }

    try:
        reply = bedrock_generate(message, context)
        return {
            "reply": reply,
            "citations": context["citations"],
            "toolsUsed": context["toolsUsed"],
            "sessionId": session_id,
            "mode": "live-bedrock",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "reply": (
                f"Bedrock call failed: {exc}. "
                "Enable model access in the Bedrock console if you see Operation not allowed."
            ),
            "citations": context["citations"],
            "toolsUsed": context["toolsUsed"],
            "sessionId": session_id,
            "mode": "error",
            "bedrockError": str(exc),
        }


def gather_context(message: str) -> dict[str, Any]:
    lower = message.lower()
    tools_used: list[str] = []
    citations: list[dict[str, str]] = []
    tool_results: list[dict[str, Any]] = []
    kb_snippets: list[dict[str, str]] = []

    if _off_topic(lower):
        return {
            "offTopic": True,
            "refuse": (
                "I can only help with Demo College topics: admission, exams, "
                "academic regulations, and fees."
            ),
            "citations": [],
            "toolsUsed": [],
            "toolResults": [],
            "kbSnippets": [],
        }

    if any(k in lower for k in ("ticket", "raise a support", "fee clarification", "complaint")):
        ticket = create_ticket("Fee clarification", message, "fees")
        tools_used.append("create_ticket")
        tool_results.append({"tool": "create_ticket", "result": ticket})

    if any(
        k in lower
        for k in ("last date", "deadline", "admission this year", "b.tech admission", "btech admission")
    ):
        data = get_admission_deadline("B.Tech")
        tools_used.append("get_admission_deadline")
        tool_results.append({"tool": "get_admission_deadline", "result": data})

    if any(k in lower for k in ("exam schedule", "when is mid", "timetable")):
        kind = "mid-sem" if "mid" in lower else "end-sem"
        data = get_exam_schedule(kind)
        tools_used.append("get_exam_schedule")
        tool_results.append({"tool": "get_exam_schedule", "result": data})

    for hit in _search_kb(lower)[:3]:
        citations.append({"title": hit["title"], "snippet": hit["snippet"]})
        kb_snippets.append({"title": hit["title"], "snippet": hit["snippet"]})

    uniq: list[str] = []
    for t in tools_used:
        if t not in uniq:
            uniq.append(t)

    return {
        "offTopic": False,
        "citations": citations,
        "toolsUsed": uniq,
        "toolResults": tool_results,
        "kbSnippets": kb_snippets,
    }


def bedrock_generate(message: str, context: dict[str, Any]) -> str:
    import boto3

    model_id = os.environ.get("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0")
    client = boto3.client("bedrock-runtime")
    payload = {
        "toolResults": context.get("toolResults") or [],
        "kbSnippets": context.get("kbSnippets") or [],
        "citations": context.get("citations") or [],
    }
    user_content = (
        f"User question: {message}\n\n"
        f"Tool/KB context JSON:\n{json.dumps(payload, indent=2)}\n\n"
        "Write the final answer for the student. Include key facts from context."
    )
    resp = client.converse(
        modelId=model_id,
        system=[{"text": SYSTEM}],
        messages=[{"role": "user", "content": [{"text": user_content}]}],
    )
    return resp["output"]["message"]["content"][0]["text"]


def _off_topic(lower: str) -> bool:
    campus = (
        "attendance",
        "exam",
        "admission",
        "fee",
        "college",
        "semester",
        "medical",
        "document",
        "ticket",
        "b.tech",
        "btech",
        "leave",
        "regulation",
        "mid-sem",
        "midsem",
    )
    if any(k in lower for k in campus):
        return False
    return any(k in lower for k in ("poem", "mars", "joke", "song", "weather"))


def _search_kb(lower: str) -> list[dict[str, Any]]:
    keywords = [w for w in re.split(r"\W+", lower) if len(w) > 3]
    if not KB_ROOT.exists():
        return []
    hits: list[dict[str, Any]] = []
    for path in KB_ROOT.rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        score = sum(1 for k in keywords if k in text.lower())
        if score == 0:
            continue
        rel = str(path.relative_to(KB_ROOT)).replace("\\", "/")
        lines = [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.startswith("#")]
        snippet = next(
            (ln for ln in lines if any(k in ln.lower() for k in keywords)),
            lines[0] if lines else "",
        )[:220]
        hits.append({"title": rel, "snippet": snippet, "score": score})
    hits.sort(key=lambda h: h["score"], reverse=True)
    return hits
