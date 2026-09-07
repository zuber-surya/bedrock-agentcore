"""Shared CampusAssist reasoning: tools + KB context + Bedrock reply."""
from __future__ import annotations

import json
import logging
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
from students import (  # noqa: E402
    check_student_record,
    extract_student_id,
    wants_student_record,
)

# Primary + backup (account 390403887579 / IAM zuber, us-east-1)
DEFAULT_BEDROCK_MODEL_ID = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
DEFAULT_BEDROCK_FALLBACK_MODEL_ID = "us.amazon.nova-lite-v1:0"

# SYSTEM = """You are CampusAssist for Demo Institute of Technology.
# Answer ONLY using college knowledge (admission, exams, regulations, fees) and tool results.
# When toolResults or kbSnippets include amounts, dates, or table rows, quote those exact facts.
# Do not say information is missing if it appears in the provided context.
# Always cite document titles when using knowledge base snippets.
# If the question is off-topic, politely refuse.
# Keep answers concise for a live demo."""

SYSTEM = """
You are CampusAssist for Demo Institute of Technology.

SCOPE: Only answer questions about admission, exams, academic regulations, fees, and student records for this college. If a question is off-topic, politely decline and redirect to a relevant topic.

SOURCES OF TRUTH, IN THIS ORDER:
1. Tool results (check_student_record, create_ticket, get_admission_deadline, get_exam_schedule) — for anything about a specific student or live tool facts.
2. Knowledge base snippets — for general policy, exam, admission, and fee questions.
3. If neither source contains the answer, say: "I don't have that information — please contact the administration office." Never answer from general knowledge instead.

ACCURACY RULES:
- When a knowledge base snippet or tool result contains a specific amount, date, deadline, percentage, or table value, reproduce that value exactly as given — do not round, reword, or estimate it.
- For a specific student, use check_student_record only — never invent CGPA, attendance, or results.
- Do not combine or infer facts across two different documents unless both are directly relevant to the question.
- If retrieved snippets are only partially relevant, answer only the part you can support and say what's missing.

CITATION FORMAT (required every time you use a knowledge base snippet):
- Do NOT mention document names, titles, or "according to..." anywhere inside the main answer text.
- Only after the full answer, on a new final line, add:
Source: <document title>
If multiple documents were used, list them comma-separated on that same line.
- Do not cite a document you did not actually retrieve content from.

TOOL ACTIONS:
- Never guess a student ID — ask for it (demo IDs S1-001 … S1-006) if not provided.
- Before creating a support ticket, restate the issue briefly when helpful.

FORMAT FOR THIS LIVE DEMO:
- Prefer short, scannable answers (a short heading, bullets, or a small table when useful).
- Use markdown the UI can render: **bold**, headings (#/##), bullet lists (-), and pipe tables.
- For tables: blank line before and after; each row on its own line; header, then | --- | --- |, then body;
  every row must start and end with |. If unsure, use bullets instead of a broken table.
- Always end with the Source line after the answer body.
"""

LOG = logging.getLogger("campusassist.message")
if not LOG.handlers:
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setFormatter(logging.Formatter("%(message)s"))
    LOG.addHandler(_handler)
    LOG.setLevel(logging.INFO)
    LOG.propagate = False


def _mlog(tag: str, **fields: Any) -> None:
    """One structured line per processing step (visible in local stdout / CloudWatch)."""
    parts = [f"[{tag}]"]
    for key, val in fields.items():
        if val is None:
            continue
        if isinstance(val, (dict, list)):
            text = json.dumps(val, ensure_ascii=False, default=str)
        else:
            text = str(val).replace("\n", " ").strip()
        if len(text) > 240:
            text = text[:237] + "..."
        parts.append(f"{key}={text}")
    LOG.info(" ".join(parts))
    for h in LOG.handlers:
        try:
            h.flush()
        except Exception:
            pass


