#!/usr/bin/env python3
"""
Agent Status Dashboard

A lightweight Flask web application that displays real-time agent status
from a CSV file. Agents register dynamically by posting status updates.
The dashboard auto-refreshes every 5 seconds.

Configuration via environment variables:
    DASHBOARD_PORT  - Port to run on (default: 5050)
    CSV_PATH        - Path to status CSV file (default: ./agent_status.csv)
    DASHBOARD_TITLE - Title shown in the dashboard (default: Agent Status Dashboard)

Usage:
    pip install flask
    python dashboard.py

Then open http://localhost:5050 in your browser.
"""

import os
import csv
import json
from datetime import datetime, timezone
from flask import Flask, render_template_string, jsonify

app = Flask(__name__)

# Configuration from environment variables
DASHBOARD_PORT = int(os.environ.get("DASHBOARD_PORT", "5050"))
CSV_PATH = os.environ.get("CSV_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "agent_status.csv"))
DASHBOARD_TITLE = os.environ.get("DASHBOARD_TITLE", "Agent Status Dashboard")

VALID_STATUSES = {"working", "waiting", "completed", "idle", "blocked", "error"}

STATUS_COLORS = {
    "working":   "#2EB67D",  # green
    "waiting":   "#ECB22E",  # yellow
    "completed": "#36C5F0",  # blue
    "idle":      "#888888",  # gray
    "blocked":   "#E01E5A",  # red
    "error":     "#E01E5A",
}

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{{ title }}</title>
  <style>
    :root {
      --bg-primary: #1a1a2e;
      --bg-secondary: #16213e;
      --bg-card: #0f3460;
      --text-primary: #e4e4e4;
      --text-secondary: #a0a0a0;
      --border: #233554;
      --accent: #00d2ff;
    }
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: 'SF Mono', 'Fira Code', 'Cascadia Code', monospace;
      background: var(--bg-primary);
      color: var(--text-primary);
      min-height: 100vh;
      padding: 20px;
    }
    header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 24px;
      padding-bottom: 16px;
      border-bottom: 1px solid var(--border);
      flex-wrap: wrap;
      gap: 12px;
    }
    h1 {
      font-size: 1.5rem;
      font-weight: 600;
      background: linear-gradient(90deg, #00d2ff, #7b2ff7);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }
    .meta {
      display: flex;
      gap: 16px;
      align-items: center;
      font-size: 0.85rem;
      color: var(--text-secondary);
      flex-wrap: wrap;
    }
    .meta span { display: flex; align-items: center; gap: 4px; }
    .counter {
      background: var(--bg-card);
      padding: 4px 12px;
      border-radius: 4px;
      border: 1px solid var(--border);
    }
    .counter-value {
      color: var(--accent);
      font-weight: bold;
    }
    button {
      background: var(--bg-card);
      color: var(--accent);
      border: 1px solid var(--accent);
      padding: 6px 16px;
      border-radius: 4px;
      cursor: pointer;
      font-family: inherit;
      font-size: 0.85rem;
      transition: all 0.2s;
    }
    button:hover { background: var(--accent); color: var(--bg-primary); }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
      gap: 16px;
      margin-bottom: 32px;
    }
    .card {
      background: var(--bg-secondary);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 16px;
      transition: border-color 0.3s;
    }
    .card:hover { border-color: var(--accent); }
    .card-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 12px;
    }
    .agent-name { font-weight: 600; font-size: 0.95rem; }
    .status-badge {
      padding: 2px 10px;
      border-radius: 12px;
      font-size: 0.75rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }
    .card-body {
      font-size: 0.8rem;
      color: var(--text-secondary);
    }
    .card-body .timestamp { margin-top: 8px; }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 0.85rem;
      margin-top: 24px;
    }
    th, td {
      padding: 10px 14px;
      text-align: left;
      border-bottom: 1px solid var(--border);
    }
    th {
      background: var(--bg-secondary);
      color: var(--accent);
      font-weight: 600;
      position: sticky;
      top: 0;
    }
    tr:hover { background: var(--bg-secondary); }
    .log-section { margin-top: 32px; }
    .log-section h2 {
      font-size: 1.1rem;
      margin-bottom: 12px;
      color: var(--accent);
    }
    .log-container {
      max-height: 400px;
      overflow-y: auto;
      border: 1px solid var(--border);
      border-radius: 8px;
    }
    #autoRefreshIndicator {
      width: 8px; height: 8px;
      border-radius: 50%;
      display: inline-block;
    }
    .pulse { animation: pulse 1s infinite; }
    @keyframes pulse {
      0%, 100% { opacity: 1; }
      50% { opacity: 0.3; }
    }
    .no-agents {
      text-align: center;
      padding: 40px;
      color: var(--text-secondary);
      font-size: 1rem;
    }
  </style>
