---
name: sonarqube-scan
description: Use when you need to run a SonarQube scan or query project status through the authenticated `sonar` CLI, wait for completion, and return a local report path or brief quality gate summary. If the installed CLI cannot do a full repo scan, fall back to the authenticated SonarQube API for project status and issues.
---

# SonarQube Scan

## Overview

Run the `sonar` command from the repository root and wait for it to finish. The CLI is already authenticated, so do not add login or token-management steps.

## When to Use

- Use this skill when a coding agent needs to trigger a SonarQube scan.
- Use this skill when the agent needs a result it can inspect later.
- Use this skill when the CLI may run for several minutes and must be awaited synchronously.

## Configuration Discovery

Search for the project key in pipeline YAML and workflow files first. Prefer an explicit repository setting such as `SonarQubeProjectKey`; if the value is present, use it. If the key cannot be found, ask the user for the missing project key and any other scan input required by the CLI.

## Known CLI Behavior

The installed `sonar` CLI may not support a full repository scan command. If that happens, use the authenticated API to fetch the project quality gate and issue data instead of pretending a scan was produced locally.

## File Selection

Do not send irrelevant files to SonarQube.

- Respect SCM-based ignore behavior so gitignored files stay out of analysis when the scanner supports it.
- Prefer explicit SonarQube exclusions for generated, vendored, and build output paths such as `node_modules`, `dist`, `bin`, `obj`, coverage output, and other temporary artifacts.
- If the repository already defines `sonar.exclusions`, reuse it instead of inventing a new file list.
- If the repository has a strict allowlist approach via `sonar.inclusions`, preserve that behavior.

## Scan Flow

1. Resolve the project key and any missing scan inputs.
2. Resolve file-selection rules so irrelevant and gitignored files are excluded before analysis.
3. Run `sonar` from the repository root and wait for it to finish.
4. Inspect the CLI output for a report path or artifact location.
5. If the CLI exposes a local file path, verify that path exists and return it.
6. If the CLI does not expose a path, inspect common scanner output such as `.scannerwork/report-task.txt` and treat that as the local artifact path when it exists.
7. If no local artifact can be confirmed, or the CLI cannot run a full repo scan, query SonarQube API data for a brief quality gate summary and the latest open issues.

## Result Handling

Return:

- the local report path when one is available,
- a brief pass/fail quality gate summary,
- the latest open issues when the CLI could not produce a scan artifact,
- and the CLI output needed to understand failures.

## Error Handling

If configuration discovery fails, ask the user instead of guessing. If `sonar` exits non-zero, surface the exit status and the raw command output. If both local artifact discovery and API fallback fail, report that failure clearly.
