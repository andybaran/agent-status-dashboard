# CLAUDE.md — Agent Status Dashboard Integration

> **Copy this file into your project and adapt it.**
> It teaches Claude how to report status to the Agent Status Dashboard
> so you get real-time visibility into multi-agent workflows.

## Dashboard Status Reporting

A dashboard is running at `DASHBOARD_URL` (default: `http://localhost:5050`).
You **must** report your status at every task boundary.

### API

```bash
POST {DASHBOARD_URL}/api/update/{agent_name}/{status}
```

**Valid statuses:** `working`, `waiting`, `completed`, `idle`, `blocked`, `error`

**Optional query parameters:**

| Parameter | Description |
|-----------|-------------|
| `task` | Name/description of the current task |
| `task_url` | URL to the task (e.g. GitHub issue, Jira ticket) |
| `model` | AI model being used (e.g. Claude Sonnet 4.5, GPT-4.1) |

Task info is displayed on the agent's dashboard card. If `task_url` is provided,
it renders as a clickable link. Model is displayed below the task in italic.
All three carry forward until replaced.

### Rules

1. **Always report `working`** before starting any task.
2. **Report `waiting`** when blocked on user input, another agent, or an external dependency.
3. **Report `completed`** when your task finishes successfully.
4. **Report `error`** if your task fails — then describe the failure.
5. **Never leave status as `working`** when you are done. Agents stuck in `working`
   are marked stale after 10 minutes.

### Agent Name

Use a consistent, descriptive `Title Case` name with spaces.
Names are normalized server-side (hyphens/underscores become spaces, acronyms
like UI, API, AWS are preserved). Pick one name and use it for the entire session.

Good: `Research Agent`, `Code Review Agent`, `Terraform Agent`
Bad: `agent1`, `my-agent`, `Claude`

### How to Report (curl)

```bash
# Starting work
curl -s -X POST http://localhost:5050/api/update/My%20Agent/working

# Starting work on a specific task
curl -s -X POST "http://localhost:5050/api/update/My%20Agent/working?task=Implement+login+form"

# Starting work on a GitHub issue
curl -s -X POST "http://localhost:5050/api/update/My%20Agent/working?task=Fix+auth+bug&task_url=https://github.com/org/repo/issues/42"

# Report the model you are using
curl -s -X POST "http://localhost:5050/api/update/My%20Agent/working?task=Fix+auth+bug&model=Claude+Opus+4.6"

# Waiting on dependency
curl -s -X POST http://localhost:5050/api/update/My%20Agent/waiting

# Done
curl -s -X POST http://localhost:5050/api/update/My%20Agent/completed

# Something broke
curl -s -X POST http://localhost:5050/api/update/My%20Agent/error
```

### Workflow Pattern

```
Start task   →  POST .../working?task=My+Task+Name
  ↓
Do work...
  ↓
Need input?  →  POST .../waiting  →  (get input)  →  POST .../working
  ↓
Success?     →  POST .../completed
Failure?     →  POST .../error
```

### Multi-Agent Coordination

If you are one of several agents working in parallel:

- Each agent uses a **unique, stable name** (e.g. `Frontend Agent`, `Backend Agent`)
- Report `waiting` when you need output from another agent
- Report `working` when you resume after the dependency is met
- The dashboard tracks all agents on a shared timeline — the human operator
  can see who is active, who is blocked, and overall concurrency

## Quick Context for Your Project

<!-- ============================================================
     ADAPT THIS SECTION to describe YOUR project.
     Delete these HTML comments when you're done.
     ============================================================ -->

**Project:** _[Your project name]_
**Repository:** _[Your repo URL]_
**Stack:** _[Your tech stack]_

### What This Agent Does

_[Describe what this specific agent is responsible for in your workflow.]_

### Key Files

| File | Purpose |
|------|---------|
| _[file]_ | _[description]_ |

### Build & Test

```bash
# [Your build command]
# [Your test command]
```