</head>
<body>
  <header>
    <h1>&#x1F916; {{ title }}</h1>
    <div class="meta">
      <span class="counter">
        Total Agents: <span class="counter-value" id="totalAgents">0</span>
      </span>
      <span class="counter">
        Currently Working: <span class="counter-value" id="workingAgents">0</span>
      </span>
      <span class="counter">
        Total Working Time: <span class="counter-value" id="totalWorkingTime">0s</span>
      </span>
      <span>
        <span id="autoRefreshIndicator" style="background:#2EB67D" class="pulse"></span>
        Auto-refresh: 5s
      </span>
      <span id="lastUpdate">--</span>
      <button onclick="fetchData()">&#x21bb; Refresh Now</button>
    </div>
  </header>

  <div class="grid" id="agentCards"></div>

  <div class="log-section">
    <h2>Activity Log (last 100 entries)</h2>
    <div class="log-container">
      <table>
        <thead><tr><th>Timestamp</th><th>Agent</th><th>Status</th></tr></thead>
        <tbody id="logBody"></tbody>
      </table>
    </div>
  </div>

  <div class="log-section" style="margin-top:32px">
    <h2>&#x1F4C8; Concurrent Working Agents</h2>
    <div style="background:var(--bg-secondary);border:1px solid var(--border);border-radius:8px;padding:16px;">
      <canvas id="concurrencyChart" width="900" height="260" style="width:100%;height:260px;"></canvas>
    </div>
  </div>

  <script>
    const STATUS_COLORS = {
      working:   '#2EB67D',
      waiting:   '#ECB22E',
      completed: '#36C5F0',
      idle:      '#888888',
      blocked:   '#E01E5A',
      error:     '#E01E5A',
    };

    function statusColor(s) {
      return STATUS_COLORS[(s || '').toLowerCase()] || '#888888';
    }

    function fetchData() {
      Promise.all([
        fetch('/api/status').then(r => r.json()),
        fetch('/api/concurrency').then(r => r.json())
      ])
        .then(([statusData, concData]) => {
          renderCards(statusData.current);
          renderLog(statusData.log);
          renderConcurrencyChart(concData);
          updateCounters(statusData.current);
          document.getElementById('lastUpdate').textContent =
            'Updated: ' + new Date().toLocaleTimeString();
        })
        .catch(err => console.error('Fetch error:', err));
    }

    function updateCounters(agents) {
      const total = Object.keys(agents).length;
      const working = Object.values(agents).filter(a => a.status === 'working').length;
      const totalSecs = Object.values(agents).reduce((sum, a) => sum + (a.working_seconds || 0), 0);
      document.getElementById('totalAgents').textContent = total;
      document.getElementById('workingAgents').textContent = working;
      document.getElementById('totalWorkingTime').textContent = fmtDuration(totalSecs);
    }

    function fmtDuration(secs) {
      if (!secs || secs <= 0) return '0s';
      const h = Math.floor(secs / 3600);
      const m = Math.floor((secs % 3600) / 60);
      const s = secs % 60;
      if (h > 0) return h + 'h ' + m + 'm ' + s + 's';
      if (m > 0) return m + 'm ' + s + 's';
      return s + 's';
    }

    function renderCards(agents) {
      const grid = document.getElementById('agentCards');
      grid.innerHTML = '';
      const entries = Object.entries(agents);
      if (entries.length === 0) {
        grid.innerHTML = '<div class="no-agents">No agents registered yet. Agents will appear when they post status updates.</div>';
        return;
      }
      // Sort by name for consistent ordering
      entries.sort((a, b) => a[0].localeCompare(b[0]));
      for (const [name, info] of entries) {
        const color = statusColor(info.status);
        grid.innerHTML += `
          <div class="card" style="border-left: 3px solid ${color}">
            <div class="card-header">
              <span class="agent-name">${name}</span>
              <span class="status-badge" style="background:${color}22;color:${color};border:1px solid ${color}">${info.status || 'idle'}</span>
            </div>
            <div class="card-body">
              <div class="timestamp">Last update: ${info.timestamp || 'never'}</div>
              <div class="timestamp">Total working time: ${fmtDuration(info.working_seconds)}</div>
            </div>
          </div>`;
      }
    }

    function renderLog(rows) {
      const body = document.getElementById('logBody');
      body.innerHTML = '';
      if (rows.length === 0) {
        body.innerHTML = '<tr><td colspan="3" style="text-align:center;color:var(--text-secondary)">No activity yet</td></tr>';
        return;
      }
      rows.forEach(r => {
        const color = statusColor(r.status);
        body.innerHTML += `<tr><td>${r.timestamp}</td><td>${r.agent_name}</td><td style="color:${color}">${r.status}</td></tr>`;
      });
    }

    function renderConcurrencyChart(data) {
      const canvas = document.getElementById('concurrencyChart');
      const ctx = canvas.getContext('2d');
      const dpr = window.devicePixelRatio || 1;
      const rect = canvas.getBoundingClientRect();
      canvas.width = rect.width * dpr;
      canvas.height = rect.height * dpr;
      ctx.scale(dpr, dpr);
      const W = rect.width, H = rect.height;

      const points = data.points || [];
      const maxAgents = Math.max(data.max_agents || 1, 1);
      const tMin = data.t_min || 0;
      const tMax = data.t_max || 1;

      const pad = {top: 20, right: 20, bottom: 40, left: 50};
      const plotW = W - pad.left - pad.right;
      const plotH = H - pad.top - pad.bottom;

      ctx.clearRect(0, 0, W, H);

      // Grid lines
      ctx.strokeStyle = '#233554';
      ctx.lineWidth = 0.5;
      for (let i = 0; i <= maxAgents; i++) {
        const y = pad.top + plotH - (i / maxAgents) * plotH;
        ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(pad.left + plotW, y); ctx.stroke();
      }

      // Y-axis labels
      ctx.fillStyle = '#a0a0a0';
      ctx.font = '11px SF Mono, Fira Code, monospace';
      ctx.textAlign = 'right';
      ctx.textBaseline = 'middle';
      for (let i = 0; i <= maxAgents; i += Math.max(1, Math.floor(maxAgents / 5))) {
        const y = pad.top + plotH - (i / maxAgents) * plotH;
        ctx.fillText(i, pad.left - 8, y);
      }

      // Y-axis title
      ctx.save();
      ctx.translate(14, pad.top + plotH / 2);
      ctx.rotate(-Math.PI / 2);
      ctx.textAlign = 'center';
      ctx.fillStyle = '#00d2ff';
      ctx.font = '12px SF Mono, Fira Code, monospace';
      ctx.fillText('Agents', 0, 0);
      ctx.restore();

      // X-axis labels (time)
      ctx.textAlign = 'center';
      ctx.textBaseline = 'top';
      ctx.fillStyle = '#a0a0a0';
      ctx.font = '11px SF Mono, Fira Code, monospace';
      const span = tMax - tMin;
      const tickCount = Math.min(8, Math.max(points.length, 1));
      for (let i = 0; i <= tickCount; i++) {
        const t = tMin + (i / tickCount) * span;
        const x = pad.left + (i / tickCount) * plotW;
        const d = new Date(t * 1000);
        const lbl = d.toLocaleTimeString([], {hour:'2-digit', minute:'2-digit', second:'2-digit'});
        ctx.fillText(lbl, x, pad.top + plotH + 6);
        ctx.strokeStyle = '#233554'; ctx.lineWidth = 0.3;
        ctx.beginPath(); ctx.moveTo(x, pad.top); ctx.lineTo(x, pad.top + plotH); ctx.stroke();
      }

      if (points.length < 2) {
        ctx.fillStyle = '#a0a0a0';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.font = '14px SF Mono, Fira Code, monospace';
        ctx.fillText('Waiting for data…', W / 2, H / 2);
        return;
      }

      // Now-line
      const nowFrac = (data.t_now - tMin) / span;
      const nowPx = pad.left + nowFrac * plotW;
      ctx.save();
      ctx.setLineDash([4, 4]);
      ctx.strokeStyle = '#ECB22E';
      ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(nowPx, pad.top); ctx.lineTo(nowPx, pad.top + plotH); ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = '#ECB22E';
      ctx.font = '10px SF Mono, Fira Code, monospace';
      ctx.textAlign = 'center';
      ctx.fillText('now', nowPx, pad.top - 6);
      ctx.restore();

      // Stepped area fill
      ctx.beginPath();
      let firstX = pad.left + ((points[0].t - tMin) / span) * plotW;
      let firstY = pad.top + plotH - (points[0].count / maxAgents) * plotH;
      ctx.moveTo(firstX, pad.top + plotH);
      ctx.lineTo(firstX, firstY);
      for (let i = 1; i < points.length; i++) {
        const px = pad.left + ((points[i].t - tMin) / span) * plotW;
        const py = pad.top + plotH - (points[i].count / maxAgents) * plotH;
        const prevY = pad.top + plotH - (points[i - 1].count / maxAgents) * plotH;
        ctx.lineTo(px, prevY);  // horizontal step
        ctx.lineTo(px, py);     // vertical step
      }
      const lastX = pad.left + ((points[points.length - 1].t - tMin) / span) * plotW;
      const lastY = pad.top + plotH - (points[points.length - 1].count / maxAgents) * plotH;
      // extend to now
      ctx.lineTo(nowPx, lastY);
      ctx.lineTo(nowPx, pad.top + plotH);
      ctx.closePath();

      const grad = ctx.createLinearGradient(0, pad.top, 0, pad.top + plotH);
      grad.addColorStop(0, 'rgba(0, 210, 255, 0.35)');
      grad.addColorStop(1, 'rgba(0, 210, 255, 0.03)');
      ctx.fillStyle = grad;
      ctx.fill();

      // Stepped line
      ctx.beginPath();
      ctx.moveTo(firstX, firstY);
      for (let i = 1; i < points.length; i++) {
        const px = pad.left + ((points[i].t - tMin) / span) * plotW;
        const py = pad.top + plotH - (points[i].count / maxAgents) * plotH;
        const prevY = pad.top + plotH - (points[i - 1].count / maxAgents) * plotH;
        ctx.lineTo(px, prevY);
        ctx.lineTo(px, py);
      }
      ctx.lineTo(nowPx, lastY);
      ctx.strokeStyle = '#00d2ff';
      ctx.lineWidth = 2;
      ctx.stroke();

      // Dot at current value
      ctx.beginPath();
      ctx.arc(nowPx, lastY, 4, 0, Math.PI * 2);
      ctx.fillStyle = '#00d2ff';
      ctx.fill();
      ctx.fillStyle = '#e4e4e4';
      ctx.font = 'bold 12px SF Mono, Fira Code, monospace';
      ctx.textAlign = 'left';
      ctx.fillText(points[points.length - 1].count, nowPx + 8, lastY + 4);
    }

    fetchData();
    setInterval(fetchData, 5000);
  </script>
