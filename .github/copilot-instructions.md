# Agent Status Dashboard — Copilot Instructions

## Project Overview

A lightweight, platform-agnostic Flask dashboard for monitoring AI agent status
in orchestration workflows. Works with any AI platform (GitHub Copilot, Claude,
OpenAI, LangChain, CrewAI, AutoGen, or custom agents). Agents self-register
dynamically via HTTP POST — no pre-configuration required.

**Repository:** `andybaran/agent-status-dashboard`
**License:** MIT
**Docker image:** `ghcr.io/andybaran/agent-status-dashboard:latest`

## Architecture

This is a **single-file Flask application** (`dashboard.py`, ~1390 lines) with
embedded HTML, CSS, and JavaScript. There are no separate template files, static
assets, or frontend build steps. Everything is in one file by design for maximum
portability.

### Key Sections in `dashboard.py`

| Lines (approx.) | Section |
|-----------------|---------|
| 1–25 | Module docstring with all env vars |
| 27–45 | Imports, Flask app, config constants |
| 48–90 | VALID_STATUSES, ACRONYMS builder, `normalize_agent_name()`, staleness config, status colors |
| 118–130 | Logo SVG (default + configurable), `LOGO_SVG` constant |
| 132–1020 | `DASHBOARD_HTML` — full HTML template with CSS and JS |
| 141–200 | CSS `:root` design tokens (light theme) |
| 203–240 | CSS `[data-theme="dark"]` tokens |
| 240–670 | CSS rules (header, cards, chart, stats, activity log) |
| 670–680 | Theme init script (runs in `<head>` to prevent FOUC) |
| 680–1020 | JavaScript: fetch loops, chart rendering, card rendering, sorting, theme toggle |
| 1025–1090 | `init_db()`, database schema, migration, CSV auto-import |
| 1096–1100 | `get_known_agents()` |
| 1104–1120 | `write_status()` |
| 1119–1200 | `get_current_status()` with staleness logic, task/model carry-forward |
| 1202–1390 | Flask routes: `/`, `/api/status`, `/api/update`, `/api/export/csv`, `/api/concurrency` |
| 1385–1392 | `if __name__` block |

### Design Token System

CSS custom properties use the `--ds-*` prefix (design system). These are
**not** tied to any vendor's design system — they are generic semantic tokens:

- `--ds-foreground-*` — text colors (strong, primary, faint, action, success, etc.)
- `--ds-surface-*` — background colors
- `--ds-border-*` — border colors
- `--ds-chart-*` — chart canvas colors
- `--ds-elevation-*` — box shadows
- `--ds-space-*` — spacing scale (100=8px through 500=48px)
- `--ds-radius-*` — border radius scale
- `--ds-font-*` — font stacks (text, code)
- `--ds-brand-primary` — brand accent color
- `--ds-header-bg/fg` — app header colors

Dark theme overrides all tokens via `[data-theme="dark"]` selector.

## Configuration

All configuration is via environment variables — no config files.

| Variable | Default | Description |
|----------|---------|-------------|
| `DASHBOARD_PORT` | `5050` | Port to listen on |
| `DB_PATH` | `./agent_status.db` | Path to the SQLite database file |
| `CSV_PATH` | (legacy) | Path to legacy CSV file for auto-import on first run |
| `DASHBOARD_TITLE` | `Agent Status Dashboard` | Header title text |
| `STALE_THRESHOLD_MINUTES` | `10` | Minutes before a "working" agent is marked stale |
| `DASHBOARD_LOGO_SVG` | *(robot icon)* | Custom SVG for the header logo |
| `DASHBOARD_ACRONYMS` | `UI,API,CI,CD,HCP,VSO,CSI,LDAP,AWS,GitOps` | Comma-separated acronyms preserved during name normalization |

## API

```
POST /api/update/<agent_name>/<status>   — Update agent status
POST /api/reset                          — Reset all working agents to idle
POST /api/reset/<agent_name>             — Reset a specific agent to idle
GET  /api/status                          — All agent statuses + activity log
GET  /api/export/csv                      — Export full status log as CSV
GET  /api/concurrency                     — Time-series concurrency data for chart
GET  /                                    — Dashboard HTML page
```

Valid statuses: `working`, `waiting`, `completed`, `idle`, `blocked`, `error`

Agent names are normalized server-side (hyphens/underscores → spaces, title-cased,
acronyms preserved). The API response returns the canonical name.

Optional query parameters: `task`, `task_url`, `model`, `role`, `goal`, `progress`.
Agents with `role=orchestrator` are displayed in a dedicated panel above agent cards.

