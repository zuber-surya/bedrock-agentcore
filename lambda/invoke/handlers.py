"""CampusAssist tool handlers — used as Lambda functions and by local agent.

Facts (dates, fees, rules) come from KB markdown under kb/ or docs/kb — not from
hardcoded answer tables in this module.
"""
from __future__ import annotations

import json
import random
import re
import string
from datetime import date
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent


def _kb_root() -> Path:
    # Packaged next to handlers.py (Lambda / AgentCore zip) or repo docs/kb
    if (HERE / "kb").is_dir():
        return HERE / "kb"
    repo_kb = HERE.parents[1] / "docs" / "kb"
    if repo_kb.is_dir():
        return repo_kb
    return HERE / "kb"


def _read_kb(*parts: str) -> str:
    path = _kb_root().joinpath(*parts)
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def _normalize_program(program: str | None) -> str:
    if not program:
        return "b.tech"
    key = program.strip().lower().replace(" ", "")
    if key in ("btech", "b.tech", "b.e", "be"):
        return "b.tech"
    if key in ("mtech", "m.tech"):
        return "m.tech"
    return key


def _parse_iso_or_text(raw: str) -> str:
    """Normalize common demo date forms to YYYY-MM-DD when possible."""
    raw = raw.strip().strip("*")
    # 30 June 2026 / 1 March 2026
    m = re.search(
        r"(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})",
        raw,
        re.I,
    )
    if m:
        day, month, year = int(m.group(1)), m.group(2).lower(), int(m.group(3))
        months = {
            "january": 1,
            "february": 2,
            "march": 3,
            "april": 4,
            "may": 5,
            "june": 6,
            "july": 7,
            "august": 8,
            "september": 9,
            "october": 10,
            "november": 11,
            "december": 12,
        }
        return f"{year:04d}-{months[month]:02d}-{day:02d}"
    m = re.search(r"(\d{4}-\d{2}-\d{2})", raw)
    if m:
        return m.group(1)
    return raw


def get_admission_deadline(program: str | None = "B.Tech") -> dict[str, Any]:
    key = _normalize_program(program)
    brochure = _read_kb("admission", "brochure.md")
    process = _read_kb("admission", "process.md")
    text = f"{brochure}\n{process}"
    if not text.strip():
        return {
            "found": False,
            "tool": "get_admission_deadline",
            "message": "Admission KB documents are not available.",
        }

    if key == "m.tech":
        # No M.Tech deadline in current KB docs
        return {
            "found": False,
            "tool": "get_admission_deadline",
            "program": "M.Tech",
            "message": "No M.Tech deadline found in admission KB. Check admission brochure/process docs.",
            "sources": ["admission/brochure.md", "admission/process.md"],
        }

    opens_m = re.search(r"Applications open:\s*\*?\*?([^*\n|]+)", brochure, re.I)
    if not opens_m:
        opens_m = re.search(r"Portal opens\s*\|\s*([^|\n]+)", process, re.I)
    last_m = re.search(
        r"Last date for B\.Tech admission applications:\s*\*?\*?([^*\n|]+)",
        brochure,
        re.I,
    )
    if not last_m:
        last_m = re.search(r"Application closes\s*\|\s*\*?\*?([^*\n|]+)", process, re.I)

    if not (opens_m and last_m):
        return {
            "found": False,
            "tool": "get_admission_deadline",
            "program": "B.Tech",
            "message": "Could not parse B.Tech open/close dates from admission KB.",
            "sources": ["admission/brochure.md", "admission/process.md"],
        }

    opens = _parse_iso_or_text(opens_m.group(1))
    last_date = _parse_iso_or_text(last_m.group(1))
    note_m = re.search(r"Late applications[^\n]+", brochure, re.I)
    note = note_m.group(0).strip() if note_m else ""
    return {
        "found": True,
        "tool": "get_admission_deadline",
        "program": "B.Tech",
        "last_date": last_date,
        "opens": opens,
        "note": note,
        "sources": ["admission/brochure.md", "admission/process.md"],
    }


