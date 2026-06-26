# Angular 16 → 22 Offline Migration Guide

## Purpose
This handbook describes a repeatable offline migration path from Angular 16 to Angular 22.

It is written for airgapped environments where online Angular migration docs are unavailable. The recommended approach is always:

- move **one major Angular version at a time**
- apply the official migrations for that hop
- fix compile, template, and runtime fallout before continuing
- validate after each hop

## How to use this guide
For each hop:
1. Read the version section for the **next** Angular major only.
2. Upgrade `@angular/core` and `@angular/cli` to that major.
3. Let `ng update` run the official migrations.
4. Fix build/test/runtime issues.
5. Run the validation checklist.
6. Only then move to the next major version.

## General rules
- Do not skip versions.
- Do not mix several Angular majors in one change set.
- Do not rely on internet search during the migration.
- Prefer official Angular schematics over manual text edits.
- Treat warnings as migration signals, not noise.
- If the app is partly migrated already, normalize it before continuing.

## Baseline inspection checklist
Before the first hop, record:
- `ng version`
- `node --version`
- package manager version
- current `package.json` Angular versions
- whether the app is **standalone**, **NgModule-based**, or mixed
- whether Angular Material is installed
- whether DevExtreme / `devextreme-angular` is installed
- whether tests are Karma/Jasmine, Vitest, or both

## Recommended commands
Use the Angular CLI for updates:

```bash
ng update @angular/core@<major> @angular/cli@<major>
```

If a hop exposes framework migrations that Angular offers as schematics, apply them and verify immediately after each step.

If the project uses Angular Material, update it with the matching major when Angular recommends it:

```bash
ng update @angular/material@<major>
```

For DevExtreme, update `devextreme` and `devextreme-angular` together to the 25.2.x line and verify peer compatibility before continuing.

---

## Angular 16 → 17

### What to expect
Angular 17 removes support for Node.js 16 and requires newer TypeScript and `zone.js`.

Migration-relevant changes from the release notes and update guidance:
- Node.js 16 is no longer supported
- `zone.js` 0.14 is required
- TypeScript older than 5.2 is no longer supported
- control flow migration schematics are available
- block syntax is introduced (`@if`, `@for`, `@switch`)
- Angular 17 is the first version where the new built-in control flow becomes a major migration topic

### What to do
1. Make sure the environment is on a supported Node version for Angular 17.
2. Run:

```bash
ng update @angular/core@17 @angular/cli@17
```

3. Apply any migrations Angular offers.
4. If the app still uses legacy template control flow (`*ngIf`, `*ngFor`, `*ngSwitch`) and you want the built-in syntax, run the control flow schematic after the package update:

```bash
ng generate @angular/core:control-flow
```

5. Fix template diagnostics, strictness issues, and any package incompatibilities surfaced by the update.

### Watch for
- Node 16 failures in CI or local dev
- `zone.js` version mismatches
- template control flow compilation errors
- older TypeScript pinning the workspace below the supported range
- Material or third-party libraries that still assume older Angular compiler behavior

### Validate
- `ng build`
- `ng test`
- `ng lint`
- app boots in browser
- main route renders
- Material widgets still render, if present
- DevExtreme widgets still render, if present

### Fixture notes from the Angular 16 → 17 testbed
In the representative NgModule-based fixture we validated during authoring:
- `ng update @angular/core@17 @angular/cli@17 @angular/material@17` handled the Angular/Material hop cleanly.
- `extract-i18n` in `angular.json` was updated by the CLI from `browserTarget` to `buildTarget`.
- DevExtreme 24.1.7 continued to work with Angular 17, so it did not need an immediate version bump for this hop.
- Karma ran headless successfully after configuring Chrome binary auto-detection through `CHROME_BIN`.
- The sample fixture did not include an `ng lint` target; treat lint as mandatory only when the workspace provides it.
- DevExtreme emitted its normal license warning in tests, but the suite still passed.

---

## Angular 17 → 18

### What to expect
Angular 18 tightens the toolchain floor and expands the new reactive/runtime model.

Migration-relevant changes:
- Node.js 18.19.0 or newer is required
- TypeScript 5.4 or newer is required
- zoneless change detection appears as an experimental option
- incremental hydration is introduced as a public API direction
- fixture timing and change-detection behavior are more explicit
- control flow continues to mature

### What to do
1. Confirm the workspace Node version is in the supported range for Angular 18.
2. Run:

```bash
ng update @angular/core@18 @angular/cli@18
```

3. Review the update output for any migration tasks.
4. Fix compiler and template issues first.
5. If the workspace uses tests that depend on timing, re-check `whenStable`, `detectChanges`, and any async assertions.

