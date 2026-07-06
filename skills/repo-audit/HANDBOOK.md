# Repo Audit Handbook

## Purpose
This skill is audit-only in v1. It discovers runnable repo-audit targets, routes them to the right specialists, preserves blocked scopes separately, and consolidates everything into one concise report.

## Preflight
Before choosing specialists, verify the repo shape and look for these inputs:
- Angular workspace / frontend app files, especially `angular.json` or Angular package usage
- Angular test code or specs, especially `*.spec.ts`
- `.csproj` / `.sln` / backend code or other C# source
- C# test projects or test source

If the evidence is ambiguous, prefer the conservative path: mark the checkpoint blocked rather than silently narrowing the specialist set.

## Fixed routing
Use the same map every time, but apply it per discovered scope rather than once per repo:
- Angular scope → `angular-offline-migration` and `angular`
- Angular test scope → `angular-tests`
- .NET / C# scope → `csharp`
- C# test scope → `csharp-tests`

Treat Angular presence as a scope-level evidence check, not a free-form judgment call. If an Angular scope is present, emit an `angular` target for that scope; if Angular specs are present in that same scope, emit a separate `angular-tests` target.

If a C# project looks like a test scope by name or location but is an `OutputType Exe` project without `Microsoft.NET.Test.Sdk` or a recognized .NET test framework reference, keep it as a `csharp-tests` target but require the audit to flag it explicitly as a nonstandard/manual test harness.

If the evidence is missing or ambiguous, add a blocked item rather than guessing.

## Execution flow
1. Load the skill-owned workflow assets.
   - Read `chains/repo-audit.chain.json` and treat it as the canonical workflow definition for repo-audit.
   - Read `HANDBOOK.md` from this skill directory and use it as the execution handbook.
   - Treat these files as skill-owned assets. Do not expect the audited repo to contain copies of them, and do not mark their absence in the audited repo as blocked.
   - Prefer its dynamic workflow shape: discovery → target fanout → synthesis.
2. Discover the repo shape and emit structured targets.
   - Use flexible, pattern-based discovery (e.g. `bash`, `find`, `read`) to detect Angular, C#, and tests from evidence such as file names, extensions, and common paths.
   - Prefer pattern-based detection over hard-coded paths, so the flow adapts to different project layouts.
   - Normalize findings into:
     - `targets`: runnable specialist scopes
     - `blocked`: ambiguous or insufficient-evidence scopes
   - Each runnable target should include:
     - `id`
     - `domain`
     - `scopeLabel`
     - `rootPath`
     - `evidencePaths`
     - `skills`
     - `taskSummary`
     - `blockedNotes`
   - Each blocked item should include:
     - `domain`
     - `scopeLabel`
     - `reason`
     - `evidencePaths`
   - Reserve `blocked` for ambiguous or insufficient evidence that prevents creating a runnable target.
   - Do not use `blocked` for missing skill-owned assets, missing local dependencies such as `node_modules`, or other runner/environment limitations discovered after routing.
   - **Discovery guardrails (aggressive):**
     - Ignore heavy and irrelevant directories such as `node_modules`, `.git`, `.pi`, `.worktrees`, `dist`, `bin`, `obj`, and large test-output folders when scanning.
     - Focus searches on likely roots (e.g. top-level project folders, `src/`, `tests/`, `Pipelines/`) instead of recursively traversing the entire filesystem.
     - Limit directory exploration to **two levels deep** from each chosen root (for example, `find . -maxdepth 2` or equivalent); do not scan deeper trees as part of repo-audit v1.
     - Stop discovery for a stack once its presence/absence is clear and its key artifacts are located; do not exhaustively list every file.
     - Do not run heavy build or test commands (`pnpm`, `npm`, `ng build`, `ng test`, `dotnet build`, `dotnet test`) as part of discovery; repo-audit v1 inspects configuration and existing artifacts only.
     - This guardrail is discovery-specific. Specialist audits should still prefer configuration and artifact inspection, but repo-audit v1 should not rely on full build or test suite execution as normal validation.
3. Emit one target per specialist scope.
   - Do not collapse multiple Angular projects into one target.
   - Do not merge app/code scopes with test scopes.
   - Examples:
     - one Angular project with specs → one `angular` target + one `angular-tests` target
     - two Angular projects → at least two `angular` targets, plus separate `angular-tests` targets where specs exist
     - one backend plus one C# test project → one `csharp` target + one `csharp-tests` target
     - one WebApi plus multiple batch apps → one `csharp` target per independent project root or project group, not one collapsed backend target for the whole repo
4. Launch specialists via dynamic fanout.
   - Run one fresh-context `reviewer` per runnable target.
   - Keep each target's `skills` in the structured target data.
   - If the workflow runner cannot vary the `skill` field per target, provide a shared domain-skill bundle statically and instruct each specialist to load only `target.skills`.
   - Provide each subagent with a short, explicit task that enforces audit-only behavior and requests a concise, structured report.
   - Make it explicit in each task that the specialist is expected to return a **high-level overview and top risks**, not an exhaustive, line-by-line drilldown; the goal is a fast, decision-ready summary.
   - When specialists do not depend on one another, launch them in parallel via subagent dynamic fanout.
5. Consolidate the results into one checklist-first report.
   - Collect all specialist outputs.
   - Preserve discovery-to-synthesis coverage: if discovery emitted N runnable targets, synthesis should account for all N target audits or explicitly note any missing audit result.
   - Derive checklist statuses (pass / warn / fail / blocked) per checkpoint from the domain reports.
   - Build an executive summary from the top risks and blockers.
   - Attribute findings to their domains and include evidence paths (files, artifacts).
   - Preserve explicit per-target evidence in synthesis; do not collapse target findings to vague references such as "cited above" when concrete evidence paths are available.
6. Preserve blockers and missing-input notes.
   - Carry the `blocked` collection and missing-input explanations unchanged into the final report.

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

After discovery, repo-audit SHOULD fan out one `reviewer` per runnable target. Use `reviewer` by default for specialists.

Conceptual shape:

```jsonc
{
  "expand": {
    "from": { "output": "discovery", "path": "/targets" },
    "item": "target",
    "key": "/id",
    "maxItems": 24
  },
  "parallel": {
    "agent": "reviewer",
    "task": "Audit exactly one repo scope. Target: {target}. Load only target.skills. Return a short high-level overview: checklist, top risks, evidence paths, status.",
    "skill": ["angular-offline-migration", "angular", "angular-tests", "csharp", "csharp-tests"],
    "context": "fresh"
  },
  "collect": {
    "as": "scopeAudits"
  },
  "concurrency": 4
}
```

Guidelines for specialists:
- Use `reviewer` for repo-audit specialists; avoid heavy acceptance contracts that expect code changes or test runs.
- Each task MUST ask for a **high-level overview and top risks**, not an exhaustive drilldown.
- The structured target data MUST carry the target's required `skills`, even if the runner uses a shared static skill bundle.
- A moderate `concurrency` value keeps runs stable; sequential execution is acceptable if parallelism is unreliable.
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
