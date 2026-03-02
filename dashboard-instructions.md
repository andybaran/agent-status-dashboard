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

**Naming convention:** Use `Title Case` with spaces (e.g. `Research Agent`).
Names are normalized server-side — hyphens, underscores, and casing differences
all resolve to the same canonical name. Known acronyms (UI, API, CSI, VSO, etc.)
are preserved automatically.

Examples:
```bash
# Start working
curl -X POST http://localhost:5050/api/update/MyAgent/working

# Agent with spaces (URL-encode)
curl -X POST http://localhost:5050/api/update/Terraform%20Agent/working

# Mark completed
curl -X POST http://localhost:5050/api/update/MyAgent/completed

# Report error
curl -X POST http://localhost:5050/api/update/MyAgent/error
```

Response:
```json
{"ok": true, "agent": "MyAgent", "status": "working"}
```

### Get All Agent Status
```bash
GET /api/status
```

Response:
```json
{
  "current": {
    "MyAgent": {"status": "working", "timestamp": "2026-01-15T10:30:00Z", "working_seconds": 120}
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
