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
4. For every hop, align the Angular-adjacent package set to versions supported by that Angular major: `typescript`, `rxjs`, `zone.js`, Angular build/test tooling, Angular ESLint, and Angular Material when present.
5. Temporary stabilization may relax configuration only (tsconfig, lint config, test config, budgets, diagnostics) to restore green build, lint, and test results.
6. Review every temporary configuration relaxation after the first green pass; remove it when there is a trivial fix, otherwise keep it only as intentional, documented migration debt.
7. Validate after every hop before continuing.
8. Treat Angular Material and DevExtreme as separate compatibility surfaces.
9. Treat the test-runner modernization as its own end-state step.

## Workflow
1. Record the current Angular, TypeScript, RxJS, Node, builder, and Angular-adjacent package state.
2. Check whether the app is standalone, NgModule-based, or mixed.
3. Update to the next major Angular version only.
4. Align the Angular-adjacent packages required for that target major.
5. Apply the official migrations for that hop.
6. Fix compiler, template, test, and runtime fallout.
7. If needed, temporarily relax configuration only to restore green build, lint, and test results.
8. Review and remove trivial-fix exceptions before calling the hop clean.
9. Run the verification checklist.
10. Proceed only when the hop is clean.

## Local references
- Handbook: `HANDBOOK.md`
- Keep all detailed guidance, version notes, red flags, and smoke checks in the handbook.
