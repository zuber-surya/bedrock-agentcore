"""Campus Placement agent: placement KB + Bedrock reply."""
from __future__ import annotations

import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
# AgentCore ZIP: placement_logic.py + kb/placement/
# Lambda invoke: placement_logic.py + kb/placement/ beside it
# Repo agent-placement/: same layout; fallback to docs/kb/placement
if (HERE / "kb" / "placement").is_dir():
    KB_ROOT = HERE / "kb" / "placement"
elif (HERE / "kb").is_dir() and any((HERE / "kb").rglob("*.md")):
    KB_ROOT = HERE / "kb"
else:
    KB_ROOT = HERE.parents[1] / "docs" / "kb" / "placement"

DEFAULT_BEDROCK_MODEL_ID = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
DEFAULT_BEDROCK_FALLBACK_MODEL_ID = "us.amazon.nova-lite-v1:0"

SYSTEM = """
You are the Campus Placement assistant for Demo Institute of Technology (Training & Placement Cell).

SCOPE: Only answer questions about campus placement, drives, eligibility, internships-to-PPO, T&P process, and placement contacts.
If the question is about admission, exams, fees, or general academics, politely say to ask CampusAssist instead.

SOURCES OF TRUTH:
1. Tool results from check_student_record (student CGPA, attendance, arrears, results, eligibility) when a student ID is provided.
2. Knowledge base snippets from the placement docs (policy text).
3. If neither source contains the answer, say you do not have that information and suggest contacting placement@demo-college.edu.
   Never invent company lists, drive dates, CGPA cutoffs, contact details, or student facts.

ACCURACY:
- Quote exact CGPA, percentages, arrears rules, windows, phone/email, and company names from the snippets or tool results.
- For a specific student, use check_student_record / placementEligibility only — do not invent eligible/not.
- Do not invent drives, companies, sectors, or columns that are not in the snippets.
- Prefer the snippet's own wording for lists (keep company names as written).

CITATION FORMAT:
- Do not mention document names inside the main answer.
- After the answer, on a final line: Source: <document title>

MARKDOWN FORMAT:
- Short scannable markdown: **bold**, headings (#/##), bullets (-).
- For tables: put a blank line before and after the table; each row on its own line;
  header row, then a separator row like | --- | --- |, then body rows; every row must start and end with |.
- If a clean pipe table is awkward, use a bullet list instead of a broken table.
"""

LOG = logging.getLogger("campusassist.placement")
if not LOG.handlers:
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setFormatter(logging.Formatter("%(message)s"))
    LOG.addHandler(_handler)
    LOG.setLevel(logging.INFO)
    LOG.propagate = False


def _mlog(tag: str, **fields: Any) -> None:
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


def run_placement_assist(message: str, session_id: str) -> dict[str, Any]:
    message = (message or "").strip()
    _mlog("msg", agent="placement", sessionId=session_id, message=message)
    if not message:
        out = {
            "reply": "Please ask a question about campus placement, drives, or eligibility.",
            "citations": [],
            "toolsUsed": [],
            "sessionId": session_id,
            "mode": "error",
            "agent": "placement",
        }
        _mlog("out", mode=out["mode"], citations=0)
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
            "agent": "placement",
        }
        _mlog("out", mode=out["mode"], reply=out["reply"])
        return out

    if context.get("needsStudentId"):
        out = {
            "reply": context["askStudentId"],
            "citations": context.get("citations") or [],
            "toolsUsed": [],
            "sessionId": session_id,
            "mode": "live-bedrock",
            "agent": "placement",
        }
        _mlog("out", mode=out["mode"], needsStudentId=True)
        return out

    use_bedrock = os.environ.get("USE_BEDROCK", "").lower() == "true"
    model_id = os.environ.get("BEDROCK_MODEL_ID", "").strip() or DEFAULT_BEDROCK_MODEL_ID
    if not use_bedrock:
        out = {
            "reply": "Bedrock is required. Set USE_BEDROCK=true.",
            "citations": context["citations"],
            "toolsUsed": [],
            "sessionId": session_id,
            "mode": "error",
            "agent": "placement",
        }
        return out

    try:
        reply = bedrock_generate(message, context, model_id=model_id)
        out = {
            "reply": reply,
            "citations": context["citations"],
            "toolsUsed": context.get("toolsUsed") or [],
            "sessionId": session_id,
            "mode": "live-bedrock",
            "agent": "placement",
        }
        _mlog(
            "out",
            mode=out["mode"],
            citations=len(out["citations"]),
            reply=out["reply"],
        )
        return out
    except Exception as exc:  # noqa: BLE001
        out = {
            "reply": f"Bedrock call failed: {exc}.",
            "citations": context["citations"],
            "toolsUsed": [],
            "sessionId": session_id,
            "mode": "error",
            "agent": "placement",
            "bedrockError": str(exc),
        }
        _mlog("out", mode=out["mode"], error=str(exc))
        return out


