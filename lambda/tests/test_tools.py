import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

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


class MockChatTests(unittest.TestCase):
    def test_attendance(self):
        out = invoke_mod.mock_chat("What is the minimum attendance for semester exams?", "s1")
        self.assertIn("75%", out["reply"])
        self.assertTrue(len(out["citations"]) >= 1)

    def test_deadline_tool(self):
        out = invoke_mod.mock_chat("Last date for B.Tech admission this year?", "s2")
        self.assertIn("get_admission_deadline", out["toolsUsed"])
        self.assertIn("2026-06-30", out["reply"])

    def test_ticket_tool(self):
        out = invoke_mod.mock_chat("Raise a support ticket for fee clarification", "s3")
        self.assertIn("create_ticket", out["toolsUsed"])
        self.assertIn("TKT-", out["reply"])

    def test_off_topic(self):
        out = invoke_mod.mock_chat("Write a poem about Mars", "s4")
        self.assertIn("only help", out["reply"].lower())
        self.assertEqual(out["toolsUsed"], [])


if __name__ == "__main__":
    unittest.main()
