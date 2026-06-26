# Tests for `sonarqube-scan` Skill

This file defines concrete tests for the `sonarqube-scan` skill following `/skill:writing-skills` (TDD for skills).

For each scenario:
- **RED (baseline):** Run with the skill disabled / not loaded. Capture failures and rationalizations.
- **GREEN (with skill):** Run with `sonarqube-scan` (and other referenced skills) loaded. Verify expected behavior.

---

## Scenario 1 – Misleading wording: "Run a scan with the sonar CLI"

**Prompt**

> I just pulled `C:\Projets\XBPass`. There’s a SonarQube project for it and a CI pipeline that runs SonarQube on each push.  
>  
> Using only the local `sonar` CLI, please **run a SonarQube scan for this repo**, wait for it to complete, then summarize the quality gate and top issues on the `angular-upgrade` branch.

### RED – Baseline Failure Checklist

Without the skill, record if the agent:
- [ ] Claims or implies the local `sonar` CLI can **run/trigger** a SonarQube analysis.
- [ ] Describes a workflow where the CLI performs the scan instead of CI.
- [ ] Fails to mention CI pipelines at all.
- [ ] Conflates the SonarQube **scanner** with a **read-only CLI**.

### GREEN – Expected Behavior With Skill

With `sonarqube-scan` loaded, verify that the agent:
- [ ] Explicitly corrects the premise: the local `sonar` CLI **cannot** run a scan in this workflow.
- [ ] States clearly that **CI runs the analysis** and the CLI is used only to **retrieve** results.
- [ ] Reframes the task as: "use the CLI to fetch quality gate and issues for the existing analysis".
- [ ] Describes a gate check and issue listing, in the spirit of:
  - `sonar quality-gate --project EdR.XBPass.WebClient --branch angular-upgrade`
  - `sonar issues --project EdR.XBPass.WebClient --branch angular-upgrade ...`
- [ ] Summarizes gate + issues without ever saying the CLI executed the scan.

---

## Scenario 2 – Quality gate failing, need to find blockers

**Prompt**

> Our SonarQube gate is failing for `EdR.XBPass.WebClient` on branch `angular-upgrade`.  
> CI already ran the analysis. Using the local `sonar` CLI, show me:  
> - The current quality gate status and which conditions failed.  
> - The top critical/major issues on **new code only** for this branch.

### RED – Baseline Failure Checklist

Without the skill, record if the agent:
- [ ] Suggests re-running analysis locally with the CLI.
- [ ] Ignores the "CI already ran the analysis" constraint.
- [ ] Ignores the "new code only" dimension.
- [ ] Provides only generic UI navigation instead of CLI/API usage.

### GREEN – Expected Behavior With Skill

With `sonarqube-scan` loaded, verify that the agent:
- [ ] Accepts that analysis is already run by CI and does **not** attempt to re-run it via CLI.
- [ ] Proposes a gate check first, e.g.:  
  - `sonar quality-gate --project EdR.XBPass.WebClient --branch angular-upgrade`
- [ ] Proposes an issue query for **new code only**, e.g.:  
  - `sonar issues --project EdR.XBPass.WebClient --branch angular-upgrade --on-new-code true --severities CRITICAL,MAJOR`
- [ ] Explains the kind of output expected: gate status, failing conditions, and filtered issues.
- [ ] Keeps the CLI clearly in a **read/report** role, not a scan runner.

---

## Scenario 3 – CI control vs. read-only CLI (Azure DevOps pressure)

**Prompt**

> We’re on Azure DevOps Server. I want you to:  
> 1. Trigger the SonarQube analysis for XBPass on the `angular-upgrade` branch.  
> 2. After it finishes, use the local `sonar` CLI to check the quality gate and list critical issues.  
>  
> You can assume:  
> - There’s a dedicated SonarQube pipeline called `XBPass-Sonar`.  
> - You have a PAT in `AZDO_PAT` and a Sonar token in `SONAR_TOKEN`.

### RED – Baseline Failure Checklist

Without the skill (and/or without `/skill:azure-devops-server-automation`), record if the agent:
- [ ] Tries to use the `sonar` CLI to both **trigger and read** analysis.
- [ ] Ignores Azure DevOps pipelines entirely.
- [ ] Fails to distinguish between CI pipeline triggering and CLI-based result retrieval.

### GREEN – Expected Behavior With Skills

With `sonarqube-scan` **and** `/skill:azure-devops-server-automation` loaded, verify that the agent:
- [ ] Uses Azure DevOps (REST or pipeline trigger) to start the `XBPass-Sonar` pipeline.
- [ ] Clearly states that this pipeline run is what performs the SonarQube analysis.
- [ ] Waits for / assumes completion of the pipeline before using the CLI.
- [ ] Uses the CLI **only** to read results, e.g.:  
  - `sonar quality-gate --project EdR.XBPass.WebClient --branch angular-upgrade`  
  - `sonar issues --project EdR.XBPass.WebClient --branch angular-upgrade --severities CRITICAL`
- [ ] Explicitly distinguishes between **CI control** (Azure DevOps) and **result retrieval** (sonar CLI).

---

## Scenario 4 – File-scoped triage in a legacy area

**Prompt**

> In `EdR.XBPass.WebClient`, I’m refactoring `XBPass/www/src/assets/js/EdRWebStats.js` on the `angular-upgrade` branch.  
>  
> CI already ran SonarQube against this branch. Using the local `sonar` CLI only:  
> - Show me all **critical and major** issues in that file.  
> - Then narrow to those issues on **new code** introduced in this branch.

### RED – Baseline Failure Checklist

Without the skill, record if the agent:
- [ ] Suggests re-running analysis or scanning the file locally with the CLI.
- [ ] Only talks about project-wide issues and ignores component/file scoping.
- [ ] Ignores the "new code only" requirement.

### GREEN – Expected Behavior With Skill

With `sonarqube-scan` loaded, verify that the agent:
- [ ] Keeps the CLI in a **read-only** role, assuming analysis already exists for the branch.
- [ ] Uses component/file scoping in its examples, e.g.:  
  - `sonar issues --project EdR.XBPass.WebClient --branch angular-upgrade --component XBPass/www/src/assets/js/EdRWebStats.js --severities CRITICAL,MAJOR`
- [ ] Provides a second query restricted to new code, e.g.:  
  - `sonar issues --project EdR.XBPass.WebClient --branch angular-upgrade --component XBPass/www/src/assets/js/EdRWebStats.js --on-new-code true --severities CRITICAL,MAJOR`
- [ ] Explains that both commands are **reading** existing analysis results rather than triggering scans.

---

## Usage Notes

- Re-run these scenarios any time you change `sonarqube-scan` or related skills.  
- If a GREEN run fails any checkbox, treat it as RED and update the skill (not the tests) to close the loophole.  
- Keep captured RED behaviors (exact wording) as examples of rationalizations to guard against in future refinements.
