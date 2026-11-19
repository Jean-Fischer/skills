#!/usr/bin/env python3
"""Constrained task-oriented Forgejo REST helper.

The CLI deliberately exposes only the workflows reviewed for this skill.
It never accepts credentials as arguments and never prints response/error bodies,
with the single documented exception that `job-log` streams a fetched job log as
raw text to stdout.
"""

from __future__ import annotations

import argparse
import io
import json
import math
import os
import re
import subprocess
import sys
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request, urlopen


ACTIONS_PAGE_SIZE = 100
ACTIONS_POLL_INTERVAL_SECONDS = 2.0
ACTIONS_QUIET_PERIOD_SECONDS = 10.0
DEFAULT_ACTIONS_TIMEOUT_SECONDS = 300.0


class HelperError(Exception):
    def __init__(self, code: str, message: str, *, status: int | None = None) -> None:
        self.code = code
        self.message = message
        self.status = status
        super().__init__(message)


class HelperArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise HelperError("arguments_error", "invalid command arguments")


@dataclass(frozen=True)
class Repository:
    owner: str
    name: str


@dataclass(frozen=True)
class Settings:
    api_url: str
    token: str


@dataclass
class ActionsRunRecord:
    run: dict[str, Any]
    jobs: dict[int, Any]
    unidentified_jobs: list[Any]
    jobs_complete: bool = False


@dataclass(frozen=True)
class ActionsCollectionResult:
    items: list[Any]
    complete: bool
    error: str | None = None
    timed_out: bool = False


