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

1. **Discover the repo shape**
   - Use flexible, pattern-based discovery (e.g. `bash`, `find`, `read`) to detect Angular, C#, and tests from evidence such as file names, extensions, and common paths.
   - Prefer pattern-based detection over hard-coded paths so the flow adapts to different project layouts.
   - If evidence for a technology or tool is ambiguous, mark that checkpoint as blocked rather than guessing.
   - See `HANDBOOK.md` for detailed discovery guardrails (ignored directories, search roots, and command constraints).

2. **Apply a fixed routing map**
   - Angular present → run Angular specialists.
   - Angular test code present → run Angular test specialists.
   - .NET / C# present → run C# specialists.
   - C# test code present → run C# test specialists.
   - Mixed repos are not a reason to skip any verified stack.

3. **Launch specialists via subagents**
   - For each required domain, start a fresh-context subagent run using a generic agent such as `reviewer` or `worker`.
   - Attach the appropriate skills at runtime via the `skill` field, for example:
     - Angular: `skill: ["angular-offline-migration", "angular"]`
     - Angular tests: `skill: ["angular-tests"]`
     - C#: `skill: ["csharp"]`
     - C# tests: `skill: ["csharp-tests"]`
   - Provide each subagent with a short, explicit task that enforces audit-only behavior and requests a concise, structured report.
   - When specialists do not depend on one another, launch them in parallel.

4. **Aggregate into a single report**
   - Collect all specialist outputs.
   - Derive checklist statuses (PASS / WARN / FAIL / BLOCKED) per checkpoint from the domain reports.
   - Build an executive summary from the top risks and blockers.
   - Attribute findings to their domains and include evidence paths (files, artifacts).
   - Preserve blocked checkpoints and missing-input notes unchanged.

For exact preflight inputs, the fixed routing map, and the required report shape, follow `HANDBOOK.md`.

## Quick Reference

Domain skills used by `repo-audit`:
- Angular: `/skill:angular-offline-migration` and `/skill:angular`
- Angular tests: `/skill:angular-tests`
- C# backend: `/skill:csharp`
- C# tests: `/skill:csharp-tests`

## Common Mistakes

- **Choosing specialists without discovery** – Always inspect the repo first; use evidence, not assumptions.
- **Guessing when evidence is ambiguous** – Mark checkpoints as blocked instead of inferring missing stacks.
- **Skipping stacks in mixed repos** – Angular + C# + tests + static analysis should all be checked when evidence exists.
- **Editing code or pipelines during audit** – v1 is audit-only; report findings and next actions, do not remediate.
- **Re-running specialists too often** – Only re-run a specialist when its source artifact has changed in a meaningful way.
