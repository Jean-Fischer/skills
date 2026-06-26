---
name: csharp
description: Use when the user wants C# coding standards and implementation guidance for production code, including project structure, namespaces, nullability, constructors, XML docs, and general .NET conventions.
---

# C# Standards

## Purpose

Use this skill for general C# implementation work.

It applies to production code and covers the local conventions you should follow before you make structural or behavioral changes.

## Core rules

1. Read the existing codebase before changing anything.
2. Prefer the local repository style when it is already established.
3. Keep changes small and consistent with the current architecture.
4. Favor clarity over cleverness.
5. Treat nullability as part of the design, not just a compiler setting.
6. Avoid unnecessary abstractions and new dependencies.
7. Preserve the project’s current organization unless the task explicitly requires a refactor.
8. If a local convention conflicts with a generic rule, follow the local convention unless it is clearly unsafe.

## What this skill covers

- project and folder structure
- naming and member ordering
- namespaces
- constructors and dependency injection
- documentation
- nullability
- common language patterns
- validation and maintainability

## Workflow

When working on C# code:

1. Inspect the relevant files.
2. Identify the local convention before proposing changes.
3. Apply the smallest change that solves the task.
4. Check whether related tests or configuration need updates.
5. Validate the result before closing the work.

## Validation

Use the project’s existing commands when they exist.

If no local guidance exists, confirm at least:
- the code builds
- the affected tests pass
- any local analyzers or linting checks pass
- the change still matches nearby style

## References

See `HANDBOOK.md` for the fuller C# conventions, version notes, examples, and detailed project-layout guidance.
