---
name: sonarqube-scan
description: Use when a repository needs a SonarQube scan or an authenticated quality-gate and issue summary from the local sonar CLI, especially when the scan may run for several minutes or fall back to API data.
---

# SonarQube Scan

## Overview
Run the authenticated `sonar` command from the repository root, capture a local artifact when one exists, and fall back to API data when the CLI cannot produce a full scan. Review the full issue set before summarizing the gate and latest open issues.

## When to Use
- You need to trigger or inspect a SonarQube scan.
- You need a local report path or a concise quality-gate summary.
- The CLI may not support a full repository scan.

## Workflow
1. Resolve the project key and exclusions from repository config.
2. Run `sonar` and wait for completion.
3. Confirm any local artifact path or `.scannerwork/report-task.txt`.
4. If no artifact exists, query the authenticated API for quality gate and open issues.
5. Report the gate, local path if present, and latest open issues.

## References
- Move CLI flags, file-selection guidance, fallback details, and troubleshooting into `HANDBOOK.md`.