def settings_from_environment() -> Settings:
    api_url = os.environ.get("GITEA_SERVER_URL")
    token = os.environ.get("GITEA_SERVER_TOKEN")
    if not api_url:
        raise HelperError("configuration_error", "GITEA_SERVER_URL is required")
    if not token:
        raise HelperError("configuration_error", "GITEA_SERVER_TOKEN is required")
    parsed = urlparse(api_url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.path not in {"", "/"}
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise HelperError(
            "configuration_error", "GITEA_SERVER_URL must be an HTTP server URL"
        )
    return Settings(api_url=f"{api_url.rstrip('/')}/api/v1", token=token)


def git_output(*args: str) -> str:
    try:
        return subprocess.check_output(
            ["git", *args], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError) as error:
        raise HelperError("git_error", "required Git diagnostic failed") from error


def repository_from_origin() -> Repository:
    try:
        origin = subprocess.check_output(
            ["git", "config", "--get", "remote.origin.url"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError) as error:
        raise HelperError(
            "origin_parse_error", "origin does not contain an owner/repository pair"
        ) from error
    patterns = (
        r"^[^@/:\s]+@[^:\s]+:([^/\s?#]+)/([^/\s?#]+?)(?:\.git)?$",
        r"^(?:ssh|https?)://[^/\s]+/([^/\s?#]+)/([^/\s?#]+?)(?:\.git)?$",
    )
    for pattern in patterns:
        match = re.fullmatch(pattern, origin)
        if match:
            return Repository(owner=match.group(1), name=match.group(2))
    raise HelperError(
        "origin_parse_error", "origin does not contain an owner/repository pair"
    )


class ForgejoClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        *,
        allow_not_found: bool = False,
        timeout: float = 20,
    ) -> Any | None:
        data = json.dumps(body).encode() if body is not None else None
        request = Request(
            f"{self.settings.api_url}{path}",
            data=data,
            method=method,
            headers={
                "Accept": "application/json",
                "Authorization": f"token {self.settings.token}",
                **({"Content-Type": "application/json"} if data is not None else {}),
            },
        )
        try:
            with urlopen(request, timeout=timeout) as response:
                response_body = response.read()
        except HTTPError as error:
            if allow_not_found and error.code == 404:
                return None
            raise HelperError(
                "http_error", "Forgejo request failed", status=error.code
            ) from error
        except (URLError, OSError) as error:
            raise HelperError(
                "network_error", "Forgejo request could not be completed"
            ) from error
        if not response_body:
            return None
        try:
            return json.loads(response_body)
        except json.JSONDecodeError as error:
            raise HelperError(
                "response_error", "Forgejo returned invalid JSON"
            ) from error

    def authenticate(self) -> dict[str, Any]:
        user = self.request("GET", "/user")
        if not isinstance(user, dict):
            raise HelperError("response_error", "Forgejo user response was invalid")
        return user

    def request_raw(self, method: str, path: str) -> tuple[bytes, str | None]:
        request = Request(
            f"{self.settings.api_url}{path}",
            method=method,
            headers={
                "Accept": "application/json",
                "Authorization": f"token {self.settings.token}",
            },
        )
        try:
            with urlopen(request, timeout=60) as response:
                return response.read(), response.headers.get("Content-Type")
        except HTTPError as error:
            raise HelperError(
                "http_error", "Forgejo request failed", status=error.code
            ) from error
        except (URLError, OSError) as error:
            raise HelperError(
                "network_error", "Forgejo request could not be completed"
            ) from error


def output(value: Any) -> None:
    print(json.dumps(value, sort_keys=True))


def api_context() -> tuple[ForgejoClient, Repository]:
    settings = settings_from_environment()
    repository = repository_from_origin()
    client = ForgejoClient(settings)
    client.authenticate()
    return client, repository


def command_preflight(_: argparse.Namespace) -> None:
    settings = settings_from_environment()
    repository = repository_from_origin()
    user = ForgejoClient(settings).authenticate()
    output(
        {"api_url": settings.api_url, "repository": repository.__dict__, "user": user}
    )


def repository_path(repository: Repository) -> str:
    return (
        f"/repos/{quote(repository.owner, safe='')}/{quote(repository.name, safe='')}"
    )


def command_issue(args: argparse.Namespace) -> None:
    client, repository = api_context()
    output(client.request("GET", f"{repository_path(repository)}/issues/{args.number}"))


def command_pr(args: argparse.Namespace) -> None:
    client, repository = api_context()
    output(client.request("GET", f"{repository_path(repository)}/pulls/{args.number}"))


def gate_state(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.lower()
    if normalized in {"failure", "error", "cancelled", "timed_out", "action_required"}:
        return "failure"
    if normalized in {"pending", "queued", "in_progress", "waiting", "requested"}:
        return "pending"
    if normalized in {"success", "neutral", "skipped"}:
        return "success"
    return None


def aggregate_gate_state(*values: Any) -> str:
    states = [state for value in values if (state := gate_state(value)) is not None]
    for candidate in ("failure", "pending", "success"):
        if candidate in states:
            return candidate
    return "unknown"


def status_values(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return [value for item in payload for value in status_values(item)]
    if not isinstance(payload, dict):
        return []
    values = [payload.get(name) for name in ("conclusion", "status", "state")]
    for collection_name in ("statuses", "check_runs", "workflow_runs", "jobs"):
        collection = payload.get(collection_name)
        if isinstance(collection, list):
            for item in collection:
                values.extend(status_values(item))
    return values


def action_health(
    client: ForgejoClient, repository: Repository, head_sha: str
) -> tuple[Any | None, dict[str, Any]]:
    try:
        runs = client.request(
            "GET",
            f"{repository_path(repository)}/actions/runs?{urlencode({'head_sha': head_sha, 'limit': 100, 'page': 1})}",
        )
    except HelperError:
        return None, {}
    if not isinstance(runs, dict) or not isinstance(runs.get("workflow_runs"), list):
        return runs, {}
    jobs_by_run: dict[str, Any] = {}
    for run in runs["workflow_runs"]:
        if not isinstance(run, dict) or not isinstance(run.get("id"), int):
            continue
        try:
            jobs_by_run[str(run["id"])] = client.request(
                "GET", f"{repository_path(repository)}/actions/runs/{run['id']}/jobs"
            )
        except HelperError:
            continue
    return runs, jobs_by_run


def command_pr_health(args: argparse.Namespace) -> None:
    client, repository = api_context()
    pull_request = client.request(
        "GET", f"{repository_path(repository)}/pulls/{args.number}"
    )
    if (
        not isinstance(pull_request, dict)
        or not isinstance(pull_request.get("head"), dict)
        or not pull_request["head"].get("sha")
    ):
        raise HelperError(
            "response_error", "Forgejo pull request response has no head commit"
        )
    statuses = client.request(
        "GET",
        f"{repository_path(repository)}/commits/{pull_request['head']['sha']}/status",
    )
    runs, jobs_by_run = action_health(client, repository, pull_request["head"]["sha"])
    health_values = status_values(statuses)
    health_values.extend(status_values(runs))
    health_values.extend(
        value for jobs in jobs_by_run.values() for value in status_values(jobs)
    )
    result: dict[str, Any] = {
        "pull_request": pull_request,
        "commit_status": statuses,
        "aggregate_state": aggregate_gate_state(*health_values),
    }
    if runs is not None:
        result["actions_runs"] = runs
        result["actions_jobs"] = jobs_by_run
    output(result)


def pull_request_ref(value: str) -> str:
    try:
        subprocess.run(
            ["git", "check-ref-format", "--branch", value],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise HelperError(
            "arguments_error", "pull request refs must be valid branch names"
        ) from error
    return quote(value, safe="")


def existing_pull_request(
    client: ForgejoClient, repository: Repository, base: str, head: str
) -> dict[str, Any] | None:
    for page in range(1, 101):
        query = urlencode({"state": "all", "limit": 100, "page": page})
        pull_requests = client.request(
            "GET", f"{repository_path(repository)}/pulls?{query}"
        )
        if not isinstance(pull_requests, list):
            raise HelperError(
                "response_error", "Forgejo pull-request list response was invalid"
            )
        for pull_request in pull_requests:
            if not isinstance(pull_request, dict):
                continue
            pr_base = pull_request.get("base")
            pr_head = pull_request.get("head")
            if (
                isinstance(pr_base, dict)
                and isinstance(pr_head, dict)
                and pr_base.get("ref") == base
                and pr_head.get("ref") == head
            ):
                return pull_request
        if len(pull_requests) < 100:
            return None
    raise HelperError(
        "response_error", "Forgejo pull-request lookup exceeded page limit"
    )


def actions_outcome(record: Any) -> str:
    if not isinstance(record, dict):
        return "unknown"
    status = record.get("status")
    conclusion = record.get("conclusion")
    normalized_status = status.lower() if isinstance(status, str) else ""
    normalized_conclusion = conclusion.lower() if isinstance(conclusion, str) else ""
    if normalized_status in {
        "queued",
        "pending",
        "waiting",
        "requested",
        "in_progress",
        "running",
    }:
        return "pending"
    if normalized_conclusion in {"cancelled", "canceled"} or normalized_status in {
        "cancelled",
        "canceled",
    }:
        return "cancelled"
    if normalized_conclusion in {"timed_out", "timeout"} or normalized_status in {
        "timed_out",
        "timeout",
    }:
        return "timeout"
    if normalized_conclusion in {
        "failure",
        "failed",
        "error",
        "action_required",
        "neutral",
        "skipped",
    } or normalized_status in {"failure", "failed", "error"}:
        return "failure"
    if normalized_status == "success" or (
        normalized_status == "completed" and normalized_conclusion == "success"
    ):
        return "success"
    return "unknown"


def actions_collection(
    client: ForgejoClient,
    repository: Repository,
    endpoint: str,
    collection_key: str,
    deadline: float,
    query_parameters: dict[str, str] | None = None,
) -> ActionsCollectionResult:
    items: list[Any] = []
    page = 1
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return ActionsCollectionResult(items, complete=False, timed_out=True)
        query = urlencode(
            {"limit": ACTIONS_PAGE_SIZE, "page": page, **(query_parameters or {})}
        )
        try:
            payload = client.request("GET", f"{endpoint}?{query}", timeout=remaining)
        except HelperError as error:
            return ActionsCollectionResult(
                items,
                complete=False,
                error=error.code,
                timed_out=time.monotonic() >= deadline,
            )
        if not isinstance(payload, dict) or not isinstance(
            payload.get(collection_key), list
        ):
            return ActionsCollectionResult(
                items, complete=False, error="response_error"
            )
        page_items = payload[collection_key]
        items.extend(page_items)
        total_count = payload.get("total_count")
        if total_count is not None and (
            not isinstance(total_count, int)
            or isinstance(total_count, bool)
            or total_count < 0
        ):
            return ActionsCollectionResult(
                items, complete=False, error="response_error"
            )
        if total_count is not None:
            if total_count < len(items):
                return ActionsCollectionResult(
                    items, complete=False, error="response_error"
                )
            if len(items) >= total_count:
                return ActionsCollectionResult(items, complete=True)
            if not page_items:
                return ActionsCollectionResult(
                    items, complete=False, error="response_error"
                )
        elif len(page_items) < ACTIONS_PAGE_SIZE:
            return ActionsCollectionResult(items, complete=True)
        page += 1


def run_is_resolved(record: ActionsRunRecord) -> bool:
    if not record.jobs_complete or actions_outcome(record.run) == "pending":
        return False
    return all(actions_outcome(job) != "pending" for job in record.jobs.values())


def actions_wait_result(
    head_sha: str,
    records: dict[int, ActionsRunRecord],
    unidentified_runs: list[Any],
    *,
    timed_out: bool,
    discovery_complete: bool,
    error: str | None,
) -> dict[str, Any]:
    runs: list[dict[str, Any]] = []
    outcomes: list[str] = []
    for run_id, record in records.items():
        run_state = actions_outcome(record.run)
        jobs = [
            {"job": job, "state": actions_outcome(job)} for job in record.jobs.values()
        ]
        jobs.extend(
            {"job": job, "state": "unknown"} for job in record.unidentified_jobs
        )
        job_states = [job["state"] for job in jobs]
        if run_state == "failure" or "failure" in job_states:
            run_result = "failure"
        elif run_state == "cancelled" or "cancelled" in job_states:
            run_result = "cancelled"
        elif run_state == "timeout" or "timeout" in job_states:
            run_result = "timeout"
        elif run_state == "pending" or "pending" in job_states:
            run_result = "pending"
        elif (
            run_state == "success"
            and jobs
            and all(state == "success" for state in job_states)
            and record.jobs_complete
        ):
            run_result = "success"
        else:
            run_result = "unknown"
        outcomes.append(run_result)
        runs.append(
            {
                "id": run_id,
                "run": record.run,
                "run_state": run_state,
                "aggregate_state": run_result,
                "jobs": jobs,
                "jobs_complete": record.jobs_complete,
            }
        )
    if unidentified_runs:
        outcomes.append("unknown")
    if timed_out:
        aggregate = "timeout"
    elif "failure" in outcomes:
        aggregate = "failure"
    elif "cancelled" in outcomes:
        aggregate = "cancelled"
    elif "timeout" in outcomes:
        aggregate = "timeout"
    elif "pending" in outcomes:
        aggregate = "pending"
    elif (
        not outcomes
        or "unknown" in outcomes
        or error is not None
        or not discovery_complete
    ):
        aggregate = "unknown"
    else:
        aggregate = "success"
    result: dict[str, Any] = {
        "head_sha": head_sha,
        "aggregate_state": aggregate,
        "discovery_complete": discovery_complete,
        "timed_out": timed_out,
        "runs": runs,
    }
    if unidentified_runs:
        result["unidentified_runs"] = unidentified_runs
    if error is not None:
        result["error"] = error
    if not records and not unidentified_runs and error is None:
        result["reason"] = "no_runs"
    return result


def wait_for_actions(
    client: ForgejoClient,
    repository: Repository,
    head_sha: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    runs_endpoint = f"{repository_path(repository)}/actions/runs"
    records: dict[int, ActionsRunRecord] = {}
    unidentified_runs: list[Any] = []
    quiet_since: float | None = None
    error: str | None = None
    timed_out = False
    discovery_complete = False

    while True:
        if time.monotonic() >= deadline:
            timed_out = True
            break
        runs_result = actions_collection(
            client,
            repository,
            runs_endpoint,
            "workflow_runs",
            deadline,
            {"head_sha": head_sha},
        )

        new_records = False
        malformed_run = False
        for run in runs_result.items:
            if (
                not isinstance(run, dict)
                or not isinstance(run.get("id"), int)
                or isinstance(run.get("id"), bool)
                or run["id"] < 1
            ):
                unidentified_runs.append(run)
                malformed_run = True
                continue
            run_sha = run.get("head_sha")
            if not isinstance(run_sha, str) or not run_sha.strip():
                unidentified_runs.append(run)
                malformed_run = True
                continue
            if run_sha != head_sha:
                continue
            run_id = run["id"]
            if run_id not in records:
                records[run_id] = ActionsRunRecord(
                    run=run,
                    jobs={},
                    unidentified_jobs=[],
                )
                new_records = True
            else:
                records[run_id].run = run
        if malformed_run:
            error = "response_error"
            break
        if runs_result.timed_out:
            timed_out = True
            break
        if runs_result.error is not None or not runs_result.complete:
            error = runs_result.error or "response_error"
            break

        new_jobs = False
        for run_id, record in records.items():
            jobs_result = actions_collection(
                client,
                repository,
                f"{runs_endpoint}/{run_id}/jobs",
                "jobs",
                deadline,
            )
            latest_jobs: dict[int, Any] = {}
            unidentified_jobs: list[Any] = []
            for job in jobs_result.items:
                if not isinstance(job, dict):
                    unidentified_jobs.append(job)
                    continue
                job_id = job.get("id")
                if not isinstance(job_id, int) or isinstance(job_id, bool):
                    unidentified_jobs.append(job)
                    continue
                latest_jobs[job_id] = job
                if job_id not in record.jobs:
                    new_jobs = True
            record.jobs = latest_jobs
            record.unidentified_jobs = unidentified_jobs
            record.jobs_complete = jobs_result.complete
            if jobs_result.timed_out:
                timed_out = True
                break
            if jobs_result.error is not None or not jobs_result.complete:
                error = jobs_result.error or "response_error"
                break
        if timed_out or error is not None:
            break

        now = time.monotonic()
        if now >= deadline:
            timed_out = True
            break
        if new_records or new_jobs:
            quiet_since = None
        if not records:
            if quiet_since is None:
                quiet_since = now
        elif all(run_is_resolved(record) for record in records.values()):
            if quiet_since is None:
                quiet_since = now
        else:
            quiet_since = None
        if (
            quiet_since is not None
            and now - quiet_since >= ACTIONS_QUIET_PERIOD_SECONDS
        ):
            discovery_complete = True
            break

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            timed_out = True
            break
        time.sleep(min(ACTIONS_POLL_INTERVAL_SECONDS, remaining))

    return actions_wait_result(
        head_sha,
        records,
        unidentified_runs,
        timed_out=timed_out,
        discovery_complete=discovery_complete,
        error=error,
    )


def command_create_pr(args: argparse.Namespace) -> int:
    if args.auto_merge and not args.wait_for_actions:
        raise HelperError("arguments_error", "--auto-merge requires --wait-for-actions")
    if args.timeout is not None and not args.wait_for_actions:
        raise HelperError("arguments_error", "--timeout requires --wait-for-actions")
    timeout_seconds = (
        DEFAULT_ACTIONS_TIMEOUT_SECONDS if args.timeout is None else args.timeout
    )
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise HelperError(
            "arguments_error", "--timeout must be a finite positive number"
        )

    pull_request_ref(args.base)
    pull_request_ref(args.head)
    client, repository = api_context()
    pull_request = existing_pull_request(client, repository, args.base, args.head)
    if pull_request is None:
        body = read_optional_body_file(args.body_file)
        payload: dict[str, Any] = {
            "base": args.base,
            "head": args.head,
            "title": args.title,
        }
        if body is not None:
            payload["body"] = body
        try:
            created = client.request(
                "POST", f"{repository_path(repository)}/pulls", payload
            )
        except HelperError as error:
            if error.code != "http_error" or error.status != 409:
                raise
            pull_request = existing_pull_request(
                client, repository, args.base, args.head
            )
            if pull_request is None:
                raise
        else:
            if not isinstance(created, dict):
                raise HelperError(
                    "response_error", "Forgejo pull-request response was invalid"
                )
            pull_request = created

    if not args.wait_for_actions:
        output(pull_request)
        return 0

    head = pull_request.get("head")
    head_sha = head.get("sha") if isinstance(head, dict) else None
    if not isinstance(head_sha, str) or not head_sha.strip():
        actions = actions_wait_result(
            "",
            {},
            [],
            timed_out=False,
            discovery_complete=False,
            error="missing_head_sha",
        )
        result = {"pull_request": pull_request, "actions": actions}
        if args.auto_merge:
            result["auto_merge"] = {
                "state": "not_attempted",
                "reason": "actions_not_successful",
            }
        output(result)
        return 1

    actions = wait_for_actions(client, repository, head_sha, timeout_seconds)
    result = {"pull_request": pull_request, "actions": actions}
    succeeded = actions["aggregate_state"] == "success"
    if args.auto_merge:
        if succeeded:
            number = pull_request.get("number")
            if not isinstance(number, int) or isinstance(number, bool) or number < 1:
                result["auto_merge"] = {
                    "state": "refused",
                    "error": "response_error",
                }
                succeeded = False
            else:
                try:
                    merged = merge_pull_request(client, repository, number)
                except HelperError as error:
                    merge_result: dict[str, Any] = {
                        "state": (
                            "refused"
                            if error.code == "http_error"
                            and error.status is not None
                            and error.status < 500
                            else "unknown"
                        ),
                        "error": error.code,
                    }
                    if error.status is not None:
                        merge_result["status"] = error.status
                    result["auto_merge"] = merge_result
                    succeeded = False
                else:
                    result["auto_merge"] = {
                        "state": "merged",
                        "pull_request": merged,
                    }
        else:
            result["auto_merge"] = {
                "state": "not_attempted",
                "reason": "actions_not_successful",
            }
    output(result)
    return 0 if succeeded else 1


def read_optional_body_file(path: str | None) -> str | None:
    return Path(path).read_text(encoding="utf-8") if path else None


def require_positive_number(value: int) -> None:
    if value < 1:
        raise HelperError("arguments_error", "issue numbers must be positive integers")


def require_non_blank(value: str, label: str) -> None:
    if not value.strip():
        raise HelperError("arguments_error", f"{label} must not be blank")


def command_create_issue(args: argparse.Namespace) -> None:
    client, repository = api_context()
    require_non_blank(args.title, "issue title")
    body = read_optional_body_file(args.body_file)
    payload: dict[str, Any] = {"title": args.title}
    if body is not None:
        payload["body"] = body
    if args.label is not None:
        match = next(
            (
                item
                for item in labels_for_repository(client, repository)
                if isinstance(item, dict) and item.get("name") == args.label
            ),
            None,
        )
        if match is None or not isinstance(match.get("id"), int):
            raise HelperError(
                "label_not_found", "no repository label matched the requested name"
            )
        payload["labels"] = [match["id"]]
    output(client.request("POST", f"{repository_path(repository)}/issues", payload))


def command_close_issue(args: argparse.Namespace) -> None:
    client, repository = api_context()
    require_positive_number(args.number)
    output(
        client.request(
            "PATCH",
            f"{repository_path(repository)}/issues/{args.number}",
            {"state": "closed"},
        )
    )


def title_body_payload(args: argparse.Namespace, object_name: str) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if args.title is not None:
        require_non_blank(args.title, f"{object_name} title")
        payload["title"] = args.title
    if args.body is not None and args.body_file is not None:
        raise HelperError(
            "arguments_error", "provide at most one of --body or --body-file"
        )
    if args.body is not None:
        payload["body"] = args.body
    elif args.body_file is not None:
        payload["body"] = read_optional_body_file(args.body_file)
    if not payload:
        raise HelperError(
            "arguments_error", "provide at least one of --title, --body, or --body-file"
        )
    return payload


def command_update_issue(args: argparse.Namespace) -> None:
    payload = title_body_payload(args, "issue")
    client, repository = api_context()
    require_positive_number(args.number)
    issue_path = f"{repository_path(repository)}/issues/{args.number}"
    current = client.request("GET", issue_path)
    if not isinstance(current, dict):
        raise HelperError("response_error", "Forgejo issue response was invalid")
    if current.get("pull_request") is not None:
        raise HelperError(
            "wrong_object_type", "update-issue does not edit pull requests"
        )
    output(client.request("PATCH", issue_path, payload))


def command_comment_issue(args: argparse.Namespace) -> None:
    client, repository = api_context()
    require_positive_number(args.number)
    if bool(args.body) == bool(args.body_file):
        raise HelperError(
            "arguments_error", "provide exactly one of --body or --body-file"
        )
    body = (
        args.body if args.body is not None else read_optional_body_file(args.body_file)
    )
    output(
        client.request(
            "POST",
            f"{repository_path(repository)}/issues/{args.number}/comments",
            {"body": body},
        )
    )


def paged_list(
    client: ForgejoClient, repository: Repository, endpoint: str, label: str
) -> tuple[list[Any], int]:
    items: list[Any] = []
    for page in range(1, 101):
        query = urlencode({"limit": 100, "page": page})
        page_items = client.request(
            "GET", f"{repository_path(repository)}{endpoint}?{query}"
        )
        if not isinstance(page_items, list):
            raise HelperError("response_error", f"Forgejo {label} response was invalid")
        items.extend(page_items)
        if len(page_items) < 100:
            return items, page
    raise HelperError("response_error", f"Forgejo {label} lookup exceeded page limit")


def list_result(items: list[Any], pages: int) -> dict[str, Any]:
    return {
        "items": items,
        "pagination": {"pages_fetched": pages, "item_count": len(items)},
    }


def normalized_record(
    item: Any, fields: tuple[str, ...], required: tuple[str, ...], label: str
) -> dict[str, Any]:
    if not isinstance(item, dict) or any(field not in item for field in required):
        raise HelperError("response_error", f"Forgejo {label} response was invalid")
    return {field: item[field] for field in fields if field in item}


def command_issue_comments(args: argparse.Namespace) -> None:
    client, repository = api_context()
    require_positive_number(args.number)
    items, pages = paged_list(
        client, repository, f"/issues/{args.number}/comments", "issue-comment-list"
    )
    fields = ("id", "user", "body", "created_at", "updated_at", "html_url")
    output(
        list_result(
            [
                normalized_record(item, fields, ("id", "body"), "issue-comment-list")
                for item in items
            ],
            pages,
        )
    )


def command_edit_issue_comment(args: argparse.Namespace) -> None:
    if args.body is not None and args.body_file is not None:
        raise HelperError(
            "arguments_error", "provide exactly one of --body or --body-file"
        )
    if args.body is None and args.body_file is None:
        raise HelperError(
            "arguments_error", "provide exactly one of --body or --body-file"
        )
    body = (
        args.body if args.body is not None else read_optional_body_file(args.body_file)
    )
    client, repository = api_context()
    require_positive_number(args.number)
    if args.comment_id < 1:
        raise HelperError("arguments_error", "comment ids must be positive integers")
    comments, _ = paged_list(
        client, repository, f"/issues/{args.number}/comments", "issue-comment-list"
    )
    if any(
        not isinstance(comment, dict) or not isinstance(comment.get("id"), int)
        for comment in comments
    ):
        raise HelperError(
            "response_error", "Forgejo issue-comment-list response was invalid"
        )
    matches = [comment for comment in comments if comment["id"] == args.comment_id]
    if not matches:
        raise HelperError(
            "comment_not_found", "comment does not belong to the requested issue"
        )
    if len(matches) != 1:
        raise HelperError(
            "ambiguous_comment", "comment id did not identify exactly one comment"
        )
    updated = client.request(
        "PATCH",
        f"{repository_path(repository)}/issues/comments/{args.comment_id}",
        {"body": body},
    )
    if not isinstance(updated, dict) or updated.get("id") != args.comment_id:
        raise HelperError(
            "response_error", "Forgejo issue-comment response was invalid"
        )
    output(updated)


def pull_request_for_command(
    client: ForgejoClient, repository: Repository, number: int
) -> dict[str, Any]:
    path = f"{repository_path(repository)}/pulls/{number}"
    value = client.request("GET", path, allow_not_found=True)
    if isinstance(value, dict):
        return value
    issue = client.request(
        "GET", f"{repository_path(repository)}/issues/{number}", allow_not_found=True
    )
    if isinstance(issue, dict):
        raise HelperError("wrong_object_type", "requested number is not a pull request")
    raise HelperError("http_error", "Forgejo request failed", status=404)


def command_update_pr(args: argparse.Namespace) -> None:
    payload = title_body_payload(args, "pull-request")
    client, repository = api_context()
    require_positive_number(args.number)
    pull_request_for_command(client, repository, args.number)
    output(
        client.request(
            "PATCH", f"{repository_path(repository)}/pulls/{args.number}", payload
        )
    )


def command_pr_files(args: argparse.Namespace) -> None:
    client, repository = api_context()
    require_positive_number(args.number)
    pull_request_for_command(client, repository, args.number)
    items, pages = paged_list(
        client, repository, f"/pulls/{args.number}/files", "pull-request-file-list"
    )
    fields = (
        "filename",
        "status",
        "additions",
        "deletions",
        "changes",
        "sha",
        "blob_url",
        "raw_url",
        "contents_url",
    )
    output(
        list_result(
            [
                normalized_record(item, fields, ("filename",), "pull-request-file-list")
                for item in items
            ],
            pages,
        )
    )


def command_pr_reviews(args: argparse.Namespace) -> None:
    client, repository = api_context()
    require_positive_number(args.number)
    pull_request_for_command(client, repository, args.number)
    items, pages = paged_list(
        client, repository, f"/pulls/{args.number}/reviews", "pull-request-review-list"
    )
    fields = (
        "id",
        "user",
        "state",
        "body",
        "submitted_at",
        "commit_id",
        "dismissed",
        "dismissed_by",
        "dismissal_message",
    )
    output(
        list_result(
            [
                normalized_record(
                    item, fields, ("id", "state"), "pull-request-review-list"
                )
                for item in items
            ],
            pages,
        )
    )


def command_add_issue_label(args: argparse.Namespace) -> None:
    client, repository = api_context()
    require_positive_number(args.number)
    require_non_blank(args.label, "label name")
    label_record = repository_label_for_name(client, repository, args.label)
    current = client.request(
        "GET", f"{repository_path(repository)}/issues/{args.number}"
    )
    if not isinstance(current, dict):
        raise HelperError("response_error", "Forgejo issue response was invalid")
    labels = current.get("labels")
    if not isinstance(labels, list) or any(
        not isinstance(item, dict) or not isinstance(item.get("id"), int)
        for item in labels
    ):
        raise HelperError("response_error", "Forgejo issue labels response was invalid")
    label_id = label_record["id"]
    existing_ids = [item["id"] for item in labels]
    if label_id in existing_ids:
        output(
            {
                "number": args.number,
                "label": args.label,
                "changed": False,
                "labels": labels,
            }
        )
        return
    result = client.request(
        "POST",
        f"{repository_path(repository)}/issues/{args.number}/labels",
        {"labels": existing_ids + [label_id]},
    )
    if not isinstance(result, list):
        raise HelperError("response_error", "Forgejo issue-label response was invalid")
    output(
        {"number": args.number, "label": args.label, "changed": True, "labels": result}
    )


def command_remove_issue_label(args: argparse.Namespace) -> None:
    client, repository = api_context()
    require_positive_number(args.number)
    require_non_blank(args.label, "label name")
    label_record = repository_label_for_name(client, repository, args.label)
    label_id = label_record["id"]
    issue_path = f"{repository_path(repository)}/issues/{args.number}"
    current = client.request("GET", issue_path)
    if not isinstance(current, dict):
        raise HelperError("response_error", "Forgejo issue response was invalid")
    labels = current.get("labels")
    if not isinstance(labels, list) or any(
        not isinstance(item, dict) or not isinstance(item.get("id"), int)
        for item in labels
    ):
        raise HelperError("response_error", "Forgejo issue labels response was invalid")
    if label_id not in [item["id"] for item in labels]:
        output(
            {
                "number": args.number,
                "label": args.label,
                "changed": False,
                "labels": labels,
            }
        )
        return
    client.request("DELETE", f"{issue_path}/labels/{label_id}")
    updated = client.request("GET", issue_path)
    if not isinstance(updated, dict) or not isinstance(updated.get("labels"), list):
        raise HelperError("response_error", "Forgejo issue-label response was invalid")
    updated_labels = updated["labels"]
    if any(
        not isinstance(item, dict) or not isinstance(item.get("id"), int)
        for item in updated_labels
    ):
        raise HelperError("response_error", "Forgejo issue-label response was invalid")
    if label_id in [item["id"] for item in updated_labels]:
        raise HelperError("response_error", "Forgejo issue label was not removed")
    output(
        {
            "number": args.number,
            "label": args.label,
            "changed": True,
            "labels": updated_labels,
        }
    )


def all_issues_for_state(
    client: ForgejoClient, repository: Repository, state: str
) -> list[Any]:
    issues: list[Any] = []
    for page in range(1, 101):
        query = urlencode({"state": state, "limit": 100, "page": page})
        page_issues = client.request(
            "GET", f"{repository_path(repository)}/issues?{query}"
        )
        if not isinstance(page_issues, list):
            raise HelperError(
                "response_error", "Forgejo issue-list response was invalid"
            )
        issues.extend(page_issues)
        if len(page_issues) < 100:
            return issues
    raise HelperError("response_error", "Forgejo issue-list lookup exceeded page limit")


def command_list_issues(args: argparse.Namespace) -> None:
    client, repository = api_context()
    output(all_issues_for_state(client, repository, args.state))


def merged_pull_request(
    client: ForgejoClient, repository: Repository, number: int
) -> dict[str, Any]:
    pr = client.request("GET", f"{repository_path(repository)}/pulls/{number}")
    if not isinstance(pr, dict):
        raise HelperError("response_error", "Forgejo pull-request response was invalid")
    return pr


def merge_pull_request(
    client: ForgejoClient, repository: Repository, number: int
) -> dict[str, Any]:
    require_positive_number(number)
    pull_request = merged_pull_request(client, repository, number)
    if pull_request.get("merged"):
        return pull_request
    try:
        client.request(
            "POST",
            f"{repository_path(repository)}/pulls/{number}/merge",
            {"Do": "merge", "delete_branch_after_merge": True},
        )
    except HelperError as error:
        if error.code != "http_error" or error.status != 409:
            raise
        pull_request = merged_pull_request(client, repository, number)
        if not pull_request.get("merged"):
            raise
        return pull_request
    return merged_pull_request(client, repository, number)


def command_merge_pr(args: argparse.Namespace) -> None:
    client, repository = api_context()
    output(merge_pull_request(client, repository, args.number))


def labels_for_repository(client: ForgejoClient, repository: Repository) -> list[Any]:
    labels: list[Any] = []
    for page in range(1, 101):
        query = urlencode({"limit": 100, "page": page})
        page_labels = client.request(
            "GET", f"{repository_path(repository)}/labels?{query}"
        )
        if not isinstance(page_labels, list):
            raise HelperError(
                "response_error", "Forgejo label-list response was invalid"
            )
        labels.extend(page_labels)
        if len(page_labels) < 100:
            return labels
    raise HelperError("response_error", "Forgejo label-list lookup exceeded page limit")


def repository_label_for_name(
    client: ForgejoClient, repository: Repository, name: str
) -> dict[str, Any]:
    matches = [
        label
        for label in labels_for_repository(client, repository)
        if isinstance(label, dict) and label.get("name") == name
    ]
    if not matches:
        raise HelperError(
            "label_not_found", "no repository label matched the requested name"
        )
    if len(matches) > 1 or not isinstance(matches[0].get("id"), int):
        raise HelperError(
            "ambiguous_label",
            "repository label name did not identify exactly one label",
        )
    return matches[0]


def command_git_check(_: argparse.Namespace) -> None:
    repository = repository_from_origin()
    branch = git_output("branch", "--show-current")
    status = git_output("status", "--short", "--branch")
    output(
        {
            "repository": repository.__dict__,
            "branch": branch,
            "status": status.splitlines(),
        }
    )


def command_list_labels(args: argparse.Namespace) -> None:
    client, repository = api_context()
    labels = labels_for_repository(client, repository)
    if args.name is not None:
        labels = [
            item
            for item in labels
            if isinstance(item, dict) and item.get("name") == args.name
        ]
    output(labels)


def normalized_label_color(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    color = value[1:] if value.startswith("#") else value
    return color.lower() if re.fullmatch(r"[0-9a-fA-F]{6}", color) else None


def matching_label_for_creation(
    labels: list[Any], name: str, color: str, description: str | None
) -> dict[str, Any] | None:
    matches = [
        label
        for label in labels
        if isinstance(label, dict) and label.get("name") == name
    ]
    if not matches:
        return None
    if len(matches) != 1 or not isinstance(matches[0].get("id"), int):
        raise HelperError(
            "ambiguous_label",
            "repository label name did not identify exactly one label",
        )
    label = matches[0]
    if normalized_label_color(label.get("color")) != color or (
        description is not None and label.get("description", "") != description
    ):
        raise HelperError(
            "label_exists", "repository label exists with different properties"
        )
    return label


def command_create_label(args: argparse.Namespace) -> None:
    require_non_blank(args.name, "label name")
    color = normalized_label_color(args.color)
    if color is None:
        raise HelperError(
            "arguments_error", "label color must be six-digit hexadecimal"
        )
    client, repository = api_context()
    existing = matching_label_for_creation(
        labels_for_repository(client, repository),
        args.name,
        color,
        args.description,
    )
    if existing is not None:
        output({"created": False, "label": existing})
        return

    payload: dict[str, Any] = {"name": args.name, "color": color}
    if args.description is not None:
        payload["description"] = args.description
    try:
        created = client.request(
            "POST", f"{repository_path(repository)}/labels", payload
        )
    except HelperError as error:
        if error.code != "http_error" or error.status != 409:
            raise
        existing = matching_label_for_creation(
            labels_for_repository(client, repository),
            args.name,
            color,
            args.description,
        )
        if existing is None:
            raise
        output({"created": False, "label": existing})
        return
    if (
        not isinstance(created, dict)
        or not isinstance(created.get("id"), int)
        or created.get("name") != args.name
        or normalized_label_color(created.get("color")) != color
        or (
            args.description is not None
            and created.get("description", "") != args.description
        )
    ):
        raise HelperError("response_error", "Forgejo label response was invalid")
    output({"created": True, "label": created})


def workflow_inputs(values: list[str]) -> dict[str, str]:
    inputs: dict[str, str] = {}
    for value in values:
        key, separator, input_value = value.partition("=")
        if not separator or not key.strip():
            raise HelperError(
                "arguments_error", "workflow inputs must use non-empty key=value pairs"
            )
        if key in inputs:
            raise HelperError("arguments_error", "workflow input keys must be unique")
        inputs[key] = input_value
    return inputs


def command_workflow_dispatch(args: argparse.Namespace) -> None:
    require_non_blank(args.workflow_file, "workflow filename")
    require_non_blank(args.ref, "workflow ref")
    inputs = workflow_inputs(args.input)
    client, repository = api_context()
    payload: dict[str, Any] = {"ref": args.ref}
    if inputs:
        payload["inputs"] = inputs
    response = client.request(
        "POST",
        f"{repository_path(repository)}/actions/workflows/"
        f"{quote(args.workflow_file, safe='')}/dispatches",
        payload,
    )
    result: dict[str, Any] = {"accepted": True}
    if response is not None:
        result["response"] = response
    output(result)


def command_rerun_run(args: argparse.Namespace) -> None:
    client, repository = api_context()
    require_positive_number(args.run_id)
    run = client.request(
        "GET", f"{repository_path(repository)}/actions/runs/{args.run_id}"
    )
    if not isinstance(run, dict):
        raise HelperError("response_error", "Forgejo Actions run response was invalid")
    active = run.get("status")
    if isinstance(active, str) and active.lower() in {
        "queued",
        "running",
        "in_progress",
        "waiting",
        "requested",
    }:
        raise HelperError(
            "not_rerunnable", "Actions run is still active and cannot be rerun"
        )
    client.request(
        "POST", f"{repository_path(repository)}/actions/runs/{args.run_id}/rerun"
    )
    rerun = client.request(
        "GET", f"{repository_path(repository)}/actions/runs/{args.run_id}"
    )
    if not isinstance(rerun, dict):
        raise HelperError("response_error", "Forgejo Actions run response was invalid")
    output(rerun)


def command_job_log(args: argparse.Namespace) -> None:
    client, repository = api_context()
    require_positive_number(args.run_id)
    require_positive_number(args.job_id)
    log_bytes, content_type = client.request_raw(
        "GET", f"{repository_path(repository)}/actions/jobs/{args.job_id}/logs"
    )
    if zipfile.is_zipfile(io.BytesIO(log_bytes)):
        try:
            with zipfile.ZipFile(io.BytesIO(log_bytes)) as archive:
                lines = [
                    archive.read(name).decode("utf-8", errors="replace")
                    for name in archive.namelist()
                    if not name.endswith("/")
                ]
        except (zipfile.BadZipFile, OSError, RuntimeError) as error:
            raise HelperError(
                "response_error", "Forgejo job log was not readable"
            ) from error
        log_text = "".join(lines)
    elif (
        content_type is not None
        and content_type.split(";", 1)[0].strip().lower() == "text/plain"
    ):
        # Forgejo versions may return the log body directly instead of a ZIP.
        log_text = log_bytes.decode("utf-8", errors="replace")
    else:
        raise HelperError("response_error", "Forgejo job log format was not recognized")
    sys.stdout.write(log_text)


def parser() -> argparse.ArgumentParser:
    result = HelperArgumentParser(description="Constrained Forgejo task helper")
    commands = result.add_subparsers(dest="command", required=True)
    commands.add_parser("preflight").set_defaults(handler=command_preflight)
    for name, handler in (
        ("issue", command_issue),
        ("pr", command_pr),
        ("pr-health", command_pr_health),
    ):
        command = commands.add_parser(name)
        command.add_argument("number", type=int)
        command.set_defaults(handler=handler)
    create_pr = commands.add_parser("create-pr")
    create_pr.add_argument("--base", required=True)
    create_pr.add_argument("--head", required=True)
    create_pr.add_argument("--title", required=True)
    create_pr.add_argument("--body-file")
    create_pr.add_argument("--wait-for-actions", action="store_true")
    create_pr.add_argument("--timeout", type=float)
    create_pr.add_argument("--auto-merge", action="store_true")
    create_pr.set_defaults(handler=command_create_pr)
    create_issue = commands.add_parser("create-issue")
    create_issue.add_argument("--title", required=True)
    create_issue.add_argument("--body-file")
    create_issue.add_argument("--label")
    create_issue.set_defaults(handler=command_create_issue)
    close_issue = commands.add_parser("close-issue")
    close_issue.add_argument("number", type=int)
    close_issue.set_defaults(handler=command_close_issue)
    update_issue = commands.add_parser("update-issue")
    update_issue.add_argument("number", type=int)
    update_issue.add_argument("--title")
    update_issue.add_argument("--body")
    update_issue.add_argument("--body-file")
    update_issue.set_defaults(handler=command_update_issue)
    update_pr = commands.add_parser("update-pr")
    update_pr.add_argument("number", type=int)
    update_pr.add_argument("--title")
    update_pr.add_argument("--body")
    update_pr.add_argument("--body-file")
    update_pr.set_defaults(handler=command_update_pr)
    comment_issue = commands.add_parser("comment-issue")
    comment_issue.add_argument("number", type=int)
    comment_issue.add_argument("--body")
    comment_issue.add_argument("--body-file")
    comment_issue.set_defaults(handler=command_comment_issue)
    edit_issue_comment = commands.add_parser("edit-issue-comment")
    edit_issue_comment.add_argument("number", type=int)
    edit_issue_comment.add_argument("comment_id", type=int)
    edit_issue_comment.add_argument("--body")
    edit_issue_comment.add_argument("--body-file")
    edit_issue_comment.set_defaults(handler=command_edit_issue_comment)
    issue_comments = commands.add_parser("issue-comments")
    issue_comments.add_argument("number", type=int)
    issue_comments.set_defaults(handler=command_issue_comments)
    pr_files = commands.add_parser("pr-files")
    pr_files.add_argument("number", type=int)
    pr_files.set_defaults(handler=command_pr_files)
    pr_reviews = commands.add_parser("pr-reviews")
    pr_reviews.add_argument("number", type=int)
    pr_reviews.set_defaults(handler=command_pr_reviews)
    add_issue_label = commands.add_parser("add-issue-label")
    add_issue_label.add_argument("number", type=int)
    add_issue_label.add_argument("--label", required=True)
    add_issue_label.set_defaults(handler=command_add_issue_label)
    remove_issue_label = commands.add_parser("remove-issue-label")
    remove_issue_label.add_argument("number", type=int)
    remove_issue_label.add_argument("--label", required=True)
    remove_issue_label.set_defaults(handler=command_remove_issue_label)
    list_issues = commands.add_parser("list-issues")
    list_issues.add_argument(
        "--state", choices=("open", "closed", "all"), default="open"
    )
    list_issues.set_defaults(handler=command_list_issues)
    merge_pr = commands.add_parser("merge-pr")
    merge_pr.add_argument("number", type=int)
    merge_pr.set_defaults(handler=command_merge_pr)
    list_labels = commands.add_parser("list-labels")
    list_labels.add_argument("--name")
    list_labels.set_defaults(handler=command_list_labels)
    create_label = commands.add_parser("create-label")
    create_label.add_argument("--name", required=True)
    create_label.add_argument("--color", required=True)
    create_label.add_argument("--description")
    create_label.set_defaults(handler=command_create_label)
    workflow_dispatch = commands.add_parser("workflow-dispatch")
    workflow_dispatch.add_argument("workflow_file")
    workflow_dispatch.add_argument("--ref", required=True)
    workflow_dispatch.add_argument("--input", action="append", default=[])
    workflow_dispatch.set_defaults(handler=command_workflow_dispatch)
    rerun_run = commands.add_parser("rerun-run")
    rerun_run.add_argument("run_id", type=int)
    rerun_run.set_defaults(handler=command_rerun_run)
    job_log = commands.add_parser("job-log")
    job_log.add_argument("run_id", type=int)
    job_log.add_argument("job_id", type=int)
    job_log.set_defaults(handler=command_job_log)
    commands.add_parser("git-check").set_defaults(handler=command_git_check)
    return result


def main() -> int:
    try:
        args = parser().parse_args()
        result = args.handler(args)
        if isinstance(result, int):
            return result
    except HelperError as error:
        value: dict[str, Any] = {"error": error.code, "message": error.message}
        if error.status is not None:
            value["status"] = error.status
        print(json.dumps(value, sort_keys=True), file=sys.stderr)
        return 1
    except OSError:
        print(
            json.dumps(
                {
                    "error": "file_error",
                    "message": "required local file could not be read",
                }
            ),
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
