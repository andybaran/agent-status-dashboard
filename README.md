# Agent Status Dashboard

A lightweight, real-time dashboard for monitoring AI agent status in orchestration workflows. Agents self-register dynamically by posting status updates—no pre-configuration required.

> **For AI agents / orchestrators:** See [`dashboard-instructions.md`](dashboard-instructions.md) for a concise, machine-readable API reference designed to be included in agent system prompts or tool definitions.

## Features

- **Dynamic Agent Registration** — Agents appear automatically when they post their first status update
- **Real-time Status Cards** — Visual status for each agent with color-coded badges
- **Working Time Tracking** — Tracks total time each agent has spent in "working" status
- **Activity Log** — Last 100 status changes with timestamps
- **Concurrency Chart** — Canvas-based visualization of concurrent working agents over time
- **Staleness Detection** — Agents stuck in "working" beyond a configurable threshold are automatically shown as "idle (stale)" with a warning tag
- **Light/Dark Theme** — HDS-compliant theme toggle (light, dark, system) with `localStorage` persistence
- **No External Dependencies** — Pure Python/Flask with vanilla JavaScript

## Quick Start

### Docker (Recommended)

```bash
# Run with persistent CSV storage
docker run -d \
  -p 5050:5050 \
  -v $(pwd)/data:/data \
  ghcr.io/andybaran/agent-status-dashboard:latest

# Open dashboard
open http://localhost:5050
```

### Local Python

```bash
pip install flask
python dashboard.py

# Dashboard available at http://localhost:5050
```

## Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `DASHBOARD_PORT` | `5050` | Port to run the dashboard |
| `CSV_PATH` | `./agent_status.csv` | Path to the status CSV file |
| `DASHBOARD_TITLE` | `Agent Status Dashboard` | Title shown in the header |
| `STALE_THRESHOLD_MINUTES` | `30` | Minutes before a "working" agent is marked stale |

Example:
```bash
DASHBOARD_PORT=8080 DASHBOARD_TITLE="My Agents" STALE_THRESHOLD_MINUTES=60 python dashboard.py
```

## API Reference

### Update Agent Status

```bash
POST /api/update/<agent_name>/<status>
```

**Valid statuses:** `working`, `waiting`, `completed`, `idle`, `blocked`, `error`

**Examples:**
```bash
# Start a task
curl -X POST http://localhost:5050/api/update/MyAgent/working

# Agent name with spaces (URL-encode)
curl -X POST http://localhost:5050/api/update/Terraform%20Agent/working

# Complete successfully
curl -X POST http://localhost:5050/api/update/MyAgent/completed

# Report an error
curl -X POST http://localhost:5050/api/update/MyAgent/error
```

**Response:**
```json
{"ok": true, "agent": "MyAgent", "status": "working"}
```

### Get All Agent Status

```bash
GET /api/status
```

**Response:**
```json
{
  "current": {
    "MyAgent": {
      "status": "working",
      "timestamp": "2026-01-15T10:30:00Z",
      "working_seconds": 120
    },
    "StaleAgent": {
      "status": "idle",
      "timestamp": "2026-01-14T08:00:00Z",
      "working_seconds": 7200,
      "stale": true
    }
  },
  "log": [
    {"timestamp": "2026-01-15T10:30:00Z", "agent_name": "MyAgent", "status": "working"},
    ...
  ]
}
```

> **Note:** The `stale` field (boolean) appears only on agents whose last CSV status was `working` but whose last update is older than `STALE_THRESHOLD_MINUTES`. These agents are displayed as "idle (stale)" in the UI.

### Get Concurrency Data

```bash
GET /api/concurrency
```

Returns time-series data for the concurrency chart.

## Docker Compose

```yaml
version: '3.8'
services:
  agent-dashboard:
    image: ghcr.io/andybaran/agent-status-dashboard:latest
    ports:
      - "5050:5050"
    volumes:
      - ./data:/data
    environment:
      - DASHBOARD_TITLE=My Agent Dashboard
    restart: unless-stopped
```

