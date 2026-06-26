---
name: repo-audit
description: Use when auditing or triaging a local repo or codebase — for example, when the user says "review this repo", "inspect this codebase", "repo-wide health check", or "triage findings". Inspect the repo first, then route verified Angular, .NET/C#, Checkmarx, or SonarQube signals to the right specialists.
---

# Repo Audit

Use this skill as the top-level entry point for a repository-wide audit.

## Rules
1. Inspect the repo first; do not choose specialists blindly.
2. Use a fixed specialist map; do not invent new checks.
3. If the repo is Angular, run both Angular specialists: `angular-offline-migration` and `angular`.
4. Prefer audit/reporting only; v1 does not edit files or apply fixes.
5. Mark missing inputs as blocked instead of guessing.
6. Re-run the relevant specialist only if the source artifact changes.
7. For the exact preflight checklist, routing map, and report shape, follow `HANDBOOK.md`.

## Specialist choice
- `angular-offline-migration` and `angular` when Angular is present; the migration skill covers version/state risk and the Angular skill covers best-practice review.
- `csharp` when the repo has .NET / C# code or backend conventions to audit.
- `checkmarx-high-critical-findings` when a local Checkmarx artifact exists.
- `sonarqube-scan` when SonarQube analysis, quality gate status, or issue summaries are available.
- Mixed repos are not a reason to skip a verified stack.

## Output
Report what was checked, which specialists ran, the top findings in risk order, and any blocked inputs. Keep it checklist-first and short; the detailed report shape lives in `HANDBOOK.md`.

## Under pressure
Use the newest local artifacts, run every specialist required by verified evidence, and stop after the top blockers if time is tight.
