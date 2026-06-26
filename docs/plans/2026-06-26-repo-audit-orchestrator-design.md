# Repo Audit Orchestrator Design

## Purpose
Create a top-level Pi skill that audits a local repository against a fixed set of checkpoints and produces one consolidated report.

The first version is **audit-only**. It does not edit files, apply fixes, or rerun scans for remediation.

## Goals
- Inspect the local repo first and understand its shape.
- Detect pipeline YAML / CI / security-gate files before deeper checks.
- Delegate work to existing specialist skills instead of reimplementing them.
- Run independent specialists in parallel by default.
- Produce a hybrid report: checklist first, then a short executive summary.
- Keep the top-level skill thin and deterministic.

## Non-goals
- No remediation mode in v1.
- No automatic file edits.
- No open-ended skill selection.
- No repo-standards specialist for v1.
- No free-form re-interpretation of the specialist map.

## Reused specialist skills
Use the existing skills as fixed delegates:
- `skills/angular-offline-migration` for Angular migration health
- `skills/angular` for Angular best-practice and implementation hygiene
- `skills/csharp` for the .NET / C# baseline and repo conventions
- `skills/checkmarx-high-critical-findings` for Checkmarx findings
- `skills/sonarqube-scan` for SonarQube findings

If the repo does not appear to use one of these stacks, the orchestrator may skip that specialist. If the stack is present, the corresponding specialist must run.

## Execution flow
1. **Preflight**
   - verify the current directory is a git repository
   - inspect local repo metadata
   - locate pipeline YAML files first
   - detect whether Angular, .NET/C#, Checkmarx, and SonarQube checks are applicable

2. **Fixed routing**
   - build a checklist of relevant specialists from a hard-coded map
   - do not let the orchestrator invent new checks
   - guarantee Angular repos get both Angular migration and Angular best-practice coverage

3. **Parallel fan-out**
   - run independent specialists in parallel whenever possible
   - keep each specialist read-only
   - let each specialist gather evidence from the repo or from existing scan artifacts

4. **Consolidation**
   - normalize specialist output into a common structure
   - deduplicate repeated findings across specialists
   - group findings by file, subsystem, and severity
   - surface blockers before warnings

5. **Report**
   - checklist first
   - short executive summary second
   - include evidence paths and missing-input blockers

## Report format
### 1) Executive summary
Keep this short, ideally 3–6 lines:
- overall repo health
- top blockers
- missing inputs or unavailable scans
- strongest positive signal if the repo looks good

### 2) Checklist
One row per checkpoint, with a status such as:
- pass
- warn
- fail
- blocked

Suggested checkpoints:
- pipeline YAML present
- Angular migration health
- Angular best-practices health
- .NET / C# baseline
- Checkmarx status
- SonarQube status

### 3) Specialist findings
Group by specialist and include:
- severity
- evidence path or artifact
- short reason
- blocker or non-blocker

### 4) Recommended next actions
List the highest-priority items first.
If an input is missing, say so explicitly instead of guessing.

## Failure handling
- If a specialist cannot run because an expected input is missing, mark it `blocked`.
- Preserve partial results from other specialists.
- Do not infer a passing result from missing data.
- If a scan artifact is stale or absent, report that as part of the finding.
- Keep the audit single-pass in v1; do not rerun for remediation.

## Validation approach
Use pressure scenarios to verify the orchestrator does not silently skip required checks.

### Baseline failure scenarios
- Angular repo where the orchestrator would otherwise run only the Angular best-practices skill and skip migration checks.
- Repo with both CI and security-gate YAML files present, where pipeline discovery must happen before specialist fan-out.
- Repo with Checkmarx and SonarQube inputs present, where the audit must collect both results.
- Mixed repo where only one stack is present, to confirm irrelevant specialists are skipped rather than forced.
- Repo with missing scan artifacts, to confirm the report marks the result `blocked` instead of guessing.

### Success criteria
- Relevant specialists are routed deterministically.
- Independent checks run in parallel by default.
- Angular repos always get both Angular specialists.
- The final report is checklist-first and concise.
- No remediation behavior appears in v1.

## Implementation notes for the eventual skill
- Keep the eventual `SKILL.md` short and trigger-focused.
- Put routing tables, report schema, and examples in a companion handbook if detail grows.
- Use a rich description only for triggering conditions, not workflow summary.
- If remediation is ever added, make it a separate explicit mode or separate skill.
