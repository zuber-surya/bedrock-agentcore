"""API Gateway → AgentCore Runtime invoke proxy.

Env:
  AGENT_RUNTIME_ARN — AgentCore runtime agent ARN (optional in local mock mode)
  MOCK_MODE — if "true", answer from local KB snippets + tools (no AWS call)
"""
from __future__ import annotations

import json
import os
import re
import uuid
from pathlib import Path
from typing import Any

# Allow importing sibling tools package when packaged flat or as lambda/tools
try:
    from handlers import (  # type: ignore
        create_ticket,
        get_admission_deadline,
        get_exam_schedule,
    )
except ImportError:
    from tools.handlers import (  # type: ignore
        create_ticket,
        get_admission_deadline,
        get_exam_schedule,
    )

CORS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Allow-Methods": "POST,OPTIONS",
    "Content-Type": "application/json",
}

KB_ROOT = Path(__file__).resolve().parents[2] / "docs" / "kb"


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

    mock = os.environ.get("MOCK_MODE", "true").lower() == "true"
    if mock or not os.environ.get("AGENT_RUNTIME_ARN"):
        result = mock_chat(message, session_id)
    else:
        result = invoke_agentcore(message, session_id)

    return _resp(200, result)


def _resp(status: int, body: dict[str, Any]) -> dict[str, Any]:
    return {"statusCode": status, "headers": CORS, "body": json.dumps(body)}


def invoke_agentcore(message: str, session_id: str) -> dict[str, Any]:
    """Invoke Bedrock AgentCore Runtime. Falls back to mock on failure."""
    try:
        import boto3

        client = boto3.client("bedrock-agentcore")
        arn = os.environ["AGENT_RUNTIME_ARN"]
        response = client.invoke_agent_runtime(
            agentRuntimeArn=arn,
            runtimeSessionId=session_id[:100],
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
                return parsed
        except json.JSONDecodeError:
            pass
        return {
            "reply": text,
            "citations": [],
            "toolsUsed": [],
            "sessionId": session_id,
        }
    except Exception as exc:  # noqa: BLE001 — demo proxy should never 500 blankly
        fallback = mock_chat(message, session_id)
        fallback["warning"] = f"AgentCore invoke failed; used mock. ({exc})"
        return fallback


def mock_chat(message: str, session_id: str) -> dict[str, Any]:
    """Deterministic local demo brain using tools + simple KB keyword retrieval."""
    lower = message.lower()
    tools_used: list[str] = []
    citations: list[dict[str, str]] = []
    reply_parts: list[str] = []

    if _is_off_topic(lower):
        return {
            "reply": (
                "I can only help with Demo College topics: admission, exams, "
                "academic regulations, and fees. Please ask a campus-related question."
            ),
            "citations": [],
            "toolsUsed": [],
            "sessionId": session_id,
        }

    if any(k in lower for k in ("ticket", "raise a support", "fee clarification", "complaint")):
        ticket = create_ticket(
            subject="Fee clarification",
            details=message,
            category="fees",
        )
        tools_used.append("create_ticket")
        reply_parts.append(ticket["message"])
        reply_parts.append(f"Ticket ID: **{ticket['ticket_id']}** (status: {ticket['status']}).")

    if any(k in lower for k in ("last date", "deadline", "admission this year", "b.tech admission", "btech admission")):
        data = get_admission_deadline("B.Tech")
        tools_used.append("get_admission_deadline")
        reply_parts.append(
            f"For {data['program']}, applications open {data['opens']} and the "
            f"**last date is {data['last_date']}**. {data['note']}"
        )

    if any(k in lower for k in ("exam schedule", "when is mid", "timetable")):
        data = get_exam_schedule("mid-sem" if "mid" in lower else "end-sem")
        tools_used.append("get_exam_schedule")
        reply_parts.append(
            f"{data['name']}: {data['window_start']} to {data['window_end']}. {data['note']}"
        )

    # RAG-ish keyword hits from local docs
    hits = _search_kb(lower)
    seen_answers: set[str] = set()
    for hit in hits[:3]:
        citations.append({"title": hit["title"], "snippet": hit["snippet"]})
        if hit["answer"] not in seen_answers:
            seen_answers.add(hit["answer"])
            reply_parts.append(hit["answer"])

    if not reply_parts:
        reply_parts.append(
            "I could not find a specific answer in the college knowledge base. "
            "Try asking about attendance, medical leave, admission documents, deadlines, or fees."
        )

    # Deduplicate tools while preserving order
    seen: set[str] = set()
    unique_tools = []
    for t in tools_used:
        if t not in seen:
            seen.add(t)
            unique_tools.append(t)

    return {
        "reply": "\n\n".join(reply_parts),
        "citations": citations,
        "toolsUsed": unique_tools,
        "sessionId": session_id,
    }


def _is_off_topic(lower: str) -> bool:
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
    creative = ("poem", "mars", "joke", "song", "story about", "weather")
    return any(k in lower for k in creative)


def _search_kb(lower: str) -> list[dict[str, str]]:
    if not KB_ROOT.exists():
        return _builtin_hits(lower)

    keywords = [w for w in re.split(r"\W+", lower) if len(w) > 3]
    hits: list[dict[str, str]] = []
    for path in KB_ROOT.rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        score = sum(1 for k in keywords if k in text.lower())
        if score == 0:
            continue
        snippet = _best_snippet(text, keywords)
        rel = str(path.relative_to(KB_ROOT)).replace("\\", "/")
        hits.append(
            {
                "title": rel,
                "snippet": snippet,
                "answer": _answer_from_doc(rel, text, lower),
                "score": score,
            }
        )
    hits.sort(key=lambda h: h["score"], reverse=True)
    return hits


def _best_snippet(text: str, keywords: list[str]) -> str:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.startswith("#")]
    for ln in lines:
        if any(k in ln.lower() for k in keywords):
            return ln[:220]
    return (lines[0] if lines else text[:220])[:220]


