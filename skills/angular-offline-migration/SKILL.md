---
name: angular-offline-migration
description: Use when migrating an Angular workspace offline or auditing a migrated repo for final-state red flags.
---

# Offline Angular Migration

Use this skill as the thin entry point. Keep operational detail in `HANDBOOK.md`.

## Rules
1. Inspect the current project before changing anything.
2. Upgrade only one Angular major version at a time.
3. Use `ng update` and official schematics whenever Angular provides them.
4. Validate after every hop before continuing.
5. Treat Angular Material and DevExtreme as separate compatibility surfaces.
6. Treat the test-runner modernization as its own end-state step.

## Workflow
1. Record the current Angular, TypeScript, RxJS, Node, and builder state.
2. Check whether the app is standalone, NgModule-based, or mixed.
3. Update to the next major Angular version only.
4. Apply the official migrations for that hop.
5. Fix compiler, template, test, and runtime fallout.
6. Run the verification checklist.
7. Proceed only when the hop is clean.

## Local references
- Handbook: `HANDBOOK.md`
- Keep all detailed guidance, version notes, red flags, and smoke checks in the handbook.
