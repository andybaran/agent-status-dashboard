# Agent Status Dashboard

A lightweight, real-time dashboard for monitoring AI agent status in orchestration workflows. Agents self-register dynamically by posting status updates—no pre-configuration required.

## Features

- **Dynamic Agent Registration** — Agents appear automatically when they post their first status update
- **Real-time Status Cards** — Visual status for each agent with color-coded badges
- **Working Time Tracking** — Tracks total time each agent has spent in "working" status
- **Activity Log** — Last 100 status changes with timestamps
- **Concurrency Chart** — Canvas-based visualization of concurrent working agents over time
- **Dark Theme** — Monospace styling optimized for terminal-adjacent workflows
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

Example:
```bash
DASHBOARD_PORT=8080 DASHBOARD_TITLE="My Agents" python dashboard.py
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
    "OtherAgent": {
      "status": "idle",
      "timestamp": "2026-01-15T10:25:00Z",
      "working_seconds": 300
    }
  },
  "log": [
    {"timestamp": "2026-01-15T10:30:00Z", "agent_name": "MyAgent", "status": "working"},
    ...
  ]
}
```

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

## License

MIT License - Copyright 2026 Andy Baran