### Watch for
- TypeScript 5.4 incompatibilities
- fixture timing changes in tests
- custom change-detection assumptions
- code that starts to assume zoneless behavior without being configured for it
- incremental hydration or deferred-block related diagnostics

### Validate
- `ng build`
- `ng test`
- `ng lint`
- browser smoke test
- Material smoke test
- DevExtreme smoke test

### Fixture notes from the Angular 17 → 18 testbed
In the representative NgModule-based fixture we validated during authoring:
- `ng update @angular/core@18 @angular/cli@18 @angular/material@18` updated the Angular/Material packages cleanly.
- Running the optional `use-application-builder` migration switched the build and serve targets to `@angular/build:application` and adjusted `angular.json`/`tsconfig.json` accordingly.
- The migration initially introduced `@angular/build` at the wrong major when run through a newer temporary CLI, so the fixture had to be corrected back to `@angular/build@18.2.21`.
- The application builder worked with the NgModule-based fixture, but the test target still needed `@angular-devkit/build-angular:karma` plus the matching devkit package.
- DevExtreme 24.1.7 remained compatible with Angular 18 in this fixture.

---

## Angular 18 → 19

### What to expect
Angular 19 is a major compatibility and defaults shift.

Migration-relevant changes:
- TypeScript versions below 5.5 are no longer supported
- directives, components, and pipes are standalone by default
- `ng update` handles the standalone-related migration steps
- `this.` in templates now refers to class members, not template context variables
- `Router.errorHandler` is removed
- `BrowserModule.withServerTransition` is removed
- `ComponentFixture` and `TestBed` timing behavior changed in ways that can affect async tests
- effect timing changes can shift when side effects run

### What to do
1. Confirm the workspace is on a supported Node version for Angular 19.
2. Run:

```bash
ng update @angular/core@19 @angular/cli@19
```

3. Let Angular perform the standalone migration it needs.
4. If the project is intentionally NgModule-based, make sure declarations that Angular marks as standalone are adjusted to remain compatible with the app architecture.
5. Fix template references that relied on `this.` for template variables.
6. Update router error handling patterns if they used the removed `Router.errorHandler`.
7. Revisit tests that depend on `whenStable`, `fakeAsync`, or automatic change detection.

### Watch for
- standalone default changes in older NgModule-based apps
- test flakes caused by effect timing or `ComponentFixture` behavior
- template expressions using `this.` in the wrong place
- router error handling and server-transition leftovers
- deprecated helper methods or test assumptions exposed by the new timing model

### Validate
- `ng build`
- `ng test`
- `ng lint`
- app boots
- routing still works
- Material and DevExtreme surfaces still render

### Fixture notes from the Angular 18 → 19 testbed
In the representative NgModule-based fixture we validated during authoring:
- `ng update @angular/core@19 @angular/cli@19 @angular/material@19` updated the Angular/Material packages and TypeScript cleanly.
- The core migration automatically added `standalone: false` to the NgModule-declared components, which is exactly what an intentionally NgModule-based app needs for Angular 19.
- `@angular/build` and `@angular-devkit/build-angular` both needed to move to 19.2.x for the build and test targets to remain healthy.
- The application continued to build and the Karma test suite continued to pass after the standalone-default migration.
- DevExtreme 24.1.7 continued to work with Angular 19 in this fixture.

---

## Angular 19 → 20

### What to expect
Angular 20 continues the signal/runtime modernization and raises the toolchain floor.

Migration-relevant changes:
- TypeScript 5.8 or newer is required
- Node.js 20.19+, 22.12+, or 24.0+ are supported for the current 20.x line
- `toSignal`, `toObservable`, `linkedSignal`, and `PendingTasks` are stable by this point in the release train
- `TestBed.tick()` exists for tests that need explicit control over change detection progression
- zoneless change detection remains a major migration topic
- extended diagnostics become more useful for `@for` and other template issues

### What to do
1. Confirm the Node and TypeScript versions satisfy Angular 20.
2. Run:

```bash
ng update @angular/core@20 @angular/cli@20
```

3. Review diagnostics related to control flow, signals, and templates.
4. Update tests that should prefer `TestBed.tick()` or more explicit async handling.
5. If you use new signal APIs, check for any deprecation or rename warnings in the update output.

### Watch for
- Node 18 or older toolchains still in the workspace
- TypeScript 5.7 or earlier
- `@for` track functions that are not invoked correctly
- host-binding type issues exposed by stronger checking
- test code that assumes the old `ComponentFixture` timing model

### Validate
- `ng build`
- `ng test`
- `ng lint`
- browser smoke test
- Material smoke test
- DevExtreme smoke test

