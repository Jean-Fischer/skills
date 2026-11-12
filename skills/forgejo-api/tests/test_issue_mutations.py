"""Black-box tests for narrowly scoped issue, PR, comment, and label mutations."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse


HELPER = Path(__file__).resolve().parents[1] / "forgejo_helper.py"


class ForgejoFixture:
    def __init__(self) -> None:
        self.issue = {
            "number": 7,
            "title": "Original title",
            "body": "Original body",
            "state": "open",
            "labels": [
                {"id": 11, "name": "status:needs-decision"},
                {"id": 12, "name": "ready-for-agent"},
            ],
        }
        self.labels = [
            {"id": 11, "name": "status:needs-decision"},
            {"id": 12, "name": "ready-for-agent"},
        ]
        self.pull_request = {
            "number": 7,
            "title": "Original PR title",
            "body": "Original PR body",
            "state": "open",
            "head": {"ref": "feature"},
        }
        self.comments = {
            7: [{"id": 51, "body": "Original comment", "issue_url": "/issues/7"}]
        }
        self.label_creation_conflict = False
        self.requests: list[tuple[str, str, dict[str, object] | None]] = []
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

    def close(self) -> None:
        self.tempdir.cleanup()

    def run_helper(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            def _respond(self, status: int, value: object | None = None) -> None:
                body = b"" if value is None else json.dumps(value).encode()
                self.send_response(status)
                if body:
                    self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                if body:
                    self.wfile.write(body)

            def _record(self, method: str) -> dict[str, object] | None:
                if self.headers.get("Authorization") != "token test-token":
                    self._respond(401, {"message": "unexpected unauthorized body"})
                    return None
                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(length) if length else b""
                payload = json.loads(raw) if raw else None
                fixture.requests.append((method, self.path, payload))
                return payload

            def do_GET(self) -> None:
                self._record("GET")
                path = urlparse(self.path).path
                if path == "/api/v1/user":
                    self._respond(200, {"login": "test"})
                elif path == "/api/v1/repos/owner/repo/labels":
                    self._respond(200, fixture.labels)
                elif path == "/api/v1/repos/owner/repo/issues/7":
                    self._respond(200, fixture.issue)
                elif path == "/api/v1/repos/owner/repo/pulls/7":
                    if fixture.pull_request is None:
                        self._respond(404, {"message": "not found"})
                    else:
                        self._respond(200, fixture.pull_request)
                elif path == "/api/v1/repos/owner/repo/issues/7/comments":
                    self._respond(200, fixture.comments[7])
                else:
                    self._respond(404, {"message": "unexpected fixture GET"})

            def do_POST(self) -> None:
                payload = self._record("POST")
                if payload is None:
                    return
                path = urlparse(self.path).path
                if path == "/api/v1/repos/owner/repo/labels":
                    created = {"id": max(item["id"] for item in fixture.labels) + 1}
                    created.update(payload)
                    created.setdefault("description", "")
                    fixture.labels.append(created)
                    if fixture.label_creation_conflict:
                        fixture.label_creation_conflict = False
                        self._respond(409, {"message": "already created"})
                    else:
                        self._respond(201, created)
                else:
                    self._respond(404, {"message": "unexpected fixture POST"})

            def do_PATCH(self) -> None:
                payload = self._record("PATCH")
                if payload is None:
                    return
                path = urlparse(self.path).path
                if path == "/api/v1/repos/owner/repo/issues/7":
                    fixture.issue.update(payload)
                    self._respond(200, fixture.issue)
                elif path == "/api/v1/repos/owner/repo/pulls/7":
                    fixture.pull_request.update(payload)
                    self._respond(200, fixture.pull_request)
                elif path == "/api/v1/repos/owner/repo/issues/comments/51":
                    fixture.comments[7][0].update(payload)
                    self._respond(200, fixture.comments[7][0])
                else:
                    self._respond(404, {"message": "unexpected fixture PATCH"})

            def do_DELETE(self) -> None:
                self._record("DELETE")
                path = urlparse(self.path).path
                if path == "/api/v1/repos/owner/repo/issues/7/labels/11":
                    fixture.issue["labels"] = [
                        item for item in fixture.issue["labels"] if item["id"] != 11
                    ]
                    self._respond(204)
                else:
                    self._respond(404, {"message": "unexpected fixture DELETE"})

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
                [sys.executable, "-B", str(HELPER), *arguments],
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


class IssueMutationCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = ForgejoFixture()

    def tearDown(self) -> None:
        self.fixture.close()

    def test_updates_only_requested_issue_fields(self) -> None:
        result = self.fixture.run_helper(
            "update-issue", "7", "--title", "Reviewed title", "--body", "Reviewed body"
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        updated = json.loads(result.stdout)
        self.assertEqual(updated["title"], "Reviewed title")
        self.assertEqual(updated["body"], "Reviewed body")
        self.assertEqual(updated["state"], "open")
        patches = [
            request for request in self.fixture.requests if request[0] == "PATCH"
        ]
        self.assertEqual(
            patches,
            [
                (
                    "PATCH",
                    "/api/v1/repos/owner/repo/issues/7",
                    {"title": "Reviewed title", "body": "Reviewed body"},
                )
            ],
        )
        self.assertEqual(result.stderr, "")

    def test_updates_issue_body_from_file(self) -> None:
        body_file = Path(self.fixture.tempdir.name) / "updated-body.md"
        body_file.write_text("A full reviewed specification.\n", encoding="utf-8")

        result = self.fixture.run_helper(
            "update-issue", "7", "--body-file", str(body_file)
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        patches = [
            request for request in self.fixture.requests if request[0] == "PATCH"
        ]
        self.assertEqual(
            patches,
            [
                (
                    "PATCH",
                    "/api/v1/repos/owner/repo/issues/7",
                    {"body": "A full reviewed specification.\n"},
                )
            ],
        )

    def test_update_requires_a_field_and_nonblank_title(self) -> None:
        missing_field = self.fixture.run_helper("update-issue", "7")
        blank_title = self.fixture.run_helper("update-issue", "7", "--title", "  ")

        self.assertIn("arguments_error", missing_field.stderr)
        self.assertIn("arguments_error", blank_title.stderr)
        self.assertEqual(self.fixture.requests, [])

    def test_rejects_pull_request_as_issue_update_target(self) -> None:
        self.fixture.issue["pull_request"] = {}

        result = self.fixture.run_helper(
            "update-issue", "7", "--title", "Not a PR edit"
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("wrong_object_type", result.stderr)
        self.assertFalse(
            any(request[0] == "PATCH" for request in self.fixture.requests)
        )

    def test_explicit_empty_body_can_clear_issue_body(self) -> None:
        result = self.fixture.run_helper("update-issue", "7", "--body", "")

        self.assertEqual(result.returncode, 0, result.stderr)
        patches = [
            request for request in self.fixture.requests if request[0] == "PATCH"
        ]
        self.assertEqual(
            patches,
            [("PATCH", "/api/v1/repos/owner/repo/issues/7", {"body": ""})],
        )

    def test_edits_comment_only_after_finding_it_on_the_requested_issue(self) -> None:
        result = self.fixture.run_helper(
            "edit-issue-comment", "7", "51", "--body", "Reviewed comment"
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        updated = json.loads(result.stdout)
        self.assertEqual(updated["id"], 51)
        self.assertEqual(updated["body"], "Reviewed comment")
        patches = [
            request for request in self.fixture.requests if request[0] == "PATCH"
        ]
        self.assertEqual(
            patches,
            [
                (
                    "PATCH",
                    "/api/v1/repos/owner/repo/issues/comments/51",
                    {"body": "Reviewed comment"},
                )
            ],
        )
        self.assertIn(
            (
                "GET",
                "/api/v1/repos/owner/repo/issues/7/comments?limit=100&page=1",
                None,
            ),
            self.fixture.requests,
        )

    def test_comment_not_on_issue_is_not_edited(self) -> None:
        self.fixture.comments[7] = []

        result = self.fixture.run_helper(
            "edit-issue-comment", "7", "51", "--body", "Wrong issue"
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("comment_not_found", result.stderr)
        self.assertFalse(
            any(request[0] == "PATCH" for request in self.fixture.requests)
        )

    def test_removes_only_the_named_issue_label(self) -> None:
        result = self.fixture.run_helper(
            "remove-issue-label", "7", "--label", "status:needs-decision"
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        value = json.loads(result.stdout)
        self.assertTrue(value["changed"])
        self.assertEqual(value["label"], "status:needs-decision")
        self.assertEqual(
            [item["name"] for item in value["labels"]], ["ready-for-agent"]
        )
        deletions = [
            request for request in self.fixture.requests if request[0] == "DELETE"
        ]
        self.assertEqual(
            deletions,
            [("DELETE", "/api/v1/repos/owner/repo/issues/7/labels/11", None)],
        )

    def test_removing_absent_label_is_a_noop(self) -> None:
        self.fixture.issue["labels"] = [{"id": 12, "name": "ready-for-agent"}]

        result = self.fixture.run_helper(
            "remove-issue-label", "7", "--label", "status:needs-decision"
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        value = json.loads(result.stdout)
        self.assertFalse(value["changed"])
        self.assertEqual(value["labels"], self.fixture.issue["labels"])
        self.assertFalse(
            any(request[0] == "DELETE" for request in self.fixture.requests)
        )

    def test_ambiguous_label_fails_before_issue_read_or_mutation(self) -> None:
        self.fixture.labels.append({"id": 13, "name": "status:needs-decision"})

        result = self.fixture.run_helper(
            "remove-issue-label", "7", "--label", "status:needs-decision"
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ambiguous_label", result.stderr)
        self.assertFalse(
            any(
                request[0] in {"GET", "DELETE"} and "/issues/7" in request[1]
                for request in self.fixture.requests
            )
        )

    def test_updates_only_requested_pull_request_fields(self) -> None:
        result = self.fixture.run_helper(
            "update-pr", "7", "--title", "Reviewed PR title"
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        updated = json.loads(result.stdout)
        self.assertEqual(updated["title"], "Reviewed PR title")
        self.assertEqual(updated["body"], "Original PR body")
        self.assertEqual(updated["state"], "open")
        patches = [
            request for request in self.fixture.requests if request[0] == "PATCH"
        ]
        self.assertEqual(
            patches,
            [
                (
                    "PATCH",
                    "/api/v1/repos/owner/repo/pulls/7",
                    {"title": "Reviewed PR title"},
                )
            ],
        )

    def test_creates_repository_label_with_normalized_color(self) -> None:
        result = self.fixture.run_helper(
            "create-label",
            "--name",
            "wayfinder:prototype",
            "--color",
            "#C5DEF5",
            "--description",
            "Prototype validation work",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        value = json.loads(result.stdout)
        self.assertTrue(value["created"])
        self.assertEqual(value["label"]["name"], "wayfinder:prototype")
        self.assertEqual(value["label"]["color"], "c5def5")
        posts = [request for request in self.fixture.requests if request[0] == "POST"]
        self.assertEqual(
            posts,
            [
                (
                    "POST",
                    "/api/v1/repos/owner/repo/labels",
                    {
                        "name": "wayfinder:prototype",
                        "color": "c5def5",
                        "description": "Prototype validation work",
                    },
                )
            ],
        )

    def test_existing_matching_repository_label_is_a_noop(self) -> None:
        self.fixture.labels.append(
            {
                "id": 13,
                "name": "wayfinder:prototype",
                "color": "c5def5",
                "description": "Prototype validation work",
            }
        )

        result = self.fixture.run_helper(
            "create-label",
            "--name",
            "wayfinder:prototype",
            "--color",
            "#C5DEF5",
            "--description",
            "Prototype validation work",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(json.loads(result.stdout)["created"])
        self.assertFalse(any(request[0] == "POST" for request in self.fixture.requests))

    def test_concurrent_matching_label_creation_returns_a_noop(self) -> None:
        self.fixture.label_creation_conflict = True

        result = self.fixture.run_helper(
            "create-label",
            "--name",
            "wayfinder:prototype",
            "--color",
            "c5def5",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(json.loads(result.stdout)["created"])
        self.assertEqual(
            [request[0] for request in self.fixture.requests].count("POST"), 1
        )

    def test_existing_repository_label_with_different_properties_is_not_updated(
        self,
    ) -> None:
        self.fixture.labels.append(
            {
                "id": 13,
                "name": "wayfinder:prototype",
                "color": "c5def5",
                "description": "Prototype validation work",
            }
        )

        result = self.fixture.run_helper(
            "create-label",
            "--name",
            "wayfinder:prototype",
            "--color",
            "000000",
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stderr)["error"], "label_exists")
        self.assertFalse(any(request[0] == "POST" for request in self.fixture.requests))

    def test_invalid_label_color_fails_before_api_access(self) -> None:
        result = self.fixture.run_helper(
            "create-label", "--name", "wayfinder:prototype", "--color", "blue"
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stderr)["error"], "arguments_error")
        self.assertEqual(self.fixture.requests, [])

    def test_update_pr_rejects_an_issue_number_without_mutation(self) -> None:
        self.fixture.pull_request = None

        result = self.fixture.run_helper("update-pr", "7", "--title", "Wrong target")

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stderr)["error"], "wrong_object_type")
        self.assertFalse(
            any(request[0] == "PATCH" for request in self.fixture.requests)
        )

    def test_unknown_label_fails_before_add_issue_label_mutation(self) -> None:
        result = self.fixture.run_helper("add-issue-label", "7", "--label", "missing")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("label_not_found", result.stderr)
        self.assertFalse(
            any(
                request[0] in {"POST", "PATCH", "DELETE"}
                for request in self.fixture.requests
            )
        )

    def test_unknown_label_fails_without_issue_mutation(self) -> None:
        result = self.fixture.run_helper(
            "remove-issue-label", "7", "--label", "missing"
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("label_not_found", result.stderr)
        self.assertFalse(
            any(request[0] in {"PATCH", "DELETE"} for request in self.fixture.requests)
        )


if __name__ == "__main__":
    unittest.main()
