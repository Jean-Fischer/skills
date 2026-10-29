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
import os
import re
import subprocess
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request, urlopen


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
            with urlopen(request, timeout=20) as response:
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


def command_create_pr(args: argparse.Namespace) -> None:
    client, repository = api_context()
    pull_request_ref(args.base)
    pull_request_ref(args.head)
    existing = existing_pull_request(client, repository, args.base, args.head)
    if existing is not None:
        output(existing)
        return
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
        existing = existing_pull_request(client, repository, args.base, args.head)
        if existing is None:
            raise
        output(existing)
        return
    output(created)


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
    matches = [
        item
        for item in labels_for_repository(client, repository)
        if isinstance(item, dict) and item.get("name") == args.label
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
    label_id = matches[0]["id"]
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


def command_merge_pr(args: argparse.Namespace) -> None:
    client, repository = api_context()
    require_positive_number(args.number)
    pull_request = merged_pull_request(client, repository, args.number)
    if pull_request.get("merged"):
        output(pull_request)
        return
    try:
        client.request(
            "POST",
            f"{repository_path(repository)}/pulls/{args.number}/merge",
            {"Do": "merge", "delete_branch_after_merge": True},
        )
    except HelperError as error:
        if error.code != "http_error" or error.status != 409:
            raise
        pull_request = merged_pull_request(client, repository, args.number)
        if not pull_request.get("merged"):
            raise
        output(pull_request)
        return
    output(merged_pull_request(client, repository, args.number))


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
    create_pr.set_defaults(handler=command_create_pr)
    create_issue = commands.add_parser("create-issue")
    create_issue.add_argument("--title", required=True)
    create_issue.add_argument("--body-file")
    create_issue.add_argument("--label")
    create_issue.set_defaults(handler=command_create_issue)
    close_issue = commands.add_parser("close-issue")
    close_issue.add_argument("number", type=int)
    close_issue.set_defaults(handler=command_close_issue)
    comment_issue = commands.add_parser("comment-issue")
    comment_issue.add_argument("number", type=int)
    comment_issue.add_argument("--body")
    comment_issue.add_argument("--body-file")
    comment_issue.set_defaults(handler=command_comment_issue)
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
        args.handler(args)
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