### Fixture notes from the Angular 19 → 20 testbed
In the representative NgModule-based fixture we validated during authoring:
- `ng update @angular/core@20 @angular/cli@20 @angular/material@20` updated the Angular/Material packages, TypeScript, and zone.js cleanly.
- The workspace gained the CLI schematic defaults block that maintains previous generation behavior.
- `@angular/build` and `@angular-devkit/build-angular` both moved to 20.3.x and the application/test targets continued to work.
- The existing `TestBed`-based tests continued to pass without needing `TestBed.tick()` changes, because the fixture does not rely on the timing edge cases that Angular 20 tightens.
- DevExtreme 24.1.7 remained compatible with Angular 20 in this fixture.

---

## Angular 20 → 21

### What to expect
Angular 21 further tightens runtime and testing behavior and continues the signal-first direction.

Migration-relevant changes:
- TypeScript 5.9 or newer is required, with `< 6.0` support for the 21.x line
- Node.js 20.19+, 22.12+, or 24.0+ are supported for 21.x
- `NgModuleFactory` is removed
- test helpers and bootstrap behavior have additional shape changes
- `Router` and component-outlet related APIs continue to evolve
- signal and template diagnostics continue to improve

### What to do
1. Confirm the workspace is on a supported Node and TypeScript version for Angular 21.
2. Run:

```bash
ng update @angular/core@21 @angular/cli@21
```

3. Fix any remaining NgModule-era assumptions that depend on removed or tightened APIs.
4. Check test setup carefully, especially `TestBed`, `whenStable`, fixture auto-detection, and any custom platform-location assumptions.
5. Re-run the full validation suite and make sure no hidden runtime issues remain.

### Watch for
- `NgModuleFactory` usage
- test failures that only appear after timing behavior changes
- `bootstrapApplication` / bootstrap-context assumptions
- router or component-outlet behavior that changed during the release train
- outdated TypeScript or Node versions left behind from earlier hops

### Validate
- `ng build`
- `ng test`
- `ng lint`
- app boots
- main route renders
- Material smoke test passes
- DevExtreme smoke test passes

### Fixture notes from the Angular 20 → 21 testbed
In the representative NgModule-based fixture we validated during authoring:
- `ng update @angular/core@21 @angular/cli@21 @angular/material@21` updated the Angular/Material packages and TypeScript to the 21.x line cleanly.
- The core migration rewrote `src/main.ts` to pass `provideZoneChangeDetection()` through `bootstrapModule` via application providers.
- The build continued to work with the 21.x package set.
- The fixture later switched its unit tests from Karma/Jasmine to Vitest using `@angular/build:unit-test` and a local `runnerConfig` shim.
- DevExtreme 25.2.8 built successfully in the Angular 21 fixture once the initial budget was raised to 2MB, but the Vitest suite still hit the same directory-import ESM error from `devextreme-angular`.
- The Angular wrapper therefore still needs isolation or stubbing in Vitest; the 25.2.x line did not remove the runner issue in this fixture.
- The fixture still did not need any special router or `NgModuleFactory` remediation because it is intentionally simple.

---

## Angular 21 → 22

### What to expect
Angular 22 keeps the signal-first direction and raises the toolchain floor again.

Migration-relevant changes:
- TypeScript 6.0.0 or newer is required, with `< 6.1.0` support for the 22.x line
- Node.js 22.22.3+, 24.15.0+, or 26.0.0+ are supported for 22.x
- `ChangeDetectionStrategy.Eager` is added by the migration to preserve prior eager change-detection behavior because v22 makes `OnPush` the default
- existing templates, tests, and custom builders may need a quick sanity check after the TS 6 upgrade
- DevExtreme 25.2.x remains the validated compatibility line for this fixture

### What to do
1. Confirm the workspace is on a supported Node and TypeScript version for Angular 22.
2. Run:

```bash
ng update @angular/core@22 @angular/cli@22
```

3. Review the generated `ChangeDetectionStrategy.Eager` additions and decide whether they should stay or be intentionally replaced with `OnPush` in later refactors.
4. Fix compiler, template, and runtime fallout from the update.
5. Recheck DevExtreme warnings, budgets, and Vitest isolation if the fixture uses them.
6. Re-run the validation checklist before moving on.

### Watch for
- components that gained explicit eager change detection
- TypeScript 6 syntax or lib incompatibilities
- stale test harness assumptions after the CLI update
- build-budget noise from large third-party style bundles
- DevExtreme runtime-only issues that only show up under Vitest or in the browser

### Validate
- `ng build`
- `ng test`
- `ng lint`
- app boots
- main route renders
- Material smoke test passes, if Material is present
- DevExtreme smoke test passes