</body>
</html>
"""


def read_csv():
    """Read the CSV file and return all rows."""
    rows = []
    if not os.path.exists(CSV_PATH):
        return rows
    try:
        with open(CSV_PATH, "r", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row)
    except Exception:
        pass
    return rows


def get_known_agents():
    """Get set of all agents that have ever posted status updates."""
    rows = read_csv()
    agents = set()
    for row in rows:
        name = row.get("agent_name", "")
        if name:
            agents.add(name)
    return agents


def write_status(agent_name, status):
    """Append a status row to the CSV file."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    # Ensure directory exists
    csv_dir = os.path.dirname(CSV_PATH)
    if csv_dir and not os.path.exists(csv_dir):
        os.makedirs(csv_dir, exist_ok=True)
    file_exists = os.path.exists(CSV_PATH) and os.path.getsize(CSV_PATH) > 0
    with open(CSV_PATH, "a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["timestamp", "agent_name", "status"])
        writer.writerow([ts, agent_name, status])


def get_current_status():
    """Get the most recent status for each agent, including total working time."""
    rows = read_csv()
    known_agents = get_known_agents()

    # Initialize all known agents
    current = {}
    for name in known_agents:
        current[name] = {"status": "idle", "timestamp": "never", "working_seconds": 0}

    # Track working intervals per agent
    working_start = {}  # agent -> timestamp when "working" began
    working_totals = {name: 0.0 for name in known_agents}

    for row in rows:
        name = row.get("agent_name", "")
        status = row.get("status", "idle")
        ts_str = row.get("timestamp", "")
        if name not in current:
            continue
        try:
            ts = datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=timezone.utc
            ).timestamp()
        except (ValueError, TypeError):
            ts = None

        if status == "working":
            if name not in working_start and ts is not None:
                working_start[name] = ts
        else:
            if name in working_start and ts is not None:
                working_totals[name] += ts - working_start[name]
                del working_start[name]

        current[name] = {"status": status, "timestamp": ts_str}

    # Add any still-working time up to now
    now = datetime.now(timezone.utc).timestamp()
    for name, start in working_start.items():
        working_totals[name] += now - start

    for name in known_agents:
        current[name]["working_seconds"] = round(working_totals.get(name, 0))

    return current