def gather_context(message: str) -> dict[str, Any]:
    from students import (
        check_student_record,
        extract_student_id,
        wants_student_record,
    )

    lower = message.lower()
    if _off_topic(lower):
        return {
            "offTopic": True,
            "refuse": (
                "I only help with campus placement (drives, eligibility, T&P process). "
                "For admission, exams, fees, or regulations, ask CampusAssist."
            ),
            "citations": [],
            "toolsUsed": [],
            "toolResults": [],
            "kbSnippets": [],
        }

    tools_used: list[str] = []
    tool_results: list[dict[str, Any]] = []

    if wants_student_record(message):
        sid = extract_student_id(message)
        if not sid:
            return {
                "offTopic": False,
                "needsStudentId": True,
                "askStudentId": (
                    "Please share your student ID (demo format **S1-001** … **S1-006**) "
                    "so I can check your placement eligibility and record."
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
            eligible=(record.get("placementEligibility") or {}).get("eligible"),
        )

    hits_raw = _retrieve_kb(message, uri_contains="placement/")
    if hits_raw is not None:
        hits = hits_raw
        method = "retrieve"
    else:
        hits = _search_kb(lower)[:3]
        method = "keyword"
    _mlog(
        "kb",
        root=str(KB_ROOT),
        method=method,
        hitCount=len(hits),
        kbId=os.environ.get("KNOWLEDGE_BASE_ID", "") or None,
    )
    citations: list[dict[str, str]] = []
    kb_snippets: list[dict[str, str]] = []
    for hit in hits:
        citations.append({"title": hit["title"], "snippet": hit["snippet"]})
        kb_snippets.append({"title": hit["title"], "snippet": hit["snippet"]})
        _mlog("kb.hit", title=hit["title"], score=hit.get("score"))

    return {
        "offTopic": False,
        "citations": citations,
        "toolsUsed": tools_used,
        "toolResults": tool_results,
        "kbSnippets": kb_snippets,
    }


def _bedrock_model_chain(primary: str | None = None) -> list[str]:
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
        f"Placement KB context JSON:\n{json.dumps(payload, indent=2)}\n\n"
        "Write the final answer for the student using only exact values from toolResults "
        "and kbSnippets.\n"
        "If check_student_record is present, state eligibility using placementEligibility "
        "and quote student CGPA/attendance/arrears from the tool — do not invent them.\n"
        "Do not invent companies, sectors, or dates. Use valid pipe-table markdown "
        "(blank line before table; header; | --- | --- |; body rows) or bullets."
    )
    chain = _bedrock_model_chain(model_id)
    last_exc: Exception | None = None
    for idx, mid in enumerate(chain):
        _mlog("llm", modelId=mid, attempt=idx + 1, of=len(chain))
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
    placement = (
        "placement",
        "campus drive",
        "recruit",
        "job",
        "offer",
        "company",
        "internship",
        "ppo",
        "t&p",
        "t and p",
        "training and placement",
        "eligible",
        "eligibility",
        "cgpa",
        "arrear",
        "backlog",
    )
    if any(k in lower for k in placement):
        return False
    # Clearly non-placement campus topics → redirect
    campus_other = (
        "attendance",
        "exam",
        "admission",
        "fee",
        "tuition",
        "ticket",
        "medical leave",
        "brochure",
    )
    if any(k in lower for k in campus_other):
        return True
    return any(k in lower for k in ("poem", "mars", "joke", "song", "weather"))


