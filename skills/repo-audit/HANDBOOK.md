# Repo Audit Handbook

## Purpose
This skill is audit-only in v1. It routes to the right existing specialists and consolidates their findings into one concise report.

## Preflight
Before choosing specialists, verify the repo shape and look for these inputs:
- Angular workspace / frontend app files, especially `angular.json` or Angular package usage
- `.csproj` / `.sln` / backend code or other C# source
- pipeline YAML or security-gate files
- local Checkmarx SARIF or normalized findings
- SonarQube analysis or quality-gate output

If the evidence is ambiguous, prefer the conservative path: mark the checkpoint blocked rather than silently narrowing the specialist set.

## Fixed routing
Use the same map every time:
- Angular present → run `angular-offline-migration` and `angular`
- .NET / C# present → run `csharp`
- Checkmarx artifact present → run `checkmarx-high-critical-findings`
- SonarQube analysis available → run `sonarqube-scan`

Treat Angular presence as a repo-level evidence check, not a free-form judgment call. If Angular is present, both Angular specialists must run.

If the evidence is missing, mark that checkpoint `blocked` rather than guessing.

## Execution flow
1. Discover the repo shape.
2. Find the newest relevant local artifacts.
3. Launch the applicable specialists in parallel when they do not depend on each other.
4. Consolidate the results into one checklist-first report.
5. Preserve blockers and missing-input notes.

## Remediation policy
No remediation in v1.

If the audit finds an issue, report it instead of editing code or broadening the scope.

## Pressure mode
If time is tight:
1. Use the newest artifact for each check.
2. Run every specialist required by verified evidence.
3. Do not drop a required specialist to save time.
4. Focus on critical failures, blocker findings, and quality-gate misses.
5. Skip historical comparison and deep root-cause expansion.
6. Stop once the audit can clearly state pass / warn / fail / blocked for each checkpoint.

## Report shape
Keep the final answer short and structured:
- checklist of checkpoints with statuses
- executive summary
- specialist findings with evidence paths
- next actions
- blocked or missing inputs
