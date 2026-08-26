# Forgejo helper command map

The constrained helper is the v1 Forgejo REST surface:

```bash
python3 forgejo_helper.py <command>
```

Run `preflight` first. It and every REST command authenticate with `GET /user`; `GITEA_SERVER_URL` alone selects the API server, while `origin` alone supplies `owner/repo`. The helper accepts credentials only through `GITEA_SERVER_URL` and `GITEA_SERVER_TOKEN`, needs no `jq`, never reads cache state by default, and has no Git mutation surface. Successful commands write JSON (or `null` for an empty successful response) to stdout; failures write sanitized JSON to stderr and return non-zero without response-body or credential leakage. Negative-case argument handling (blank titles, non-positive issue numbers, missing required arguments) reports a sanitized `arguments_error`.

## Read commands

| Command | REST requests after authentication | Result |
| --- | --- | --- |
| `preflight` | none | authenticated user, API URL, origin-derived repository |
| `issue <number>` | `GET /repos/{owner}/{repo}/issues/{number}` | issue JSON |
| `pr <number>` | `GET /repos/{owner}/{repo}/pulls/{number}` | pull-request JSON |
| `pr-health <number>` | PR read, commit status, then available `GET /repos/{owner}/{repo}/actions/runs?head_sha={head-sha}` and per-run jobs | Raw PR/status/Actions data plus aggregate state |
| `list-issues [--state open\|closed\|all]` | `GET /repos/{owner}/{repo}/issues?state=...` paged to completion | JSON array of issues (default `open`) |
| `list-labels [--name <x>]` | `GET /repos/{owner}/{repo}/labels` paged to completion; optional exact-name filter applied client-side | JSON array of repo labels |
| `issue-comments <number>` | `GET /repos/{owner}/{repo}/issues/{number}/comments` paged to completion | `{items, pagination}` |
| `pr-files <number>` | PR verification, then `GET /repos/{owner}/{repo}/pulls/{number}/files` paged to completion | `{items, pagination}` |
| `pr-reviews <number>` | PR verification, then `GET /repos/{owner}/{repo}/pulls/{number}/reviews` paged to completion | `{items, pagination}` |
| `job-log <run_id> <job_id>` | `GET /repos/{owner}/{repo}/actions/jobs/{job_id}/logs` (zip) after auth | Raw decompressed log text to stdout (the one non-JSON exception) |
| `git-check` | none | read-only local Git diagnostics |

`pr-health` preserves `pull_request`, `commit_status`, `actions_runs`, and per-run `actions_jobs` payloads. Its additive `aggregate_state` uses `failure > pending > success`; no usable gate data is `unknown`. If Actions endpoints are unavailable, the command succeeds with the remaining PR/commit health and omits Actions fields without warning.

`list-issues` accepts `open`, `closed`, or `all` state and returns the full paged-through array so the caller does not drive `page`/`limit` itself. It is repo-scoped from `origin`; it has no label, milestone, or assignee filters.

## Mutation commands

### `create-pr`

`create-pr --base <base> --head <head> --title <title> [--body-file <path>]`

1. Authenticates.
2. Pages through `GET /repos/{owner}/{repo}/pulls?state=all` and compares validated base/head branch names.
3. Returns an existing matching PR unchanged; otherwise it posts the supplied base, head, title, and optional body to `/pulls`. A `409 Conflict` triggers one idempotent re-read.

### `create-issue`

`create-issue --title <title> [--body-file <body>] [--label <name>]` posts `{title, body?, labels?}` to `/repos/{owner}/{repo}/issues` and returns the created issue JSON. The title is required and must be non-blank. The optional `--label <name>` resolves the label name to its id via the repo label list; an unknown name fails with a sanitized `label_not_found` before any issue is posted. Each invocation posts exactly one issue; it does not deduplicate (issues have no deterministic natural key).

### `close-issue`

`close-issue <number>` sends `PATCH /repos/{owner}/{repo}/issues/{number}` with `{"state":"closed"}` and returns the updated issue JSON. It is naturally idempotent: closing an already-closed issue returns the same `200` JSON without error. It is strictly close-only (no reopen); a nonexistent issue returns a sanitized `http_error` 404.

### `comment-issue`

`comment-issue <number> --body <text>` or `comment-issue <number> --body-file <path>` (exactly one required) posts `{body}` to `/repos/{owner}/{repo}/issues/{number}/comments` and returns the created comment JSON. Each invocation posts exactly one comment; comments on closed issues are allowed (no state check).

### `merge-pr`

`merge-pr <number>` merges a pull request with the fixed `Do: "merge"` strategy and requests Forgejo to delete the source branch after a successful merge (`delete_branch_after_merge: true`). The API requires `Do`; the repo default is not read. It is idempotent: it reads the PR first and returns the current merged JSON as a no-op when `merged` is already true; otherwise it posts to `/repos/{owner}/{repo}/pulls/{number}/merge` and on a `409` re-reads, returning the merged state if the merge landed. An already-merged PR is not re-submitted, so this command does not retry branch deletion for an earlier merge that left the branch behind. It allows merging into `main` (protected-main and non-fast-forward coordination is owned by the Git-side workflow, not this command). No flags: no alternate style, opt-out of branch deletion, force, or auto-merge. Errors: 404 (PR not found), 405 (not mergeable), 409 (merge conflict), 423 (archived repo) surface as sanitized `http_error`.

### `rerun-run`

`rerun-run <run_id>` reruns a whole Actions workflow run: `POST /repos/{owner}/{repo}/actions/runs/{run_id}/rerun`. It first reads the run and refuses an active run (queued/running/in_progress/waiting/requested) with a sanitized `not_rerunnable` error. It is a plain single mutation with no dedup guarantee; on success it returns the re-read run JSON. Errors: 404 / 403 / 400 / 422 surface as sanitized `http_error`.

### `add-issue-label`

`add-issue-label <number> --label <name>` resolves one exact, case-sensitive repository label, reads current issue/PR labels, and appends the label only when absent. It posts the complete label ID set to `/repos/{owner}/{repo}/issues/{number}/labels`, preserving existing labels. It returns `changed: false` for an existing label and `changed: true` after mutation. Missing and ambiguous exact names fail before mutation.

## Excluded mutations

Label removal/administration, milestone, assignee, update/reopen, release, organization, review, and standalone deletion mutations are outside the v1 helper surface. `merge-pr` is the reviewed exception for its coupled post-merge source-branch deletion. Protected-branch rejection and non-fast-forward are Git coordination failures; follow the repository's protected-branch and one-writer policy, not an API bypass.

## Capability fallback

Only an absent helper capability permits raw REST use. Immediately before one minimal request, write this exact terminal-only notice to stderr, then verify the result:

```bash
printf '%s\n' 'FORGEJO_HELPER_BYPASS: required capability is not implemented by the constrained helper.' >&2
```

Configuration, authentication, origin parsing, and HTTP failures never permit this fallback. A fallback must not become a reusable generic client; add the missing audited helper command in follow-up work.
