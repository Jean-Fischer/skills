# SonarQube Scan – CLI Handbook

Companion reference for the `sonarqube-scan` skill. This file assumes you have a **local `sonar` CLI** (or equivalent wrapper) that talks to your SonarQube server via its HTTP API.

> **Important:** This CLI is used as a **reader/reporting client**. It does **not** trigger new analyses. Analyses must be run by CI (build pipelines, dedicated SonarQube pipelines, etc.).

Because custom wrappers differ, commands below are **examples**. Always run `sonar --help` (or the equivalent for your wrapper) to confirm exact subcommands and flags, and adapt them to your local `sonar` wrapper.

---

## 1. Authentication & Configuration

Most SonarQube-aware CLIs need:

- **Server URL** – e.g. `https://sonarqube.yourcompany.local`
- **Token** – PAT with at least `Browse` permission on the project

Typical environment variables:

```bash
export SONAR_HOST_URL="https://sonarqube.yourcompany.local"
export SONAR_TOKEN="<your-token>"
```

Your wrapper may also support per-command flags (e.g. `--server`, `--token`). Prefer environment variables so commands stay shorter and safer for copy/paste.

---

## 2. Quick Quality Gate Check

### Purpose
Check whether a branch or PR currently passes the quality gate, with just enough detail to decide "can I merge/deploy?".

### Example command

```bash
# Example – adjust to your CLI's syntax
sonar quality-gate \
  --project EdR.XBPass.WebClient \
  --branch angular-upgrade
```

### Typical output (conceptual)

- `status`: `OK` | `ERROR` | `WARN`
- `conditions[]`: list of failed/passed conditions, e.g.
  - `new_coverage < 80%`
  - `new_duplicated_lines_density > 3%`
  - `new_critical_issues > 0`
- `measures`: headline metrics (coverage, bugs, vulnerabilities, code smells)

### Underlying API

- `GET /api/qualitygates/project_status?projectKey=...&branch=...`

---

## 3. Listing Issues for a Branch or PR

### Purpose
See concrete issues that are causing a failing gate or that you want to triage on a branch/PR.

### Example command – issues on a branch

```bash
sonar issues \
  --project EdR.XBPass.WebClient \
  --branch angular-upgrade \
  --severities CRITICAL,MAJOR \
  --types BUG,VULNERABILITY \
  --statuses OPEN,REOPENED
```

### Example command – issues on a PR / new code

```bash
sonar issues \
  --project EdR.XBPass.WebClient \
  --pull-request 1234 \
  --on-new-code true \
  --severities CRITICAL,BLOCKER
```

### Useful filters (conceptual)

- `--severities`: `INFO,MINOR,MAJOR,CRITICAL,BLOCKER`
- `--types`: `BUG,VULNERABILITY,CODE_SMELL,SECURITY_HOTSPOT`
- `--statuses`: `OPEN,REOPENED,CONFIRMED`
- `--on-new-code true`: restrict to issues in new/changed lines
- `--created-after`, `--created-before`: time windows for regressions

### Underlying API

- `GET /api/issues/search?projectKeys=...&branch=...`
- `GET /api/issues/search?projectKeys=...&pullRequest=...`

---

## 4. Component- or File-Scoped Issue Lists

### Purpose
Focus on the part of the code you are actually changing (module, directory, or file), instead of the entire project.

### Example – issues under a directory

```bash
sonar issues \
  --project EdR.XBPass.WebClient \
  --branch angular-upgrade \
  --component XBPass/www/src/assets/js \
  --severities CRITICAL,MAJOR
```

### Example – issues in a single file

```bash
sonar issues \
  --project EdR.XBPass.WebClient \
  --branch angular-upgrade \
  --component XBPass/www/src/assets/js/EdRWebStats.js
```

### Underlying API

- `componentKeys` or `componentRootUuids` parameters to `/api/issues/search`

This is especially useful when refactoring legacy areas: you can see how many critical/major issues remain localized to that component.

---

## 5. Author / Assignee Triage

### Purpose
See which issues are currently assigned to you (or your team) and prioritize fixes.

### Example – issues authored by a user

```bash
sonar issues \
  --project EdR.XBPass.WebClient \
  --branch angular-upgrade \
  --authors "j.fischer@edr.com" \
  --severities CRITICAL,MAJOR
```

### Example – issues assigned to a user

```bash
sonar issues \
  --project EdR.XBPass.WebClient \
  --branch angular-upgrade \
  --assignees "jfischer" \
  --statuses OPEN,REOPENED
```

### Underlying API

- `authors` / `assignees` filters on `/api/issues/search`

---

## 6. Measures and Trends

Some wrappers expose higher-level measures and trends. When available, use them to spot regressions quickly.

### Example – headline measures for project/branch

```bash
sonar measures \
  --project EdR.XBPass.WebClient \
  --branch angular-upgrade \
  --metrics coverage,bugs,vulnerabilities,code_smells,duplicated_lines_density
```

### Underlying API

- `GET /api/measures/component?component=...&metricKeys=...`

Trend/time series data is typically exposed via:

- `GET /api/measures/search_history?metrics=...&component=...`

Your CLI may surface trends as a separate subcommand (e.g. `sonar measures-history ...`).

---

## 7. CI Integration Patterns

The `sonarqube-scan` skill assumes **CI already ran the analysis**. Common integration patterns:

- **Dedicated SonarQube pipeline**  
  A pipeline whose only job is to build and analyze the project. Use `/skill:azure-devops-server-automation` to trigger it and then use the `sonar` CLI to read results.

- **Build pipeline with SonarQube step**  
  Your normal build/test pipeline includes a SonarQube analysis step. After it finishes, use the `sonar` CLI (possibly in a follow-up job) to summarize the quality gate and issues.

When running `sonar` from CI, feed it the same branch/PR identifiers that the analysis used (e.g. `$(Build.SourceBranchName)` in Azure DevOps) to ensure you are reading the correct scope.

---

## 8. Troubleshooting

- **Empty or unexpected results**  
  - Confirm that a recent analysis exists for the `projectKey` + `branch`/`pullRequest` you are querying.  
  - Verify that CI and CLI use the **same** identifiers.

- **Permission errors**  
  - Ensure `SONAR_TOKEN` has rights to browse the project.  
  - For branch/PR data, some instances require additional permissions.

- **CLI flag mismatches**  
  - These examples are conceptual. Always check `sonar --help` (or `sonar issues --help`, etc.) and adjust flags/names to match your wrapper.

If in doubt, reproduce a CLI call by inspecting the underlying HTTP request in the CLI's verbose/debug mode and mapping it to the documented SonarQube web APIs referenced above.
