"""Black-box tests for Forgejo job-log response formats."""

from __future__ import annotations

import io
import os
import subprocess
import sys
import tempfile
import threading
import unittest
import zipfile
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path


HELPER = Path(__file__).resolve().parents[1] / "forgejo_helper.py"
LOG_TEXT = "compile started\ncompile failed: missing dependency\n"


def zip_log(text: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("job.log", text)
    return buffer.getvalue()


class JobLogCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.repo = Path(self.tempdir.name) / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "--quiet"], cwd=self.repo, check=True)
        subprocess.run(
            [
                "git",
                "remote",
                "add",
                "origin",
                "https://forgejo.invalid/owner/repo.git",
            ],
            cwd=self.repo,
            check=True,
        )

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def run_job_log(self, body: bytes, content_type: str) -> subprocess.CompletedProcess[str]:
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                if self.headers.get("Authorization") != "token test-token":
                    self.send_error(401)
                    return
                if self.path == "/api/v1/user":
                    response = b'{"login":"test"}'
                    response_type = "application/json"
                elif self.path == "/api/v1/repos/owner/repo/actions/jobs/2/logs":
                    response = body
                    response_type = content_type
                else:
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header("Content-Type", response_type)
                self.send_header("Content-Length", str(len(response)))
                self.end_headers()
                self.wfile.write(response)

            def log_message(self, _format: str, *_args: object) -> None:
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            env = os.environ.copy()
            env["GITEA_SERVER_URL"] = f"http://127.0.0.1:{server.server_port}"
            env["GITEA_SERVER_TOKEN"] = "test-token"
            return subprocess.run(
                [sys.executable, "-B", str(HELPER), "job-log", "1", "2"],
                cwd=self.repo,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=2)

    def test_plain_text_log_passes_through(self) -> None:
        result = self.run_job_log(LOG_TEXT.encode(), "text/plain; charset=utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, LOG_TEXT)
        self.assertEqual(result.stderr, "")

    def test_zip_log_is_decompressed(self) -> None:
        result = self.run_job_log(zip_log(LOG_TEXT), "application/zip")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, LOG_TEXT)
        self.assertEqual(result.stderr, "")

    def test_unrecognized_response_is_rejected_without_echoing_body(self) -> None:
        body = b'{"error":"unexpected response"}'
        result = self.run_job_log(body, "application/json")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("response_error", result.stderr)
        self.assertNotIn(body.decode(), result.stderr)


if __name__ == "__main__":
    unittest.main()
