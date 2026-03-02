# Copilot Instructions — Agent Status Dashboard Integration

> **Copy this file to `.github/copilot-instructions.md` in your project and adapt it.**
> It teaches GitHub Copilot (and other AI assistants that read this file) how to
> report status to the Agent Status Dashboard for real-time workflow visibility.

## Agent Status Dashboard

A dashboard is running at `DASHBOARD_URL` (default: `http://localhost:5050`).
Every agent in this workflow **must** report its status at task boundaries
so the human operator has real-time visibility into progress.

**Dashboard:** http://localhost:5050
**API docs:** See `dashboard-instructions.md` in the dashboard repo.

### Status Reporting API

```
POST /api/update/<agent_name>/<status>
```

| Status | When to use |
|--------|-------------|
| `working` | Starting a task or resuming after a wait |
| `waiting` | Blocked on user input, another agent, or external dependency |
| `completed` | Task finished successfully |
| `error` | Task failed (describe the failure in your response) |
| `idle` | No active task — use between tasks if you remain available |
| `blocked` | Cannot proceed and need intervention |

**Optional query parameters:**

| Parameter | Description |
|-----------|-------------|
| `task` | Name/description of the current task |
| `task_url` | URL to the task (e.g. GitHub issue, Jira ticket, GitLab MR) |
| `model` | AI model being used (e.g. Claude Sonnet 4.5, GPT-4.1) |

Task info is displayed on the agent's dashboard card. If `task_url` is provided,
it renders as a clickable link. Model is displayed below the task in italic.
All three carry forward until replaced.

### Naming Convention

Use a **consistent, descriptive `Title Case` name** for the entire session:

- ✅ `Research Agent`, `Code Review Agent`, `Terraform Agent`, `UI Agent`
- ❌ `agent1`, `my-agent`, `Claude`, `copilot`

Names are normalized server-side: hyphens/underscores become spaces, known
acronyms (UI, API, AWS, CI, CD, etc.) are preserved. The same agent must
always report the same name so the dashboard can track it correctly.

### Task URL Best Practices

The `task_url` parameter turns the task name on the dashboard into a **clickable
link**. **Always provide it** when the task relates to a trackable item.

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
Without `task_url`, the task name appears as plain text.

### Reporting via curl (Bash tool)

```bash
# Start working on a GitHub issue (preferred — always include task_url when available)
curl -s -X POST "http://localhost:5050/api/update/My%20Agent%20Name/working?task=Fix+auth+bug&task_url=https://github.com/org/repo/issues/42&model=Claude+Sonnet+4.5" > /dev/null

# Start working on a Jira ticket
curl -s -X POST "http://localhost:5050/api/update/My%20Agent%20Name/working?task=Implement+feature+X&task_url=https://myteam.atlassian.net/browse/PROJ-123" > /dev/null

# Start working on a GitHub PR
curl -s -X POST "http://localhost:5050/api/update/My%20Agent%20Name/working?task=Review+PR+99&task_url=https://github.com/org/repo/pull/99" > /dev/null

# Start working without a trackable URL (ok, but prefer including task_url)
curl -s -X POST "http://localhost:5050/api/update/My%20Agent%20Name/working?task=Refactor+utils" > /dev/null

# Waiting on something
curl -s -X POST http://localhost:5050/api/update/My%20Agent%20Name/waiting > /dev/null

# Done — re-send task_url so the link stays visible on the card
curl -s -X POST "http://localhost:5050/api/update/My%20Agent%20Name/completed?task=Fix+auth+bug&task_url=https://github.com/org/repo/issues/42" > /dev/null

# Error — include task_url for traceability
curl -s -X POST "http://localhost:5050/api/update/My%20Agent%20Name/error?task=Fix+auth+bug&task_url=https://github.com/org/repo/issues/42" > /dev/null
```

> URL-encode spaces as `%20`. The `> /dev/null` suppresses curl output to keep
> your context clean.

### Required Workflow

Every agent **must** follow this lifecycle:

```
1. POST .../working?task=My+Task&task_url=https://...  ← before starting any task
2. (do the work)
   ↳ re-POST .../working every 2–3 min                ← heartbeat to prevent staleness
3. POST .../waiting                                     ← if blocked on input/dependency
4. (receive input)
5. POST .../working                                     ← resume after wait
6. (finish work)
7. POST .../completed?task=My+Task&task_url=https://... ← on success (re-send task_url)
   POST .../error?task=My+Task&task_url=https://...     ← on failure (re-send task_url)
```

⚠️ **Critical:** Never leave your status as `working` when you are finished.
Agents stuck in `working` status are flagged as stale after 10 minutes.

⚠️ **Heartbeat:** For long-running tasks, re-POST your `working` status with
the same `task`, `task_url`, and `model` parameters **every 2–3 minutes**. This
resets the staleness timer and keeps your card active on the dashboard. Without
heartbeats, agents working longer than 10 minutes will be marked as stale.

⚠️ **Always include `task_url`** when the task originates from or relates to a
GitHub issue, PR, Jira ticket, Linear issue, or any system with a trackable URL.
Without it, the task name appears as plain text instead of a clickable link.

### Multi-Agent Orchestration

When running multiple agents in parallel:

- **Each agent uses a unique, stable name** throughout the session
- Agents report `waiting` when they depend on another agent's output
- Agents report `working` when they resume after the dependency is met
- The dashboard shows all agents on a shared timeline with a concurrency chart
- The human operator uses the dashboard to monitor progress, spot blockers,
  and understand which agents are active

Example with 3 agents working on a feature:

```
Research Agent  →  working → completed
Code Agent      →  waiting (for research) → working → completed
Test Agent      →  waiting (for code) → working → error → working → completed
```

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

### Checking Other Agents' Status

To check what other agents are doing (useful for coordination):

```bash
curl -s http://localhost:5050/api/status | python3 -c "
import sys, json
data = json.load(sys.stdin)
for name, info in sorted(data['current'].items()):
    print(f'{name}: {info[\"status\"]}')"
```

---

## Project-Specific Instructions

<!-- ============================================================
     EVERYTHING BELOW THIS LINE should be adapted for YOUR project.
     Delete these HTML comments when you're done.
     ============================================================ -->

### Project Overview

**Project:** _[Your project name and one-line description]_
**Repository:** _[owner/repo]_
**Stack:** _[Languages, frameworks, tools]_

### Architecture

_[Describe your project architecture — key components, data flow, etc.]_

### Key Files

| File | Purpose |
|------|---------|
| _[file path]_ | _[what it does]_ |

### Development

```bash
# Build
_[your build command]_

# Test
_[your test command]_

# Lint
_[your lint command]_
```

### Agent Roles

_[Define which agents work on this project and what each one does:]_

| Agent Name | Responsibility |
|------------|---------------|
| _[Research Agent]_ | _[Investigates APIs, reads docs, answers questions]_ |
| _[Code Agent]_ | _[Implements features, fixes bugs]_ |
| _[Test Agent]_ | _[Writes and runs tests]_ |
| _[Review Agent]_ | _[Reviews code changes for quality and correctness]_ |

### Conventions

_[Your project-specific code style, naming conventions, etc.]_

### Do NOT

- _[Project-specific prohibitions]_
