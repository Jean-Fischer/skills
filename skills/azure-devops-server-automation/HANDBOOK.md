# Azure DevOps Server Automation Handbook

## Scope
This handbook covers Azure DevOps Server on-prem automation only.
Use the server's own base URL rather than cloud-only shortcuts.

Supported v1 surfaces:
- pull requests
- YAML pipelines
- variable groups

Non-goals:
- classic pipelines
- releases
- Azure DevOps CLI-first workflows
- GitHub App or CLA-bot style automation

---

## Authentication

Use a PAT from `AZDO_PAT`.

Typical request header pattern:

```http
Authorization: Basic base64(:$AZDO_PAT)
Content-Type: application/json
```

Notes:
- The username portion is blank.
- Keep the PAT outside the repo and out of prompts.
- Use the Azure DevOps Server base URL for your collection/project.

---

## Repo context resolution

When the command runs inside a Git repository, treat the remote URL as the default source of repo context.

Resolution order:
1. Explicit user input or command-line overrides.
2. A repo-local sidecar config, if your workflow defines one.
3. `git remote get-url origin` from the current repository.
4. Ask the user only if the remote URL is missing or cannot be parsed confidently.

For the common Azure DevOps Server clone URL shape, derive these values from the remote:
- server base URL
- collection
- project
- repository name

Prefer the remote URL as the canonical source instead of asking for the same four values on every run. If the remote does not look like an Azure DevOps URL, do not guess.

---

## Pull requests

### Create a pull request

```http
POST /{project}/_apis/git/repositories/{repositoryId}/pullrequests?api-version=7.1
```

Example:

```http
POST https://server/tfs/DefaultCollection/MyProject/_apis/git/repositories/{repositoryId}/pullrequests?api-version=7.1
```

Body fields you usually need:
- `sourceRefName`
- `targetRefName`
- `title`
- `description`
- `reviewers` when a reviewer list is needed

### Read a pull request

```http
GET /{project}/_apis/git/repositories/{repositoryId}/pullrequests/{pullRequestId}?api-version=7.1
```

Useful query flags:
- `includeCommits=true`
- `includeWorkItemRefs=true`

### List pull requests

```http
GET /{project}/_apis/git/repositories/{repositoryId}/pullrequests?api-version=7.1
```

Useful filters:
- `searchCriteria.status=active|completed|abandoned`
- `searchCriteria.sourceRefName=refs/heads/...`
- `searchCriteria.targetRefName=refs/heads/...`
- `searchCriteria.reviewerId=...`

### Add a comment thread

```http
POST /{project}/_apis/git/repositories/{repositoryId}/pullRequests/{pullRequestId}/threads?api-version=7.1
```

Example body:

```json
{
  "comments": [
    {
      "parentCommentId": 0,
      "content": "Please clarify this change.",
      "commentType": 1
    }
  ],
  "status": 1
}
```

Notes:
- A PR comment is a thread, not a standalone comment.
- Use `threadContext` when you need a file/line comment.

---

## YAML pipelines

### List pipeline metadata

```http
GET /{project}/_apis/pipelines?api-version=7.1
```

### Read one pipeline

```http
GET /{project}/_apis/pipelines/{pipelineId}?api-version=7.1
```

### Preview a run

```http
POST /{project}/_apis/pipelines/{pipelineId}/preview?api-version=7.1
```

Request body flags and fields:
- `previewRun: true`
- `resources`
- `templateParameters`
- `variables`
- `yamlOverride`

### Trigger a run

```http
POST /{project}/_apis/pipelines/{pipelineId}/runs?api-version=7.1
```

Request body fields:
- `previewRun`
- `resources`
- `templateParameters`
- `variables`
- `yamlOverride`
- `stagesToSkip`

Example run body:

```json
{
  "templateParameters": {
    "environment": "dev"
  },
  "variables": {
    "buildConfiguration": {
      "value": "Release"
    }
  }
}
```

Notes:
- Use `preview` when you only need the final YAML.
- Use `runs` when you actually want a queued pipeline run.
- Keep YAML-only concepts separate from classic build/release flows.

---

## Variable groups

### List variable groups

```http
GET /{project}/_apis/distributedtask/variablegroups?api-version=7.1
```

Useful filters:
- `groupName=...`
- `groupIds=...`
- `$top=...`
- `continuationToken=...`
- `queryOrder=IdAscending|IdDescending`
- `actionFilter=Use|Manage`

### Read one variable group

```http
GET /{project}/_apis/distributedtask/variablegroups?groupName={groupName}&api-version=7.1
```

If you already know the id, use the same list endpoint with `groupIds={groupId}`:

```http
GET /{project}/_apis/distributedtask/variablegroups?groupIds={groupId}&api-version=7.1
```

This is the documented by-id lookup form for the list endpoint.

### Create a variable group

```http
POST /_apis/distributedtask/variablegroups?api-version=7.1
```

### Update a variable group

```http
PUT /_apis/distributedtask/variablegroups/{groupId}?api-version=7.1
```

Notes:
- The create/update routes are documented at the organization level in the REST docs and intentionally omit the project segment.
- The list/read routes are project-scoped.
- The variable-group resource is still used from project pipelines, so make the route style explicit in your request examples.

Request body fields:
- `name`
- `description`
- `type`
- `providerData`
- `variables`
- `variableGroupProjectReferences`

Example body:

```json
{
  "name": "app-secrets",
  "description": "Variables used by the deploy pipeline",
  "type": "Vsts",
  "variables": {
    "apiUrl": {
      "value": "https://example.local"
    },
    "token": {
      "isSecret": true,
      "value": "***"
    }
  }
}
```

Caveats:
- Secret variables are protected resources.
- Variable groups used by YAML pipelines must be authorized for the pipeline.
- Azure DevOps CLI commands are not supported for Azure DevOps Server in this workflow.
- `isReadOnly` is a runtime flag, not a substitute for pipeline authorization.

---

## Quick mapping

- PR create/read/list/comment:
  - `/git/repositories/{repositoryId}/pullrequests`
  - `/git/repositories/{repositoryId}/pullRequests/{pullRequestId}/threads`
- YAML pipelines:
  - `/pipelines`
  - `/pipelines/{pipelineId}`
  - `/pipelines/{pipelineId}/preview`
  - `/pipelines/{pipelineId}/runs`
- Variable groups:
  - `/distributedtask/variablegroups`
  - `/distributedtask/variablegroups/{groupId}`

Keep the skill body short; use this handbook for the concrete routes and request shapes.