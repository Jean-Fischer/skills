# Checkmarx High Critical Findings Handbook

## Scope
This handbook holds the operational detail that belongs with `checkmarx-high-critical-findings`.
Keep `SKILL.md` thin; use this file for command shape, blacklist behavior, artifact structure, and remediation notes.

## Project name resolution
Before running a scan, resolve the Checkmarx project name from local configuration.

1. Check explicit local config first.
2. Inspect pipeline YAML for a `project`, `project-name`, or Checkmarx scan setting.
   - Common places: `.github/workflows/*.yml`, `.github/workflows/*.yaml`, `.gitlab-ci.yml`, and `azure-pipelines.yml`.
   - If a `security-gate` pipeline is present and it does **not** pass an explicit project name parameter, use the Git repository name as the Checkmarx project name.
3. If no project name is defined anywhere, stop and ask the user instead of guessing.

## Scan flow
Use the helper script next to this skill directory so the scan scope stays stable.

Typical command shape:

```bash
mkdir -p artifacts/checkmarx
node /path/to/checkmarx-high-critical-findings/cx-filtered-scan.mjs \
  --source . \
  --out-dir artifacts/checkmarx \
  --project-name "<project-name>" \
  --branch "$(git rev-parse --abbrev-ref HEAD)"
```

### Important behavior
- Pass `--project-name` explicitly.
- Use a repo-local output folder such as `artifacts/checkmarx`.
- The helper reads `cxblacklist.txt` at the repo root when present.
- Missing blacklist files mean "no extra exclusions," not an error.
- The helper scans only Git-tracked, non-blacklisted files.
- The helper exports SARIF and normalizes it into `artifacts/checkmarx/latest-findings.json`.
- Use `--debug` only when request/upload troubleshooting is needed.
- Do not rerun the scan for every tiny edit; reuse the latest artifact until a meaningful batch of changes is ready.

## Distilled artifact
Work from the normalized JSON artifact rather than raw SARIF unless troubleshooting the parser.

Recommended shape:

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

## Triage order
The full finding set matters. Review everything in the artifact, then prioritize work in this order:
1. critical
2. high
3. hotspots with repeated findings or repeated rules

If nothing actionable exists, record `status: "clean"` with an empty `findings` array.
If scan or parsing fails, record `status: "failed"` and keep the error details.

## Helper script
`normalize-sarif.mjs` infers severity from `security-severity` when Checkmarx flattens SARIF result levels, so critical findings stay distinct from high findings.