## AI Agent Integration

For AI orchestration systems, have each agent call the API at task boundaries:

```python
import requests

DASHBOARD_URL = "http://localhost:5050"
AGENT_NAME = "MyAgent"

def update_status(status: str):
    requests.post(f"{DASHBOARD_URL}/api/update/{AGENT_NAME}/{status}")

# Workflow
update_status("working")
try:
    # ... do work ...
    update_status("completed")
except Exception:
    update_status("error")
```

See `dashboard-instructions.md` for machine-readable agent instructions.

## Status Colors

| Status | Color | Use Case |
|--------|-------|----------|
| `working` | 🟢 Green | Agent is actively processing |
| `waiting` | 🟡 Yellow | Blocked on external dependency |
| `completed` | 🔵 Blue | Task finished successfully |
| `idle` | ⚪ Gray | No active task |
| `blocked` | 🔴 Red | Cannot proceed |
| `error` | 🔴 Red | Task failed |

## Data Persistence

The CSV file (`/data/agent_status.csv` in Docker) is the single source of truth:
- On startup, existing CSV is read to recover agent list and state
- CSV is never reseeded on restart—only new status updates are appended
- Mount as a volume to persist across container restarts

## FAQ / Troubleshooting

### `PermissionError: [Errno 13] Permission denied` when writing to CSV

The container runs as a non-root user (UID 1000). If your mounted data directory or CSV file is owned by a different user, writes will fail.

**Fix:** Make the data directory and CSV writable before starting the container:
```bash
mkdir -p ./data
chmod 777 ./data
# If a CSV already exists:
chmod 666 ./data/agent_status.csv
```

### `no image found in image index for architecture "arm64"` when pulling

Early builds only included `linux/amd64`. The image now ships multi-platform (`amd64` + `arm64`). Pull the latest tag to get the correct architecture:
```bash
docker pull ghcr.io/andybaran/agent-status-dashboard:latest
```

### Dashboard loads but API POST returns 500

Check the container logs for the root cause:
```bash
docker logs agent-dashboard
```

The most common cause is the CSV permission issue above. Other possibilities:
- Invalid status value (must be one of: `working`, `waiting`, `completed`, `idle`, `blocked`, `error`)
- Corrupted CSV file — delete it and restart; agents will re-register on their next POST

### Container starts but no agents appear

Agents self-register — the dashboard starts empty by design. Post a status update to register an agent:
```bash
curl -X POST http://localhost:5050/api/update/TestAgent/idle
```

If you previously had data, make sure you mounted the correct directory containing your `agent_status.csv`:
```bash
docker run -d -p 5050:5050 -v /path/to/your/data:/data ghcr.io/andybaran/agent-status-dashboard:latest
```

### Port 5050 is already in use

Either stop the existing process or run on a different port:
```bash
# Find what's using port 5050
lsof -ti:5050

# Or run the dashboard on a different port
docker run -d -p 8080:5050 ghcr.io/andybaran/agent-status-dashboard:latest
```

### Agent names with special characters

URL-encode agent names when calling the API. Spaces become `%20`:
```bash
curl -X POST http://localhost:5050/api/update/My%20Agent%20Name/working
```

### Agents still show "working" long after they stopped

If an agent crashes or the orchestrator session ends without posting a final `idle` or `completed` status, the dashboard will continue to show the agent as "working." After `STALE_THRESHOLD_MINUTES` (default: 30), the dashboard automatically marks these agents as **idle (stale)** with a warning tag. To adjust the threshold:
```bash
docker run -d -p 5050:5050 -e STALE_THRESHOLD_MINUTES=60 ...
```

To manually clear a stale agent, post an `idle` status:
```bash
curl -X POST http://localhost:5050/api/update/StaleAgent/idle
```

## License

MIT License - Copyright 2026 Andy Baran
