"""Fake student records + DynamoDB / in-memory lookup for CampusAssist agents."""
from __future__ import annotations

import os
import re
from decimal import Decimal
from typing import Any

# Demo IDs: S1-001 … S1-006
STUDENT_ID_RE = re.compile(r"\b(S1-\d{3})\b", re.I)
STUDENT_ID_TAG_RE = re.compile(r"\[studentId\s*=\s*(S1-\d{3})\]", re.I)

# In-memory seed (used when STUDENTS_TABLE unset — local/CI)
_SEED: dict[str, dict[str, Any]] = {
    "S1-001": {
        "studentId": "S1-001",
        "name": "Asha Rao",
        "program": "B.Tech CSE",
        "year": 4,
        "cgpa": 7.2,
        "activeBacklogs": 0,
        "standingArrears": 0,
        "attendancePct": 82,
        "semesterResults": [
            {"sem": 5, "sgpa": 7.4, "status": "pass"},
            {"sem": 6, "sgpa": 7.1, "status": "pass"},
            {"sem": 7, "sgpa": 7.0, "status": "pass"},
        ],
        "registeredForPlacement": True,
    },
    "S1-002": {
        "studentId": "S1-002",
        "name": "Rahul Mehta",
        "program": "B.Tech ECE",
        "year": 4,
        "cgpa": 5.9,
        "activeBacklogs": 0,
        "standingArrears": 1,
        "attendancePct": 80,
        "semesterResults": [
            {"sem": 5, "sgpa": 6.0, "status": "pass"},
            {"sem": 6, "sgpa": 5.8, "status": "pass"},
            {"sem": 7, "sgpa": 5.9, "status": "pass"},
        ],
        "registeredForPlacement": True,
    },
    "S1-003": {
        "studentId": "S1-003",
        "name": "Priya Nair",
        "program": "B.Tech CSE",
        "year": 4,
        "cgpa": 7.8,
        "activeBacklogs": 1,
        "standingArrears": 1,
        "attendancePct": 88,
        "semesterResults": [
            {"sem": 5, "sgpa": 7.9, "status": "pass"},
            {"sem": 6, "sgpa": 7.6, "status": "pass"},
            {"sem": 7, "sgpa": 7.5, "status": "arrear"},
        ],
        "registeredForPlacement": True,
    },
    "S1-004": {
        "studentId": "S1-004",
        "name": "Vikram Shah",
        "program": "B.Tech ME",
        "year": 4,
        "cgpa": 6.8,
        "activeBacklogs": 0,
        "standingArrears": 0,
        "attendancePct": 68,
        "semesterResults": [
            {"sem": 5, "sgpa": 6.9, "status": "pass"},
            {"sem": 6, "sgpa": 6.7, "status": "pass"},
            {"sem": 7, "sgpa": 6.8, "status": "pass"},
        ],
        "registeredForPlacement": True,
    },
    "S1-005": {
        "studentId": "S1-005",
        "name": "Neha Kapoor",
        "program": "B.Tech CSE",
        "year": 4,
        "cgpa": 7.0,
        "activeBacklogs": 0,
        "standingArrears": 3,
        "attendancePct": 79,
        "semesterResults": [
            {"sem": 5, "sgpa": 6.5, "status": "pass"},
            {"sem": 6, "sgpa": 6.8, "status": "pass"},
            {"sem": 7, "sgpa": 7.0, "status": "pass"},
        ],
        "registeredForPlacement": True,
    },
    "S1-006": {
        "studentId": "S1-006",
        "name": "Arjun Desai",
        "program": "B.Tech IT",
        "year": 3,
        "cgpa": 8.1,
        "activeBacklogs": 0,
        "standingArrears": 0,
        "attendancePct": 90,
        "semesterResults": [
            {"sem": 4, "sgpa": 8.0, "status": "pass"},
            {"sem": 5, "sgpa": 8.2, "status": "pass"},
        ],
        "registeredForPlacement": False,
    },
}


def seed_students() -> list[dict[str, Any]]:
    """Return seed rows (for scripts / tests)."""
    return [dict(v) for v in _SEED.values()]


