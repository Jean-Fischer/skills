---
name: csharp-tests
description: C# test standards and test-writing guidance for test code. Use when writing, reviewing, refactoring, or stabilizing C# tests, including xUnit, NSubstitute, test naming, fixtures, async tests, mocking, and test organization.
---

# C# Test Standards

## Purpose

Use this skill for C# test code.

It covers the conventions you should follow when adding, changing, or reviewing tests so the test suite stays readable, stable, and behavior-focused.

## Core rules

1. Test behavior rather than implementation details.
2. Keep tests clear and intention-revealing.
3. Follow the repository’s existing test framework and library choices.
4. Prefer one behavior per test when possible.
5. Keep setup small and visible.
6. Avoid unnecessary mocking.
7. Do not assert on logs unless logging is the subject of the test.
8. Keep the suite consistent across the repository.

## What this skill covers

- test naming
- organization and class structure
- setup and teardown patterns
- mocking and substitutes
- async behavior
- assertions
- test data
- stability and flakiness prevention

## Workflow

When working on C# tests:

1. Inspect the existing test style in the repository.
2. Match the framework and naming pattern already in use.
3. Add or update tests that prove the intended behavior.
4. Remove brittle or redundant assertions if needed.
5. Check that the test still reads clearly when you are done.

## Validation

Use the project’s existing test command where possible.

If there is no local convention, confirm:
- the test project compiles
- the target tests pass
- the test behaves as expected after the code change
- the result remains stable on repeat runs

## References

See `HANDBOOK.md` for framework-specific conventions, naming rules, setup patterns, and examples.
