# Examples

This folder contains everything you need to get started with the Agent Status Dashboard.

## Contents

| File | What it is |
|------|-----------|
| `multi_agent_demo.py` | Runnable 8-agent pipeline demo — see the dashboard in action |
| `claude.md` | **Template** — copy into your project as `CLAUDE.md` to teach Claude to report status |
| `copilot-instructions.md` | **Template** — copy into your project as `.github/copilot-instructions.md` to teach Copilot to report status |

## Quick Start

### 1. Run the demo to see the dashboard in action

```bash
pip install requests
python examples/multi_agent_demo.py
```

### 2. Integrate the dashboard into your own project

Copy the template that matches your AI assistant:

```bash
# For Claude (Claude Code, Anthropic API, etc.)
cp examples/claude.md /path/to/your/project/CLAUDE.md

# For GitHub Copilot
mkdir -p /path/to/your/project/.github
cp examples/copilot-instructions.md /path/to/your/project/.github/copilot-instructions.md
```

Then edit the "Project-Specific Instructions" section at the bottom of each
file to describe your project. The dashboard integration section at the top
works as-is.

---

## Multi-Agent Data Pipeline Demo

**File:** `multi_agent_demo.py`

A self-contained Python script that simulates a data-pipeline workflow with 8 concurrent agents. The agents coordinate via threading primitives to model realistic dependencies — some agents wait for upstream work before starting, one agent encounters and recovers from an error, and the orchestrator waits for the entire pipeline before finishing.

### Agent Roles

| Agent | Behavior |
|-------|----------|
| **Orchestrator** | Starts first, coordinates the pipeline, finishes last |
| **Data Collector** | Gathers raw data from sources |
| **Data Validator** | Waits for collection, then validates |
| **Transform Agent** | Waits for validation, then transforms data |
| **ML Trainer** | Waits for transformation, trains a model (longest job) |
| **QA Agent** | Runs quality checks — encounters a transient error and retries |
| **Report Builder** | Generates the final report after QA passes |
| **Notifier** | Sends notifications, signals pipeline completion |

### Prerequisites

```bash
pip install requests
```

The dashboard must be running. Start it with Docker:

```bash
docker run -d --name demo-dashboard \
  -p 5050:5050 \
  -v $(pwd)/data:/data \
  -e DASHBOARD_TITLE="Demo Pipeline Dashboard" \
  -e STALE_THRESHOLD_MINUTES=5 \
  ghcr.io/andybaran/agent-status-dashboard:latest
```

Or locally:

```bash
pip install flask
# Use nohup so the dashboard survives terminal/session close
nohup python3 ../dashboard.py > /tmp/dashboard.log 2>&1 &
echo "Dashboard PID: $! — open http://localhost:5050"
```

> ⚠️ **Do not use plain `python dashboard.py &`** — the process will be killed
> when the terminal or AI session that started it closes. `nohup` detaches it
> from the session so it keeps running.

To verify it is running:

```bash
curl -s http://localhost:5050/api/status > /dev/null && echo "Dashboard is up" || echo "Dashboard is not running"
```

To stop it later:

```bash
pkill -f "python3.*dashboard.py" && echo "Stopped"
```

### Run the Demo

```bash
# Default speed (~3 minutes)
python multi_agent_demo.py

# Fast mode (~90 seconds)
DEMO_SPEED=0.5 python multi_agent_demo.py

# Custom dashboard URL
DASHBOARD_URL=http://myhost:8080 python multi_agent_demo.py
```

### What to Watch For

1. **Agent cards** appear as each agent starts — watch the status badges change from `working` → `waiting` → `completed`
2. **Task names as clickable links** — each card shows the task name linked to its GitHub issue/PR (e.g. click "Fetch raw data from sources" to open the issue)
3. **AI model** is displayed below each task name in italic (e.g. "Claude Opus 4.6", "GPT-4.1")
4. **Heartbeat check-ins** — the ML Trainer (longest-running agent) sends periodic `working` re-posts to prevent staleness
5. **Concurrency chart** shows the number of simultaneously active agents rising and falling
6. **QA Agent** briefly shows an `error` status before retrying and completing
6. **Sort controls** — try sorting by Status to see all "working" agents grouped together
7. **Activity log** — every status transition is recorded with a timestamp
8. **Working time** — each card tracks cumulative time spent in "working" status
9. **Total Duration vs Total Working Time** — compare wall-clock time to summed agent time to see the parallelism benefit

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DASHBOARD_URL` | `http://localhost:5050` | Dashboard API endpoint |
| `DEMO_SPEED` | `1.0` | Speed multiplier (0.5 = fast, 2.0 = slow) |

### Cleaning Up

The demo agents register in the dashboard's database. To start fresh:

```bash
# Docker — stop container and delete data
docker rm -f demo-dashboard
rm -rf ./data

# Restart with Docker
docker run -d --name demo-dashboard -p 5050:5050 -v $(pwd)/data:/data ghcr.io/andybaran/agent-status-dashboard:latest

# Local — stop the background process and delete the database
pkill -f "python3.*dashboard.py"
rm -f ../agent_status.db

# Restart locally (nohup keeps it running after the terminal closes)
nohup python3 ../dashboard.py > /tmp/dashboard.log 2>&1 &
echo "Dashboard PID: $!"
```
