---
name: repo-audit
description: Use when auditing or triaging a local repo or codebase — for example, when the user says "review this repo", "inspect this codebase", "repo-wide health check", or "triage findings".
---

# Repo Audit

## Overview

`repo-audit` is an **orchestrator skill** for repository-wide audits.

When active, it helps an agent:
- Discover the repo shape from evidence (files, artifacts) instead of assumptions.
- Decide which technology stacks and analysis tools are present.
- Read and follow the local workflow asset at `chains/repo-audit.chain.json` when available.
- Dispatch anonymous subagents (generic `reviewer` or `worker` agents) with domain skills enabled at runtime.
- Aggregate the stack-specific reports into one concise, checklist-first summary.

In v1, `repo-audit` is **audit-only**: specialists and the orchestrator MUST NOT edit files or implement fixes.

## When to Use

Use this skill when:
- A human asks for a repo-wide health check or "review this repo".
- You need to triage findings across the whole codebase (Angular + backend + tests + static analysis).
- You want a single, consolidated report that summarizes top risks and blockers.

Do NOT use this skill when:
- The request is limited to a single file, component, or small feature.
- You are implementing fixes or refactors rather than auditing.
- You only need to inspect one specialist domain (e.g. Angular tests only) — in that case, use the domain skill directly.

## Core Pattern (Orchestration)

`repo-audit` defines this orchestration pattern:

1. **Load the skill-owned workflow assets first**
   - Read `chains/repo-audit.chain.json` and treat it as the canonical workflow definition for repo-audit.
   - Read `HANDBOOK.md` from this skill directory and use it as the execution handbook.
   - Treat these files as skill-owned assets. Do not expect the audited repo to contain copies of them, and do not mark their absence in the audited repo as blocked.
   - Prefer executing that workflow shape with `subagent(...)` when `pi-subagents` is available.
   - If the workflow cannot be executed directly, follow the same phases manually in the parent session.

2. **Discover the repo shape and emit structured targets**
   - Use flexible, pattern-based discovery (e.g. `bash`, `find`, `read`) to detect Angular, C#, and tests from evidence such as file names, extensions, and common paths.
   - Prefer pattern-based detection over hard-coded paths so the flow adapts to different project layouts.
   - Discovery should normalize findings into a structured target list plus a separate blocked collection.
   - Each runnable target should represent exactly one specialist scope and include: `domain`, `scopeLabel`, `rootPath`, `evidencePaths`, `skills`, `taskSummary`, and `blockedNotes`.
   - Use separate targets for app/code scopes and test scopes. Example: an Angular project yields one `angular` target, and if specs are present, a separate `angular-tests` target.
   - If evidence for a technology or tool is ambiguous or insufficient to produce a runnable target, add it to the blocked collection rather than guessing.
   - Do not use the blocked collection for missing skill-owned assets, missing local dependencies, or other runner/environment limitations discovered after routing.
   - See `HANDBOOK.md` for detailed discovery guardrails (ignored directories, search roots, and command constraints).

3. **Apply the routing map by embedding skills into targets**
   - Angular scope → `skills: ["angular-offline-migration", "angular"]`
   - Angular test scope → `skills: ["angular-tests"]`
   - .NET / C# scope → `skills: ["csharp"]`
   - C# test scope → `skills: ["csharp-tests"]`
   - If a C# project looks like a test scope by name or location but is an `OutputType Exe` project without `Microsoft.NET.Test.Sdk` or a recognized .NET test framework reference, still treat it as a `csharp-tests` target but require the specialist to flag it explicitly as a nonstandard/manual test harness rather than assuming automated test coverage.
   - Mixed repos are not a reason to skip any verified stack.
   - If discovery finds multiple independent scopes for the same domain, emit multiple runnable targets rather than collapsing them into one broad review.

4. **Launch specialists via dynamic fanout**
   - Fan out one fresh-context subagent per runnable target using a generic agent such as `reviewer`.
   - Keep each target's embedded `skills` in the structured target data and make them explicit in the specialist task.
   - When the workflow runner cannot vary the `skill` field per target, provide a shared domain-skill bundle statically and instruct each specialist to load only the target's required skills.
   - Use the target's `scopeLabel`, `rootPath`, `evidencePaths`, and `taskSummary` to keep each specialist narrowly scoped.
   - The handbook's "do not run heavy build/test commands" rule is a discovery guardrail. Specialist audits should still prefer config and artifact inspection, and repo-audit v1 should not rely on full build or test suite execution.
   - Provide each subagent with a short, explicit task that enforces audit-only behavior and requests a concise, structured report.
   - When specialists do not depend on one another, launch them in parallel.

5. **Aggregate into a single report**
   - Collect all specialist outputs.
   - Preserve coverage from discovery through synthesis: if discovery emitted N runnable targets, synthesis should account for all N target audits or explicitly note any missing audit result.
   - Derive checklist statuses (PASS / WARN / FAIL / BLOCKED) per checkpoint from the domain reports.
   - Build an executive summary from the top risks and blockers.
   - Attribute findings to their domains and include evidence paths (files, artifacts).
   - Preserve explicit per-target evidence in synthesis; do not collapse target findings to vague references such as "cited above" when concrete evidence paths are available.
   - Preserve the separate blocked collection and missing-input notes unchanged.

For exact preflight inputs, discovery guardrails, and the required report shape, follow `HANDBOOK.md`.

## Quick Reference

Domain skills used by `repo-audit`:
- Angular target: `/skill:angular-offline-migration` and `/skill:angular`
- Angular test target: `/skill:angular-tests`
- C# target: `/skill:csharp`
- C# test target: `/skill:csharp-tests`

Local workflow asset:
- Canonical orchestration: `chains/repo-audit.chain.json`

## Common Mistakes

- **Choosing specialists without discovery** – Always inspect the repo first; use evidence, not assumptions.
- **Guessing when evidence is ambiguous** – Mark checkpoints as blocked instead of inferring missing stacks.
- **Treating missing skill assets as repo blockers** – `HANDBOOK.md` and `chains/repo-audit.chain.json` belong to this skill; do not expect copies in the audited repo.
- **Skipping stacks in mixed repos** – Angular + C# + tests + static analysis should all be checked when evidence exists.
- **Collapsing multiple scopes into one review** – If discovery finds two Angular projects, several test roots, or multiple C# project roots, emit separate runnable targets and fan out one specialist per scope.
- **Editing code or pipelines during audit** – v1 is audit-only; report findings and next actions, do not remediate.
- **Re-running specialists too often** – Only re-run a specialist when its source artifact has changed in a meaningful way.