## Data Model

Status data is stored in a **SQLite database** with a single `status_log` table:

**Schema:** `id (INTEGER PRIMARY KEY), timestamp (TEXT), agent_name (TEXT), status (TEXT), task_name (TEXT), task_url (TEXT), model (TEXT), role (TEXT), goal (TEXT), progress (TEXT)`

**Characteristics:**
- Rows are **append-only** (no updates/deletes in normal operation)
- Indexed on `(agent_name, timestamp)` for efficient queries
- Write-Ahead Logging (WAL) mode ensures durability and allows concurrent reads
- `timestamp` is always UTC ISO 8601 format
- On startup, if a legacy CSV file exists, it is auto-imported into the database
- `get_current_status()` normalizes agent names on read for historical data compatibility
- `write_status()` inserts one row per status change
- `get_current_status()` queries the latest row per agent
- Staleness is computed at read time, not persisted in the database

## Development

### Prerequisites

- Python 3.11+
- Flask (`pip install flask`)

### Run locally

```bash
pip install flask
python dashboard.py
# → http://localhost:5050
```

### Run with Docker

```bash
docker build -t agent-dashboard .
docker run -d -p 5050:5050 -v $(pwd)/data:/data agent-dashboard
```

### Test syntax

```bash
python -c "import dashboard; print('OK')"
```

There are no automated tests currently. When adding tests, use `pytest` with
Flask's test client (`app.test_client()`).

## CI/CD

GitHub Actions workflow at `.github/workflows/build-image.yml`:

- **Trigger:** 
  - Push to `main` when `Dockerfile`, `dashboard.py`, `requirements.txt`, or the workflow file itself changes
  - Push of version tags matching `v*` (e.g. `v1.0.0`)
- **Builds:** Multi-platform Docker image (`linux/amd64` + `linux/arm64`)
- **Pushes to:** `ghcr.io/andybaran/agent-status-dashboard`
  - On `main` push: `:latest` + `:SHA` tags
  - On version tag push: `:latest` + `:VERSION` + `:MAJOR.MINOR` tags
- **Caching:** GitHub Actions cache (`type=gha`)

### Creating a New Release

To create a new versioned release:

```bash
git tag -a vX.Y.Z -m "vX.Y.Z: Release description"
git push origin vX.Y.Z
```

This will trigger the workflow to build and push Docker images with version tags.

## Code Style & Conventions

- **Single-file architecture** — keep everything in `dashboard.py`. Do not split
  into templates, static files, or separate modules unless there is a compelling
  reason (>2000 lines or complex routing)
- **No external CSS/JS** — all styling and behavior is inline in the HTML template
- **CSS custom properties** — use `--ds-*` tokens for all colors, spacing, and
  typography. Never use raw hex values in CSS rules
- **Theme support** — all visual properties must work in both light and dark mode.
  Test both themes when making visual changes
- **`localStorage` key** — theme preference stored as `ds-theme` (values: `light`,
  `dark`, `system`)
- **Agent names** — always normalize via `normalize_agent_name()` on both ingest
  and read paths. Never compare raw agent name strings
- **Status validation** — all status values must be in `VALID_STATUSES` set
- **Timestamps** — always use `datetime.now(timezone.utc)` for UTC ISO 8601 format

## Key Implementation Details

### Theme Toggle
- Three-state cycle: light → dark → system → light
- Init script in `<head>` reads `localStorage` + `prefers-color-scheme` before
  body renders to prevent flash of wrong theme (FOUC)
- Chart re-renders on theme change using cached data (`window.__lastConcData`)
- Status badge colors have separate light/dark palettes in JavaScript

### Staleness Detection
- Only applies to agents whose last status is `working`
- Threshold check: `(now - last_update) > STALE_THRESHOLD` seconds
- Sets `status = "idle"` and `stale = True` in the API response
- UI shows "idle (stale)" badge with orange `.stale-tag`
- NOT written back to the database — computed at read time

### Agent Name Normalization
- `normalize_agent_name()`: strip → replace `-`/`_` with space → collapse spaces →
  `.title()` → replace acronyms from `ACRONYMS` dict
- Applied in `api_update()` (ingest) and `get_current_status()` (read)
- Acronyms dict built from `DASHBOARD_ACRONYMS` env var or defaults
- `.title()` breaks acronyms (`UI` → `Ui`), so we post-process with the map
- `GitOps` is a special case — stored as `"Gitops": "GitOps"` in the default map

