---
name: checkmarx-high-critical-findings
description: Use when triaging the latest local Checkmarx scan artifact — especially SARIF or normalized findings that include high and critical issues, hotspot clusters, or a repo-local remediation handoff.
---

# Checkmarx High Critical Findings

## Overview
Use the latest local Checkmarx result to build a repo-local remediation handoff. The scan output should account for the full finding set before prioritizing critical, high, and repeated hotspot issues.

## When to Use
- You have one local repository or project.
- You want the latest scan artifact, not historical results.
- You need to triage the complete finding set, not just a subset.
- High and critical issues need to be surfaced first.

## Workflow
1. Resolve the project name from local config or pipeline files.
2. Run the repo-local helper that scans tracked, filtered files and exports SARIF.
3. Normalize the SARIF into the distilled JSON artifact.
4. Review the full finding set from the artifact.
5. Fix findings in this order:
   - critical
   - high
   - clustered hotspots / repeated rules
6. Reuse the latest artifact while making local fixes.
7. Rerun only after a meaningful batch of changes or before handoff.

## References
- Helper: `cx-filtered-scan.mjs`
- Normalizer: `normalize-sarif.mjs`
- Move scan-command details, blacklist rules, project-name resolution, and artifact schema into `HANDBOOK.md`.
