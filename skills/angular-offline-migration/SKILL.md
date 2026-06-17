---
name: angular-offline-migration
description: Use when migrating an Angular 16 workspace to Angular 21 offline, or when auditing an existing Angular 21 repo for final-state migration red flags.
---

# Offline Angular Migration

## Core rules
1. Inspect the current project before changing anything.
2. Upgrade only one Angular major version at a time.
3. Use the local migration handbook as the source of truth.
4. Prefer official Angular schematics and `ng update` over manual edits when Angular provides a migration.
5. Treat the test-runner modernization (Karma/Jasmine → Vitest) as a separate end-state step after the major-version hops.
6. Validate after every hop before continuing.
7. Treat Angular Material and DevExtreme as separate compatibility surfaces.
8. Assume older Angular 16 projects may already be partially migrated or inconsistent.

## Required workflow
For each version hop:
1. Record the current Angular, TypeScript, RxJS, Node, and builder state.
2. Check whether the app is standalone, NgModule-based, or mixed.
3. Update to the next major Angular version only.
4. Apply any official migrations for that hop.
5. Fix compiler, template, test, and runtime fallout.
6. Run the local verification checklist.
7. Only proceed when the hop is clean.

## Audit mode (Angular 21 final state)
Use this when the repo already claims to be migrated and you need to verify the final state.

Check for these red flags:
- package/config leftovers: direct `karma`, `jasmine`, `@angular-devkit/build-angular`, or `karma.conf.js` references
- resolved leftover chain: `pnpm why karma` or `pnpm why inflight` still returning a resolved package in a clean workspace
- test harness wiring: `ng test` still wired to the old builder or a stale bootstrap file
- `tsconfig.spec.json` not matching the final Vitest setup
- DevExtreme specs that still need stubbing/isolation because they fail under Vitest

Confirm these final-state signals:
- Angular packages are on the intended 21.x line
- build uses `@angular/build:application`
- tests use `@angular/build:unit-test`
- the app builds, tests, and lints cleanly
- Angular Material and DevExtreme behavior is intentional, documented, and not left half-migrated

If a red flag remains, either fix it or document it as an intentional exception.

## Verification checklist
A hop is not complete until all of the following are satisfied:
- build succeeds
- tests succeed or any failures are explained and tracked
- lint succeeds or issues are documented
- the application boots
- the main UI renders
- Angular Material works if present
- DevExtreme works if present
- no unresolved blockers remain for the next hop

## Special-case handling
### Angular Material
Check themes, typography, deprecated APIs, imports, and visible component behavior.

### DevExtreme / devextreme-angular
Check package compatibility, grid/editor rendering, bindings, validation, and runtime-only issues.
If the workspace migrates tests to Vitest, expect DevExtreme Angular to need extra isolation or stubbing until the package is compatible with the new runner.

### Lockfile hygiene
When cleaning dependency leftovers, validate `pnpm-lock.yaml` from a clean resolution state.
- Use a fresh temp copy of `package.json` or a fully cleaned workspace (`node_modules` removed) before deciding whether `karma` or `inflight` are real leftovers.
- `pnpm why karma` and `pnpm why inflight` should be empty in the clean workspace; any remaining `karma` mention should be optional peer metadata on `@angular/build`, not a resolved package.
- Treat `karma@6.4.4` and `inflight@1.0.6` as concrete leftovers only if they appear as resolved package entries.
- `inflight` is a high-signal migration check: if it still appears as a resolved package, the test-stack cleanup is not yet clean; if it disappears in the clean resolution, that is a strong sign the Vitest-only state is converging correctly.

### Partially migrated apps
Normalize mixed standalone/NgModule setups, old bootstrap patterns, and stale test infrastructure before attempting later version hops.

## Local references
- Offline handbook: `docs/plans/2026-06-17-angular-16-to-21-offline-migration-guide.md`
- Final test stack and cleanup details live in the handbook.

## Style
Be concise, version-specific, and checklist-driven. Do not rely on the internet. Do not skip ahead.