def _kb_sections(text: str) -> list[tuple[str, list[str]]]:
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
    heading_l = heading.lower()
    body_l = " ".join(body).lower()
    text = heading_l + " " + body_l
    score = sum(1 for k in keywords if k in text)
    if score == 0:
        return 0
    # Strong boost when the section heading matches the question (companies / contact)
    score += sum(3 for k in keywords if k in heading_l)
    if any(ch.isdigit() for ch in text):
        score += 2
    if any(k in text for k in ("eligibility", "cgpa", "drive", "placement", "%", "contact", "company", "agency")):
        score += 1
    if "document type" in text or "**institution:**" in text:
        score = max(0, score - 3)
    return score


def _section_snippet(heading: str, body: list[str]) -> str:
    parts = ([heading] if heading else []) + body
    return " ".join(parts)[:600]


def _title_from_s3_uri(uri: str) -> str:
    """Map s3://bucket/kb/placement/overview.md -> placement/overview.md."""
    if not uri:
        return "placement"
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
    """Bedrock Knowledge Bases Retrieve (S3 Vectors). None => keyword fallback.

    S3 Vectors does not support STRING_CONTAINS filters, so uri_contains is
    applied client-side against the result S3 URI.
    """
    kb_id = (os.environ.get("KNOWLEDGE_BASE_ID") or "").strip()
    if not kb_id:
        return None
    try:
        import boto3

        client = boto3.client("bedrock-agent-runtime")
        # Over-fetch when URI-filtering so placement chunks still fill topK.
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
            title = _title_from_s3_uri(str(uri))
            if not title.startswith("placement/"):
                title = f"placement/{title}" if title else "placement/overview.md"
            hits.append(
                {
                    "title": title,
                    # Keep enough text for full placement overview (~1.7KB); 600 was truncating companies/eligibility.
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
    keywords = [w for w in re.split(r"\W+", lower) if len(w) > 2]
    expanded = list(keywords)
    for k in keywords:
        if k.startswith("eligib"):
            expanded.extend(["eligibility", "cgpa", "backlog", "arrear", "attendance"])
        if k.startswith("plac"):
            expanded.extend(["placement", "drive", "t&p", "company", "agency"])
        if k.startswith("compan") or k == "agency":
            expanded.extend(["company", "companies", "agency", "drive", "novasoft", "contour", "helix", "riverbank"])
        if k.startswith("contact") or k in ("email", "phone", "portal", "call"):
            expanded.extend(["contact", "email", "phone", "portal", "placement@", "t&p", "cell"])
        if k.startswith("intern"):
            expanded.extend(["internship", "ppo"])
    keywords = list(dict.fromkeys(expanded))
    if not KB_ROOT.exists():
        return []
    hits: list[dict[str, Any]] = []
    for path in KB_ROOT.rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        sections = _kb_sections(text)
        if not sections:
            continue
        rel = str(path.relative_to(KB_ROOT)).replace("\\", "/")
        title_base = rel if rel.startswith("placement/") else f"placement/{rel}"
        # Keep top scoring sections (not only the single best) so companies/contact
        # are not drowned out by the process section sharing the word "placement".
        ranked = sorted(
            ((h, b, _section_score(h, b, keywords)) for h, b in sections),
            key=lambda t: t[2],
            reverse=True,
        )
        for heading, body, score in ranked[:3]:
            if score <= 0:
                continue
            hits.append(
                {
                    "title": title_base,
                    "snippet": _section_snippet(heading, body),
                    "score": score,
                }
            )
    hits.sort(key=lambda h: h["score"], reverse=True)
    return hits