def run_campus_assist(message: str, session_id: str) -> dict[str, Any]:
    message = (message or "").strip()
    _mlog("msg", sessionId=session_id, message=message)
    if not message:
        out = {
            "reply": "Please ask a question about admission, exams, regulations, or fees.",
            "citations": [],
            "toolsUsed": [],
            "sessionId": session_id,
            "mode": "error",
        }
        _mlog("out", mode=out["mode"], toolsUsed=out["toolsUsed"], citations=0)
        return out

    context = gather_context(message)
    _mlog("filter", offTopic=bool(context.get("offTopic")))
    if context.get("offTopic"):
        out = {
            "reply": context["refuse"],
            "citations": [],
            "toolsUsed": [],
            "sessionId": session_id,
            "mode": "off-topic",
        }
        _mlog("out", mode=out["mode"], toolsUsed=[], citations=0, reply=out["reply"])
        return out

    if context.get("needsStudentId"):
        out = {
            "reply": context["askStudentId"],
            "citations": context.get("citations") or [],
            "toolsUsed": [],
            "sessionId": session_id,
            "mode": "live-bedrock",
        }
        _mlog("out", mode=out["mode"], needsStudentId=True)
        return out

    use_bedrock = os.environ.get("USE_BEDROCK", "").lower() == "true"
    model_id = (
        os.environ.get("BEDROCK_MODEL_ID", "").strip() or DEFAULT_BEDROCK_MODEL_ID
    )
    if not use_bedrock:
        out = {
            "reply": (
                "Bedrock is required. Set USE_BEDROCK=true "
                "(mock and hardcoded replies were removed)."
            ),
            "citations": context["citations"],
            "toolsUsed": context["toolsUsed"],
            "sessionId": session_id,
            "mode": "error",
        }
        _mlog("out", mode=out["mode"], toolsUsed=out["toolsUsed"], citations=len(out["citations"]))
        return out

    try:
        reply = bedrock_generate(message, context, model_id=model_id)
        out = {
            "reply": reply,
            "citations": context["citations"],
            "toolsUsed": context["toolsUsed"],
            "sessionId": session_id,
            "mode": "live-bedrock",
        }
        _mlog(
            "out",
            mode=out["mode"],
            toolsUsed=out["toolsUsed"],
            citations=len(out["citations"]),
            reply=out["reply"],
        )
        return out
    except Exception as exc:  # noqa: BLE001
        out = {
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
        _mlog("out", mode=out["mode"], error=str(exc), toolsUsed=out["toolsUsed"])
        return out


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
        _mlog("tools", matched="create_ticket")
        _mlog("tools.result", ticket_id=ticket.get("ticket_id"), category=ticket.get("category"))

    # Student record: attendance / results / CGPA (placement eligibility routes to placement agent)
    if wants_student_record(message) and not any(
        k in lower for k in ("placement", "campus drive", "eligible for campus")
    ):
        sid = extract_student_id(message)
        if not sid:
            return {
                "offTopic": False,
                "needsStudentId": True,
                "askStudentId": (
                    "Please share your student ID (demo format **S1-001** … **S1-006**) "
                    "so I can look up your attendance or academic results."
                ),
                "citations": [],
                "toolsUsed": [],
                "toolResults": [],
                "kbSnippets": [],
            }
        record = check_student_record(sid)
        tools_used.append("check_student_record")
        tool_results.append({"tool": "check_student_record", "result": record})
        _mlog(
            "tools",
            matched="check_student_record",
            studentId=sid,
            found=record.get("found"),
        )

    if any(
        k in lower
        for k in (
            "last date",
            "deadline",
            "admission this year",
            "b.tech admission",
            "btech admission",
            "application closes",
            "applications close",
            "application close",
            "closing date",
            "when application",
            "when do applications",
            "when does application",
        )
    ) or (
        "application" in lower
        and any(k in lower for k in ("close", "closes", "closing", "closed"))
    ):
        data = get_admission_deadline("B.Tech")
        tools_used.append("get_admission_deadline")
        tool_results.append({"tool": "get_admission_deadline", "result": data})
        _mlog("tools", matched="get_admission_deadline")
        _mlog(
            "tools.result",
            last_date=data.get("last_date"),
            opens=data.get("opens"),
            program=data.get("program"),
        )

    if any(k in lower for k in ("exam schedule", "when is mid", "timetable")):
        kind = "mid-sem" if "mid" in lower else "end-sem"
        data = get_exam_schedule(kind)
        tools_used.append("get_exam_schedule")
        tool_results.append({"tool": "get_exam_schedule", "result": data})
        _mlog("tools", matched="get_exam_schedule", kind=kind)
        _mlog(
            "tools.result",
            name=data.get("name"),
            window_start=data.get("window_start"),
            window_end=data.get("window_end"),
        )

    if not tools_used:
        _mlog("tools", matched="none")

    retrieved = _retrieve_kb(message)
    if retrieved is not None:
        hits = retrieved
        method = "retrieve"
    else:
        hits = _search_kb(lower)[:3]
        method = "keyword_line_score"
    _mlog(
        "kb",
        root=str(KB_ROOT),
        method=method,
        topK=3,
        hitCount=len(hits),
        kbId=os.environ.get("KNOWLEDGE_BASE_ID", "") or None,
    )
    for hit in hits:
        citations.append({"title": hit["title"], "snippet": hit["snippet"]})
        kb_snippets.append({"title": hit["title"], "snippet": hit["snippet"]})
        _mlog("kb.hit", title=hit["title"], score=hit.get("score"), snippet=hit["snippet"])

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


def _bedrock_model_chain(primary: str | None = None) -> list[str]:
    """Claude Haiku primary, Nova Lite backup (deduped, env-overridable)."""
    primary_id = (primary or os.environ.get("BEDROCK_MODEL_ID", "")).strip() or DEFAULT_BEDROCK_MODEL_ID
    fallback_id = (
        os.environ.get("BEDROCK_FALLBACK_MODEL_ID", "").strip()
        or DEFAULT_BEDROCK_FALLBACK_MODEL_ID
    )
    chain: list[str] = []
    for mid in (primary_id, fallback_id):
        if mid and mid not in chain:
            chain.append(mid)
    return chain


def bedrock_generate(
    message: str, context: dict[str, Any], model_id: str | None = None
) -> str:
    import boto3

    client = boto3.client("bedrock-runtime")
    payload = {
        "toolResults": context.get("toolResults") or [],
        "kbSnippets": context.get("kbSnippets") or [],
        "citations": context.get("citations") or [],
    }
    user_content = (
        f"User question: {message}\n\n"
        f"Tool/KB context JSON:\n{json.dumps(payload, indent=2)}\n\n"
        "Write the final answer for the student. "
        "Use exact amounts, dates, and table values from toolResults/kbSnippets when present. "
        "If a fee or tuition amount is in the context, state it clearly with INR."
    )
    chain = _bedrock_model_chain(model_id)
    last_exc: Exception | None = None
    for idx, mid in enumerate(chain):
        _mlog(
            "llm",
            service="bedrock-runtime",
            api="converse",
            modelId=mid,
            attempt=idx + 1,
            of=len(chain),
        )
        try:
            resp = client.converse(
                modelId=mid,
                system=[{"text": SYSTEM}],
                messages=[{"role": "user", "content": [{"text": user_content}]}],
                inferenceConfig={"maxTokens": 1024},
            )
            if idx > 0:
                _mlog("llm.fallback", used=mid, primary=chain[0])
            return resp["output"]["message"]["content"][0]["text"]
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            _mlog("llm.fail", modelId=mid, error=str(exc))
            continue
    assert last_exc is not None
    raise last_exc


def _off_topic(lower: str) -> bool:
    campus = (
        "attendance",
        "exam",
        "admission",
        "application",
        "fee",
        "tuition",
        "tution",
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


def _normalize_query(lower: str) -> str:
    """Fix common typos before keyword search."""
    replacements = (
        ("tution", "tuition"),
        ("tutions", "tuition"),
        ("btech", "b.tech"),
        ("semister", "semester"),
    )
    for src, dst in replacements:
        lower = lower.replace(src, dst)
    return lower


def _kb_sections(text: str) -> list[tuple[str, list[str]]]:
    """Split a KB doc into (heading, body_lines) sections on markdown headings.

    Content before the first heading (the H1 title plus metadata lines like
    "**Document type:**") becomes its own leading section. Splitting by section
    instead of by single line keeps a whole list/table together in one snippet
    instead of an arbitrary fixed-size line window cutting it off mid-list.
    """
    sections: list[tuple[str, list[str]]] = []
    heading = ""
    body: list[str] = []
    for ln in text.splitlines():
        s = ln.strip()
        if not s:
            continue
        if s.startswith("#"):
            if heading or body:
                sections.append((heading, body))
            heading = s.lstrip("#").strip()
            body = []
        else:
            body.append(s)
    if heading or body:
        sections.append((heading, body))
    return sections


def _section_score(heading: str, body: list[str], keywords: list[str]) -> int:
    text = (heading + " " + " ".join(body)).lower()
    score = sum(1 for k in keywords if k in text)
    if score == 0:
        return 0
    # Prefer sections with concrete facts (amounts / dates) over narrative ones.
    if any(ch.isdigit() for ch in text):
        score += 2
    if any(k in text for k in ("tuition", "fee", "deadline", "closes", "attendance", "%", "document")):
        score += 1
    # Deprioritize the metadata preamble section (institution name, doc type) —
    # it tends to false-positive match via substrings (e.g. "tech" in "Technology").
    if "document type" in text or "**institution:**" in text:
        score = max(0, score - 3)
    return score


def _section_snippet(heading: str, body: list[str]) -> str:
    parts = ([heading] if heading else []) + body
    return " ".join(parts)[:600]


def _title_from_s3_uri(uri: str) -> str:
    """Map s3://bucket/kb/fees/fee-policy.md -> fees/fee-policy.md."""
    if not uri:
        return "kb"
    marker = "/kb/"
    if marker in uri:
        return uri.split(marker, 1)[1]
    if uri.startswith("s3://"):
        parts = uri.split("/")
        return "/".join(parts[3:]) if len(parts) > 3 else uri
    return uri


def _retrieve_kb(
    query: str, *, uri_contains: str | None = None, number_of_results: int = 3
) -> list[dict[str, Any]] | None:
    """Bedrock Knowledge Bases Retrieve (S3 Vectors). None => caller should keyword-fallback.

    S3 Vectors does not support STRING_CONTAINS filters; uri_contains is client-side.
    """
    kb_id = (os.environ.get("KNOWLEDGE_BASE_ID") or "").strip()
    if not kb_id:
        return None
    try:
        import boto3

        client = boto3.client("bedrock-agent-runtime")
        fetch_n = max(number_of_results * 5, 10) if uri_contains else number_of_results
        resp = client.retrieve(
            knowledgeBaseId=kb_id,
            retrievalQuery={"text": query},
            retrievalConfiguration={
                "vectorSearchConfiguration": {"numberOfResults": fetch_n}
            },
        )
        hits: list[dict[str, Any]] = []
        for item in resp.get("retrievalResults") or []:
            meta = item.get("metadata") or {}
            loc = item.get("location") or {}
            s3_loc = loc.get("s3Location") or {}
            uri = (
                s3_loc.get("uri")
                or meta.get("x-amz-bedrock-kb-source-uri")
                or ""
            )
            if uri_contains and uri_contains not in str(uri):
                continue
            text = ((item.get("content") or {}).get("text") or "").strip()
            if not text:
                continue
            hits.append(
                {
                    "title": _title_from_s3_uri(str(uri)),
                    "snippet": text[:4000],
                    "score": item.get("score"),
                }
            )
            if len(hits) >= number_of_results:
                break
        return hits
    except Exception as exc:  # noqa: BLE001 — fallback to keyword search
        _mlog("kb", method="retrieve", error=str(exc))
        return None


def _search_kb(lower: str) -> list[dict[str, Any]]:
    lower = _normalize_query(lower)
    keywords = [w for w in re.split(r"\W+", lower) if len(w) > 2]
    # Stem-ish expansions so typos / variants still hit KB lines
    expanded = list(keywords)
    for k in keywords:
        if k.startswith("clos"):
            expanded.extend(["close", "closes", "closing", "closed", "deadline", "last date"])
        if k.startswith("applic"):
            expanded.append("application")
        if k.startswith("tuit") or k == "tution":
            expanded.extend(["tuition", "fee", "fees", "amount"])
        if k.startswith("fee"):
            expanded.extend(["fee", "fees", "tuition", "amount", "inr"])
        if k.startswith("document"):
            expanded.extend(["document", "documents", "upload", "submit", "certificate"])
    keywords = list(dict.fromkeys(expanded))
    if not KB_ROOT.exists():
        return []
    hits: list[dict[str, Any]] = []
    for path in KB_ROOT.rglob("*.md"):
        rel = str(path.relative_to(KB_ROOT)).replace("\\", "/")
        if rel.startswith("placement/"):
            continue
        text = path.read_text(encoding="utf-8")
        sections = _kb_sections(text)
        if not sections:
            continue
        best_heading, best_body, best_score = max(
            ((h, b, _section_score(h, b, keywords)) for h, b in sections),
            key=lambda t: t[2],
        )
        if best_score <= 0:
            continue
        # Prefer fee policy for fee/tuition questions
        if any(k in lower for k in ("fee", "tuition", "tution")) and rel.startswith("fees/"):
            best_score += 5
        hits.append({"title": rel, "snippet": _section_snippet(best_heading, best_body), "score": best_score})
    hits.sort(key=lambda h: h["score"], reverse=True)
    return hits