@app.route("/")
def index():
    return render_template_string(DASHBOARD_HTML, title=DASHBOARD_TITLE)


@app.route("/api/status")
def api_status():
    current = get_current_status()
    rows = read_csv()
    # Return last 100 entries, newest first
    log = list(reversed(rows[-100:]))
    return jsonify({"current": current, "log": log})


@app.route("/api/update/<agent_name>/<status>", methods=["POST"])
def api_update(agent_name, status):
    """API endpoint to update agent status. Agents self-register by posting."""
    status_lower = status.lower()
    if status_lower not in VALID_STATUSES:
        return jsonify({
            "ok": False,
            "error": f"Invalid status '{status}'. Valid: {', '.join(sorted(VALID_STATUSES))}"
        }), 400
    write_status(agent_name, status_lower)
    return jsonify({"ok": True, "agent": agent_name, "status": status_lower})


@app.route("/api/concurrency")
def api_concurrency():
    """Return time-series data of concurrent working agents for the chart."""
    rows = read_csv()
    known_agents = get_known_agents()
    max_agents = max(len(known_agents), 1)

    if not rows:
        now = datetime.now(timezone.utc).timestamp()
        return jsonify({
            "points": [],
            "max_agents": max_agents,
            "t_min": now,
            "t_max": now + 300,
            "t_now": now,
        })

    # Parse all timestamps and build events in chronological order
    events = []
    for row in rows:
        ts_str = row.get("timestamp", "")
        try:
            ts = datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=timezone.utc
            ).timestamp()
        except (ValueError, TypeError):
            continue
        events.append((ts, row.get("agent_name", ""), row.get("status", "")))

    if not events:
        now = datetime.now(timezone.utc).timestamp()
        return jsonify({
            "points": [],
            "max_agents": max_agents,
            "t_min": now,
            "t_max": now + 300,
            "t_now": now,
        })

    # Walk events chronologically, tracking each agent's current status
    agent_status = {}
    points = []
    prev_count = -1
    for ts, agent, status in events:
        agent_status[agent] = status
        count = sum(1 for s in agent_status.values() if s == "working")
        if count != prev_count:
            points.append({"t": ts, "count": count})
            prev_count = count

    now = datetime.now(timezone.utc).timestamp()
    t_min = events[0][0]
    t_max = now + 300  # 5 minutes into the future

    return jsonify({
        "points": points,
        "max_agents": max_agents,
        "t_min": t_min,
        "t_max": t_max,
        "t_now": now,
    })


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print(f"  {DASHBOARD_TITLE}")
    print(f"  Open http://localhost:{DASHBOARD_PORT} in your browser")
    print(f"  CSV path: {CSV_PATH}")
    print("=" * 60 + "\n")
    app.run(host="0.0.0.0", port=DASHBOARD_PORT, debug=False)
