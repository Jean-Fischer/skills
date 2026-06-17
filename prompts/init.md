---
description: Bootstrap a project AGENTS.md from the repository itself
---
You are initializing repository instructions.

Goal: create or update a concise, high-signal `AGENTS.md` at the project root using evidence from the repo. Treat `AGENTS.md` as the canonical file. Only create `CLAUDE.md` if the user explicitly asked for Claude Code compatibility.

Before writing, inspect the repo and gather only facts you can verify from files and commands:
- project purpose and primary stack
- package manager / runtime
- install, test, lint, format, build, run commands
- directory layout and important entry points
- any existing agent instructions (`AGENTS.md`, `CLAUDE.md`, `.pi/SYSTEM.md`, `README*`, `CONTRIBUTING*`, package scripts, CI files)
- repo-specific safety rules and things to avoid

Write `AGENTS.md` with these best practices:
- Keep it short and specific; aim for ~80–150 lines, not a handbook
- Prefer concrete commands and paths over generic advice
- Put always-needed guidance only; link out to deeper docs instead of copying them
- Include one clear section for commands, one for conventions, one for safety / avoid rules
- Use the same terminology the repo already uses
- Do not invent commands or workflows that are not supported by files or validation
- Avoid duplicating README content unless the agent truly needs it
- If existing instructions conflict, prefer the more specific / closer file and note the overlap

Suggested structure:
1. `# Project Instructions`
2. What this repo is
3. Setup / install
4. Common commands
5. Testing and verification
6. Code / file conventions
7. Safety / avoid rules
8. Notes for working in this repo

If evidence is incomplete, ask exactly one clarifying question before writing.

When finished, report:
- files read
- assumptions made
- the final `AGENTS.md` path
- any noteworthy repo-specific rules discovered