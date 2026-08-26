#!/usr/bin/env python3
"""Black-box tests for the constrained Forgejo helper CLI."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
HELPER = SKILL_ROOT / "forgejo_helper.py"


class ForgejoFixture:
    def __init__(self) -> None:
        self.requests: list[tuple[str, str, dict | None]] = []
        self.authorizations: list[str | None] = []
        self.existing_pr: dict | None = None
        self.created_pr: dict | None = None
        self.conflict_on_create = False
        self.empty_create_response = False
        self.error_body: object = {"message": "not found"}
        self.commit_status: dict = {"state": "success", "statuses": []}
        self.actions_runs: dict = {
            "total_count": 1,
            "workflow_runs": [{"id": 41, "status": "success"}],
        }
        self.actions_jobs: dict[int, object] = {41: [{"id": 42, "status": "failure"}]}
        self.actions_available = True
        self.existing_issues: dict[int, dict] = {}
        self.created_issue: dict | None = None
        self.created_comment: dict | None = None
        self.closed_issue: dict | None = None
        self.issues_available = True
        self.comment_on_missing = False
        self.paged_issues: int | None = None
        self.pr: dict = {"number": 5, "head": {"sha": "deadbeef"}}
        self.merge_error_status: int | None = None
        self.merged_pr: dict | None = None
        self.label_modal: list[dict] = []
        self.issue_comments: list[dict] = []
        self.pr_files: list[dict] = []
        self.pr_reviews: list[dict] = []
        self.labels_available = True
        self.run_state: dict | None = None
        self.rerun_status: int | None = None
        self.log_body: bytes = b""
        self.log_status: int | None = None
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: object) -> None:
                pass

            def _json(self, status: int, body: object) -> None:
                encoded = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def _request_body(self) -> dict | None:
                size = int(self.headers.get("Content-Length", 0))
                return json.loads(self.rfile.read(size)) if size else None

            def do_GET(self) -> None:
                fixture.requests.append(("GET", self.path, None))
                fixture.authorizations.append(self.headers.get("Authorization"))
                if self.path == "/api/v1/user":
                    self._json(200, {"login": "fixture-user"})
                elif self.path == "/api/v1/repos/forgeadmin/homelab/issues/7":
                    self._json(
                        200,
                        fixture.existing_issues.get(
                            7,
                            {
                                "number": 7,
                                "title": "fixture issue",
                                "state": "open",
                                "labels": [],
                            },
                        ),
                    )
                elif (
                    self.path
                    == "/api/v1/repos/forgeadmin/homelab/issues/7/comments?limit=100&page=1"
                ):
                    self._json(200, fixture.issue_comments)
                elif (
                    self.path
                    == "/api/v1/repos/forgeadmin/homelab/pulls/5/files?limit=100&page=1"
                ):
                    self._json(200, fixture.pr_files)
                elif (
                    self.path
                    == "/api/v1/repos/forgeadmin/homelab/pulls/5/reviews?limit=100&page=1"
                ):
                    self._json(200, fixture.pr_reviews)
                elif self.path == "/api/v1/repos/forgeadmin/homelab/pulls/5":
                    self._json(
                        200,
                        fixture.merged_pr
                        if fixture.merged_pr is not None
                        else fixture.pr,
                    )
                elif (
                    self.path.startswith("/api/v1/repos/forgeadmin/homelab/pulls/")
                    and self.path.endswith("/merge") is False
                ):
                    pr_number = int(self.path.split("/")[-1])
                    if pr_number == 7:
                        self._json(404, {"message": "not found"})
                        return
                    if pr_number == 5 and fixture.merged_pr is not None:
                        self._json(200, fixture.merged_pr)
                    else:
                        self._json(
                            200, fixture.pr if pr_number == 5 else {"number": pr_number}
                        )
                elif (
                    self.path == "/api/v1/repos/forgeadmin/homelab/labels"
                    or self.path.startswith("/api/v1/repos/forgeadmin/homelab/labels?")
                ):
                    if not fixture.labels_available:
                        self._json(404, {"message": "unavailable"})
                        return
                    self._json(200, fixture.label_modal)
                elif (
                    self.path
                    == "/api/v1/repos/forgeadmin/homelab/actions/runs?head_sha=deadbeef&limit=100&page=1"
                ):
                    self._json(
                        200 if fixture.actions_available else 404,
                        fixture.actions_runs
                        if fixture.actions_available
                        else {"message": "unavailable"},
                    )
                elif (
                    self.path.startswith(
                        "/api/v1/repos/forgeadmin/homelab/actions/runs/"
                    )
                    and self.path.endswith("/rerun") is False
                    and "/jobs" not in self.path
                ):
                    run_id = int(self.path.split("/")[-1])
                    if fixture.run_state is None:
                        self._json(404, {"message": "not found"})
                        return
                    self._json(200, fixture.run_state)
                elif (
                    self.path == "/api/v1/repos/forgeadmin/homelab/actions/jobs/42/logs"
                ):
                    if fixture.log_status is not None:
                        self.send_response(fixture.log_status)
                        self.end_headers()
                        return
                    encoded = fixture.log_body
                    self.send_response(200)
                    self.send_header("Content-Type", "application/zip")
                    self.send_header("Content-Length", str(len(encoded)))
                    self.end_headers()
                    self.wfile.write(encoded)
                elif (
                    self.path
                    == "/api/v1/repos/forgeadmin/homelab/commits/deadbeef/status"
                ):
                    self._json(200, fixture.commit_status)
                elif self.path.startswith(
                    "/api/v1/repos/forgeadmin/homelab/actions/runs/"
                ) and self.path.endswith("/jobs"):
                    run_id = int(self.path.split("/")[-2])
                    self._json(200, fixture.actions_jobs.get(run_id, []))
                elif (
                    self.path
                    == "/api/v1/repos/forgeadmin/homelab/pulls?state=all&limit=100&page=1"
                ):
                    self._json(
                        200,
                        [] if fixture.existing_pr is None else [fixture.existing_pr],
                    )
                elif self.path.startswith("/api/v1/repos/forgeadmin/homelab/issues?"):
                    if not fixture.issues_available:
                        self._json(404, {"message": "unavailable"})
                        return
                    params = dict(
                        chunk.split("=", 1)
                        for chunk in self.path.split("?", 1)[1].split("&")
                        if "=" in chunk
                    )
                    state = params.get("state", "open")
                    if fixture.paged_issues is not None:
                        page = int(params.get("page", "1"))
                        start = (page - 1) * 100
                        remaining = fixture.paged_issues - start
                        count = max(0, min(100, remaining))
                        self._json(
                            200,
                            [
                                {"number": i, "state": "open"}
                                for i in range(start + 1, start + count + 1)
                            ],
                        )
                        return
                    filtered = [
                        i
                        for i in fixture.existing_issues.values()
                        if state == "all" or i.get("state") == state
                    ]
                    self._json(200, filtered)
                else:
                    self._json(404, fixture.error_body)

            def do_POST(self) -> None:
                body = self._request_body()
                fixture.requests.append(("POST", self.path, body))
                fixture.authorizations.append(self.headers.get("Authorization"))
                if self.path == "/api/v1/repos/forgeadmin/homelab/pulls":
                    if fixture.empty_create_response:
                        self.send_response(204)
                        self.end_headers()
                        return
                    if fixture.conflict_on_create:
                        fixture.existing_pr = {
                            "number": 9,
                            "title": "Concurrent PR",
                            "base": {"ref": "main"},
                            "head": {"ref": "feature"},
                        }
                        self._json(409, {"message": "already exists"})
                        return
                    fixture.created_pr = {"number": 8, **(body or {})}
                    self._json(201, fixture.created_pr)
                elif self.path == "/api/v1/repos/forgeadmin/homelab/issues":
                    fixture.created_issue = {"number": 12, **(body or {})}
                    fixture.existing_issues[12] = fixture.created_issue
                    self._json(201, fixture.created_issue)
                elif self.path == "/api/v1/repos/forgeadmin/homelab/issues/7/labels":
                    current = fixture.existing_issues.setdefault(
                        7, {"number": 7, "labels": []}
                    )
                    current["labels"] = [
                        item
                        for item in fixture.label_modal
                        if isinstance(item, dict)
                        and item.get("id") in (body or {}).get("labels", [])
                    ]
                    self._json(200, current["labels"])
                elif self.path == "/api/v1/repos/forgeadmin/homelab/issues/7/comments":
                    if fixture.comment_on_missing:
                        self._json(404, {"message": "not found"})
                        return
                    fixture.created_comment = {"id": 99, **(body or {})}
                    self._json(201, fixture.created_comment)
                elif self.path == "/api/v1/repos/forgeadmin/homelab/pulls/5/merge":
                    if fixture.merge_error_status is not None:
                        self._json(
                            fixture.merge_error_status, {"message": "merge failed"}
                        )
                        return
                    fixture.merged_pr = {"number": 5, "merged": True, **(body or {})}
                    self._json(200, None)
                elif (
                    self.path
                    == "/api/v1/repos/forgeadmin/homelab/actions/runs/40/rerun"
                ):
                    if fixture.rerun_status is not None:
                        self._json(fixture.rerun_status, {"message": "rerun failed"})
                        return
                    self.send_response(204)
                    self.end_headers()
                else:
                    self._json(404, {"message": "not found"})

            def do_PATCH(self) -> None:
                body = self._request_body()
                fixture.requests.append(("PATCH", self.path, body))
                fixture.authorizations.append(self.headers.get("Authorization"))
                if self.path == "/api/v1/repos/forgeadmin/homelab/issues/7":
                    if not fixture.issues_available:
                        self._json(404, {"message": "not found"})
                        return
                    current = fixture.existing_issues.get(
                        7, {"number": 7, "title": "fixture issue", "state": "open"}
                    )
                    merged = {**current, **(body or {})}
                    fixture.existing_issues[7] = merged
                    fixture.closed_issue = merged
                    self._json(200, merged)
                else:
                    self._json(404, fixture.error_body)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_port}"

    @property
    def api_url(self) -> str:
        return f"{self.url}/api/v1"

    def __enter__(self) -> "ForgejoFixture":
        self.thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()


class ForgejoHelperTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp_dir.name) / "repo"
        self.repo.mkdir()
        self.git("init", "-q")
        self.git(
            "remote", "add", "origin", "git@forgejo.home.arpa:forgeadmin/homelab.git"
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def git(self, *args: str) -> None:
        subprocess.run(
            ["git", *args], cwd=self.repo, check=True, capture_output=True, text=True
        )

    def invoke(
        self,
        *args: str,
        fixture: ForgejoFixture | None = None,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        command_env = os.environ.copy()
        command_env.pop("GITEA_SERVER_URL", None)
        command_env.pop("GITEA_SERVER_TOKEN", None)
        if fixture:
            command_env.update(
                {"GITEA_SERVER_URL": fixture.url, "GITEA_SERVER_TOKEN": "test-token"}
            )
        if env:
            command_env.update(env)
        return subprocess.run(
            [sys.executable, str(HELPER), *args],
            cwd=self.repo,
            env=command_env,
            capture_output=True,
            text=True,
        )

    def assert_success_json(self, result: subprocess.CompletedProcess[str]) -> dict:
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def assert_sanitized_error(
        self, result: subprocess.CompletedProcess[str], code: str
    ) -> None:
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stderr)["error"], code)
        self.assertNotIn("test-token", result.stderr)

    def test_preflight_authenticates_and_resolves_origin_repository(self) -> None:
        with ForgejoFixture() as fixture:
            payload = self.assert_success_json(
                self.invoke("preflight", fixture=fixture)
            )
        self.assertEqual(fixture.requests, [("GET", "/api/v1/user", None)])
        self.assertEqual(payload["user"], {"login": "fixture-user"})
        self.assertEqual(
            payload["repository"], {"owner": "forgeadmin", "name": "homelab"}
        )
        self.assertEqual(payload["api_url"], fixture.api_url)
        self.assertEqual(fixture.authorizations, ["token test-token"])

    def test_read_commands_authenticate_before_requesting_the_target(self) -> None:
        with ForgejoFixture() as fixture:
            issue = self.assert_success_json(self.invoke("issue", "7", fixture=fixture))
            self.assertEqual(issue["number"], 7)
            self.assertEqual(
                fixture.requests,
                [
                    ("GET", "/api/v1/user", None),
                    ("GET", "/api/v1/repos/forgeadmin/homelab/issues/7", None),
                ],
            )
            fixture.requests.clear()
            fixture.authorizations.clear()
            pull_request = self.assert_success_json(
                self.invoke("pr", "5", fixture=fixture)
            )
        self.assertEqual(pull_request["number"], 5)
        self.assertEqual(
            fixture.requests,
            [
                ("GET", "/api/v1/user", None),
                ("GET", "/api/v1/repos/forgeadmin/homelab/pulls/5", None),
            ],
        )
        self.assertEqual(
            fixture.authorizations, ["token test-token", "token test-token"]
        )

    def test_pr_health_returns_raw_pull_request_and_commit_status(self) -> None:
        with ForgejoFixture() as fixture:
            payload = self.assert_success_json(
                self.invoke("pr-health", "5", fixture=fixture)
            )
        self.assertEqual(payload["pull_request"]["number"], 5)
        self.assertEqual(payload["commit_status"]["state"], "success")
        self.assertEqual(
            [path for _, path, _ in fixture.requests],
            [
                "/api/v1/user",
                "/api/v1/repos/forgeadmin/homelab/pulls/5",
                "/api/v1/repos/forgeadmin/homelab/commits/deadbeef/status",
                "/api/v1/repos/forgeadmin/homelab/actions/runs?head_sha=deadbeef&limit=100&page=1",
                "/api/v1/repos/forgeadmin/homelab/actions/runs/41/jobs",
            ],
        )

    def test_pr_health_preserves_raw_gate_data_and_uses_failure_precedence(
        self,
    ) -> None:
        with ForgejoFixture() as fixture:
            fixture.commit_status = {
                "state": "pending",
                "statuses": [{"state": "success", "context": "lint"}],
            }
            fixture.actions_runs = {
                "total_count": 1,
                "workflow_runs": [
                    {"id": 41, "status": "success", "run_marker": "preserve"}
                ],
            }
            fixture.actions_jobs = {
                41: [{"id": 42, "status": "failure", "job_marker": "preserve"}]
            }
            payload = self.assert_success_json(
                self.invoke("pr-health", "5", fixture=fixture)
            )
        self.assertEqual(payload["aggregate_state"], "failure")
        self.assertEqual(payload["commit_status"], fixture.commit_status)
        self.assertEqual(payload["actions_runs"], fixture.actions_runs)
        self.assertEqual(payload["actions_jobs"], {"41": fixture.actions_jobs[41]})
        self.assertEqual(
            [path for _, path, _ in fixture.requests],
            [
                "/api/v1/user",
                "/api/v1/repos/forgeadmin/homelab/pulls/5",
                "/api/v1/repos/forgeadmin/homelab/commits/deadbeef/status",
                "/api/v1/repos/forgeadmin/homelab/actions/runs?head_sha=deadbeef&limit=100&page=1",
                "/api/v1/repos/forgeadmin/homelab/actions/runs/41/jobs",
            ],
        )

    def test_pr_health_is_unknown_without_usable_gate_data(self) -> None:
        with ForgejoFixture() as fixture:
            fixture.commit_status = {"state": "not_a_gate_state", "statuses": []}
            fixture.actions_runs = {"total_count": 0, "workflow_runs": []}
            payload = self.assert_success_json(
                self.invoke("pr-health", "5", fixture=fixture)
            )
        self.assertEqual(payload["aggregate_state"], "unknown")
        self.assertEqual(payload["actions_runs"], fixture.actions_runs)
        self.assertEqual(payload["actions_jobs"], {})

    def test_pr_health_prioritizes_pending_over_success(self) -> None:
        with ForgejoFixture() as fixture:
            fixture.commit_status = {"state": "success", "statuses": []}
            fixture.actions_runs = {
                "total_count": 1,
                "workflow_runs": [{"id": 41, "status": "pending"}],
            }
            fixture.actions_jobs = {41: []}
            payload = self.assert_success_json(
                self.invoke("pr-health", "5", fixture=fixture)
            )
        self.assertEqual(payload["aggregate_state"], "pending")

    def test_pr_health_aggregates_jobs_from_object_response(self) -> None:
        with ForgejoFixture() as fixture:
            fixture.commit_status = {"state": "success", "statuses": []}
            fixture.actions_runs = {
                "total_count": 1,
                "workflow_runs": [{"id": 41, "status": "success"}],
            }
            fixture.actions_jobs = {
                41: {"total_count": 1, "jobs": [{"id": 42, "status": "failure"}]}
            }
            payload = self.assert_success_json(
                self.invoke("pr-health", "5", fixture=fixture)
            )
        self.assertEqual(payload["aggregate_state"], "failure")
        self.assertEqual(payload["actions_jobs"], {"41": fixture.actions_jobs[41]})

    def test_pr_health_omits_unavailable_actions_without_warning(self) -> None:
        with ForgejoFixture() as fixture:
            fixture.commit_status = {"state": "success", "statuses": []}
            fixture.actions_available = False
            result = self.invoke("pr-health", "5", fixture=fixture)
        payload = self.assert_success_json(result)
        self.assertEqual(payload["aggregate_state"], "success")
        self.assertNotIn("actions_runs", payload)
        self.assertNotIn("actions_jobs", payload)
        self.assertEqual(result.stderr, "")

    def test_create_pr_is_idempotent_and_reads_optional_body_file(self) -> None:
        body_file = self.repo / "body.md"
        body_file.write_text("A concise pull request body.\n", encoding="utf-8")
        with ForgejoFixture() as fixture:
            created = self.assert_success_json(
                self.invoke(
                    "create-pr",
                    "--base",
                    "main",
                    "--head",
                    "feature",
                    "--title",
                    "Add helper",
                    "--body-file",
                    str(body_file),
                    fixture=fixture,
                )
            )
            self.assertEqual(created["number"], 8)
            self.assertEqual(
                fixture.requests[-1],
                (
                    "POST",
                    "/api/v1/repos/forgeadmin/homelab/pulls",
                    {
                        "base": "main",
                        "head": "feature",
                        "title": "Add helper",
                        "body": "A concise pull request body.\n",
                    },
                ),
            )
            fixture.requests.clear()
            fixture.existing_pr = {
                "number": 3,
                "title": "Existing PR",
                "base": {"ref": "main"},
                "head": {"ref": "feature"},
            }
            existing = self.assert_success_json(
                self.invoke(
                    "create-pr",
                    "--base",
                    "main",
                    "--head",
                    "feature",
                    "--title",
                    "Ignored",
                    fixture=fixture,
                )
            )
        self.assertEqual(existing["number"], 3)
        self.assertEqual(
            fixture.requests,
            [
                ("GET", "/api/v1/user", None),
                (
                    "GET",
                    "/api/v1/repos/forgeadmin/homelab/pulls?state=all&limit=100&page=1",
                    None,
                ),
            ],
        )

    def test_configuration_and_http_failures_are_sanitized(self) -> None:
        self.assert_sanitized_error(self.invoke("preflight"), "configuration_error")
        self.git("remote", "set-url", "origin", "not a remote")
        with ForgejoFixture() as fixture:
            self.assert_sanitized_error(
                self.invoke("preflight", fixture=fixture), "origin_parse_error"
            )
        self.git("remote", "remove", "origin")
        with ForgejoFixture() as fixture:
            self.assert_sanitized_error(
                self.invoke("preflight", fixture=fixture), "origin_parse_error"
            )
        self.git(
            "remote",
            "add",
            "origin",
            "https://forgejo.example/owner?query/repository.git",
        )
        with ForgejoFixture() as fixture:
            self.assert_sanitized_error(
                self.invoke("preflight", fixture=fixture), "origin_parse_error"
            )
        self.git("remote", "remove", "origin")
        self.git(
            "remote", "add", "origin", "git@forgejo.home.arpa:forgeadmin/homelab.git"
        )
        with ForgejoFixture() as fixture:
            self.assert_sanitized_error(
                self.invoke("issue", "99", fixture=fixture), "http_error"
            )
            self.assert_sanitized_error(
                self.invoke(
                    "create-pr",
                    "--base",
                    "main",
                    "--head",
                    "feature",
                    "--title",
                    "Read file",
                    "--body-file",
                    "missing.md",
                    fixture=fixture,
                ),
                "file_error",
            )

    def test_public_cli_preserves_configuration_and_response_body_boundaries(
        self,
    ) -> None:
        for environment in (
            {"GITEA_SERVER_TOKEN": "test-token"},
            {"GITEA_SERVER_URL": "https://forgejo.example"},
        ):
            result = self.invoke("preflight", env=environment)
            self.assert_sanitized_error(result, "configuration_error")
            self.assertEqual(result.stdout, "")
            self.assertNotIn("test-token", result.stdout + result.stderr)

        self.git(
            "remote",
            "set-url",
            "origin",
            "git@independent-ssh-alias:forgeadmin/homelab.git",
        )
        with ForgejoFixture() as fixture:
            fixture.error_body = {"message": "response-body-secret"}
            result = self.invoke("issue", "99", fixture=fixture)
        self.assert_sanitized_error(result, "http_error")
        self.assertEqual(result.stdout, "")
        self.assertNotIn("response-body-secret", result.stdout + result.stderr)
        self.assertNotIn("test-token", result.stdout + result.stderr)

    def test_public_cli_handles_empty_success_and_has_no_jq_or_generic_request_surface(
        self,
    ) -> None:
        tool_dir = Path(self.temp_dir.name) / "bin"
        tool_dir.mkdir()
        (tool_dir / "git").symlink_to("/usr/bin/git")
        with ForgejoFixture() as fixture:
            fixture.empty_create_response = True
            result = self.invoke(
                "create-pr",
                "--base",
                "main",
                "--head",
                "feature",
                "--title",
                "Empty response",
                fixture=fixture,
                env={"PATH": str(tool_dir)},
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), None)
        self.assertEqual(
            fixture.requests[-1],
            (
                "POST",
                "/api/v1/repos/forgeadmin/homelab/pulls",
                {
                    "base": "main",
                    "head": "feature",
                    "title": "Empty response",
                },
            ),
        )
        for command in (("request", "/user"), ("preflight", "--token", "test-token")):
            result = self.invoke(*command)
            self.assert_sanitized_error(result, "arguments_error")
            self.assertEqual(result.stdout, "")
            self.assertNotIn("test-token", result.stdout + result.stderr)

    def test_create_pr_recovers_from_a_concurrent_create(self) -> None:
        with ForgejoFixture() as fixture:
            fixture.conflict_on_create = True
            result = self.assert_success_json(
                self.invoke(
                    "create-pr",
                    "--base",
                    "main",
                    "--head",
                    "feature",
                    "--title",
                    "Race",
                    fixture=fixture,
                )
            )
        self.assertEqual(result["number"], 9)
        self.assertEqual(
            [method for method, _, _ in fixture.requests], ["GET", "GET", "POST", "GET"]
        )

    def test_create_pr_encodes_valid_slash_refs_and_rejects_invalid_refs(self) -> None:
        with ForgejoFixture() as fixture:
            created = self.assert_success_json(
                self.invoke(
                    "create-pr",
                    "--base",
                    "main",
                    "--head",
                    "feature/topic",
                    "--title",
                    "Slash ref",
                    fixture=fixture,
                )
            )
            self.assertEqual(created["number"], 8)
            self.assertEqual(
                fixture.requests[1],
                (
                    "GET",
                    "/api/v1/repos/forgeadmin/homelab/pulls?state=all&limit=100&page=1",
                    None,
                ),
            )
            self.assert_sanitized_error(
                self.invoke(
                    "create-pr",
                    "--base",
                    "main",
                    "--head",
                    "feature?query",
                    "--title",
                    "Invalid ref",
                    fixture=fixture,
                ),
                "arguments_error",
            )

    def test_merge_pr_merges_with_fixed_strategy_deletes_branch_and_returns_merged_pr(
        self,
    ) -> None:
        with ForgejoFixture() as fixture:
            result = self.invoke("merge-pr", "5", fixture=fixture)
        payload = self.assert_success_json(result)
        self.assertEqual(payload["merged"], True)
        self.assertEqual(
            [r for r in fixture.requests if r[0] == "POST"],
            [
                (
                    "POST",
                    "/api/v1/repos/forgeadmin/homelab/pulls/5/merge",
                    {"Do": "merge", "delete_branch_after_merge": True},
                ),
            ],
        )
        self.assertEqual(
            [p for _, p, _ in fixture.requests],
            [
                "/api/v1/user",
                "/api/v1/repos/forgeadmin/homelab/pulls/5",
                "/api/v1/repos/forgeadmin/homelab/pulls/5/merge",
                "/api/v1/repos/forgeadmin/homelab/pulls/5",
            ],
        )

    def test_merge_pr_is_idempotent_when_already_merged(self) -> None:
        with ForgejoFixture() as fixture:
            fixture.merged_pr = {"number": 5, "merged": True}
            result = self.invoke("merge-pr", "5", fixture=fixture)
        payload = self.assert_success_json(result)
        self.assertEqual(payload["merged"], True)
        # No POST merge is issued; the already-merged PR is returned as-is.
        self.assertEqual([r for r in fixture.requests if r[0] == "POST"], [])
        self.assertEqual(
            fixture.authorizations, ["token test-token", "token test-token"]
        )

    def test_merge_pr_sanitizes_merge_failures(self) -> None:
        with ForgejoFixture() as fixture:
            fixture.merge_error_status = 405
            self.assert_sanitized_error(
                self.invoke("merge-pr", "5", fixture=fixture), "http_error"
            )
            fixture.merge_error_status = 409
            self.assert_sanitized_error(
                self.invoke("merge-pr", "5", fixture=fixture), "http_error"
            )
            fixture.merge_error_status = None
            self.assert_sanitized_error(
                self.invoke("merge-pr", "0", fixture=fixture), "arguments_error"
            )

    def test_rerun_run_reruns_a_finished_run_and_returns_its_status(self) -> None:
        with ForgejoFixture() as fixture:
            fixture.run_state = {"id": 40, "status": "success"}
            result = self.invoke("rerun-run", "40", fixture=fixture)
        payload = self.assert_success_json(result)
        self.assertEqual(payload["status"], "success")
        self.assertEqual(
            [r for r in fixture.requests if r[0] == "POST"],
            [
                (
                    "POST",
                    "/api/v1/repos/forgeadmin/homelab/actions/runs/40/rerun",
                    None,
                ),
            ],
        )
        self.assertEqual(
            [p for _, p, _ in fixture.requests],
            [
                "/api/v1/user",
                "/api/v1/repos/forgeadmin/homelab/actions/runs/40",
                "/api/v1/repos/forgeadmin/homelab/actions/runs/40/rerun",
                "/api/v1/repos/forgeadmin/homelab/actions/runs/40",
            ],
        )

    def test_rerun_run_guards_against_an_active_run(self) -> None:
        with ForgejoFixture() as fixture:
            fixture.run_state = {"id": 40, "status": "running"}
            self.assert_sanitized_error(
                self.invoke("rerun-run", "40", fixture=fixture), "not_rerunnable"
            )
            self.assertEqual([r for r in fixture.requests if r[0] == "POST"], [])

    def test_rerun_run_sanitizes_missing_run_and_bad_numbers(self) -> None:
        with ForgejoFixture() as fixture:
            self.assert_sanitized_error(
                self.invoke("rerun-run", "0", fixture=fixture), "arguments_error"
            )
            self.assert_sanitized_error(
                self.invoke("rerun-run", "999", fixture=fixture), "http_error"
            )

    def test_job_log_fetches_and_decompresses_the_job_log_to_raw_stdout(self) -> None:
        import io
        import zipfile

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr(
                "0_step.log", "lint: ok\nbuild: pass\nquality-gate: FAILED\n"
            )
        with ForgejoFixture() as fixture:
            fixture.log_body = buffer.getvalue()
            result = self.invoke("job-log", "40", "42", fixture=fixture)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "lint: ok\nbuild: pass\nquality-gate: FAILED\n")
        self.assertIn(
            ("GET", "/api/v1/repos/forgeadmin/homelab/actions/jobs/42/logs", None),
            fixture.requests,
        )
        self.assertEqual(result.stderr, "")

    def test_job_log_sanitizes_http_and_argument_failures(self) -> None:
        with ForgejoFixture() as fixture:
            fixture.log_status = 404
            self.assert_sanitized_error(
                self.invoke("job-log", "40", "42", fixture=fixture), "http_error"
            )
            self.assert_sanitized_error(
                self.invoke("job-log", "0", "42", fixture=fixture), "arguments_error"
            )
            self.assert_sanitized_error(
                self.invoke("job-log", "40", "0", fixture=fixture), "arguments_error"
            )

    def test_list_labels_returns_repo_labels_and_filters_by_exact_name(self) -> None:
        with ForgejoFixture() as fixture:
            fixture.label_modal = [
                {"id": 1, "name": "ready-for-agent"},
                {"id": 2, "name": "status:approved"},
            ]
            all_labels = self.assert_success_json(
                self.invoke("list-labels", fixture=fixture)
            )
            self.assertEqual(
                [(label["id"], label["name"]) for label in all_labels],
                [(1, "ready-for-agent"), (2, "status:approved")],
            )
            fixture.requests.clear()
            single = self.assert_success_json(
                self.invoke("list-labels", "--name", "status:approved", fixture=fixture)
            )
        self.assertEqual(
            [(label["id"], label["name"]) for label in single], [(2, "status:approved")]
        )
        self.assertEqual(
            [p for _, p, _ in fixture.requests],
            [
                "/api/v1/user",
                "/api/v1/repos/forgeadmin/homelab/labels?limit=100&page=1",
            ],
        )

    def test_create_issue_with_label_resolves_name_to_id_and_posts_it(self) -> None:
        with ForgejoFixture() as fixture:
            fixture.label_modal = [{"id": 2, "name": "status:approved"}]
            created = self.assert_success_json(
                self.invoke(
                    "create-issue",
                    "--title",
                    "Bug",
                    "--label",
                    "status:approved",
                    fixture=fixture,
                )
            )
        self.assertEqual(created["labels"], [2])
        self.assertEqual(
            fixture.requests[-1],
            (
                "POST",
                "/api/v1/repos/forgeadmin/homelab/issues",
                {
                    "title": "Bug",
                    "labels": [2],
                },
            ),
        )

    def test_create_issue_with_unknown_label_fails_without_posting(self) -> None:
        with ForgejoFixture() as fixture:
            fixture.label_modal = [{"id": 2, "name": "status:approved"}]
            self.assert_sanitized_error(
                self.invoke(
                    "create-issue",
                    "--title",
                    "Bug",
                    "--label",
                    "no-such-label",
                    fixture=fixture,
                ),
                "label_not_found",
            )
            self.assertEqual(
                len([r for r in fixture.requests if r[1].endswith("/issues")]), 0
            )
            self.assertEqual(len([r for r in fixture.requests if r[0] == "POST"]), 0)

    def test_https_origin_is_supported_without_using_it_as_an_api_url(self) -> None:
        self.git(
            "remote",
            "set-url",
            "origin",
            "https://forgejo.example/owner/repository.git",
        )
        with ForgejoFixture() as fixture:
            payload = self.assert_success_json(
                self.invoke("preflight", fixture=fixture)
            )
        self.assertEqual(
            payload["repository"], {"owner": "owner", "name": "repository"}
        )
        self.assertEqual(payload["api_url"], fixture.api_url)

    def test_git_check_is_local_diagnostic_and_origin_only(self) -> None:
        payload = self.assert_success_json(self.invoke("git-check"))
        self.assertEqual(
            payload["repository"], {"owner": "forgeadmin", "name": "homelab"}
        )
        self.assertEqual(payload["branch"], "master")
        self.assertEqual(payload["status"], ["## No commits yet on master"])

    def test_create_issue_posts_title_and_optional_body_and_returns_issue(self) -> None:
        body_file = self.repo / "issue_body.md"
        body_file.write_text("Detailed reproduction steps.\n", encoding="utf-8")
        with ForgejoFixture() as fixture:
            created = self.assert_success_json(
                self.invoke(
                    "create-issue",
                    "--title",
                    "Backup failed",
                    "--body-file",
                    str(body_file),
                    fixture=fixture,
                )
            )
        self.assertEqual(created["number"], 12)
        self.assertEqual(
            fixture.requests[-1],
            (
                "POST",
                "/api/v1/repos/forgeadmin/homelab/issues",
                {
                    "title": "Backup failed",
                    "body": "Detailed reproduction steps.\n",
                },
            ),
        )
        self.assertEqual(
            len([r for r in fixture.requests if r[1].endswith("/issues")]), 1
        )

    def test_create_issue_posts_again_without_dedup(self) -> None:
        with ForgejoFixture() as fixture:
            self.assert_success_json(
                self.invoke("create-issue", "--title", "Backup failed", fixture=fixture)
            )
            self.assert_success_json(
                self.invoke("create-issue", "--title", "Backup failed", fixture=fixture)
            )
        issues_posts = [r for r in fixture.requests if r[1].endswith("/issues")]
        self.assertEqual(len(issues_posts), 2)

    def test_close_issue_patches_state_closed_and_is_idempotent_on_already_closed(
        self,
    ) -> None:
        with ForgejoFixture() as fixture:
            fixture.issues_available = True
            closed = self.assert_success_json(
                self.invoke("close-issue", "7", fixture=fixture)
            )
            self.assertEqual(closed["state"], "closed")
            self.assertEqual(
                fixture.requests[-1],
                (
                    "PATCH",
                    "/api/v1/repos/forgeadmin/homelab/issues/7",
                    {"state": "closed"},
                ),
            )
            already = self.assert_success_json(
                self.invoke("close-issue", "7", fixture=fixture)
            )
        self.assertEqual(already["state"], "closed")
        self.assertEqual([m for m, _, _ in fixture.requests].count("PATCH"), 2)

    def test_comment_issue_requires_exactly_one_body_source(self) -> None:
        with ForgejoFixture() as fixture:
            comment = self.assert_success_json(
                self.invoke(
                    "comment-issue",
                    "7",
                    "--body",
                    "Status update: done.",
                    fixture=fixture,
                )
            )
            self.assertEqual(comment["id"], 99)
            self.assertEqual(
                fixture.requests[-1],
                (
                    "POST",
                    "/api/v1/repos/forgeadmin/homelab/issues/7/comments",
                    {
                        "body": "Status update: done.",
                    },
                ),
            )
            self.assert_sanitized_error(
                self.invoke(
                    "comment-issue",
                    "7",
                    "--body",
                    "x",
                    "--body-file",
                    str(self.repo / "nope.md"),
                    fixture=fixture,
                ),
                "arguments_error",
            )
            self.assert_sanitized_error(
                self.invoke("comment-issue", "7", fixture=fixture), "arguments_error"
            )

    def test_list_issues_defaults_to_open_and_accepts_state(self) -> None:
        with ForgejoFixture() as fixture:
            fixture.existing_issues = {
                1: {"number": 1, "title": "Open issue", "state": "open"},
                2: {"number": 2, "title": "Closed issue", "state": "closed"},
            }
            default = self.assert_success_json(
                self.invoke("list-issues", fixture=fixture)
            )
            self.assertEqual([i["number"] for i in default], [1])
            all_state = self.assert_success_json(
                self.invoke("list-issues", "--state", "all", fixture=fixture)
            )
            self.assertEqual([i["number"] for i in all_state], [1, 2])
        issue_queries = [
            path
            for _, path, _ in fixture.requests
            if path.startswith("/api/v1/repos/forgeadmin/homelab/issues?")
        ]
        self.assertEqual(
            issue_queries[0].split("?", 1)[1], "state=open&limit=100&page=1"
        )
        self.assertEqual(
            issue_queries[1].split("?", 1)[1], "state=all&limit=100&page=1"
        )

    def test_list_issues_pages_through_complete_result(self) -> None:
        with ForgejoFixture() as fixture:
            fixture.issues_available = True
            fixture.paged_issues = 120
            result = self.assert_success_json(
                self.invoke("list-issues", fixture=fixture)
            )
        self.assertEqual(len(result), 120)
        issue_queries = [
            path
            for _, path, _ in fixture.requests
            if path.startswith("/api/v1/repos/forgeadmin/homelab/issues?")
        ]
        self.assertEqual(len(issue_queries), 2)
        self.assertIn("page=1", issue_queries[0])
        self.assertIn("page=2", issue_queries[1])

    def test_task_reads_return_paged_items_and_pr_reads_verify_type(self) -> None:
        with ForgejoFixture() as fixture:
            fixture.issue_comments = [
                {"id": 1, "body": "hello", "private_extra": "omit"}
            ]
            fixture.pr_files = [
                {
                    "filename": "README.md",
                    "status": "modified",
                    "changes": 2,
                    "patch": "secret diff",
                }
            ]
            fixture.pr_reviews = [
                {
                    "id": 4,
                    "state": "APPROVED",
                    "user": {"login": "reviewer"},
                    "html_url": "omit",
                }
            ]
            comments = self.assert_success_json(
                self.invoke("issue-comments", "7", fixture=fixture)
            )
            files = self.assert_success_json(
                self.invoke("pr-files", "5", fixture=fixture)
            )
            reviews = self.assert_success_json(
                self.invoke("pr-reviews", "5", fixture=fixture)
            )
        self.assertEqual(comments["items"][0]["id"], 1)
        self.assertEqual(files["items"][0]["filename"], "README.md")
        self.assertNotIn("patch", files["items"][0])
        self.assertNotIn("private_extra", comments["items"][0])
        self.assertNotIn("html_url", reviews["items"][0])
        self.assertEqual(reviews["items"][0]["state"], "APPROVED")
        self.assertEqual(comments["pagination"]["pages_fetched"], 1)
        with ForgejoFixture() as fixture:
            self.assert_sanitized_error(
                self.invoke("pr-files", "7", fixture=fixture), "wrong_object_type"
            )
            target_requests = [
                path
                for method, path, _ in fixture.requests
                if method == "GET" and "/pulls/7/files" in path
            ]
            self.assertEqual(target_requests, [])

    def test_add_issue_label_is_exact_and_idempotent(self) -> None:
        with ForgejoFixture() as fixture:
            fixture.label_modal = [
                {"id": 3, "name": "ready-for-agent"},
                {"id": 4, "name": "other"},
            ]
            first = self.assert_success_json(
                self.invoke(
                    "add-issue-label",
                    "7",
                    "--label",
                    "ready-for-agent",
                    fixture=fixture,
                )
            )
            self.assertTrue(first["changed"])
            second = self.assert_success_json(
                self.invoke(
                    "add-issue-label",
                    "7",
                    "--label",
                    "ready-for-agent",
                    fixture=fixture,
                )
            )
            self.assertFalse(second["changed"])
            self.assert_sanitized_error(
                self.invoke(
                    "add-issue-label", "7", "--label", "missing", fixture=fixture
                ),
                "label_not_found",
            )
        posts = [
            request
            for request in fixture.requests
            if request[0] == "POST" and request[1].endswith("/labels")
        ]
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0][2], {"labels": [3]})

    def test_issue_mutation_commands_guard_invalid_numbers_and_titles(self) -> None:
        with ForgejoFixture() as fixture:
            self.assert_sanitized_error(
                self.invoke("close-issue", "0", fixture=fixture), "arguments_error"
            )
            self.assert_sanitized_error(
                self.invoke("comment-issue", "-1", "--body", "x", fixture=fixture),
                "arguments_error",
            )
            self.assert_sanitized_error(
                self.invoke("create-issue", "--title", "   ", fixture=fixture),
                "arguments_error",
            )

    def test_issue_mutation_commands_sanitize_missing_issue_http_error(self) -> None:
        with ForgejoFixture() as fixture:
            fixture.issues_available = False
            self.assert_sanitized_error(
                self.invoke("close-issue", "7", fixture=fixture), "http_error"
            )
            fixture.comment_on_missing = True
            self.assert_sanitized_error(
                self.invoke("comment-issue", "7", "--body", "x", fixture=fixture),
                "http_error",
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
