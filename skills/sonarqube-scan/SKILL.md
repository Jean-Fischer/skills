---
name: sonarqube-scan
description: Use when you need SonarQube analysis results for a repo after CI already ran — quality gate, coverage, issues, hotspots, or branch/PR status — and should query the local sonar CLI instead of browsing the UI.
---

# SonarQube Scan

## Overview
Use the authenticated `sonar` CLI as a **read/reporting client** for SonarQube. The actual code analysis runs on the SonarQube server, typically triggered by a CI pipeline. This skill focuses on reading the latest analysis results, quality gate status, and issues for a repository via the local CLI and, when needed, the SonarQube HTTP API.

## When to Use
- You need to inspect the current SonarQube quality gate and key issues for this repository.
- A CI pipeline already runs SonarQube analysis for this project (dedicated SonarQube pipeline or regular build pipeline).
- You prefer using the local `sonar` CLI to fetch results rather than browsing the SonarQube UI or calling the API by hand.

When you need to **configure or trigger** the CI pipeline that runs SonarQube, use your CI tooling directly. In Azure DevOps Server environments, see `/skill:azure-devops-server-automation` for pipeline discovery and triggering.

## Quick Reference – What the `sonar` CLI Can Retrieve
In this workflow the `sonar` CLI does **not** run a new analysis. It queries the SonarQube server for results of analyses that CI has already executed. Common retrieval capabilities include:

- **Quality gate status** for a project/branch/PR (PASS/FAIL, failed conditions, key metrics).
- **High-level measures** such as coverage, duplication, bugs, vulnerabilities, code smells, and security hotspots.
- **Issue lists** filtered by severity, type (BUG/VULNERABILITY/CODE_SMELL), status, tags, component path (file/folder), author/assignee, or time window.
- **Issue details** including rule, message, location (file + line), flows, and links back to the SonarQube UI for deeper inspection.
- **Contextual views** scoped to a branch, a pull request, or a specific component (module, directory, or file).

Exact flags, subcommands, and output formats depend on your local `sonar` CLI; keep those specifics in `HANDBOOK.md` and reference them from this skill when needed.

## Typical Usage Patterns
Use the `sonar` CLI in a few recurring ways:

1. **Quick health check before merging or releasing**  
   Query the quality gate for the target branch (or PR) and show key measures and the gate verdict. Use this when deciding whether a branch is eligible to merge or a release can proceed.

2. **Investigating a failing quality gate**  
   When the gate is red, fetch the list of blocking issues (e.g., critical vulnerabilities or new code smells above the threshold). Filter by severity and "on new code" to see what must be fixed to turn the gate green.

3. **File- or component-focused review**  
   When working in a specific area (e.g., a refactor in one module), list issues restricted to that component path. This keeps the signal focused on the code you are touching.

4. **Author/assignee triage**  
   Filter issues by author or assignee to review what is currently assigned to you or your team, or to check whether a change-set introduced new issues.

In all cases, the CLI acts as a structured, scriptable view over the same data you would see in the SonarQube UI. For concrete CLI examples of these patterns, see `HANDBOOK.md` sections 2 (Quick Quality Gate Check) and 3 (Listing Issues for a Branch or PR).

## Workflow
1. Ensure the CI pipeline that runs SonarQube analysis for this repository has completed (either a dedicated SonarQube pipeline or your default build pipeline).
2. From the repository root, run the authenticated `sonar` CLI to query the SonarQube server for the latest analysis of the relevant project/branch/PR. Make sure you use the same branch or pull-request identifiers that your CI pipeline used when running the analysis.
3. Optionally, check for any local artifact path or `.scannerwork/report-task.txt` associated with the last analysis when it exists on the current workspace.
4. If no local artifact is present or it lacks what you need, use authenticated SonarQube APIs (via the CLI or direct HTTP calls) to retrieve the quality gate status, measures, and issues.
5. Summarize the gate result, key metrics, and top open issues for the scope in question, and feed that back into your review, merge, or release decision.

## Common Mistakes
- **Expecting `sonar` to trigger a new scan:** In this workflow, the local CLI does not start a new analysis; it only retrieves results for analyses already run by CI on the SonarQube server.
- **Trying to manage CI from this skill:** Use your CI tooling (and `/skill:azure-devops-server-automation` in Azure DevOps Server) to configure or trigger the pipelines that perform the analysis.

## References
- Keep CLI flags, authentication options, example commands, file-selection guidance, fallback details, and troubleshooting in `HANDBOOK.md`.