def normalize_student_id(raw: str | None) -> str:
    return (raw or "").strip().upper()


def extract_student_id(message: str) -> str | None:
    """Pull S1-xxx from message text or [studentId=S1-xxx] tag."""
    if not message:
        return None
    m = STUDENT_ID_TAG_RE.search(message)
    if m:
        return normalize_student_id(m.group(1))
    m = STUDENT_ID_RE.search(message)
    if m:
        return normalize_student_id(m.group(1))
    return None


def _to_plain(val: Any) -> Any:
    if isinstance(val, Decimal):
        if val % 1 == 0:
            return int(val)
        return float(val)
    if isinstance(val, list):
        return [_to_plain(x) for x in val]
    if isinstance(val, dict):
        return {k: _to_plain(v) for k, v in val.items()}
    return val


def evaluate_placement_eligibility(student: dict[str, Any]) -> dict[str, Any]:
    """Deterministic T&P rules matching docs/kb/placement/overview.md."""
    cgpa = float(student.get("cgpa") or 0)
    active = int(student.get("activeBacklogs") or 0)
    arrears = int(student.get("standingArrears") or 0)
    attendance = float(student.get("attendancePct") or 0)
    registered = bool(student.get("registeredForPlacement"))

    checks = [
        {
            "rule": "cgpa_min_6_5",
            "pass": cgpa >= 6.5,
            "detail": f"CGPA {cgpa} (need >= 6.5)",
        },
        {
            "rule": "no_active_backlogs",
            "pass": active == 0,
            "detail": f"activeBacklogs={active} (need 0)",
        },
        {
            "rule": "standing_arrears_max_2",
            "pass": arrears <= 2,
            "detail": f"standingArrears={arrears} (need <= 2 for core/product)",
        },
        {
            "rule": "attendance_min_75",
            "pass": attendance >= 75,
            "detail": f"attendancePct={attendance} (need >= 75)",
        },
        {
            "rule": "registered_for_placement",
            "pass": registered,
            "detail": f"registeredForPlacement={registered}",
        },
    ]
    eligible = all(c["pass"] for c in checks)
    reasons = [c["detail"] for c in checks if not c["pass"]]
    if eligible:
        reasons = ["All placement eligibility checks passed."]
    return {"eligible": eligible, "checks": checks, "reasons": reasons}


def check_student_record(student_id: str | None) -> dict[str, Any]:
    """Load student by ID from DynamoDB or in-memory seed. Tool name for UI badges."""
    sid = normalize_student_id(student_id)
    if not sid:
        return {"found": False, "studentId": "", "tool": "check_student_record"}

    table_name = (os.environ.get("STUDENTS_TABLE") or "").strip()
    student: dict[str, Any] | None = None

    if table_name:
        try:
            import boto3

            table = boto3.resource("dynamodb").Table(table_name)
            resp = table.get_item(Key={"studentId": sid})
            item = resp.get("Item")
            if item:
                student = _to_plain(item)
        except Exception as exc:  # noqa: BLE001
            return {
                "found": False,
                "studentId": sid,
                "tool": "check_student_record",
                "error": str(exc),
            }
    else:
        raw = _SEED.get(sid)
        if raw:
            student = dict(raw)

    if not student:
        return {"found": False, "studentId": sid, "tool": "check_student_record"}

    eligibility = evaluate_placement_eligibility(student)
    return {
        "found": True,
        "studentId": sid,
        "tool": "check_student_record",
        "student": student,
        "placementEligibility": eligibility,
    }


def wants_student_record(message: str) -> bool:
    """True when the question needs a per-student lookup (not general policy)."""
    lower = (message or "").lower()
    personal = (
        "am i eligible",
        "am i ",
        "my attendance",
        "my result",
        "my results",
        "my cgpa",
        "my marks",
        "my id",
        "student id",
        "check my",
        "student record",
        "for me",
        "my backlog",
        "my arrear",
    )
    if any(k in lower for k in personal):
        return True
    if extract_student_id(message) and any(
        k in lower
        for k in ("attendance", "result", "cgpa", "placement", "eligible", "record", "marks")
    ):
        return True
    return False
