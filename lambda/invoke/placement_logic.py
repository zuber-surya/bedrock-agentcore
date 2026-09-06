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
1. Knowledge base snippets from the placement docs.
2. If the snippets do not contain the answer, say you do not have that information and suggest contacting placement@demo-college.edu. Never invent company lists or CGPA cutoffs.

ACCURACY:
- Quote exact CGPA, percentages, dates, and table values from the snippets.
- Do not invent drives or companies not present in the context.

CITATION FORMAT:
- Do not mention document names inside the main answer.
- After the answer, on a final line: Source: <document title>

FORMAT:
- Short scannable markdown: **bold**, headings, bullets, or a small table when useful.
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
            "toolsUsed": [],
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

    hits = _search_kb(lower)[:3]
    _mlog("kb", root=str(KB_ROOT), hitCount=len(hits))
    citations: list[dict[str, str]] = []
    kb_snippets: list[dict[str, str]] = []
    for hit in hits:
        citations.append({"title": hit["title"], "snippet": hit["snippet"]})
        kb_snippets.append({"title": hit["title"], "snippet": hit["snippet"]})
        _mlog("kb.hit", title=hit["title"], score=hit.get("score"))

    return {
        "offTopic": False,
        "citations": citations,
        "toolsUsed": [],
        "toolResults": [],
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
        "Write the final answer for the student using exact values from the snippets."
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