### Fixture notes from the Angular 21 → 22 testbed
In the representative fixture validated during authoring:
- `ng update @angular/core@22 @angular/cli@22` updated the Angular packages and TypeScript cleanly.
- The core migration inserted `ChangeDetectionStrategy.Eager` into `src/app/app.ts`.
- `tsconfig.app.json` gained extended-diagnostic suppressions for nullish-coalescing and optional-chaining checks.
- The app continued to use `@angular/build:application` for build and `@angular/build:unit-test` for tests.
- The workspace built, tested, and served successfully after the migration.
- DevExtreme 25.2.8 remained compatible with Angular 22 in this fixture.

## Final test-runner migration: Karma/Jasmine → Vitest
Once the Angular major hops are complete, finish the end-state modernization of the fixture's test stack:

1. Replace the Karma builder with `@angular/build:unit-test`.
2. Point `test` at Vitest (`runner: "vitest"`).
3. Add `runnerConfig` only when a local shim is required.
4. Remove `karma.conf.js` and any `@angular-devkit/build-angular` test references.
5. Keep `tsconfig.spec.json` on Vitest globals if the suite uses them.
6. Rework specs so they do not depend on Karma-only bootstrap files.
7. If DevExtreme Angular is part of the fixture, prefer stubbed selectors or other isolation in Vitest; the current 25.2.x line still trips the directory-import ESM path in this fixture.

### Suggested migration order
- change the builder first
- then fix the specs that rely on the old test harness
- then verify the app and tests are green together
- finally remove any stale Karma-era references from docs and scripts

## Angular 22 final-state audit checklist
Use this when the repo already claims to be finished.

### Red flags
- direct `karma`, `jasmine`, `@angular-devkit/build-angular`, or `karma.conf.js` references
- `pnpm why karma` or `pnpm why inflight` still returning a resolved package in a clean workspace
- `ng test` still wired to the old builder or a stale bootstrap file
- `tsconfig.spec.json` not matching the final Vitest setup
- DevExtreme specs that still need stubbing/isolation because they fail under Vitest

### Final-state signals
- Angular packages are on the intended 22.x line
- `@angular/build:application` is used for build
- `@angular/build:unit-test` is used for tests
- `pnpm why karma` and `pnpm why inflight` are empty in a clean workspace, aside from optional peer metadata on `@angular/build`
- build, tests, and lint all pass, or any missing lint target is documented intentionally
- any Material or DevExtreme exceptions are intentional and documented

---

## Special handling: Angular Material
When Angular Material is installed:
- update Material together with the Angular major when the update command recommends it
- check for deprecated APIs in buttons, inputs, dialogs, toolbar, form-field, and theming
- verify theme imports after every hop
- run a small visible smoke test for common controls
- keep using component harnesses for stable tests where possible

### Material smoke checks
- toolbar is visible
- button clicks work
- form fields accept input
- cards or dialogs render if they are part of the app

## Special handling: DevExtreme / devextreme-angular
When DevExtreme is installed:
- update `devextreme` and `devextreme-angular` together to the 25.2.x line
- check the package peer dependencies against the target Angular major
- expect runtime-only issues even when build succeeds
- verify grids, editors, and validation flows visually
- treat license or theme warnings as separate from migration failures
- if the app uses Vitest, keep a stub/isolation fallback available; 25.2.x still trips the directory-import ESM path in this fixture

### DevExtreme smoke checks
- grid renders at least one row
- editors accept input
- validation still triggers
- styling/theme assets load correctly

## Special handling: partially migrated apps
Older Angular 16 repositories may already be half-migrated.

Before starting the version hops, normalize these situations:
- mixed standalone + NgModule patterns
- old bootstrap styles
- stale polyfills or builder assumptions
- legacy test setup that no longer matches the current Angular version
- imports left behind after earlier migration attempts

If the app is very inconsistent, spend one stabilization pass reducing ambiguity before continuing the official version-by-version upgrade.

---

## Verification matrix
Use this as the exit gate for every hop:

| Check | Pass criteria |
| --- | --- |
| Build | `ng build` succeeds |
| Tests | `ng test` succeeds or failures are understood and tracked |
| Lint | `ng lint` succeeds or issues are logged |
| Boot | app starts in the browser |
| UI | main route renders |
| Material | Material controls render and interact correctly |
| DevExtreme | DevExtreme widgets render and behave correctly |
| Blockers | no unresolved blocker remains before the next hop |

## Suggested workflow summary
1. Inspect the workspace.
2. Upgrade one major Angular version.
3. Apply official migrations.
4. Fix compile/runtime fallout.
5. Validate.
6. Repeat.

## Notes for the offline skill
This guide is intended to be used with the Pi Skill at:
- `SKILL.md`

A small Angular 16 NgModule-based fixture with Material, DevExtreme, Vitest, and a real lint target is a good companion harness for validating that the migration guidance is actually workable.

If you keep the harness intentionally NgModule-based, disable `@angular-eslint/prefer-standalone` in the lint config so the lint target measures code quality without forcing the fixture to abandon its migration baseline.
