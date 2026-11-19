"""CLI contract tests for Forgejo workflow dispatch and PR Actions waiting."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import sys
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse


HELPER_PATH = Path(__file__).resolve().parents[1] / "forgejo_helper.py"
SPEC = importlib.util.spec_from_file_location("forgejo_helper", HELPER_PATH)
assert SPEC is not None and SPEC.loader is not None
helper = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = helper
SPEC.loader.exec_module(helper)


class FakeResponse:
    def __init__(self, body: bytes, status: int = 200) -> None:
        self.body = body
        self.status = status
        self.headers = {"Content-Type": "application/json"}

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.body


class FakeForgejo:
    def __init__(self) -> None:
        self.requests: list[tuple[str, str, dict[str, Any] | None]] = []
        self.request_timeouts: list[tuple[str, float]] = []
        self.dispatch_response: Any = None
        self.dispatch_status = 204
        self.handler: Any = None

    def __call__(self, request: Any, timeout: float) -> FakeResponse:
        method = request.get_method()
        parsed = urlparse(request.full_url)
        self.request_timeouts.append((parsed.path, timeout))
        raw = request.data
        payload = json.loads(raw) if raw else None
        self.requests.append((method, request.full_url, payload))
        if method == "GET" and parsed.path == "/api/v1/user":
            return self.respond({"login": "test"})
        if self.handler is not None:
            status, value = self.handler(method, parsed, payload)
        elif method == "POST" and parsed.path.endswith(
            "/actions/workflows/ci.yml/dispatches"
        ):
            status, value = self.dispatch_status, self.dispatch_response
        else:
            status, value = 404, {"message": "unexpected request"}
        if status >= 400:
            raise HTTPError(
                request.full_url,
                status,
                "fixture error",
                None,
                io.BytesIO(json.dumps(value).encode()),
            )
        return self.respond(value, status=status)

    @staticmethod
    def respond(value: Any, status: int = 200) -> FakeResponse:
        body = b"" if value is None else json.dumps(value).encode()
        return FakeResponse(body, status)


class WorkflowDispatchCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.api = FakeForgejo()

    def run_helper(self, *arguments: str) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            patch.dict(
                os.environ,
                {
                    "GITEA_SERVER_URL": "https://forgejo.invalid",
                    "GITEA_SERVER_TOKEN": "test-token",
                },
            ),
            patch.object(
                helper,
                "repository_from_origin",
                return_value=helper.Repository("owner", "repo"),
            ),
            patch.object(helper, "urlopen", self.api),
            patch.object(sys, "argv", [str(HELPER_PATH), *arguments]),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            status = helper.main()
        return status, stdout.getvalue(), stderr.getvalue()

    def test_dispatch_sends_requested_ref_and_parsed_inputs(self) -> None:
        self.api.dispatch_response = None
        self.api.dispatch_status = 204

        status, stdout, stderr = self.run_helper(
            "workflow-dispatch",
            "ci.yml",
            "--ref",
            "feature/test",
            "--input",
            "target=staging",
            "--input",
            "message=hello=world",
        )

        self.assertEqual(status, 0, stderr)
        self.assertEqual(json.loads(stdout), {"accepted": True})
        self.assertEqual(stderr, "")
        dispatch = self.api.requests[-1]
        self.assertEqual(dispatch[0], "POST")
        self.assertTrue(dispatch[1].endswith("/actions/workflows/ci.yml/dispatches"))
        self.assertEqual(
            dispatch[2],
            {
                "ref": "feature/test",
                "inputs": {"target": "staging", "message": "hello=world"},
            },
        )

    def test_dispatch_preserves_direct_run_response_without_looking_up_a_run(
        self,
    ) -> None:
        self.api.dispatch_response = {"id": 42, "status": "queued"}
        self.api.dispatch_status = 201

        status, stdout, stderr = self.run_helper(
            "workflow-dispatch", "ci.yml", "--ref", "main"
        )

        self.assertEqual(status, 0, stderr)
        self.assertEqual(
            json.loads(stdout),
            {"accepted": True, "response": {"id": 42, "status": "queued"}},
        )
        self.assertEqual(len(self.api.requests), 2)

    def test_dispatch_rejects_duplicate_or_malformed_inputs_before_api_access(
        self,
    ) -> None:
        for arguments in (
            ("workflow-dispatch", "ci.yml", "--ref", "main", "--input", "=empty"),
            (
                "workflow-dispatch",
                "ci.yml",
                "--ref",
                "main",
                "--input",
                "mode=one",
                "--input",
                "mode=two",
            ),
        ):
            with self.subTest(arguments=arguments):
                self.api.requests.clear()
                status, _stdout, stderr = self.run_helper(*arguments)
                self.assertNotEqual(status, 0)
                self.assertIn("arguments_error", stderr)
                self.assertEqual(self.api.requests, [])


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, duration: float) -> None:
        self.now += duration


class PullRequestActionsCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.api = FakeForgejo()
        self.clock = FakeClock()
        self.pr: dict[str, Any] = {
            "number": 7,
            "base": {"ref": "main"},
            "head": {"ref": "feature", "sha": "head-sha"},
            "merged": False,
        }
        self.existing_pr = True
        self.runs: list[dict[str, Any]] = []
        self.jobs: dict[int, list[dict[str, Any]]] = {}
        self.run_poll_count = 0
        self.merge_response_status = 200
        self.fail_run_page = False
        self.fail_run_poll: int | None = None
        self.merged = False
        self.api.handler = self.handle_api

    def handle_api(
        self, method: str, parsed: Any, payload: dict[str, Any] | None
    ) -> tuple[int, Any]:
        path = parsed.path.removeprefix("/api/v1/repos/owner/repo")
        query = parse_qs(parsed.query)
        if method == "GET" and path == "/pulls":
            return 200, [self.pr] if self.existing_pr else []
        if method == "POST" and path == "/pulls":
            self.existing_pr = True
            self.pr = {
                **(payload or {}),
                "number": 7,
                "base": {"ref": "main"},
                "head": {"ref": "feature", "sha": "head-sha"},
                "merged": False,
            }
            return 201, self.pr
        if method == "GET" and path == "/actions/runs":
            page = int(query.get("page", ["1"])[0])
            if page == 1:
                self.run_poll_count += 1
                self.add_delayed_run_if_due()
                if self.run_poll_count == self.fail_run_poll:
                    return 500, {"message": "fixture failure"}
            if page == 2 and self.fail_run_page:
                return 500, {"message": "fixture failure"}
            start = (page - 1) * helper.ACTIONS_PAGE_SIZE
            end = start + helper.ACTIONS_PAGE_SIZE
            return 200, {
                "total_count": len(self.runs),
                "workflow_runs": self.runs[start:end],
            }
        if (
            method == "GET"
            and path.startswith("/actions/runs/")
            and path.endswith("/jobs")
        ):
            run_id = int(path.split("/")[-2])
            page = int(query.get("page", ["1"])[0])
            start = (page - 1) * helper.ACTIONS_PAGE_SIZE
            end = start + helper.ACTIONS_PAGE_SIZE
            items = self.jobs.get(run_id, [])
            return 200, {"total_count": len(items), "jobs": items[start:end]}
        if method == "POST" and path == "/pulls/7/merge":
            if self.merge_response_status >= 400:
                return self.merge_response_status, {"message": "merge refused"}
            self.merged = True
            return 204, None
        if method == "GET" and path == "/pulls/7":
            return 200, {**self.pr, "merged": self.merged}
        return 404, {"message": "unexpected fixture request"}

    def add_delayed_run_if_due(self) -> None:
        return None

    def run_helper(self, *arguments: str) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            patch.dict(
                os.environ,
                {
                    "GITEA_SERVER_URL": "https://forgejo.invalid",
                    "GITEA_SERVER_TOKEN": "test-token",
                },
            ),
            patch.object(
                helper,
                "repository_from_origin",
                return_value=helper.Repository("owner", "repo"),
            ),
            patch.object(helper, "urlopen", self.api),
            patch.object(helper.time, "monotonic", self.clock.monotonic),
            patch.object(helper.time, "sleep", self.clock.sleep),
            patch.object(sys, "argv", [str(HELPER_PATH), *arguments]),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            status = helper.main()
        return status, stdout.getvalue(), stderr.getvalue()

    def create_pr(self, *extra: str) -> tuple[int, str, str]:
        return self.run_helper(
            "create-pr",
            "--base",
            "main",
            "--head",
            "feature",
            "--title",
            "A PR",
            *extra,
        )

    def install_run(self, run_id: int = 1, conclusion: str = "success") -> None:
        self.runs = [
            {
                "id": run_id,
                "name": f"workflow-{run_id}",
                "head_sha": "head-sha",
                "status": "completed",
                "conclusion": conclusion,
            }
        ]
        self.jobs = {
            run_id: [
                {
                    "id": run_id * 10,
                    "name": f"job-{run_id}",
                    "status": "completed",
                    "conclusion": conclusion,
                }
            ]
        }

    def wait_patches(self, quiet: float = 1, interval: float = 1) -> Any:
        return patch.multiple(
            helper,
            ACTIONS_QUIET_PERIOD_SECONDS=quiet,
            ACTIONS_POLL_INTERVAL_SECONDS=interval,
        )

    def test_wait_reports_paged_and_delayed_runs_with_jobs(self) -> None:
        self.runs = [
            {
                "id": run_id,
                "name": f"workflow-{run_id}",
                "head_sha": "head-sha",
                "status": "in_progress" if run_id == 1 else "completed",
                "conclusion": None if run_id == 1 else "success",
            }
            for run_id in (1, 2, 3)
        ]
        self.jobs = {
            run_id: [
                {
                    "id": run_id * 10,
                    "name": f"job-{run_id}",
                    "status": "in_progress" if run_id == 1 else "completed",
                    "conclusion": None if run_id == 1 else "success",
                }
            ]
            for run_id in (1, 2, 3)
        }
        self.jobs[2].extend(
            {
                "id": job_id,
                "name": f"job-{job_id}",
                "status": "completed",
                "conclusion": "success",
            }
            for job_id in (21, 22)
        )

        def add_delayed_run() -> None:
            if self.run_poll_count >= 2:
                self.runs[0]["status"] = "completed"
                self.runs[0]["conclusion"] = "success"
                self.jobs[1][0]["status"] = "completed"
                self.jobs[1][0]["conclusion"] = "success"
            if self.run_poll_count >= 3 and not any(
                run["id"] == 4 for run in self.runs
            ):
                self.runs.append(
                    {
                        "id": 4,
                        "name": "workflow-4",
                        "head_sha": "head-sha",
                        "status": "completed",
                        "conclusion": "success",
                    }
                )
                self.jobs[4] = [
                    {
                        "id": 40,
                        "name": "job-4",
                        "status": "completed",
                        "conclusion": "success",
                    }
                ]

        self.add_delayed_run_if_due = add_delayed_run
        with (
            patch.object(helper, "ACTIONS_PAGE_SIZE", 2),
            self.wait_patches(quiet=2, interval=1),
        ):
            status, stdout, stderr = self.create_pr("--wait-for-actions")

        self.assertEqual(status, 0, stderr)
        actions = json.loads(stdout)["actions"]
        self.assertEqual(actions["aggregate_state"], "success")
        self.assertTrue(actions["discovery_complete"])
        self.assertEqual(
            [entry["run"]["id"] for entry in actions["runs"]], [1, 2, 3, 4]
        )
        self.assertTrue(all(entry["jobs"] for entry in actions["runs"]))
        self.assertEqual(len(actions["runs"][1]["jobs"]), 3)
        run_queries = [
            urlparse(request[1])
            for request in self.api.requests
            if urlparse(request[1]).path.endswith("/actions/runs")
        ]
        self.assertTrue(
            any(parse_qs(query.query).get("page") == ["2"] for query in run_queries)
        )
        self.assertTrue(
            all(
                parse_qs(query.query).get("head_sha") == ["head-sha"]
                for query in run_queries
            )
        )
        job_queries = [
            urlparse(request[1])
            for request in self.api.requests
            if urlparse(request[1]).path.endswith("/jobs")
        ]
        self.assertTrue(
            any(parse_qs(query.query).get("page") == ["2"] for query in job_queries)
        )

    def test_job_pagination_continues_past_one_hundred_pages(self) -> None:
        self.install_run()
        self.jobs[1] = [
            {
                "id": job_id,
                "name": f"job-{job_id}",
                "status": "completed",
                "conclusion": "success",
            }
            for job_id in range(1, 102)
        ]
        with (
            patch.object(helper, "ACTIONS_PAGE_SIZE", 1),
            self.wait_patches(quiet=1, interval=1),
        ):
            status, stdout, stderr = self.create_pr("--wait-for-actions")

        self.assertEqual(status, 0, stderr)
        actions = json.loads(stdout)["actions"]
        self.assertEqual(actions["aggregate_state"], "success")
        self.assertTrue(actions["runs"][0]["jobs_complete"])
        self.assertEqual(len(actions["runs"][0]["jobs"]), 101)
        job_pages = [
            parse_qs(urlparse(request[1]).query).get("page")
            for request in self.api.requests
            if urlparse(request[1]).path.endswith("/jobs")
        ]
        self.assertIn(["101"], job_pages)

    def test_pagination_error_returns_discovered_partial_runs(self) -> None:
        self.install_run(1)
        self.runs.append(
            {
                "id": 2,
                "status": "completed",
                "conclusion": "success",
                "head_sha": "head-sha",
            }
        )
        self.fail_run_page = True
        with patch.object(helper, "ACTIONS_PAGE_SIZE", 1):
            status, stdout, _stderr = self.create_pr("--wait-for-actions")

        self.assertNotEqual(status, 0)
        actions = json.loads(stdout)["actions"]
        self.assertEqual(actions["aggregate_state"], "unknown")
        self.assertEqual(actions["error"], "http_error")
        self.assertEqual([item["run"]["id"] for item in actions["runs"]], [1])

    def test_late_run_list_error_cannot_complete_or_auto_merge(self) -> None:
        self.install_run()
        self.fail_run_poll = 2
        with self.wait_patches(quiet=2, interval=1):
            status, stdout, _stderr = self.create_pr(
                "--wait-for-actions", "--auto-merge"
            )

        self.assertNotEqual(status, 0)
        result = json.loads(stdout)
        self.assertEqual(result["actions"]["aggregate_state"], "unknown")
        self.assertEqual(result["actions"]["error"], "http_error")
        self.assertFalse(result["actions"]["discovery_complete"])
        self.assertEqual(result["actions"]["runs"][0]["aggregate_state"], "success")
        self.assertEqual(result["auto_merge"]["state"], "not_attempted")
        self.assertFalse(
            any(request[1].endswith("/pulls/7/merge") for request in self.api.requests)
        )

    def test_run_without_head_sha_is_unknown_and_never_merges(self) -> None:
        self.install_run()
        del self.runs[0]["head_sha"]
        with self.wait_patches(quiet=1, interval=1):
            status, stdout, _stderr = self.create_pr(
                "--wait-for-actions", "--auto-merge"
            )

        self.assertNotEqual(status, 0)
        actions = json.loads(stdout)["actions"]
        self.assertEqual(actions["aggregate_state"], "unknown")
        self.assertEqual(actions["error"], "response_error")
        self.assertEqual(actions["unidentified_runs"][0]["id"], 1)
        self.assertEqual(json.loads(stdout)["auto_merge"]["state"], "not_attempted")
        self.assertFalse(
            any(request[1].endswith("/pulls/7/merge") for request in self.api.requests)
        )

    def test_no_runs_returns_unknown_after_discovery_period(self) -> None:
        with self.wait_patches(quiet=2, interval=1):
            status, stdout, stderr = self.create_pr("--wait-for-actions")

        self.assertNotEqual(status, 0)
        actions = json.loads(stdout)["actions"]
        self.assertEqual(actions["aggregate_state"], "unknown")
        self.assertEqual(actions["reason"], "no_runs")
        self.assertFalse(actions["runs"])

    def test_incomplete_job_data_cannot_report_success(self) -> None:
        self.runs = [
            {
                "id": 1,
                "head_sha": "head-sha",
                "status": "completed",
                "conclusion": "success",
            }
        ]
        self.jobs = {1: []}
        with self.wait_patches(quiet=1, interval=1):
            status, stdout, stderr = self.create_pr("--wait-for-actions")

        self.assertNotEqual(status, 0)
        self.assertEqual(json.loads(stdout)["actions"]["aggregate_state"], "unknown")

    def test_failure_and_cancellation_have_distinct_aggregate_states(self) -> None:
        for conclusion, expected in (
            ("failure", "failure"),
            ("cancelled", "cancelled"),
        ):
            with self.subTest(conclusion=conclusion):
                self.clock = FakeClock()
                self.install_run(conclusion=conclusion)
                extra = (
                    ("--wait-for-actions", "--auto-merge")
                    if conclusion == "failure"
                    else ("--wait-for-actions",)
                )
                with self.wait_patches(quiet=1, interval=1):
                    status, stdout, stderr = self.create_pr(*extra)
                self.assertNotEqual(status, 0)
                result = json.loads(stdout)
                self.assertEqual(result["actions"]["aggregate_state"], expected)
                if conclusion == "failure":
                    self.assertEqual(result["auto_merge"]["state"], "not_attempted")
                    self.assertFalse(
                        any(
                            request[1].endswith("/pulls/7/merge")
                            for request in self.api.requests
                        )
                    )

    def test_timeout_preserves_partial_results_and_never_merges(self) -> None:
        self.runs = [
            {
                "id": 1,
                "head_sha": "head-sha",
                "status": "in_progress",
                "conclusion": None,
            }
        ]
        self.jobs = {1: [{"id": 10, "status": "in_progress", "conclusion": None}]}
        with patch.object(helper, "ACTIONS_POLL_INTERVAL_SECONDS", 1):
            status, stdout, stderr = self.create_pr(
                "--wait-for-actions", "--auto-merge", "--timeout", "2"
            )

        self.assertNotEqual(status, 0)
        result = json.loads(stdout)
        self.assertEqual(result["actions"]["aggregate_state"], "timeout")
        self.assertEqual(result["actions"]["runs"][0]["run"]["id"], 1)
        self.assertEqual(result["actions"]["runs"][0]["jobs"][0]["state"], "pending")
        self.assertLessEqual(self.clock.now, 2.0)
        action_timeouts = [
            timeout
            for path, timeout in self.api.request_timeouts
            if "/actions/" in path
        ]
        self.assertTrue(action_timeouts)
        self.assertTrue(all(timeout <= 2.0 for timeout in action_timeouts))
        self.assertEqual(result["auto_merge"]["state"], "not_attempted")
        self.assertFalse(
            any(request[2] and "Do" in request[2] for request in self.api.requests)
        )

    def test_wait_does_not_merge_without_explicit_auto_merge(self) -> None:
        self.install_run()
        with self.wait_patches(quiet=1, interval=1):
            status, stdout, stderr = self.create_pr("--wait-for-actions")
        self.assertEqual(status, 0, stderr)
        self.assertEqual(json.loads(stdout)["actions"]["aggregate_state"], "success")
        self.assertFalse(
            any(request[1].endswith("/pulls/7/merge") for request in self.api.requests)
        )

    def test_auto_merge_uses_normal_merge_endpoint_after_actions_succeed(self) -> None:
        self.install_run()
        with self.wait_patches(quiet=1, interval=1):
            status, stdout, stderr = self.create_pr(
                "--wait-for-actions", "--auto-merge"
            )
        self.assertEqual(status, 0, stderr)
        result = json.loads(stdout)
        self.assertEqual(result["actions"]["aggregate_state"], "success")
        self.assertEqual(result["auto_merge"]["state"], "merged")
        self.assertFalse(
            any("/commits/" in request[1] for request in self.api.requests)
        )
        merge_requests = [
            request
            for request in self.api.requests
            if request[0] == "POST" and request[1].endswith("/pulls/7/merge")
        ]
        self.assertEqual(
            merge_requests[0][2], {"Do": "merge", "delete_branch_after_merge": True}
        )

    def test_auto_merge_refusal_is_reported_without_merging(self) -> None:
        self.install_run()
        self.merge_response_status = 405
        with self.wait_patches(quiet=1, interval=1):
            status, stdout, _stderr = self.create_pr(
                "--wait-for-actions", "--auto-merge"
            )
        self.assertNotEqual(status, 0)
        self.assertEqual(json.loads(stdout)["auto_merge"]["state"], "refused")
        self.assertEqual(json.loads(stdout)["auto_merge"]["status"], 405)
        self.assertFalse(self.merged)

    def test_wait_applies_to_newly_created_pull_request(self) -> None:
        self.existing_pr = False
        self.install_run()
        with self.wait_patches(quiet=1, interval=1):
            status, stdout, stderr = self.create_pr("--wait-for-actions")
        self.assertEqual(status, 0, stderr)
        self.assertEqual(json.loads(stdout)["actions"]["aggregate_state"], "success")
        self.assertTrue(
            any(
                request[0] == "POST" and request[1].endswith("/pulls")
                for request in self.api.requests
            )
        )

    def test_timeout_and_auto_merge_flags_require_wait(self) -> None:
        for extra in (("--auto-merge",), ("--timeout", "10")):
            with self.subTest(extra=extra):
                self.api.requests.clear()
                status, _stdout, stderr = self.create_pr(*extra)
                self.assertNotEqual(status, 0)
                self.assertIn("arguments_error", stderr)
                self.assertEqual(self.api.requests, [])

    def test_non_finite_or_non_positive_timeout_fails_before_api_access(self) -> None:
        for timeout in ("0", "-1", "nan", "inf"):
            with self.subTest(timeout=timeout):
                self.api.requests.clear()
                status, _stdout, stderr = self.create_pr(
                    "--wait-for-actions", "--timeout", timeout
                )
                self.assertNotEqual(status, 0)
                self.assertIn("arguments_error", stderr)
                self.assertEqual(self.api.requests, [])

    def test_create_pr_without_new_flags_keeps_existing_output(self) -> None:
        status, stdout, stderr = self.create_pr()
        self.assertEqual(status, 0, stderr)
        self.assertEqual(json.loads(stdout), self.pr)
        self.assertFalse(
            any("/actions/runs" in request[1] for request in self.api.requests)
        )


if __name__ == "__main__":
    unittest.main()
