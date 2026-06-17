# Angular 16 Test Fixture Plan

## Purpose
Create a small Angular 16 application that acts as the migration testbed for the offline Angular migration skill.

The fixture must be realistic enough to expose migration problems, but small enough to remain understandable during repeated version-by-version upgrades.

## Fixture Characteristics

### Baseline framework
- Angular 16
- NgModule-based architecture
- CLI-generated workspace
- Karma test runner

### Included libraries
- Angular Material
- DevExtreme / devextreme-angular
- No backend dependencies
- No SSR
- No state management library

## Suggested App Shape
- `AppModule` bootstrap
- `AppRoutingModule`
- `HomeComponent`
- `MaterialDemoComponent`
- `DevExtremeDemoComponent`

## Recommended UI Coverage

### Angular Material
Use a small set of common controls:
- toolbar
- button
- input or form field
- optional card or dialog if useful

### DevExtreme
Use one representative widget:
- `dx-data-grid` with local in-memory data, or
- another common DevExtreme widget that renders something visible and interactive

Keep the configuration simple and local-only.

## Testing Coverage
The fixture should include Karma specs for:
- the shell or root component
- the Material area
- the DevExtreme area

Tests should verify:
- render success
- basic interaction
- no obvious runtime regressions

## Migration Validation Loop
For each Angular major version hop:
1. confirm the baseline is green on Angular 16
2. run the migration guidance for the next version only
3. fix compile and runtime issues
4. rerun build, test, lint, and smoke checks
5. record the result before moving on

## Intentional Failure Scenarios
The fixture should also support controlled negative tests:
- package mismatch
- Material compatibility break
- DevExtreme compatibility break
- incomplete migration state

These cases help validate whether the skill diagnoses failures correctly instead of skipping ahead.

## Scope Guardrails
Keep the fixture boring on purpose:
- no SSR
- no auth
- no complex forms
- no large shared libraries
- no advanced theming system
- no unnecessary custom infrastructure

## Success Criteria
The fixture is successful if it can be used to verify that the migration skill:
- upgrades one version at a time
- stays offline
- handles Material and DevExtreme
- does not require an overly complex sample app to prove the workflow
