"""CampusAssist tool handlers — used as Lambda functions and by local agent mocks."""
from __future__ import annotations

import json
import random
import string
from datetime import date
from typing import Any


ADMISSION_DEADLINES = {
    "b.tech": {
        "program": "B.Tech",
        "last_date": "2026-06-30",
        "opens": "2026-03-01",
        "note": "Applications close 30 June 2026. Late applications need Principal exception.",
    },
    "m.tech": {
        "program": "M.Tech",
        "last_date": "2026-07-15",
        "opens": "2026-04-01",
        "note": "M.Tech applications close 15 July 2026.",
    },
}

EXAM_SCHEDULE = {
    "mid-sem": {
        "name": "Mid-semester examinations",
        "window_start": "2026-09-15",
        "window_end": "2026-09-22",
        "note": "Exact timetable is published by CoE two weeks prior.",
    },
    "end-sem": {
        "name": "End-semester examinations",
        "window_start": "2026-11-20",
        "window_end": "2026-12-05",
        "note": "Hall tickets released one week before the first exam.",
    },
}


def _normalize_program(program: str | None) -> str:
    if not program:
        return "b.tech"
    key = program.strip().lower().replace(" ", "")
    if key in ("btech", "b.tech", "b.e", "be"):
        return "b.tech"
    if key in ("mtech", "m.tech"):
        return "m.tech"
    return key


def get_admission_deadline(program: str | None = "B.Tech") -> dict[str, Any]:
    key = _normalize_program(program)
    data = ADMISSION_DEADLINES.get(key)
    if not data:
        return {
            "found": False,
            "message": f"No deadline on file for program '{program}'. Try B.Tech or M.Tech.",
        }
    return {"found": True, "tool": "get_admission_deadline", **data}


def get_exam_schedule(exam_type: str | None = "mid-sem") -> dict[str, Any]:
    raw = (exam_type or "mid-sem").strip().lower()
    if "end" in raw or "final" in raw or "semester exam" in raw:
        key = "end-sem"
    else:
        key = "mid-sem"
    data = EXAM_SCHEDULE[key]
    return {"found": True, "tool": "get_exam_schedule", "exam_type": key, **data}


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
