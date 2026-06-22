---
name: checkmarx-high-critical-findings
description: Use when a local Checkmarx CLI scan for one repository needs actionable high and critical findings surfaced for remediation.
---

# Checkmarx High Critical Findings

## Overview

Turn the latest local Checkmarx scan into a compact, repo-local handoff for remediation.

## When to use

- You have a single local repository/project.
- You want the latest scan only.
- You need to focus on high and critical findings first.

## Workflow

1. Run the Checkmarx CLI for the latest scan and export SARIF.
    - Pass the current git branch with `--branch`.
   - Use a repo-local output folder such as `artifacts\checkmarx` and create it before the scan if it does not already exist.
    - Maintain a repo-local Checkmarx blacklist file (for example `cxblacklist.txt` or `checkmarxblacklist`) to exclude additional content such as large generated folders, third‑party code, or tracked files that were later added to `.gitignore`. If the blacklist file is missing, treat that as "no extra exclusions" rather than an error.
    - Invoke the scan only through a small helper script that:
      - uses `git ls-files` to enumerate tracked files,
      - filters them using the blacklist patterns (same semantics as your pipelines),
      - copies only the filtered files into a temporary working directory, and
      - runs `cx scan create -s <workdir> ...` against that filtered directory.
    - This command usually takes several minutes; that is normal, and you should wait for it to finish before moving on.
    - This scan is expensive; do not rerun it for every small code iteration. Reuse the latest artifact while making local fixes, and rerun only after a meaningful batch of changes or before handoff.
2. Normalize the SARIF into `artifacts\checkmarx\latest-findings.json` (or the same output folder you chose for the scan).
3. Open the JSON artifact and fix findings in this order:
   - critical
   - high
   - file/line hotspots with the most findings

## Recommended command shape

Use the installed Checkmarx CLI for this repo and request SARIF output. Keep the command stable for the project once chosen.

Typical shape (shell / Node.js helper):

```bash
mkdir -p artifacts/checkmarx
# Run the helper from the skill directory (next to SKILL.md and normalize-sarif.mjs)
node /path/to/checkmarx-high-critical-findings/cx-filtered-scan.mjs \
  --source . \
  --out-dir artifacts/checkmarx \
  --project-name "<project-name>" \
  --branch "$(git rev-parse --abbrev-ref HEAD)"
```

- You **must** pass `--project-name` explicitly to the helper. Use the project name resolution rules below (including any `security-gate.yml`/`.yaml` conventions) to determine the correct value, then pass it to the script.
- The helper reads `cxblacklist.txt` at the repo root when present and applies the same blacklist semantics as your pipelines. If the file is missing, it simply performs no extra exclusions beyond Git tracking.
- The helper always builds a filtered temporary work directory based only on Git-tracked, non-blacklisted files and runs `cx scan create` against that directory before normalizing SARIF into `artifacts/checkmarx/latest-findings.json`.

- Use `--debug` when you need detailed request and upload logs; there is no separate verbose flag in the CLI output used here.
- Keep the repository `.gitignore` current so scan scope stays focused.
- Keep generated scan artifacts out of source control.

## Project name resolution

Before running a scan, make sure the Checkmarx project name is known.

1. Check explicit local config first.
2. Inspect pipeline YAML for an existing `project` / `project-name` / Checkmarx scan setting.
   - Common places include `.github/workflows/*.yml`, `.github/workflows/*.yaml`, `.gitlab-ci.yml`, and `azure-pipelines.yml`.
   - If a `security-gate` pipeline is present and it does **not** pass an explicit project name parameter, use the Git repository name (remote URL last path segment without `.git`) as the Checkmarx project name.
3. If no project name is defined anywhere, stop and ask the user for the exact project name instead of guessing.

## Distilled JSON

The agent should work from a compact artifact like this:

```json
{
  "status": "findings",
  "generatedAt": "2026-05-21T00:00:00.000Z",
  "projectName": "my-repo",
  "command": "cx scan create ... --report-format sarif",
  "summary": { "critical": 1, "high": 2, "total": 3 },
  "findings": [
    {
      "severity": "critical",
      "ruleId": "CX-123",
      "message": "SQL injection",
      "filePath": "src/app.ts",
      "startLine": 42,
      "endLine": 44,
      "helpUri": "https://..."
    }
  ],
  "errors": []
}
```

## Rules

- Keep only high and critical findings.
- If nothing actionable exists, write `status: "clean"` with an empty `findings` array.
- If scan or parsing fails, write `status: "failed"` and preserve the error details.
- Prefer deterministic sorting by severity, file path, then line number.
- Do not make the agent read raw SARIF unless it is troubleshooting the parser.

## Helper script

Use `normalize-sarif.mjs` in this directory to convert SARIF into the distilled JSON artifact.
It infers severity from `security-severity` when Checkmarx flattens SARIF result levels, so critical findings stay distinct from high findings.
