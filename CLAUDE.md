# CLAUDE.md — Agent Status Dashboard

## Quick Context

Single-file Flask dashboard (`dashboard.py`, ~1120 lines) for monitoring AI agent
status. Platform-agnostic. Agents self-register via `POST /api/update/<name>/<status>`.
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

## Detailed Instructions

See `.github/copilot-instructions.md` for comprehensive architecture docs,
code style conventions, common tasks, and implementation details.
