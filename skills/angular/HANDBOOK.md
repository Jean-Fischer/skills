# Angular Handbook

## Scope

This handbook collects the fuller Angular implementation guidance that belongs with the `angular` skill.
It is for Angular application code, not test code.

The intent is to keep the skill light while still giving the agent enough detail to follow the project’s Angular conventions consistently.

---

## General guidance

Always start by checking the repository’s current Angular baseline.
Follow the local convention when the codebase already has one, especially for:
- component style
- file naming
- module vs standalone organization
- template style
- forms style
- state management style
- testing and validation commands

Do not force a modern pattern into a repository that has not adopted it yet unless the task is explicitly a modernization task.

When style guidance conflicts with a stable local pattern, keep the local pattern unless it is clearly harmful or broken.

---

## Project and file structure

Prefer a structure that keeps related Angular files together.
Typical examples:
- component TypeScript, template, and style files in the same folder
- services near the feature they support unless they are clearly shared
- tests next to the code under test

Avoid collecting unrelated UI code into a generic `tests` or `components` bucket when feature grouping is clearer.

If the project is small, a flatter layout is often easier to maintain.
Introduce deeper folders only when they improve clarity.

---

## Components and directives

Keep components and directives small and focused on presentation or UI behavior.
If code is really business logic, validation logic, or data transformation, consider moving it into a service or helper.

Good habits:
- one clear responsibility per component when possible
- keep lifecycle hooks simple
- keep event handlers named for what they do
- group Angular-specific members near the top of the class if the repo uses that pattern
- keep class internals readable and predictable

Prefer the component API style already used by the repository.
If the project is on a modern Angular baseline, use standalone components, `input()` / `output()`, and signal-based patterns where appropriate.

---

## Reactivity and state

Use the simplest state model that fits the feature.
If the project supports modern Angular features, prefer:
- signals for local component state
- `computed()` for derived state
- `effect()` only for real side effects
- `linkedSignal` / `resource` when the feature calls for them

Keep state transformations pure and easy to reason about.
Avoid hidden mutation and overly complex chains of derived state.

If the repository is still using observable-centric patterns, stay consistent with that style rather than mixing approaches inside the same feature.

---

## Templates

Keep templates simple.
Prefer readable, declarative templates over heavy inline logic.

If the project has adopted modern Angular control flow, prefer:
- `@if`
- `@for`
- `@switch`

Otherwise, follow the local template style.

Other useful principles:
- keep bindings direct and readable
- avoid business logic in templates
- prefer local helper methods or computed state when logic becomes hard to scan
- keep template expressions simple enough to understand at a glance

---

## Forms

Use the form style the project already favors.
If the repository is modern Angular, prefer signal-based forms where they are already adopted and appropriate.
Otherwise, prefer reactive forms over template-driven forms for most non-trivial cases.

General guidance:
- keep validation close to the form model
- keep form state and UI state easy to distinguish
- avoid burying validation rules inside the template if they belong in code
- keep form structure readable and testable

---

## Services and dependency injection

Design services around a single responsibility.
Keep them small enough that their purpose is obvious.

Prefer the DI pattern already used by the repository:
- constructor injection if the project uses it broadly
- `inject()` if the codebase has already standardized on it

Avoid turning services into large procedural containers.
If a service grows too much, consider splitting by responsibility.

---

## Routing, layout, and loading

Keep route definitions and navigation structure easy to follow.
Use lazy loading when the repository already uses it or when the feature boundary is clear.
Avoid route complexity that is not needed for the task.

When the app has layout components, keep layout concerns separated from feature concerns.

---

## Styling and accessibility

Prefer styles and bindings that match the project’s existing Angular approach.
Keep component styles colocated when that is the established pattern.

Accessibility should be treated as part of normal implementation, not as an afterthought.
Check:
- semantic HTML
- keyboard interaction
- focus behavior
- contrast
- ARIA usage only when needed

If the project uses Angular Material or another design system, follow the project’s established accessibility and styling patterns.

---

## Validation and change discipline

When changing Angular code:
1. read the nearby code first
2. identify the current project pattern
3. make the smallest useful change
4. update related template, style, service, or route files if needed
5. validate with the project’s build and test commands

If the requested change would require a broad framework migration, pause and confirm the intended direction.

---

## Version notes

Angular evolves quickly.
Keep these notes in mind:
- use the features the repository actually supports
- do not introduce APIs that the project version cannot use yet
- keep the handbook aligned with the repo’s Angular baseline
- if the project is mid-migration, preserve current conventions until the migration plan says otherwise
- if the workspace uses DevExtreme / `devextreme-angular`, treat upgrading both packages together as mandatory compatibility work; keep them on the same supported major line and move them to the repo’s supported 25.x or 26.x series before considering the Angular change complete
- verify DevExtreme widgets in the browser and under the test runner, because build success alone is not enough

---

## Good defaults

- prefer consistency over novelty
- prefer clarity over micro-optimizations
- prefer local repo conventions over generic Angular preferences when they conflict
- prefer small, reviewable changes

---

## Update this handbook when needed

Add repository-specific Angular decisions here when they become stable, such as:
- component organization conventions
- signals vs observables preferences
- forms conventions
- DI conventions
- routing conventions
- accessibility expectations
- styling strategy
