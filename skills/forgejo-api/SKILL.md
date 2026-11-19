---
name: forgejo-api
description: Use the constrained task-oriented Forgejo helper for issue and pull-request automation, workflow dispatch, bounded PR Actions waiting, Actions reruns and logs, and Git diagnostics.
---

# Forgejo helper

Use the bundled helper as the default and only v1 REST interface; do not start an active Forgejo workflow with direct `curl`:

```bash
python3 forgejo_helper.py preflight
```

`preflight` is required before a REST workflow. It authenticates with `GET /user`; each REST command also authenticates before its target request. The helper reads only `GITEA_SERVER_URL` and `GITEA_SERVER_TOKEN` from its environment. The API server URL is independent of the SSH/HTTPS host in `origin`, which supplies only `owner/repo`. It needs no `jq`.

Never pass a token as a CLI argument, print or persist one, infer an API URL from Git, or import the cache as a normal-workflow default. Successful JSON (including an empty/204 response as `null`) goes only to stdout. Sanitized non-zero errors go only to stderr; do not print response bodies or either environment value.

## Commands

Start every REST workflow with `preflight` (above) — it authenticates and confirms the origin-derived repository. From there, use the task-oriented commands; the [command map](references/forgejo-api-map.md) is the single source of truth for every invocation, arguments, REST requests, output contract, and error mapping. Command families:

- **Reads** — `issue`, `pr`, `pr-health`, `list-issues`, `list-labels`, `issue-comments`, `pr-files`, `pr-reviews`, `job-log` (raw text to stdout), `git-check`.
- **Mutations** — `create-issue` (optional `--label`), `close-issue` (idempotent, close-only), `update-issue` / `update-pr` (title/body only), `comment-issue`, `edit-issue-comment` (verifies comment belongs to the issue), `add-issue-label` / `remove-issue-label` (exact lookup, idempotent), `create-label` (one repo label; exact existing match is a no-op), `workflow-dispatch` (dispatch only; no inferred run lookup), `create-pr` (idempotent, never updates; optional Actions wait and explicit auto-merge), `merge-pr` (fixed `Do: merge`, deletes the source branch after a successful merge, idempotent, `main` allowed), `rerun-run` (refuses active runs).

Commands are task-oriented and bounded to the list above. `workflow-dispatch` triggers one named workflow. `create-pr` remains idempotent and does not update an existing PR; its optional wait/auto-merge flags add only the workflow described below. Repo label updates/deletion, review mutations, assignees, reopening or other issue-state changes, PR changes beyond title/body updates and merge, issue dependencies, releases, organizations, and standalone deletions remain outside the helper surface (see ADR 0005). `update-issue` and `update-pr` change only supplied title/body fields; they cannot change state. `create-label` never changes an existing label. `merge-pr` and successful `create-pr --auto-merge` use the reviewed merge operation, including its coupled post-merge source-branch deletion. Unknown or ambiguous label names fail before mutation.

`workflow-dispatch <workflow-file> --ref <ref> [--input key=value ...]` dispatches only. It returns accepted status and preserves a direct API response if supplied; it never searches for a recent run. `create-pr --wait-for-actions` waits for all discovered Actions runs and jobs associated with the PR head SHA, including delayed runs and paginated results. The configurable `--timeout` bounds the wait. Results include per-run/per-job states; no runs, missing data, failure, cancellation, pending work, and timeout are non-success and exit nonzero. This wait covers Actions only, not external commit statuses. `--auto-merge` requires `--wait-for-actions` and invokes the normal Forgejo merge operation only after Actions succeed; Forgejo still enforces reviews and branch protection. A refusal or uncertain merge response is reported and exits nonzero. With no new flags, `create-pr` retains its immediate behavior.

Configuration, authentication, origin parsing, and HTTP errors are failures, not missing capabilities: stop and fix the failure. Do not bypass them with raw REST.

Git protection rejection and non-fast-forward are also Git coordination failures, not helper capability gaps. Follow the repository's protected-branch and one-writer policy; do not use this helper or raw REST to work around them.

## Capability gaps

Raw REST is permitted only when the required capability is not implemented by this constrained helper. Immediately before the one minimal fallback request, write **exactly** this terminal-only notice to stderr, then verify the result:

```bash
printf '%s\n' 'FORGEJO_HELPER_BYPASS: required capability is not implemented by the constrained helper.' >&2
```

The notice does not authorize a fallback for configuration, authentication, origin, or HTTP failures. A fallback must not become a reusable generic client; add a reviewed helper command as follow-up work.

See [the command map](references/forgejo-api-map.md) for response contracts and the audited boundary.