def get_exam_schedule(exam_type: str | None = "mid-sem") -> dict[str, Any]:
    raw = (exam_type or "mid-sem").strip().lower()
    if "end" in raw or "final" in raw or "semester exam" in raw:
        key = "end-sem"
        section = "End-semester examinations"
        name = "End-semester examinations"
    else:
        key = "mid-sem"
        section = "Mid-semester examinations"
        name = "Mid-semester examinations"

    text = _read_kb("exams", "exam-schedule.md")
    if not text.strip():
        # Fall back to exam-rules narrative if schedule doc missing
        text = _read_kb("exams", "exam-rules.md")
        return {
            "found": bool(text.strip()),
            "tool": "get_exam_schedule",
            "exam_type": key,
            "name": name,
            "excerpt": text[:500] if text else "",
            "sources": ["exams/exam-rules.md"],
            "message": "Structured exam windows not in KB; returned exam-rules excerpt."
            if text
            else "Exam KB documents are not available.",
        }

    # Slice section
    parts = re.split(r"^##\s+", text, flags=re.M)
    body = ""
    for part in parts:
        if part.lower().startswith(section.lower()):
            body = part
            break
    if not body:
        body = text

    start_m = re.search(r"Window start\s*\|\s*([^|\n]+)", body, re.I)
    end_m = re.search(r"Window end\s*\|\s*([^|\n]+)", body, re.I)
    note_m = re.search(r"Note\s*\|\s*([^|\n]+)", body, re.I)
    if not (start_m and end_m):
        return {
            "found": False,
            "tool": "get_exam_schedule",
            "exam_type": key,
            "message": f"Could not parse {key} window from exams/exam-schedule.md.",
            "sources": ["exams/exam-schedule.md"],
        }

    return {
        "found": True,
        "tool": "get_exam_schedule",
        "exam_type": key,
        "name": name,
        "window_start": _parse_iso_or_text(start_m.group(1)),
        "window_end": _parse_iso_or_text(end_m.group(1)),
        "note": (note_m.group(1).strip() if note_m else ""),
        "sources": ["exams/exam-schedule.md"],
    }


def create_ticket(subject: str, details: str = "", category: str = "fees") -> dict[str, Any]:
    suffix = "".join(random.choices(string.digits, k=5))
    ticket_id = f"TKT-{suffix}"
    return {
        "tool": "create_ticket",
        "ticket_id": ticket_id,
        "subject": subject or "Fee clarification",
        "category": category or "fees",
        "details": details,
        "status": "open",
        "created_on": date.today().isoformat(),
        "message": f"Support ticket {ticket_id} created with Accounts Desk. Keep your challan number ready.",
    }


def lambda_response(body: dict[str, Any], status: int = 200) -> dict[str, Any]:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }


def handler_admission_deadline(event: dict[str, Any], _context: Any = None) -> dict[str, Any]:
    payload = _payload(event)
    result = get_admission_deadline(payload.get("program") or payload.get("Program"))
    return lambda_response(result)


def handler_exam_schedule(event: dict[str, Any], _context: Any = None) -> dict[str, Any]:
    payload = _payload(event)
    result = get_exam_schedule(payload.get("exam_type") or payload.get("examType"))
    return lambda_response(result)


def handler_create_ticket(event: dict[str, Any], _context: Any = None) -> dict[str, Any]:
    payload = _payload(event)
    result = create_ticket(
        subject=payload.get("subject") or "Fee clarification",
        details=payload.get("details") or "",
        category=payload.get("category") or "fees",
    )
    return lambda_response(result)


def _payload(event: dict[str, Any]) -> dict[str, Any]:
    if not event:
        return {}
    if "program" in event or "exam_type" in event or "subject" in event:
        return event
    body = event.get("body")
    if isinstance(body, str) and body:
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return {}
    if isinstance(body, dict):
        return body
    return event.get("arguments") or event.get("input") or {}
