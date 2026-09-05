"""Shared CampusAssist reasoning: tools + KB retrieval + optional Bedrock."""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

TOOLS = Path(__file__).resolve().parents[1] / "lambda" / "tools"
sys.path.insert(0, str(TOOLS))

from handlers import create_ticket, get_admission_deadline, get_exam_schedule  # noqa: E402

KB_ROOT = Path(__file__).resolve().parents[1] / "docs" / "kb"

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
        }

    # Prefer Bedrock when configured; always gather tool/KB context first
    context = gather_context(message)
    if os.environ.get("BEDROCK_MODEL_ID") and os.environ.get("USE_BEDROCK", "").lower() == "true":
        try:
            reply = bedrock_generate(message, context)
            return {
                "reply": reply,
                "citations": context["citations"],
                "toolsUsed": context["toolsUsed"],
                "sessionId": session_id,
            }
        except Exception as exc:  # noqa: BLE001
            context["reply"] += f"\n\n_(Bedrock unavailable: {exc}; showing grounded fallback.)_"

    return {
        "reply": context["reply"],
        "citations": context["citations"],
        "toolsUsed": context["toolsUsed"],
        "sessionId": session_id,
    }


def gather_context(message: str) -> dict[str, Any]:
    lower = message.lower()
    tools_used: list[str] = []
    citations: list[dict[str, str]] = []
    parts: list[str] = []

    if _off_topic(lower):
        return {
            "reply": (
                "I can only help with Demo College topics: admission, exams, "
                "academic regulations, and fees."
            ),
            "citations": [],
            "toolsUsed": [],
        }

    if any(k in lower for k in ("ticket", "raise a support", "fee clarification", "complaint")):
        ticket = create_ticket("Fee clarification", message, "fees")
        tools_used.append("create_ticket")
        parts.append(ticket["message"] + f" Ticket ID: **{ticket['ticket_id']}**.")

    if any(
        k in lower
        for k in ("last date", "deadline", "admission this year", "b.tech admission", "btech admission")
    ):
        data = get_admission_deadline("B.Tech")
        tools_used.append("get_admission_deadline")
        parts.append(
            f"For {data['program']}, the **last date is {data['last_date']}** "
            f"(opens {data['opens']}). {data['note']}"
        )

    if any(k in lower for k in ("exam schedule", "when is mid", "timetable")):
        kind = "mid-sem" if "mid" in lower else "end-sem"
        data = get_exam_schedule(kind)
        tools_used.append("get_exam_schedule")
        parts.append(
            f"{data['name']}: {data['window_start']} to {data['window_end']}. {data['note']}"
        )

    seen_answers: set[str] = set()
    for hit in _search_kb(lower)[:3]:
        citations.append({"title": hit["title"], "snippet": hit["snippet"]})
        if hit["answer"] not in seen_answers:
            seen_answers.add(hit["answer"])
            parts.append(hit["answer"])

    if not parts:
        parts.append(
            "I could not find that in the college knowledge base. "
            "Try attendance, medical leave, admission documents, deadlines, or fees."
        )

    # unique tools
    uniq: list[str] = []
    for t in tools_used:
        if t not in uniq:
            uniq.append(t)

    return {"reply": "\n\n".join(parts), "citations": citations, "toolsUsed": uniq}


def bedrock_generate(message: str, context: dict[str, Any]) -> str:
    import boto3

    model_id = os.environ.get("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0")
    client = boto3.client("bedrock-runtime")
    user_content = (
        f"User question: {message}\n\n"
        f"Tool/KB context JSON:\n{json.dumps(context, indent=2)}\n\n"
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
        snippet = next((ln for ln in lines if any(k in ln.lower() for k in keywords)), lines[0] if lines else "")[
            :220
        ]
        answer = _format_answer(rel, text, lower, snippet)
        hits.append({"title": rel, "snippet": snippet, "answer": answer, "score": score})
    hits.sort(key=lambda h: h["score"], reverse=True)
    return hits


def _format_answer(rel: str, text: str, lower: str, snippet: str) -> str:
    if "attendance" in lower and "75%" in text:
        return (
            f"Per college rules, **minimum 75% attendance** is required for end-semester exam eligibility. "
            f"(Source: {rel})"
        )
    if ("medical" in lower or "mid-sem" in lower) and "medical" in text.lower():
        return (
            "Missed mid-sem for medical reasons: submit certificate within **3 working days**, "
            f"apply for medical leave; CoE may allow re-test. 75% attendance rule still applies. (Source: {rel})"
        )
    if "document" in lower:
        return (
            "Admission documents include Class 10 & 12 mark sheets, TC, photos, government ID, "
            f"category certificate if applicable, and entrance score card. (Source: {rel})"
        )
    return f"From {rel}: {snippet}"
