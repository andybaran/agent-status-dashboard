#!/usr/bin/env python3
"""
Agent Status Dashboard

A lightweight Flask web application that displays real-time agent status
from a CSV file. Agents register dynamically by posting status updates.
The dashboard auto-refreshes every 5 seconds.

Styled to be compliant with HashiCorp branding and the Helios Design System
(HDS) design tokens — colors, typography, spacing, elevation, and component
patterns mirror HCP Terraform UI conventions.

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

# HDS-aligned status colors
STATUS_COLORS = {
    "working":   "#008a22",  # HDS foreground-success
    "waiting":   "#b35900",  # HDS foreground-warning
    "completed": "#0c56e9",  # HDS foreground-action
    "idle":      "#656a76",  # HDS foreground-faint
    "blocked":   "#c00005",  # HDS foreground-critical
    "error":     "#c00005",  # HDS foreground-critical
}

STATUS_SURFACES = {
    "working":   "#e4f7e6",  # HDS surface-success
    "waiting":   "#fff3d6",  # HDS surface-warning
    "completed": "#e1ecff",  # HDS surface-highlight
    "idle":      "#f5f5f6",  # HDS surface-faint
    "blocked":   "#ffe0e0",  # HDS surface-critical
    "error":     "#ffe0e0",  # HDS surface-critical
}

STATUS_BORDERS = {
    "working":   "#008a22",  # HDS border-success
    "waiting":   "#b35900",  # HDS border-warning
    "completed": "#0c56e9",  # HDS border-action
    "idle":      "#d2d5db",  # HDS border-primary
    "blocked":   "#c00005",  # HDS border-critical
    "error":     "#c00005",  # HDS border-critical
}

# HashiCorp logo SVG (simplified mark)
HASHICORP_LOGO_SVG = '''<svg width="28" height="28" viewBox="0 0 36 36" fill="none" xmlns="http://www.w3.org/2000/svg">
  <path d="M21.625 0L14.375 4.18v11.773l-7.25-4.178V4.18L0 8.358v19.284L7.125 31.82V20.047l7.25 4.18v11.773L21.625 31.82V20.047L28.75 24.225V13.953L36 9.775 21.625 0z" fill="white"/>
</svg>'''

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{{ title }}</title>
  <style>
    /* ── HDS Design Token Mapping ──────────────────────────────── */
    :root {
      /* Foreground (text) — HDS semantic colors */
      --hds-foreground-strong:   #0c0c0e;
      --hds-foreground-primary:  #3b3d45;
      --hds-foreground-faint:    #656a76;
      --hds-foreground-disabled: #8c909c;
      --hds-foreground-action:   #0c56e9;
      --hds-foreground-success:  #008a22;
      --hds-foreground-warning:  #b35900;
      --hds-foreground-critical: #c00005;

      /* Surface (background) */
      --hds-surface-primary:     #ffffff;
      --hds-surface-faint:       #f5f5f6;
      --hds-surface-strong:      #ebebed;
      --hds-surface-interactive-hover: #f9fafb;

      /* Border */
      --hds-border-primary:      #d2d5db;
      --hds-border-faint:        #ebebed;
      --hds-border-strong:       #8c909c;

      /* Brand */
      --hds-brand-hashicorp:     #000000;

      /* App header — matches HCP dark header */
      --hds-header-bg:           #1d1f30;
      --hds-header-fg:           #ffffff;

      /* Typography — HDS system font stacks */
      --hds-font-text: -apple-system, BlinkMacSystemFont, "Segoe UI", "Helvetica Neue", Arial, sans-serif;
      --hds-font-code: ui-monospace, SFMono-Regular, Menlo, Consolas, Monaco, monospace;

      /* Spacing — HDS scale */
      --hds-space-100: 8px;
      --hds-space-150: 12px;
      --hds-space-200: 16px;
      --hds-space-300: 24px;
      --hds-space-400: 32px;
      --hds-space-500: 48px;

      /* Border radius — HDS scale */
      --hds-radius-small:  5px;
      --hds-radius-medium: 6px;
      --hds-radius-large:  8px;

      /* Elevation / Shadows — HDS scale */
      --hds-elevation-low:  0 1px 2px 0 rgba(0,0,0,0.06);
      --hds-elevation-mid:  0 2px 4px 0 rgba(0,0,0,0.06), 0 4px 12px -2px rgba(0,0,0,0.08);
      --hds-elevation-high: 0 4px 6px 0 rgba(0,0,0,0.06), 0 12px 20px -4px rgba(0,0,0,0.10);
    }

    /* ── Reset ─────────────────────────────────────────────────── */
    *, *::before, *::after { margin: 0; padding: 0; box-sizing: border-box; }

    body {
      font-family: var(--hds-font-text);
      font-size: 0.875rem;
      line-height: 1.25rem;
      color: var(--hds-foreground-primary);
      background: var(--hds-surface-faint);
      min-height: 100vh;
    }

    /* ── App Header — mirrors HCP Terraform top bar ────────────── */
    .app-header {
      height: 60px;
      background: var(--hds-header-bg);
      display: flex;
      align-items: center;
      padding: 0 var(--hds-space-300);
      gap: var(--hds-space-200);
      color: var(--hds-header-fg);
      box-shadow: var(--hds-elevation-low);
      position: sticky;
      top: 0;
      z-index: 100;
    }
    .app-header .logo { display: flex; align-items: center; gap: var(--hds-space-100); }
    .app-header .logo-divider {
      width: 1px; height: 24px;
      background: rgba(255,255,255,0.2);
      margin: 0 var(--hds-space-100);
    }
    .app-header h1 {
      font-size: 1rem;
      font-weight: 600;
      color: var(--hds-header-fg);
      letter-spacing: -0.01em;
    }
    .app-header .header-right {
      margin-left: auto;
      display: flex;
      align-items: center;
      gap: var(--hds-space-200);
      font-size: 0.8125rem;
      color: rgba(255,255,255,0.7);
    }
    .app-header .header-right .refresh-indicator {
      width: 8px; height: 8px;
      border-radius: 50%;
      background: #2EB67D;
      display: inline-block;
    }
    .pulse { animation: pulse 2s ease-in-out infinite; }
    @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.3} }

    /* ── Page Content ──────────────────────────────────────────── */
    .page-content { padding: var(--hds-space-300); max-width: 1440px; margin: 0 auto; }

    /* ── Stats Bar — HDS counter badges ────────────────────────── */
    .stats-bar {
      display: flex;
      gap: var(--hds-space-200);
      margin-bottom: var(--hds-space-300);
      flex-wrap: wrap;
      align-items: center;
    }
    .stat-card {
      background: var(--hds-surface-primary);
      border: 1px solid var(--hds-border-primary);
      border-radius: var(--hds-radius-medium);
      padding: var(--hds-space-150) var(--hds-space-200);
      box-shadow: var(--hds-elevation-low);
      display: flex;
      flex-direction: column;
      min-width: 140px;
    }
    .stat-card .stat-label {
      font-size: 0.75rem;
      color: var(--hds-foreground-faint);
      font-weight: 500;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      margin-bottom: 2px;
    }
    .stat-card .stat-value {
      font-size: 1.25rem;
      font-weight: 700;
      color: var(--hds-foreground-strong);
    }
    .stat-card .stat-value.accent { color: var(--hds-foreground-action); }

    .refresh-btn {
      margin-left: auto;
      background: var(--hds-surface-primary);
      color: var(--hds-foreground-action);
      border: 1px solid var(--hds-border-primary);
      padding: var(--hds-space-100) var(--hds-space-200);
      border-radius: var(--hds-radius-small);
      cursor: pointer;
      font-family: var(--hds-font-text);
      font-size: 0.8125rem;
      font-weight: 500;
      transition: all 0.15s;
      display: flex; align-items: center; gap: 6px;
    }
    .refresh-btn:hover {
      background: var(--hds-surface-faint);
      border-color: var(--hds-foreground-action);
    }
    .refresh-btn:focus-visible {
      outline: none;
      box-shadow: inset 0 0 0 1px #0c56e9, 0 0 0 3px #5990ff;
    }

    /* ── Agent Cards Grid — HDS Card pattern ───────────────────── */
    .section-heading {
      font-size: 1rem;
      font-weight: 600;
      color: var(--hds-foreground-strong);
      margin-bottom: var(--hds-space-200);
      display: flex;
      align-items: center;
      gap: var(--hds-space-100);
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
      gap: var(--hds-space-200);
      margin-bottom: var(--hds-space-400);
    }
    .card {
      background: var(--hds-surface-primary);
      border: 1px solid var(--hds-border-primary);
      border-radius: var(--hds-radius-large);
      padding: var(--hds-space-200);
      box-shadow: var(--hds-elevation-low);
      transition: box-shadow 0.15s, border-color 0.15s;
      border-left: 3px solid var(--hds-border-primary);
    }
    .card:hover {
      box-shadow: var(--hds-elevation-mid);
      border-color: var(--hds-border-strong);
    }
    .card-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: var(--hds-space-150);
    }
    .agent-name {
      font-weight: 600;
      font-size: 0.875rem;
      color: var(--hds-foreground-strong);
    }

    /* ── HDS Badge-style status pill ───────────────────────────── */
    .status-badge {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      padding: 2px 10px;
      border-radius: 4px;
      font-size: 0.75rem;
      font-weight: 600;
      text-transform: capitalize;
      letter-spacing: 0.02em;
      border: 1px solid transparent;
    }
    .status-badge::before {
      content: '';
      width: 6px; height: 6px;
      border-radius: 50%;
      display: inline-block;
    }
    .card-meta {
      font-size: 0.8125rem;
      color: var(--hds-foreground-faint);
      display: flex; flex-direction: column; gap: 4px;
    }
    .card-meta strong { font-weight: 500; color: var(--hds-foreground-primary); }

    /* ── Activity Log Table — HDS Table pattern ────────────────── */
    .log-section {
      margin-top: var(--hds-space-300);
    }
    .log-container {
      background: var(--hds-surface-primary);
      border: 1px solid var(--hds-border-primary);
      border-radius: var(--hds-radius-large);
      box-shadow: var(--hds-elevation-low);
      overflow: hidden;
    }
    .log-container .table-scroll {
      max-height: 400px;
      overflow-y: auto;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 0.8125rem;
    }
    th {
      padding: 10px var(--hds-space-200);
      text-align: left;
      background: var(--hds-surface-faint);
      color: var(--hds-foreground-strong);
      font-weight: 600;
      font-size: 0.75rem;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      border-bottom: 1px solid var(--hds-border-primary);
      position: sticky;
      top: 0;
      z-index: 1;
    }
    td {
      padding: 8px var(--hds-space-200);
      border-bottom: 1px solid var(--hds-border-faint);
      color: var(--hds-foreground-primary);
    }
    tr:hover td { background: var(--hds-surface-interactive-hover); }
    td.ts { font-family: var(--hds-font-code); font-size: 0.75rem; color: var(--hds-foreground-faint); }

    /* ── Chart Section ─────────────────────────────────────────── */
    .chart-section { margin-top: var(--hds-space-300); }
    .chart-container {
      background: var(--hds-surface-primary);
      border: 1px solid var(--hds-border-primary);
      border-radius: var(--hds-radius-large);
      box-shadow: var(--hds-elevation-low);
      padding: var(--hds-space-200);
    }

    .no-agents {
      text-align: center;
      padding: var(--hds-space-500);
      color: var(--hds-foreground-faint);
      font-size: 0.875rem;
    }

    .last-update-text {
      font-size: 0.75rem;
      color: var(--hds-foreground-faint);
      margin-top: var(--hds-space-200);
      text-align: right;
    }
  </style>
</head>
<body>

  <!-- ── App Header — HCP Terraform-style top bar ─────────────── -->
  <div class="app-header">
    <div class="logo">
      """ + HASHICORP_LOGO_SVG + """
      <div class="logo-divider"></div>
      <h1>{{ title }}</h1>
    </div>
    <div class="header-right">
      <span><span class="refresh-indicator pulse"></span>&nbsp;Live</span>
      <span id="lastUpdate">--</span>
    </div>
  </div>

  <!-- ── Page Content ──────────────────────────────────────────── -->
  <div class="page-content">

    <!-- Stats Bar -->
    <div class="stats-bar">
      <div class="stat-card">
        <span class="stat-label">Total Agents</span>
        <span class="stat-value" id="totalAgents">0</span>
      </div>
      <div class="stat-card">
        <span class="stat-label">Currently Working</span>
        <span class="stat-value accent" id="workingAgents">0</span>
      </div>
      <div class="stat-card">
        <span class="stat-label">Total Working Time</span>
        <span class="stat-value" id="totalWorkingTime">0s</span>
      </div>
      <button class="refresh-btn" onclick="fetchData()">&#x21bb; Refresh</button>
    </div>

    <!-- Agent Cards -->
    <div class="section-heading">Agents</div>
    <div class="grid" id="agentCards"></div>

    <!-- Concurrency Chart -->
    <div class="chart-section">
      <div class="section-heading">Concurrent Working Agents</div>
      <div class="chart-container">
        <canvas id="concurrencyChart" width="900" height="240" style="width:100%;height:240px;"></canvas>
      </div>
    </div>

    <!-- Activity Log -->
    <div class="log-section">
      <div class="section-heading">Activity Log</div>
      <div class="log-container">
        <div class="table-scroll">
          <table>
            <thead><tr><th>Timestamp</th><th>Agent</th><th>Status</th></tr></thead>
            <tbody id="logBody"></tbody>
          </table>
        </div>
      </div>
    </div>

    <div class="last-update-text" id="lastUpdateBottom"></div>
  </div>

  <script>
    /* ── HDS-aligned status colors ──────────────────────────── */
    const STATUS_COLORS = {
      working:   '#008a22',
      waiting:   '#b35900',
      completed: '#0c56e9',
      idle:      '#656a76',
      blocked:   '#c00005',
      error:     '#c00005',
    };
    const STATUS_SURFACES = {
      working:   '#e4f7e6',
      waiting:   '#fff3d6',
      completed: '#e1ecff',
      idle:      '#f5f5f6',
      blocked:   '#ffe0e0',
      error:     '#ffe0e0',
    };

    function statusColor(s)   { return STATUS_COLORS[(s||'').toLowerCase()]   || '#656a76'; }
    function statusSurface(s) { return STATUS_SURFACES[(s||'').toLowerCase()] || '#f5f5f6'; }

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
        const ts = new Date().toLocaleTimeString();
        document.getElementById('lastUpdate').textContent = ts;
        document.getElementById('lastUpdateBottom').textContent = 'Last refreshed: ' + ts;
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
      if (h > 0) return h + 'h ' + m + 'm';
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
      entries.sort((a, b) => a[0].localeCompare(b[0]));
      for (const [name, info] of entries) {
        const fg = statusColor(info.status);
        const bg = statusSurface(info.status);
        grid.innerHTML += `
          <div class="card" style="border-left-color:${fg}">
            <div class="card-header">
              <span class="agent-name">${name}</span>
              <span class="status-badge" style="background:${bg};color:${fg};border-color:${fg}"><span></span>${info.status || 'idle'}</span>
            </div>
            <div class="card-meta">
              <div>Last update: <strong>${info.timestamp || 'never'}</strong></div>
              <div>Total working time: <strong>${fmtDuration(info.working_seconds)}</strong></div>
            </div>
          </div>`;
      }
    }

    function renderLog(rows) {
      const body = document.getElementById('logBody');
      body.innerHTML = '';
      if (rows.length === 0) {
        body.innerHTML = '<tr><td colspan="3" style="text-align:center;color:var(--hds-foreground-faint)">No activity yet</td></tr>';
        return;
      }
      rows.forEach(r => {
        const fg = statusColor(r.status);
        const bg = statusSurface(r.status);
        body.innerHTML += `<tr>
          <td class="ts">${r.timestamp}</td>
          <td>${r.agent_name}</td>
          <td><span class="status-badge" style="background:${bg};color:${fg};border-color:${fg}">${r.status}</span></td>
        </tr>`;
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

      const pad = {top: 24, right: 24, bottom: 36, left: 48};
      const plotW = W - pad.left - pad.right;
      const plotH = H - pad.top - pad.bottom;

      ctx.clearRect(0, 0, W, H);

      /* Grid lines — HDS border-faint */
      ctx.strokeStyle = '#ebebed';
      ctx.lineWidth = 1;
      for (let i = 0; i <= maxAgents; i++) {
        const y = pad.top + plotH - (i / maxAgents) * plotH;
        ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(pad.left + plotW, y); ctx.stroke();
      }

      /* Y-axis labels */
      ctx.fillStyle = '#656a76';
      ctx.font = '11px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
      ctx.textAlign = 'right';
      ctx.textBaseline = 'middle';
      for (let i = 0; i <= maxAgents; i += Math.max(1, Math.floor(maxAgents / 5))) {
        const y = pad.top + plotH - (i / maxAgents) * plotH;
        ctx.fillText(i, pad.left - 10, y);
      }

      /* Y-axis title */
      ctx.save();
      ctx.translate(14, pad.top + plotH / 2);
      ctx.rotate(-Math.PI / 2);
      ctx.textAlign = 'center';
      ctx.fillStyle = '#3b3d45';
      ctx.font = '500 12px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
      ctx.fillText('Agents', 0, 0);
      ctx.restore();

      /* X-axis labels */
      ctx.textAlign = 'center';
      ctx.textBaseline = 'top';
      ctx.fillStyle = '#656a76';
      ctx.font = '11px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
      const span = tMax - tMin;
      const tickCount = Math.min(8, Math.max(points.length, 1));
      for (let i = 0; i <= tickCount; i++) {
        const t = tMin + (i / tickCount) * span;
        const x = pad.left + (i / tickCount) * plotW;
        const d = new Date(t * 1000);
        const lbl = d.toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'});
        ctx.fillText(lbl, x, pad.top + plotH + 8);
        ctx.strokeStyle = '#ebebed'; ctx.lineWidth = 0.5;
        ctx.beginPath(); ctx.moveTo(x, pad.top); ctx.lineTo(x, pad.top + plotH); ctx.stroke();
      }

      if (points.length < 2) {
        ctx.fillStyle = '#656a76';
        ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
        ctx.font = '13px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
        ctx.fillText('Waiting for data\u2026', W / 2, H / 2);
        return;
      }

      /* Now-line — HDS warning colour */
      const nowFrac = (data.t_now - tMin) / span;
      const nowPx = pad.left + nowFrac * plotW;
      ctx.save();
      ctx.setLineDash([4, 4]);
      ctx.strokeStyle = '#b35900';
      ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(nowPx, pad.top); ctx.lineTo(nowPx, pad.top + plotH); ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = '#b35900';
      ctx.font = '500 10px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText('now', nowPx, pad.top - 10);
      ctx.restore();

      /* Stepped area fill — HDS action colour (blue) */
      ctx.beginPath();
      let firstX = pad.left + ((points[0].t - tMin) / span) * plotW;
      let firstY = pad.top + plotH - (points[0].count / maxAgents) * plotH;
      ctx.moveTo(firstX, pad.top + plotH);
      ctx.lineTo(firstX, firstY);
      for (let i = 1; i < points.length; i++) {
        const px = pad.left + ((points[i].t - tMin) / span) * plotW;
        const py = pad.top + plotH - (points[i].count / maxAgents) * plotH;
        const prevY = pad.top + plotH - (points[i - 1].count / maxAgents) * plotH;
        ctx.lineTo(px, prevY);
        ctx.lineTo(px, py);
      }
      const lastX = pad.left + ((points[points.length - 1].t - tMin) / span) * plotW;
      const lastY = pad.top + plotH - (points[points.length - 1].count / maxAgents) * plotH;
      ctx.lineTo(nowPx, lastY);
      ctx.lineTo(nowPx, pad.top + plotH);
      ctx.closePath();

      const grad = ctx.createLinearGradient(0, pad.top, 0, pad.top + plotH);
      grad.addColorStop(0, 'rgba(12, 86, 233, 0.18)');
      grad.addColorStop(1, 'rgba(12, 86, 233, 0.02)');
      ctx.fillStyle = grad;
      ctx.fill();

      /* Stepped line */
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
      ctx.strokeStyle = '#0c56e9';
      ctx.lineWidth = 2;
      ctx.stroke();

      /* Dot at current value */
      ctx.beginPath();
      ctx.arc(nowPx, lastY, 4, 0, Math.PI * 2);
      ctx.fillStyle = '#0c56e9';
      ctx.fill();
      ctx.fillStyle = '#3b3d45';
      ctx.font = 'bold 12px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
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
