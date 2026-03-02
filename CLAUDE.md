# CLAUDE.md — Agent Status Dashboard

## Quick Context

Single-file Flask dashboard (`dashboard.py`, ~1390 lines) for monitoring AI agent
status. Platform-agnostic. Agents self-register via `POST /api/update/<name>/<status>`.
Optional query params: `task`, `task_url`, `model`.
Data stored in **SQLite database** (auto-created). Legacy CSV auto-import supported.
Docker image: `ghcr.io/andybaran/agent-status-dashboard:latest`.

## Build & Run

```bash
# Local
pip install flask && python dashboard.py  # → http://localhost:5050

# Docker
docker build -t agent-dashboard . && docker run -d -p 5050:5050 -v $(pwd)/data:/data agent-dashboard

# Validate syntax
python -c "import dashboard; print('OK')"
```

## Architecture

Everything is in `dashboard.py` — HTML/CSS/JS embedded as a Python string template.
No separate static files, no frontend build step, no JS framework.

- CSS uses `--ds-*` custom properties (generic design tokens, not vendor-specific)
- Light and dark themes via `[data-theme="dark"]` CSS selector
- Canvas-based chart (no charting library)
- **SQLite database** stores all status changes (auto-created, WAL mode, indexed)
- Legacy CSV auto-import on first startup if `CSV_PATH` is set
- Agent names normalized server-side (`normalize_agent_name()`)
- Staleness detection computed at read time, not persisted

## Key Rules

- Keep single-file architecture — do not split into templates/static/modules
- All colors via `--ds-*` CSS custom properties, never raw hex in CSS rules
- Both light AND dark theme must be tested for any visual change
- Agent names must always go through `normalize_agent_name()` on ingest and read
- Timestamps always UTC via `datetime.now(timezone.utc)`
- No external JS/CSS dependencies

## Config (env vars)

`DASHBOARD_PORT` (5050), `DB_PATH` (./agent_status.db), `CSV_PATH` (legacy import), `DASHBOARD_TITLE`, `STALE_THRESHOLD_MINUTES` (30),
`DASHBOARD_LOGO_SVG`, `DASHBOARD_ACRONYMS`

## CI/CD

Push to `main` → GitHub Actions builds multi-platform Docker image (amd64+arm64)
→ pushes to `ghcr.io/andybaran/agent-status-dashboard`.

## Examples

The `examples/` folder contains onboarding resources for new users:

| File | Purpose |
|------|---------|
| `examples/multi_agent_demo.py` | Runnable 8-agent data-pipeline demo (~3 min, or ~90s at `DEMO_SPEED=0.5`) |
| `examples/claude.md` | Template `CLAUDE.md` users copy into their projects for dashboard integration |
| `examples/copilot-instructions.md` | Template `.github/copilot-instructions.md` for dashboard integration |
| `examples/README.md` | Setup, usage, and integration instructions |

The demo requires only `requests` (no AI platform dependency). The template
instruction files show users how to wire dashboard status reporting into their
own AI agent workflows.

## Mandatory Update Rules

- The example in `examples/` **must** always use the latest dashboard version
  and API patterns. Update `examples/` whenever the API or config changes.
- **README.md** and **dashboard-instructions.md** MUST be updated whenever
  changes are made to the repository (new features, API changes, config, etc.).

## Detailed Instructions

See `.github/copilot-instructions.md` for comprehensive architecture docs,
code style conventions, common tasks, and implementation details.
