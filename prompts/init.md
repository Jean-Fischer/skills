---
description: Bootstrap a project AGENTS.md from the repository itself
---
You are initializing repository instructions.

Goal: create or update a complete, accurate, agent-focused `AGENTS.md` at the project root using evidence from the repo. Treat `AGENTS.md` as the canonical file and align it with the public guidance at `https://agents.md/`. Only create `CLAUDE.md` if the user explicitly asked for Claude Code compatibility.

`AGENTS.md` is a README for coding agents: detailed technical context that complements, rather than replaces, the human-facing `README.md`.

Before writing, inspect the repo and gather only facts you can verify from files and commands:
- project purpose, architecture, and primary stack
- package manager, runtime, and environment requirements
- install, setup, test, lint, format, build, run, and watch commands
- database or service dependencies, if any
- directory layout, important entry points, and monorepo/subproject boundaries
- any existing agent instructions (`AGENTS.md`, `CLAUDE.md`, `.pi/SYSTEM.md`, `README*`, `CONTRIBUTING*`, package scripts, CI files)
- repo-specific safety rules, secrets handling, auth patterns, deployment notes, and things to avoid

Identify key workflows by checking the repo for:
- package manifests and scripts
- Makefiles or equivalent task runners
- CI/CD workflow files
- docs that define development, testing, or release expectations

Write `AGENTS.md` with these best practices:
- Keep it concise, high-signal, and actionable; prefer roughly `80–150` lines unless the repo genuinely needs more
- Prefer exact commands, paths, and file names over generic advice
- Use standard Markdown with clear headings
- Include only guidance agents need often; link or point to deeper docs instead of copying them wholesale
- Use the same terminology the repo already uses
- Do not invent commands, workflows, environments, or deployment steps that are not supported by files or validation
- Avoid duplicating `README` content unless the agent truly needs it to work effectively
- If existing instructions conflict, prefer the more specific / closer file and note the overlap
- For monorepos, note when additional nested `AGENTS.md` files may be appropriate and that the closest file takes precedence

Essential sections to cover when supported by evidence:
1. `# AGENTS.md` or `# Project Instructions`
2. Project overview
   - what the project does
   - architecture overview if relevant
   - key technologies/frameworks
3. Setup / install
   - dependency install
   - environment setup
   - database/service setup if applicable
4. Development workflow
   - start dev server
   - watch / hot reload
   - package manager specifics
5. Testing instructions
   - how to run all tests and focused subsets
   - test locations / naming conventions
   - coverage or verification expectations
6. Code style / conventions
   - language/framework conventions
   - lint / format rules
   - file organization, naming, and import/export patterns
7. Build and deployment
   - build commands and outputs
   - environment-specific configuration
   - CI/CD or deployment requirements if present
8. Security / safety / avoid rules
   - secrets handling
   - authentication / permissions patterns
   - risky actions to avoid
9. Repo-specific notes / troubleshooting
   - common gotchas
   - debugging hints
   - performance or workflow tips
10. Pull request / contribution expectations, if the repo documents them

If evidence is incomplete, ask exactly one clarifying question before writing.

When finished, report:
- files read
- assumptions made
- the final `AGENTS.md` path
- any noteworthy repo-specific rules discovered