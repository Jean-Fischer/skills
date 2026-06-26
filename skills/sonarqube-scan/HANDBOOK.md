# SonarQube Scan Handbook

## Scope
This handbook holds the detail that belongs with `sonarqube-scan`.
Keep `SKILL.md` light; use this file for configuration discovery, artifact handling, and fallback behavior.

## Configuration discovery
Search for the project key and any scan inputs in repository config before running the CLI.

Preferred sources include:
- `.github/workflows/*.yml`
- `.github/workflows/*.yaml`
- `.gitlab-ci.yml`
- `azure-pipelines.yml`

If the project key cannot be found, ask the user instead of guessing.

## File selection
Do not send irrelevant files to SonarQube.

- Respect SCM-based ignore behavior when the scanner supports it.
- Reuse the repository’s existing `sonar.exclusions` if present.
- Preserve any strict `sonar.inclusions` allowlist behavior.
- Exclude generated, vendored, and build output such as `node_modules`, `dist`, `bin`, `obj`, and coverage output.

## Scan flow
1. Resolve the project key and any missing scan inputs.
2. Resolve exclusions so irrelevant files stay out of analysis.
3. Run `sonar` from the repository root and wait for it to finish.
4. Inspect the output for a local report path.
5. If needed, check `.scannerwork/report-task.txt`.
6. If the CLI cannot produce a local artifact, query the authenticated API for quality gate and issue data.

## Result handling
Return:
- the local report path when available,
- a brief pass/fail quality-gate summary,
- the latest open issues when the CLI could not produce a scan artifact,
- and any CLI output needed to understand failures.

## Known CLI behavior
The installed `sonar` CLI may not support a full repository scan command.
If that happens, use the authenticated API instead of pretending a scan artifact exists.

## Error handling
If configuration discovery fails, ask the user instead of guessing.
If `sonar` exits non-zero, surface the exit status and raw command output.
If local artifact discovery and API fallback both fail, report that clearly.
