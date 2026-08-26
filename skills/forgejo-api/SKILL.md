---
name: forgejo-api
description: Use the constrained task-oriented Forgejo helper for repository issue and pull-request reads, PR health, issue/comment/label listing and mutations, safe PR creation and merge, Actions reruns and job logs, and Git diagnostics.
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
- **Mutations** — `create-issue` (optional `--label`), `close-issue` (idempotent, close-only), `comment-issue`, `add-issue-label` (exact lookup, idempotent), `create-pr` (idempotent, never updates), `merge-pr` (fixed `Do: merge`, deletes the source branch after a successful merge, idempotent, `main` allowed), `rerun-run` (refuses active runs).

Every command is task-oriented and single-action: exactly one issue/comment/PR per invocation, no dedup beyond the naturally idempotent close/merge/create-pr. Mutations are bounded to the list above — label administration/removal, review mutations, assignees, reopening/editing, releases, organizations, and standalone deletions are outside the helper surface (see ADR 0005). `merge-pr` is the reviewed exception for its coupled post-merge source-branch deletion. An unknown label name in `create-issue --label` fails with `label_not_found` before posting.

Configuration, authentication, origin parsing, and HTTP errors are failures, not missing capabilities: stop and fix the failure. Do not bypass them with raw REST.

Git protection rejection and non-fast-forward are also Git coordination failures, not helper capability gaps. Follow the repository's protected-branch and one-writer policy; do not use this helper or raw REST to work around them.

## Capability gaps

Raw REST is permitted only when the required capability is not implemented by this constrained helper. Immediately before the one minimal fallback request, write **exactly** this terminal-only notice to stderr, then verify the result:

```bash
printf '%s\n' 'FORGEJO_HELPER_BYPASS: required capability is not implemented by the constrained helper.' >&2
```

The notice does not authorize a fallback for configuration, authentication, origin, or HTTP failures. A fallback must not become a reusable generic client; add a reviewed helper command as follow-up work.

See [the command map](references/forgejo-api-map.md) for response contracts and the audited boundary.