### Concurrency Chart
- Canvas-based (no charting library) — drawn in `renderChart()` function
- X-axis: time range from earliest database entry to 5 minutes past now
- Y-axis: concurrent "working" agents at each timestamp
- Orange vertical line marks current time
- Colors read from CSS custom properties via `getComputedStyle()` for theme awareness
- Data cached in `window.__lastConcData` for theme-switch re-renders

### SQLite Connection Handling

To ensure thread safety with Flask's `is_request_context()` behavior:
- Each route creates a short-lived SQLite connection
- Connections are closed immediately after use
- Do NOT store connection objects globally or in thread-local storage
- All queries use parameterized statements to prevent SQL injection

## Common Tasks

### Adding a new status type
1. Add to `VALID_STATUSES` set
2. Add color entries in `STATUS_COLORS`, `STATUS_BG_COLORS`, `STATUS_BORDER_COLORS`
3. Add dark-mode entries in `STATUS_COLORS_DARK`/`STATUS_BG_COLORS_DARK`/`STATUS_BORDER_COLORS_DARK` (in JavaScript)
4. Update `dashboard-instructions.md` with the new status

### Adding a new environment variable
1. Add `os.environ.get()` call near the top of the file with other config
2. Add to the module docstring
3. Add to the README config table
4. Add to this file's Configuration section

### Adding a new API endpoint
1. Add Flask route in the routes section (~line 950+)
2. Document in the README API Reference section
3. Document in `dashboard-instructions.md` for agent consumption
4. Update the healthcheck in `Dockerfile` if needed

### Updating the Docker image
1. Make changes to `dashboard.py`
2. Commit and push to `main`
3. GitHub Actions automatically builds and pushes
4. Pull new image: `docker pull ghcr.io/andybaran/agent-status-dashboard:latest`
5. Restart container with the new image

## Files

| File | Purpose |
|------|---------|
| `dashboard.py` | Single-file Flask app (HTML/CSS/JS embedded) |
| `dashboard-instructions.md` | Machine-readable API reference for AI agents |
| `README.md` | Human-readable documentation |
| `Dockerfile` | Multi-stage Docker build (python:3.13-slim, non-root UID 1000) |
| `requirements.txt` | Python dependencies (Flask only) |
| `examples/multi_agent_demo.py` | Runnable 8-agent data-pipeline demo |
| `examples/claude.md` | Template CLAUDE.md for user projects |
| `examples/copilot-instructions.md` | Template copilot-instructions.md for user projects |
| `examples/README.md` | Example setup and usage instructions |
| `.github/workflows/build-image.yml` | CI: multi-platform Docker build + push |
| `.gitignore` | Ignores Python artifacts, CSV data, IDE files |
| `LICENSE` | MIT License |

## Examples

The `examples/` folder contains onboarding resources for new users:

| File | Description |
|------|-------------|
| `examples/multi_agent_demo.py` | Runnable 8-agent data-pipeline simulation (~3 min, or ~90s at `DEMO_SPEED=0.5`) |
| `examples/claude.md` | Template `CLAUDE.md` for users to copy into their projects — teaches Claude to report status |
| `examples/copilot-instructions.md` | Template `.github/copilot-instructions.md` — teaches GitHub Copilot to report status |
| `examples/README.md` | Setup, usage, and integration instructions |

The demo requires only `requests` (no AI platform dependency) and posts to the
dashboard's HTTP API to simulate realistic agent lifecycle transitions including
error/retry, waiting, and coordination. The template instruction files show
users how to integrate status reporting into their own AI workflows.

## Mandatory Update Rules

These rules are **non-negotiable** and must be followed for every change:

1. **`examples/`** — The example must always use the latest dashboard version and
   API patterns. If you add a new API endpoint, status type, or config option,
   update the example to demonstrate or at least document it.
2. **`README.md`** — Must be updated whenever features, API, configuration,
   environment variables, or behavior changes.
3. **`dashboard-instructions.md`** — Must be updated whenever the agent-facing
   API changes (new endpoints, new statuses, new parameters, new behavior).
4. **`CLAUDE.md`** — Must be updated for architecture or workflow changes.
5. **This file** (`copilot-instructions.md`) — Must be updated for architecture,
   code conventions, file layout, or CI/CD changes.

## Do NOT

- Split `dashboard.py` into multiple files without a compelling reason
- Add JavaScript frameworks or CSS libraries (keep it vanilla)
- Use raw hex colors in CSS rules — always use `--ds-*` custom properties
- Store sensitive data in the database or expose it via the API
- Change the SQLite schema without migration logic
- Remove the FOUC-prevention script from `<head>`
- Break the multi-platform Docker build (test on both amd64 and arm64)
- Let `examples/` fall out of date with the current API
