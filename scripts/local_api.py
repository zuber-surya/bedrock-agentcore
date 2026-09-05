"""Local mock API for UI development: POST http://127.0.0.1:8080/chat"""
from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lambda" / "tools"))
sys.path.insert(0, str(ROOT / "lambda" / "invoke"))

os.environ.setdefault("MOCK_MODE", "true")

from handler import handler  # noqa: E402


class ChatHandler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "POST,OPTIONS")

    def do_OPTIONS(self):  # noqa: N802
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_POST(self):  # noqa: N802
        path = urlparse(self.path).path
        if path not in ("/chat", "/"):
            self.send_response(404)
            self.end_headers()
            return
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length).decode("utf-8")
        result = handler(
            {
                "httpMethod": "POST",
                "body": body,
                "requestContext": {"http": {"method": "POST"}},
            },
            None,
        )
        self.send_response(result["statusCode"])
        for k, v in (result.get("headers") or {}).items():
            self.send_header(k, v)
        self._cors()
        self.end_headers()
        self.wfile.write((result.get("body") or "").encode("utf-8"))

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))


def main():
    port = int(os.environ.get("PORT", "8080"))
    server = HTTPServer(("127.0.0.1", port), ChatHandler)
    print(f"CampusAssist mock API on http://127.0.0.1:{port}/chat")
    server.serve_forever()


if __name__ == "__main__":
    main()
