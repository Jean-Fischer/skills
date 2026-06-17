# Angular 16 → 21 Offline Migration Design

## Purpose
Create an offline migration system for airgapped Angular repositories that starts from Angular 16 and upgrades one major version at a time until Angular 21, while documenting what to change, how to validate each step, and how to handle real-world complications such as Angular Material, DevExtreme, and partially migrated codebases.

## Design Goals
- Support **offline use** in an environment without access to Angular migration docs.
- Keep the **Pi Skill small and portable**.
- Put the detailed migration knowledge in **one master markdown guide** to avoid confusion.
- Enforce a **version-by-version upgrade path**: 16 → 17 → 18 → 19 → 20 → 21.
- Include **verification checkpoints** after each hop so the user can prove the migration is safe before continuing.
- Handle **messy legacy realities**: mixed standalone/NgModule setups, incomplete previous migrations, Angular Material, and DevExtreme.

## Recommended Package Structure

### 1) Pi Skill: controller only
A small skill should explain how to use the handbook and enforce the migration rules.

Responsibilities:
- Require **one Angular major version at a time**.
- Direct the agent to inspect the project state before changing anything.
- Point to the offline guide as the source of truth.
- Remind the agent to validate after every hop.
- Call out special attention areas:
  - Angular Material
  - DevExtreme / devextreme-angular
  - partially migrated apps
  - old NgModule + standalone mixtures

Non-goals for the skill:
- Do not embed a long migration cookbook.
- Do not split the knowledge across many per-version files unless a later need forces it.

### 2) Master markdown guide: source of truth
One document should contain the full migration playbook.

Suggested path:
- `HANDBOOK.md`

## Master Guide Structure

### Top-level sections
1. **Scope and assumptions**
   - Target: Angular 16 → 21
   - Airgapped environment constraints
   - Recommended upgrade strategy: one major version at a time
   - Supported app types: standalone, NgModule-based, and mixed

2. **Migration policy**
   - Never skip major versions
   - Do not continue until the current hop is validated
   - Treat warnings as signals to investigate
   - Assume projects may already be partially migrated or inconsistent

3. **Pre-flight checklist**
   - Current Angular version
   - TypeScript / RxJS / Node / package manager state
   - App bootstrap style
   - Standalone vs NgModule usage
   - Presence of Angular Material and/or DevExtreme
   - Test/build tooling in use

4. **Version-by-version chapters**
   - Angular 16 → 17
   - Angular 17 → 18
   - Angular 18 → 19
   - Angular 19 → 20
   - Angular 20 → 21

5. **Special-case chapters**
   - Angular Material
   - DevExtreme / devextreme-angular
   - Partially migrated apps
   - Legacy NgModule cleanup
   - Standalone migration cleanup

6. **Validation and exit criteria**
   - Build passes
   - Tests pass or known failures are documented
   - App boots successfully
   - Main UI renders without runtime errors
   - No unresolved framework compatibility blockers remain

## Per-Version Chapter Template
Every Angular hop should follow the same template to reduce ambiguity.

### A. What changed in this version
Brief summary of the major framework and tooling expectations for that hop.

### B. Upgrade actions
Concrete actions to take:
- update Angular packages
- update related CLI/build tooling if needed
- update TypeScript/RxJS if required by the hop
- adjust app code where compiler or runtime errors appear
- fix third-party integration fallout

### C. What to check immediately
Commands and inspection steps:
- build
- unit tests
- lint
- app startup / smoke check
- template and compiler errors
- warnings that indicate follow-up work

### D. Common failure patterns
Typical issues to expect:
- dependency mismatches
- stale Angular compiler usage
- template syntax or strictness problems
- test setup breakage
- third-party library incompatibilities

### E. Exit criteria
The guide should explicitly state when the hop is considered done:
- build green
- tests green or exceptions documented
- no unresolved compatibility problems
- ready for the next version bump

## Special Handling Sections

### Angular Material
The guide should include a dedicated subsection for Material because migrations often need more than package bumps.

Include checks for:
- theme and typography
- deprecated APIs
- component import changes
- UI smoke tests for common controls

### DevExtreme / devextreme-angular
Treat DevExtreme as a separate compatibility track.

Include checks for:
- package compatibility against each Angular hop
- runtime rendering of widgets, not just compile success
- forms, validation, data loading, and grid/editor behavior
- wrapper/template binding issues

### Partially migrated apps
Older Angular 16 projects may already be half-upgraded or inconsistent.

The guide should help the agent identify and normalize:
- standalone + NgModule mixtures
- old bootstrap patterns
- stale polyfills or builder assumptions
- outdated test scaffolding
- legacy code that obscures migration failures

## Recommended Workflow
For each major version hop:
1. Inspect the current project state.
2. Upgrade only that single major version.
3. Fix compiler/build errors.
4. Fix Material / DevExtreme fallout.
5. Run validation commands.
6. Record any unresolved findings.
7. Only continue if the hop is clean.

## Validation Strategy
The guide should include a simple pass/fail matrix for each hop:
- **Compile/build**: passes
- **Tests**: passes or known failures recorded
- **Runtime boot**: application starts
- **UI smoke**: main route renders
- **Compatibility**: no unresolved blockers
- **Readiness**: safe to proceed to the next version

## Deliverables
### Required files
- Pi Skill file: short controller/orchestrator
- Master migration guide: one offline handbook

### Optional future files
- A project-specific example migration checklist
- A repo audit worksheet for large legacy apps
- A troubleshooting appendix if repeated failures emerge

## Implementation Notes
- Keep the skill intentionally short and reference the guide for details.
- Prefer a single master guide over many per-version files to reduce confusion.
- Write the guide in a way that can be copied into an airgapped environment without needing internet access.
- Favor explicit checklists and command blocks over narrative advice.

## Success Criteria
This design is successful if:
- the skill can be transferred alone and still tell the agent how to behave
- the guide contains enough information to perform the migration offline
- version hops are handled one at a time with validation gates
- Material, DevExtreme, and partially migrated apps are covered clearly
- no external docs are required during the migration
