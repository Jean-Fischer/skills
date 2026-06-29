# Repo Audit Handbook

## Purpose
This skill is audit-only in v1. It routes to the right existing specialists and consolidates their findings into one concise report.

## Preflight
Before choosing specialists, verify the repo shape and look for these inputs:
- Angular workspace / frontend app files, especially `angular.json` or Angular package usage
- Angular test code or specs, especially `*.spec.ts`
- `.csproj` / `.sln` / backend code or other C# source
- C# test projects or test source

If the evidence is ambiguous, prefer the conservative path: mark the checkpoint blocked rather than silently narrowing the specialist set.

## Fixed routing
Use the same map every time:
- Angular present → run `angular-offline-migration` and `angular`
- Angular test code present → run `angular-tests`
- .NET / C# present → run `csharp`
- C# test code present → run `csharp-tests`

Treat Angular presence as a repo-level evidence check, not a free-form judgment call. If Angular is present, both Angular specialists must run; if Angular test code is present, also run `angular-tests`.

If the evidence is missing, mark that checkpoint `blocked` rather than guessing.

## Execution flow
1. Discover the repo shape.
   - Use flexible, pattern-based discovery (e.g. `bash`, `find`, `read`) to detect Angular, C#, and tests from evidence such as file names, extensions, and common paths.
   - Prefer pattern-based detection over hard-coded paths, so the flow adapts to different project layouts.
   - If evidence for a technology or tool is ambiguous, mark that checkpoint as blocked rather than guessing.
   - **Discovery guardrails (aggressive):**
     - Ignore heavy and irrelevant directories such as `node_modules`, `.git`, `.pi`, `.worktrees`, `dist`, `bin`, `obj`, and large test-output folders when scanning.
     - Focus searches on likely roots (e.g. top-level project folders, `src/`, `tests/`, `Pipelines/`) instead of recursively traversing the entire filesystem.
     - Limit directory exploration to **two levels deep** from each chosen root (for example, `find . -maxdepth 2` or equivalent); do not scan deeper trees as part of repo-audit v1.
     - Stop discovery for a stack once its presence/absence is clear and its key artifacts are located; do not exhaustively list every file.
     - Do not run heavy build or test commands (`pnpm`, `npm`, `ng build`, `ng test`, `dotnet build`, `dotnet test`) as part of discovery; repo-audit v1 inspects configuration and existing artifacts only.
2. Find the newest relevant local artifacts.
   - For each detected stack, identify the most recent local artifact (e.g. current project files for Angular and C#).
3. Launch the applicable specialists via subagents.
   - For each required domain from the fixed routing map, start a fresh-context subagent run using a generic agent like `reviewer` or `worker`.
   - Attach the appropriate skills at runtime via the `skill` field, for example:
     - Angular: `skill: ["angular-offline-migration", "angular"]`
     - Angular tests: `skill: ["angular-tests"]`
     - C#: `skill: ["csharp"]`
     - C# tests: `skill: ["csharp-tests"]`
   - Provide each subagent with a short, explicit task that enforces audit-only behavior and requests a concise, structured report.
   - Make it explicit in each task that the specialist is expected to return a **high-level overview and top risks**, not an exhaustive, line-by-line drilldown; the goal is a fast, decision-ready summary.
   - When specialists do not depend on one another, launch them in parallel via subagent PARALLEL mode.
4. Consolidate the results into one checklist-first report.
   - Collect all specialist outputs.
   - Derive checklist statuses (pass / warn / fail / blocked) per checkpoint from the domain reports.
   - Build an executive summary from the top risks and blockers.
   - Attribute findings to their domains and include evidence paths (files, artifacts).
5. Preserve blockers and missing-input notes.
   - Carry blocked checkpoints and missing-input explanations unchanged into the final report.

## Workflow examples

These examples show how repo-audit is intended to use subagents. They are conceptual shapes, not exact API calls.

### Running repo-audit from another agent

Use a simple agent such as `reviewer` and attach the `repo-audit` skill:

```jsonc
{
  "agent": "reviewer",
  "task": "Run a repo-audit on this repo using /skill:repo-audit and return the consolidated report.",
  "skill": ["repo-audit"],
  "context": "fresh"
}
```

### Launching domain specialists (inside repo-audit)

After discovery, repo-audit SHOULD launch Angular and C# specialists using a small parallel fan-out. Use `reviewer` by default for specialists:

```jsonc
{
  "tasks": [
    {
      "agent": "reviewer",
      "task": "Using /skill:angular-offline-migration and /skill:angular, audit the Angular workspace and return a short high-level overview: checklist, top risks, evidence paths, status.",
      "skill": ["angular-offline-migration", "angular"],
      "context": "fresh"
    },
    {
      "agent": "reviewer",
      "task": "Using /skill:angular-tests, audit the Angular tests and return a short high-level overview: checklist, top risks, evidence paths, status.",
      "skill": ["angular-tests"],
      "context": "fresh"
    },
    {
      "agent": "reviewer",
      "task": "Using /skill:csharp, audit the C# backend and return a short high-level overview: checklist, top risks, evidence paths, status.",
      "skill": ["csharp"],
      "context": "fresh"
    },
    {
      "agent": "reviewer",
      "task": "Using /skill:csharp-tests, audit the C# tests and return a short high-level overview: checklist, top risks, evidence paths, status.",
      "skill": ["csharp-tests"],
      "context": "fresh"
    }
  ],
  "concurrency": 2
}
```

Guidelines for specialists:
- Use `reviewer` for repo-audit specialists; avoid heavy acceptance contracts that expect code changes or test runs.
- Each task MUST ask for a **high-level overview and top risks**, not an exhaustive drilldown.
- A small `concurrency` value (e.g. 2) keeps runs stable; sequential execution is acceptable if parallelism is unreliable.
- Specialists MUST NOT start new `repo-audit` runs; only the top-level orchestrator uses this skill.

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
