# Agent Status Dashboard - Instructions for AI Agents

## Quick Start

```bash
# Docker (preferred)
docker run -d -p 5050:5050 -v $(pwd)/data:/data ghcr.io/andybaran/agent-status-dashboard:latest

# Local
pip install flask && python dashboard.py
```

Dashboard URL: `http://localhost:5050`

## API Reference

### Update Agent Status
```bash
POST /api/update/<agent_name>/<status>
```

Valid statuses: `working`, `waiting`, `completed`, `idle`, `blocked`, `error`

**Optional query parameters:**

| Parameter | Description |
|-----------|-------------|
| `task` | Name/description of the current task |
| `task_url` | URL to the task (e.g. GitHub issue, Jira ticket, GitLab MR) |
| `model` | AI model being used (e.g. Claude Sonnet 4.5, GPT-4.1) |

Task info is displayed on the agent's card. If `task_url` is provided, the task
name is rendered as a clickable link. Model is displayed below the task in
italic. All three carry forward across status updates until a new value is
provided.

**Naming convention:** Use `Title Case` with spaces (e.g. `Research Agent`).
Names are normalized server-side — hyphens, underscores, and casing differences
all resolve to the same canonical name. Known acronyms (UI, API, CSI, VSO, etc.)
are preserved automatically.

Examples:
```bash
# Start working
curl -X POST "http://localhost:5050/api/update/My%20Agent/working"

# Start working on a specific task
curl -X POST "http://localhost:5050/api/update/My%20Agent/working?task=Implement+feature+X"

# Start working on a GitHub issue
curl -X POST "http://localhost:5050/api/update/My%20Agent/working?task=Fix+auth+bug&task_url=https://github.com/org/repo/issues/42"

# Report the model being used
curl -X POST "http://localhost:5050/api/update/My%20Agent/working?task=Fix+auth+bug&model=Claude+Sonnet+4.5"

# Agent with spaces (URL-encode)
curl -X POST "http://localhost:5050/api/update/Terraform%20Agent/working"

# Mark completed
curl -X POST "http://localhost:5050/api/update/My%20Agent/completed"

# Report error
curl -X POST "http://localhost:5050/api/update/My%20Agent/error"
```

Response:
```json
{"ok": true, "agent": "My Agent", "status": "working", "task": "Fix auth bug", "task_url": "https://github.com/org/repo/issues/42", "model": "Claude Sonnet 4.5"}
```

### Get All Agent Status
```bash
GET /api/status
```

Response:
```json
{
  "current": {
    "My Agent": {"status": "working", "timestamp": "2026-01-15T10:30:00Z", "working_seconds": 120, "task_name": "Fix auth bug", "task_url": "https://github.com/org/repo/issues/42", "model": "Claude Sonnet 4.5"}
  },
  "log": [...]
}
```

> If an agent's last status is `working` but its last update is older than `STALE_THRESHOLD_MINUTES` (default: 30), the API returns `"status": "idle"` with `"stale": true`.

### Get Concurrency Data
```bash
GET /api/concurrency
```

## Recommended Workflow

1. Post `working` when starting a task
2. Post `waiting` if blocked on external dependency
3. Post `completed` on success OR `error` on failure
4. **Always post `idle` or `completed` when done** — agents that remain in `working` status will be marked as stale after 30 minutes

Agents self-register on first status update. No pre-configuration needed.

## URL Encoding

Agent names with special characters must be URL-encoded:
- Space → `%20`
- `/` → `%2F`

Example: `Research Agent` → `Research%20Agent`

## Demo / Example

To see the dashboard in action with a simulated multi-agent workflow:

```bash
pip install requests
python examples/multi_agent_demo.py
```

This runs 8 agents through a data-pipeline workflow in ~3 minutes
(or ~90s with `DEMO_SPEED=0.5`). See `examples/README.md` for details.

## Integration Templates

Copy the example instruction file that matches your AI assistant into your project:

- `examples/claude.md` → copy as `CLAUDE.md` in your project root
- `examples/copilot-instructions.md` → copy as `.github/copilot-instructions.md`

These templates include the full dashboard API reference, naming conventions,
and workflow patterns. Edit the "Project-Specific Instructions" section at the
bottom to describe your project.
