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
6. **Always include `task_url`** when the task originates from or relates to a
   GitHub issue, pull request, Jira ticket, Linear issue, or any system with a
   trackable URL. Without it, the task name is plain text instead of a clickable link.
7. **Send heartbeat check-ins every 2–3 minutes** during long-running tasks.
   Re-POST your current `working` status with the same `task`, `task_url`, and
   `model` parameters. This resets the staleness timer and prevents the dashboard
   from marking you as stale while you are still actively working.

### Task URL Best Practices

The `task_url` parameter turns the task name on the dashboard into a **clickable
link**. Always provide it when a URL is available.

**Common URL patterns:**

| System | URL format |
|--------|-----------|
| GitHub issue | `https://github.com/{owner}/{repo}/issues/{number}` |
| GitHub PR | `https://github.com/{owner}/{repo}/pull/{number}` |
| Jira | `https://{instance}.atlassian.net/browse/{KEY-123}` |
| Linear | `https://linear.app/{team}/issue/{ID}` |
| GitLab issue | `https://gitlab.com/{group}/{project}/-/issues/{number}` |
| GitLab MR | `https://gitlab.com/{group}/{project}/-/merge_requests/{number}` |

**Important:** When transitioning between statuses (e.g. `working` → `completed`),
**re-send the same `task_url`** so the link remains visible on the dashboard card.

### Agent Name

Use a consistent, descriptive `Title Case` name with spaces.
Names are normalized server-side (hyphens/underscores become spaces, acronyms
like UI, API, AWS are preserved). Pick one name and use it for the entire session.

Good: `Research Agent`, `Code Review Agent`, `Terraform Agent`
Bad: `agent1`, `my-agent`, `Claude`

### How to Report (curl)

```bash
# Starting work on a GitHub issue (preferred — always include task_url when available)
curl -s -X POST "http://localhost:5050/api/update/My%20Agent/working?task=Fix+auth+bug&task_url=https://github.com/org/repo/issues/42&model=Claude+Opus+4.6"

# Starting work on a Jira ticket
curl -s -X POST "http://localhost:5050/api/update/My%20Agent/working?task=Implement+login+form&task_url=https://myteam.atlassian.net/browse/PROJ-123"

# Starting work on a GitHub PR
curl -s -X POST "http://localhost:5050/api/update/My%20Agent/working?task=Review+PR+99&task_url=https://github.com/org/repo/pull/99"

# Starting work without a trackable URL (ok, but prefer including task_url)
curl -s -X POST "http://localhost:5050/api/update/My%20Agent/working?task=Refactor+utils"

# Waiting on dependency
curl -s -X POST http://localhost:5050/api/update/My%20Agent/waiting

# Done — re-send task_url so the link stays visible on the card
curl -s -X POST "http://localhost:5050/api/update/My%20Agent/completed?task=Fix+auth+bug&task_url=https://github.com/org/repo/issues/42"

# Something broke
curl -s -X POST "http://localhost:5050/api/update/My%20Agent/error?task=Fix+auth+bug&task_url=https://github.com/org/repo/issues/42"
```

### Workflow Pattern

```
Start task   →  POST .../working?task=My+Task+Name&task_url=https://...
  ↓
Do work...   →  re-POST .../working every 2–3 min (heartbeat)
  ↓
Need input?  →  POST .../waiting  →  (get input)  →  POST .../working
  ↓
Success?     →  POST .../completed?task=...&task_url=...
Failure?     →  POST .../error?task=...&task_url=...
```

> **Heartbeat:** For tasks longer than a few minutes, re-POST your `working`
> status with the same parameters every 2–3 minutes. This resets the staleness
> timer (default: 10 minutes) and keeps your card active on the dashboard.

### Multi-Agent Coordination

If you are one of several agents working in parallel:

- Each agent uses a **unique, stable name** (e.g. `Frontend Agent`, `Backend Agent`)
- Report `waiting` when you need output from another agent
- Report `working` when you resume after the dependency is met
- The dashboard tracks all agents on a shared timeline — the human operator
  can see who is active, who is blocked, and overall concurrency

### Model Selection (Orchestrator Guidance)

When you are the **orchestrating agent** responsible for spawning or delegating
work to other agents, choose the most cost-effective model for each sub-task.
Not every task requires a premium model. Match model capability to task complexity:

| Task complexity | Example tasks | Suggested model tier |
|----------------|---------------|---------------------|
| **High** — complex reasoning, architecture, multi-step planning | System design, large refactors, debugging subtle issues | Premium (e.g. Claude Opus, GPT-5.3-Codex) |
| **Medium** — standard coding, analysis, writing | Feature implementation, code review, documentation | Standard (e.g. Claude Sonnet, GPT-5 mini) |
| **Low** — routine, mechanical, or well-defined | Formatting, simple lookups, status checks, notifications | Fast/cheap (e.g. Claude Haiku, GPT-4.1 mini) |

**Guidelines:**

1. **Default to the lowest tier that can handle the task well.** Upgrade only
   when the task genuinely requires stronger reasoning or broader context.
2. **Report the model** each agent is using via the `model` query parameter so
   the human operator can monitor cost across the workflow.
3. **Re-evaluate during retries.** If a cheaper model fails at a task, it may
   be worth retrying with a more capable model rather than repeating the same
   failure.
4. **Parallelism amplifies cost.** When running many agents concurrently, using
   premium models for all of them can be very expensive. Reserve premium models
   for the critical-path tasks.

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
