"""Seed DynamoDB Students table with demo S1-00x rows (idempotent PutItem)."""
from __future__ import annotations

import argparse
import os
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lambda" / "tools"))

from students import seed_students  # noqa: E402


def _dynamo_safe(val: Any) -> Any:
    if isinstance(val, float):
        return Decimal(str(val))
    if isinstance(val, list):
        return [_dynamo_safe(x) for x in val]
    if isinstance(val, dict):
        return {k: _dynamo_safe(v) for k, v in val.items()}
    return val


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed campusassist students table")
    parser.add_argument(
        "--table",
        default=os.environ.get("STUDENTS_TABLE", "campusassist-students"),
        help="DynamoDB table name",
    )
    parser.add_argument("--region", default=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))
    args = parser.parse_args()

    import boto3

    table = boto3.resource("dynamodb", region_name=args.region).Table(args.table)
    rows = seed_students()
    for row in rows:
        table.put_item(Item=_dynamo_safe(row))
        print(f"put {row['studentId']}")
    print(f"seeded {len(rows)} students into {args.table}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
