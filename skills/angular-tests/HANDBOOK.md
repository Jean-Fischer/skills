# Angular Test Handbook

## Scope

This handbook collects the fuller Angular test guidance that belongs with the `angular-tests` skill.
It is for Angular unit and integration tests, not end-to-end automation.

The aim is to keep the skill light while still giving the agent enough detail to write stable, user-centric Angular tests.

---

## General testing guidance

Start by matching the repository’s existing testing baseline.
Follow the local conventions for:
- test runner
- assertion library
- naming style
- fixture setup
- mocking style
- async style
- file naming

If the repository has a working test pattern, keep it.
Do not introduce a new test style just because it is modern or popular.

---

## What Angular tests should verify

Prefer tests that prove the component or service behavior from the outside.
Tests should answer:
- what the user sees
- what the component/service should do
- what should happen for valid and invalid input
- what the important edge cases are

Avoid tests that depend too much on implementation details like:
- private method calls
- internal class structure
- incidental DOM structure
- overly precise call counts when the behavior does not require them

---

## Test file and class organization

Keep tests close to the code under test.
If the repository uses `.spec.ts`, follow that.
If it uses another naming style, match the local style.

Good habits:
- one clear subject under test per spec file when practical
- group tests by behavior
- keep shared setup visible
- keep helper methods small and focused
- do not pile unrelated cases into one large spec class

If the repo already uses page objects or a shared test base, keep using that pattern.

---

## Component tests

Prefer tests that interact with the component the way a user would.
If the project uses Angular Material or CDK harnesses, prefer harnesses where they make the test more stable and readable.

General guidance:
- use `TestBed` for component setup when needed
- keep component fixture setup clear
- avoid brittle `querySelector` tests when a more stable API exists
- test visible outcomes rather than internal implementation details

If a component is mostly presentational, keep the test focused on rendering and interaction outcomes.
If a component coordinates a lot of behavior, split tests by scenario.

---

## Service tests

Service tests should focus on the public API of the service.
Mock only the dependencies that need isolation.
Avoid over-mocking internal logic that should be tested through the service itself.

If HTTP is involved, prefer HTTP-level testing instead of mocking low-level internals.

---

## HTTP and router testing

Use Angular’s test helpers when the feature involves HTTP or routing.
Prefer:
- `HttpTestingController` for HTTP interactions
- router test helpers or router harnesses when the navigation behavior matters

Keep route-based tests outcome-focused.
Do not mock router behavior so heavily that the test no longer reflects real routing behavior.

---

## Harnesses

When the repository uses Angular CDK or Material components, harnesses are usually the most stable option.
They help the test interact with the component like a user instead of depending on the DOM shape.

Use harnesses when:
- the component already has a harness
- the test is brittle with raw DOM queries
- the test benefits from readable interactions like click, select, or getText

Keep harness usage simple and avoid exposing internal implementation details through the test.

---

## Async testing

Be explicit with async behavior.
Use the async strategy that matches the repository’s Angular baseline.

General guidance:
- await asynchronous interactions
- keep change-detection flow understandable
- avoid timing guesses and arbitrary waits
- make stability checks explicit when the feature requires them
- keep tests deterministic

If the repository uses zoneless patterns or signal-driven updates, match that style instead of mixing timing models.

---

## Mocking and doubles

Use the lightest test double that makes the test clear.
Prefer:
- stubs
- simple fakes
- service doubles
- harnesses
- HTTP test utilities

Avoid overly complex mocking when the actual behavior is easier to express directly.
Use mocks when interaction verification is genuinely important, not as a default habit.

---

## Inputs, outputs, and state

Test component inputs and outputs in a way that matches how the component is used.
If the project uses signals or modern Angular inputs, keep the test aligned with that style.

For component state:
- verify what changes in the rendered output or public behavior
- keep assertions aligned with user-observable results
- avoid testing implementation details of reactive state unless that state is itself the public contract

---

## Data and fixtures

Keep test data as small as possible.
Use the minimum setup needed to prove the behavior.
Avoid large shared fixtures unless they are truly reusable and easy to understand.

If a fixture becomes hard to read, simplify it.

---

## Stability rules

Tests should be repeatable and easy to diagnose.
Be careful with:
- time
- randomness
- shared global state
- order dependence
- browser-only assumptions in unit tests
- brittle assertions on incidental DOM structure

If a test becomes flaky, simplify the setup before adding more logic.

---

## Validation and change discipline

When changing Angular tests:
1. inspect the nearby test style
2. match the repository’s Angular testing pattern
3. add the smallest test that proves the behavior
4. prefer stable, user-centric assertions
5. validate the result

If the change requires a bigger test infrastructure shift, confirm the direction first.

---

## Version notes

Angular testing evolves quickly.
Keep these notes in mind:
- use the testing APIs the repository actually supports
- keep async behavior aligned with the project’s Angular baseline
- preserve existing stable patterns when the repo is mid-migration
- update this handbook when a newer project-wide testing convention becomes stable

---

## Good defaults

- prefer behavior over internals
- prefer readability over cleverness
- prefer stable harnesses and utilities over brittle DOM scraping
- prefer consistency with the repo over generic testing advice

---

## Update this handbook when needed

Add repository-specific Angular test decisions here when they become stable, such as:
- runner choice
- assertion style
- mocking style
- harness usage
- router testing pattern
- HTTP testing pattern
- async handling convention
