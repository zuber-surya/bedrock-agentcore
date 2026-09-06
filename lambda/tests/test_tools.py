import importlib.util
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "invoke"))

from handlers import (  # noqa: E402
    create_ticket,
    get_admission_deadline,
    get_exam_schedule,
    handler_admission_deadline,
    handler_create_ticket,
    handler_exam_schedule,
)

INVOKE = ROOT / "invoke" / "handler.py"
spec = importlib.util.spec_from_file_location("invoke_handler", INVOKE)
invoke_mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(invoke_mod)

from campus_logic import gather_context, run_campus_assist  # noqa: E402


class ToolTests(unittest.TestCase):
    def test_admission_deadline_btech(self):
        result = get_admission_deadline("B.Tech")
        self.assertTrue(result["found"])
        self.assertEqual(result["last_date"], "2026-06-30")

    def test_exam_schedule_midsem(self):
        result = get_exam_schedule("mid-sem")
        self.assertEqual(result["exam_type"], "mid-sem")
        self.assertIn("2026-09", result["window_start"])

    def test_create_ticket(self):
        result = create_ticket("Fee clarification", "Wrong challan")
        self.assertTrue(result["ticket_id"].startswith("TKT-"))
        self.assertEqual(result["status"], "open")

    def test_lambda_wrappers(self):
        r1 = handler_admission_deadline({"program": "B.Tech"})
        self.assertEqual(r1["statusCode"], 200)
        r2 = handler_exam_schedule({"body": '{"exam_type":"end-sem"}'})
        self.assertEqual(r2["statusCode"], 200)
        r3 = handler_create_ticket({"subject": "Fees"})
        self.assertEqual(r3["statusCode"], 200)


class CampusAssistTests(unittest.TestCase):
    def test_gather_attendance_kb_snippets(self):
        ctx = gather_context("What is the minimum attendance for semester exams?")
        self.assertFalse(ctx["offTopic"])
        self.assertTrue(len(ctx["citations"]) >= 1)
        self.assertTrue(any("75%" in c["snippet"] or "attendance" in c["snippet"].lower() for c in ctx["citations"]))
        self.assertEqual(ctx.get("toolResults"), [])

    def test_gather_deadline_tool(self):
        ctx = gather_context("Last date for B.Tech admission this year?")
        self.assertIn("get_admission_deadline", ctx["toolsUsed"])
        self.assertEqual(ctx["toolResults"][0]["result"]["last_date"], "2026-06-30")

    def test_gather_application_closes_question(self):
        ctx = gather_context("when application closes?")
        self.assertIn("get_admission_deadline", ctx["toolsUsed"])
        self.assertEqual(ctx["toolResults"][0]["result"]["last_date"], "2026-06-30")
        self.assertTrue(
            any(
                "30 June" in c["snippet"] or "closes" in c["snippet"].lower() or "Last date" in c["snippet"]
                for c in ctx["citations"]
            ),
            msg=f"citations={ctx['citations']}",
        )

    def test_gather_tuition_typo_question(self):
        ctx = gather_context("what is the tution fees for B.Tech")
        self.assertTrue(any(c["title"].startswith("fees/") for c in ctx["citations"]), msg=ctx["citations"])
        self.assertTrue(
            any("75,000" in c["snippet"] or "Tuition" in c["snippet"] for c in ctx["citations"]),
            msg=f"citations={ctx['citations']}",
        )

    def test_gather_ticket_tool(self):
        ctx = gather_context("Raise a support ticket for fee clarification")
        self.assertIn("create_ticket", ctx["toolsUsed"])
        self.assertTrue(ctx["toolResults"][0]["result"]["ticket_id"].startswith("TKT-"))

    def test_off_topic(self):
        out = run_campus_assist("Write a poem about Mars", "s4")
        self.assertEqual(out["mode"], "off-topic")
        self.assertIn("only help", out["reply"].lower())
        self.assertEqual(out["toolsUsed"], [])

    def test_requires_bedrock_config(self):
        with mock.patch.dict(os.environ, {"USE_BEDROCK": "false"}, clear=False):
            out = run_campus_assist("What is the minimum attendance for semester exams?", "s1")
        self.assertEqual(out["mode"], "error")
        self.assertIn("Bedrock is required", out["reply"])

    def test_handler_routes_to_campus_logic(self):
        with mock.patch.dict(
            os.environ,
            {"AGENT_RUNTIME_ARN": "", "USE_BEDROCK": "false"},
            clear=False,
        ):
            result = invoke_mod.handler(
                {
                    "httpMethod": "POST",
                    "body": json_body("attendance rules for semester exams"),
                },
                None,
            )
        self.assertEqual(result["statusCode"], 200)
        body = __import__("json").loads(result["body"])
        self.assertEqual(body["mode"], "error")


def json_body(message: str) -> str:
    return __import__("json").dumps({"message": message, "sessionId": "t1"})


if __name__ == "__main__":
    unittest.main()
