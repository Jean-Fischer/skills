---
name: azure-devops-server-automation
description: Use when automating Azure DevOps Server on-prem pull requests, YAML pipelines, or variable groups via REST APIs with PAT authentication.
---

# Azure DevOps Server Automation

## Overview
Use this skill for thin, repo-local guidance on Azure DevOps Server automation.

Authenticate with `AZDO_PAT`.

## Scope
- Pull requests: create, read, comment
- YAML pipelines: read, preview, trigger
- Variable groups: read, create, update

## Guardrails
- Azure DevOps Server on-prem only
- No classic pipelines in v1
- No releases
- No Azure DevOps CLI dependency
- No GitHub App or CLA-bot framing

## Workflow
1. Identify the server base URL, collection/project, and repository or pipeline IDs.
2. Use the REST endpoint that matches the surface.
3. Keep secrets in `AZDO_PAT` and use PAT-based auth.
4. Stay within the supported v1 surfaces above.

See `HANDBOOK.md` for exact REST routes, request shapes, and caveats.