def _answer_from_doc(rel: str, text: str, lower: str) -> str:
    if "attendance" in lower and "75%" in text:
        return (
            "Per academic regulations and exam rules, students need **minimum 75% attendance** "
            "in each subject to be eligible for end-semester exams. "
            f"(Source: {rel})"
        )
    if "medical" in lower or "mid-sem" in lower or "midsem" in lower:
        if "medical" in text.lower():
            return (
                "If you miss a mid-sem for medical reasons, submit a medical certificate within "
                "**3 working days**, apply for medical leave, and CoE may allow a re-test or "
                f"adjust internals. Medical leave does not automatically waive the 75% rule. (Source: {rel})"
            )
    if "document" in lower and "admission" in text.lower():
        return (
            "Admission documents typically include Class 10 & 12 mark sheets, transfer certificate, "
            "photos, government ID, category certificate if applicable, and entrance score card. "
            f"(Source: {rel})"
        )
    snippet = _best_snippet(text, [w for w in re.split(r"\W+", lower) if len(w) > 3])
    return f"From {rel}: {snippet}"


def _builtin_hits(lower: str) -> list[dict[str, str]]:
    """Fallback if docs/kb is not packaged with the Lambda."""
    out: list[dict[str, str]] = []
    if "attendance" in lower:
        out.append(
            {
                "title": "regulations/attendance-conduct.md",
                "snippet": "Students must maintain at least 75% attendance in every credited course.",
                "answer": (
                    "Per academic regulations, students need **minimum 75% attendance** "
                    "to be eligible for semester exams. Below 65% leads to detention unless exception is granted."
                ),
                "score": 5,
            }
        )
    if "medical" in lower or "mid-sem" in lower:
        out.append(
            {
                "title": "exams/medical-leave-exams.md",
                "snippet": "Submit a medical certificate within 3 working days of returning to campus.",
                "answer": (
                    "For a missed mid-sem due to illness: submit medical certificate within 3 working days, "
                    "apply for medical leave; CoE may schedule a re-test. Attendance rule still applies."
                ),
                "score": 5,
            }
        )
    if "document" in lower:
        out.append(
            {
                "title": "admission/brochure.md",
                "snippet": "Class 10 mark sheet, Class 12 mark sheet, transfer certificate, photographs, photo ID…",
                "answer": (
                    "Required admission documents: Class 10 & 12 mark sheets, TC, photos, government ID, "
                    "category certificate if applicable, and entrance score card."
                ),
                "score": 5,
            }
        )
    return out
