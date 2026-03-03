#!/usr/bin/env python3
"""
Agent Status Dashboard

A lightweight Flask web application that displays real-time agent status
from a SQLite database. Agents register dynamically by posting status updates.
The dashboard auto-refreshes every 5 seconds.

Styled with a professional design token system — colors, typography, spacing,
elevation, and component patterns follow modern SaaS dashboard conventions.

Configuration via environment variables:
    DASHBOARD_PORT  - Port to run on (default: 5050)
    DB_PATH         - Path to SQLite database (default: ./agent_status.db)
    CSV_PATH        - Legacy CSV file to auto-import on first run (optional)
    DASHBOARD_TITLE - Title shown in the dashboard (default: Agent Status Dashboard)
    STALE_THRESHOLD_MINUTES - Minutes before a "working" agent is marked stale (default: 30)
    DASHBOARD_LOGO_SVG - Custom SVG logo (if empty, uses default robot icon)
    DASHBOARD_ACRONYMS - Comma-separated acronyms to preserve (e.g. "UI,API,CI,CD,AWS")

Usage:
    pip install flask
    python dashboard.py

Then open http://localhost:5050 in your browser.

Note: If CSV_PATH exists and DB_PATH is empty, the CSV data is automatically
imported into the SQLite database on startup.
"""

import os
import csv
import sqlite3
import json
import re
from datetime import datetime, timezone
from flask import Flask, render_template_string, jsonify, Response

app = Flask(__name__)

# Configuration from environment variables
DASHBOARD_PORT = int(os.environ.get("DASHBOARD_PORT", "5050"))
DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "agent_status.db"))
CSV_PATH = os.environ.get("CSV_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "agent_status.csv"))
DASHBOARD_TITLE = os.environ.get("DASHBOARD_TITLE", "Agent Status Dashboard")
APP_VERSION = os.environ.get("APP_VERSION", "1.2.0")

VALID_STATUSES = {"working", "waiting", "completed", "idle", "blocked", "error"}

# Acronyms that .title() mangles — maps wrong form to correct form.
# Override via DASHBOARD_ACRONYMS env var (comma-separated, e.g. "UI,API,CI,CD,AWS").
# Each acronym is stored as title-case key -> uppercase value (e.g. "Ui" -> "UI").
def _build_acronyms():
    env_val = os.environ.get("DASHBOARD_ACRONYMS", "").strip()
    if env_val:
        acronyms = {}
        for acr in env_val.split(","):
            acr = acr.strip()
            if acr:
                acronyms[acr.title()] = acr.upper()
        return acronyms
    # Default set if env var is not set
    return {
        "Ui": "UI", "Gitops": "GitOps", "Api": "API", "Ci": "CI", "Cd": "CD",
        "Hcp": "HCP", "Vso": "VSO", "Csi": "CSI", "Ldap": "LDAP", "Aws": "AWS",
    }

ACRONYMS = _build_acronyms()


def normalize_agent_name(name):
    """Normalize agent names so formatting variants collapse to the same identity.

    - Strips whitespace, replaces hyphens/underscores with spaces
    - Title-cases words, then restores known acronyms (UI, GitOps, etc.)
    - Numbered suffixes (e.g. '01', '02') are preserved as distinct agents
    """
    clean = name.strip().replace("-", " ").replace("_", " ")
    clean = re.sub(r"\s+", " ", clean)
    clean = clean.title()
    for wrong, right in ACRONYMS.items():
        clean = clean.replace(wrong, right)
    return clean

# Staleness threshold (seconds). If an agent's last update is older than this
# and its status is still "working", the dashboard displays it as "idle (stale)".
# Configurable via STALE_THRESHOLD_MINUTES env var (default: 10 minutes).
STALE_THRESHOLD = int(os.environ.get("STALE_THRESHOLD_MINUTES", "10")) * 60

# Status colors
STATUS_COLORS = {
    "working":   "#008a22",  # foreground-success
    "waiting":   "#b35900",  # foreground-warning
    "completed": "#0c56e9",  # foreground-action
    "idle":      "#656a76",  # foreground-faint
    "blocked":   "#c00005",  # foreground-critical
    "error":     "#c00005",  # foreground-critical
}

STATUS_SURFACES = {
    "working":   "#e4f7e6",  # surface-success
    "waiting":   "#fff3d6",  # surface-warning
    "completed": "#e1ecff",  # surface-highlight
    "idle":      "#f5f5f6",  # surface-faint
    "blocked":   "#ffe0e0",  # surface-critical
    "error":     "#ffe0e0",  # surface-critical
}

STATUS_BORDERS = {
    "working":   "#008a22",  # border-success
    "waiting":   "#b35900",  # border-warning
    "completed": "#0c56e9",  # border-action
    "idle":      "#d2d5db",  # border-primary
    "blocked":   "#c00005",  # border-critical
    "error":     "#c00005",  # border-critical
}

# Default logo SVG (robot/agent icon)
DEFAULT_LOGO_SVG = '''<svg width="28" height="28" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
  <rect x="4" y="8" width="16" height="12" rx="2" stroke="white" stroke-width="1.5" fill="none"/>
  <circle cx="9" cy="13" r="1.5" fill="white"/>
  <circle cx="15" cy="13" r="1.5" fill="white"/>
  <path d="M9 17h6" stroke="white" stroke-width="1.5" stroke-linecap="round"/>
  <path d="M12 8V5" stroke="white" stroke-width="1.5" stroke-linecap="round"/>
  <circle cx="12" cy="4" r="1.5" fill="white"/>
  <path d="M2 12h2M20 12h2" stroke="white" stroke-width="1.5" stroke-linecap="round"/>
</svg>'''

# Custom logo from environment variable (if set)
LOGO_SVG = os.environ.get("DASHBOARD_LOGO_SVG", "").strip() or DEFAULT_LOGO_SVG

# Lifecycle management — in-memory flag to trigger the shutdown modal on clients
_lifecycle_prompt_pending = False

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{{ title }}</title>
  <style>
    /* ── Design Token Mapping ──────────────────────────────── */
    :root {
      /* Foreground (text) — Semantic colors */
      --ds-foreground-strong:   #0c0c0e;
      --ds-foreground-primary:  #3b3d45;
      --ds-foreground-faint:    #656a76;
      --ds-foreground-disabled: #8c909c;
      --ds-foreground-action:   #0c56e9;
      --ds-foreground-success:  #008a22;
      --ds-foreground-warning:  #b35900;
      --ds-foreground-critical: #c00005;

      /* Surface (background) */
      --ds-surface-primary:     #ffffff;
      --ds-surface-faint:       #f5f5f6;
      --ds-surface-strong:      #ebebed;
      --ds-surface-interactive-hover: #f9fafb;

      /* Border */
      --ds-border-primary:      #d2d5db;
      --ds-border-faint:        #ebebed;
      --ds-border-strong:       #8c909c;

      /* Brand */
      --ds-brand-primary:       #000000;

      /* App header */
      --ds-header-bg:           #1d1f30;
      --ds-header-fg:           #ffffff;

      /* Chart — theme-aware canvas colors */
      --ds-chart-grid:          #ebebed;
      --ds-chart-label:         #656a76;
      --ds-chart-title:         #3b3d45;
      --ds-chart-line:          #0c56e9;
      --ds-chart-fill-start:    rgba(12, 86, 233, 0.18);
      --ds-chart-fill-end:      rgba(12, 86, 233, 0.02);
      --ds-chart-now:           #b35900;

      /* Typography — System font stacks */
      --ds-font-text: -apple-system, BlinkMacSystemFont, "Segoe UI", "Helvetica Neue", Arial, sans-serif;
      --ds-font-code: ui-monospace, SFMono-Regular, Menlo, Consolas, Monaco, monospace;

      /* Spacing — Design scale */
      --ds-space-100: 8px;
      --ds-space-150: 12px;
      --ds-space-200: 16px;
      --ds-space-300: 24px;
      --ds-space-400: 32px;
      --ds-space-500: 48px;

      /* Border radius — Design scale */
      --ds-radius-small:  5px;
      --ds-radius-medium: 6px;
      --ds-radius-large:  8px;

      /* Elevation / Shadows — Design scale */
      --ds-elevation-low:  0 1px 2px 0 rgba(0,0,0,0.06);
      --ds-elevation-mid:  0 2px 4px 0 rgba(0,0,0,0.06), 0 4px 12px -2px rgba(0,0,0,0.08);
      --ds-elevation-high: 0 4px 6px 0 rgba(0,0,0,0.06), 0 12px 20px -4px rgba(0,0,0,0.10);
    }

    /* ── Dark Theme — Dark palette ──────────────────────────── */
    [data-theme="dark"] {
      --ds-foreground-strong:   #f0f0f2;
      --ds-foreground-primary:  #c2c5cc;
      --ds-foreground-faint:    #8c909c;
      --ds-foreground-disabled: #656a76;
      --ds-foreground-action:   #5990ff;
      --ds-foreground-success:  #2EB67D;
      --ds-foreground-warning:  #ecb22e;
      --ds-foreground-critical: #f47174;

      --ds-surface-primary:     #1a1c2b;
      --ds-surface-faint:       #12131f;
      --ds-surface-strong:      #252739;
      --ds-surface-interactive-hover: #1f2133;

      --ds-border-primary:      #363850;
      --ds-border-faint:        #2a2c40;
      --ds-border-strong:       #4a4d66;

      --ds-brand-primary:       #ffffff;

      --ds-header-bg:           #0e0f1a;
      --ds-header-fg:           #f0f0f2;

      --ds-chart-grid:          #2a2c40;
      --ds-chart-label:         #8c909c;
      --ds-chart-title:         #c2c5cc;
      --ds-chart-line:          #5990ff;
      --ds-chart-fill-start:    rgba(89, 144, 255, 0.22);
      --ds-chart-fill-end:      rgba(89, 144, 255, 0.03);
      --ds-chart-now:           #ecb22e;

      --ds-elevation-low:  0 1px 2px 0 rgba(0,0,0,0.3);
      --ds-elevation-mid:  0 2px 4px 0 rgba(0,0,0,0.3), 0 4px 12px -2px rgba(0,0,0,0.4);
      --ds-elevation-high: 0 4px 6px 0 rgba(0,0,0,0.3), 0 12px 20px -4px rgba(0,0,0,0.5);
    }

    /* ── Reset ─────────────────────────────────────────────────── */
    *, *::before, *::after { margin: 0; padding: 0; box-sizing: border-box; }

    body {
      font-family: var(--ds-font-text);
      font-size: 0.875rem;
      line-height: 1.25rem;
      color: var(--ds-foreground-primary);
      background: var(--ds-surface-faint);
      min-height: 100vh;
    }

    /* ── App Header ────────────────────────────────────────────── */
    .app-header {
      height: 60px;
      background: var(--ds-header-bg);
      display: flex;
      align-items: center;
      padding: 0 var(--ds-space-300);
      gap: var(--ds-space-200);
      color: var(--ds-header-fg);
      box-shadow: var(--ds-elevation-low);
      position: sticky;
      top: 0;
      z-index: 100;
    }
    .app-header .logo { display: flex; align-items: center; gap: var(--ds-space-100); }
    .app-header .logo-divider {
      width: 1px; height: 24px;
      background: rgba(255,255,255,0.2);
      margin: 0 var(--ds-space-100);
    }
    .app-header h1 {
      font-size: 1rem;
      font-weight: 600;
      color: var(--ds-header-fg);
      letter-spacing: -0.01em;
    }
    .app-header .header-right {
      margin-left: auto;
      display: flex;
      align-items: center;
      gap: var(--ds-space-200);
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

    /* ── Theme Toggle — Icon button ──────────────────────────── */
    .theme-toggle {
      background: transparent;
      border: 1px solid rgba(255,255,255,0.2);
      border-radius: var(--ds-radius-small);
      color: rgba(255,255,255,0.7);
      cursor: pointer;
      padding: 6px 8px;
      font-size: 1rem;
      line-height: 1;
      transition: background 0.15s, border-color 0.15s;
      display: flex; align-items: center; gap: 4px;
    }
    .theme-toggle:hover {
      background: rgba(255,255,255,0.08);
      border-color: rgba(255,255,255,0.35);
      color: #ffffff;
    }
    .theme-toggle:focus-visible {
      outline: none;
      box-shadow: 0 0 0 3px rgba(89, 144, 255, 0.5);
    }
    .theme-toggle .icon-sun,
    .theme-toggle .icon-moon,
    .theme-toggle .icon-auto { display: none; }
    [data-theme="light"] .theme-toggle .icon-sun { display: inline; }
    [data-theme="dark"] .theme-toggle .icon-moon { display: inline; }
    .theme-toggle .icon-auto { display: inline; }
    [data-theme="light"] .theme-toggle .icon-auto,
    [data-theme="dark"] .theme-toggle .icon-auto { display: none; }

    /* ── Page Content ──────────────────────────────────────────── */
    .page-content { padding: var(--ds-space-300); max-width: 1440px; margin: 0 auto; }

    /* ── Stats Bar — Counter badges ────────────────────────────── */
    .stats-bar {
      display: flex;
      gap: var(--ds-space-200);
      margin-bottom: var(--ds-space-300);
      flex-wrap: wrap;
      align-items: center;
    }
    .stat-card {
      background: var(--ds-surface-primary);
      border: 1px solid var(--ds-border-primary);
      border-radius: var(--ds-radius-medium);
      padding: var(--ds-space-150) var(--ds-space-200);
      box-shadow: var(--ds-elevation-low);
      display: flex;
      flex-direction: column;
      min-width: 140px;
    }
    .stat-card .stat-label {
      font-size: 0.75rem;
      color: var(--ds-foreground-faint);
      font-weight: 500;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      margin-bottom: 2px;
    }
    .stat-card .stat-value {
      font-size: 1.25rem;
      font-weight: 700;
      color: var(--ds-foreground-strong);
    }
    .stat-card .stat-value.accent { color: var(--ds-foreground-action); }

    .refresh-btn {
      margin-left: auto;
      background: var(--ds-surface-primary);
      color: var(--ds-foreground-action);
      border: 1px solid var(--ds-border-primary);
      padding: var(--ds-space-100) var(--ds-space-200);
      border-radius: var(--ds-radius-small);
      cursor: pointer;
      font-family: var(--ds-font-text);
      font-size: 0.8125rem;
      font-weight: 500;
      transition: all 0.15s;
      display: flex; align-items: center; gap: 6px;
    }
    .refresh-btn:hover {
      background: var(--ds-surface-faint);
      border-color: var(--ds-foreground-action);
    }
    .refresh-btn:focus-visible {
      outline: none;
      box-shadow: inset 0 0 0 1px #0c56e9, 0 0 0 3px #5990ff;
    }

    /* ── Agent Cards Grid — Card pattern ───────────────────────── */
    .section-heading {
      font-size: 1rem;
      font-weight: 600;
      color: var(--ds-foreground-strong);
      margin-bottom: var(--ds-space-200);
      display: flex;
      align-items: center;
      gap: var(--ds-space-100);
    }
    .sort-controls {
      display: flex;
      align-items: center;
      gap: 6px;
      margin-left: var(--ds-space-100);
    }
    .sort-btn {
      background: var(--ds-surface-primary);
      border: 1px solid var(--ds-border-primary);
      border-radius: var(--ds-radius-small);
      color: var(--ds-foreground-faint);
      font-size: 0.75rem;
      padding: 3px 10px;
      cursor: pointer;
      transition: all 0.15s;
      font-family: var(--ds-font-text);
      line-height: 1.4;
    }
    .sort-btn:hover {
      border-color: var(--ds-foreground-action);
      color: var(--ds-foreground-action);
    }
    .sort-btn.active {
      background: var(--ds-foreground-action);
      border-color: var(--ds-foreground-action);
      color: #fff;
    }
    .sort-btn .arrow { font-size: 0.65rem; margin-left: 2px; }
    .reset-btn {
      background: var(--ds-surface-primary);
      border: 1px solid var(--ds-border-primary);
      border-radius: var(--ds-radius-small);
      color: var(--ds-foreground-faint);
      font-size: 0.75rem;
      padding: 3px 10px;
      cursor: pointer;
      transition: all 0.15s;
      font-family: var(--ds-font-text);
      line-height: 1.4;
      margin-left: var(--ds-space-100);
    }
    .reset-btn:hover {
      border-color: #dc3545;
      color: #dc3545;
      background: rgba(220, 53, 69, 0.05);
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
      gap: var(--ds-space-200);
      margin-bottom: var(--ds-space-400);
    }
    .card {
      background: var(--ds-surface-primary);
      border: 1px solid var(--ds-border-primary);
      border-radius: var(--ds-radius-large);
      padding: var(--ds-space-200);
      box-shadow: var(--ds-elevation-low);
      transition: box-shadow 0.15s, border-color 0.15s;
      border-left: 3px solid var(--ds-border-primary);
    }
    .card:hover {
      box-shadow: var(--ds-elevation-mid);
      border-color: var(--ds-border-strong);
    }
    .card-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: var(--ds-space-150);
    }
    .agent-name {
      font-weight: 600;
      font-size: 0.875rem;
      color: var(--ds-foreground-strong);
    }

    /* ── Badge-style status pill ───────────────────────────────── */
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
    .stale-tag {
      font-size: 0.625rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      color: var(--ds-foreground-warning);
      background: var(--ds-surface-faint);
      border: 1px solid var(--ds-foreground-warning);
      border-radius: 3px;
      padding: 1px 5px;
      margin-left: 6px;
      vertical-align: middle;
    }
    .card-meta {
      font-size: 0.8125rem;
      color: var(--ds-foreground-faint);
      display: flex; flex-direction: column; gap: 4px;
    }
    .card-meta strong { font-weight: 500; color: var(--ds-foreground-primary); }

    /* ── Activity Log Table — Table pattern ────────────────────── */
    .log-section {
      margin-top: var(--ds-space-300);
    }
    .log-container {
      background: var(--ds-surface-primary);
      border: 1px solid var(--ds-border-primary);
      border-radius: var(--ds-radius-large);
      box-shadow: var(--ds-elevation-low);
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
      padding: 10px var(--ds-space-200);
      text-align: left;
      background: var(--ds-surface-faint);
      color: var(--ds-foreground-strong);
      font-weight: 600;
      font-size: 0.75rem;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      border-bottom: 1px solid var(--ds-border-primary);
      position: sticky;
      top: 0;
      z-index: 1;
    }
    td {
      padding: 8px var(--ds-space-200);
      border-bottom: 1px solid var(--ds-border-faint);
      color: var(--ds-foreground-primary);
    }
    tr:hover td { background: var(--ds-surface-interactive-hover); }
    td.ts { font-family: var(--ds-font-code); font-size: 0.75rem; color: var(--ds-foreground-faint); }

    /* ── Chart Section ─────────────────────────────────────────── */
    .chart-section { margin-top: var(--ds-space-300); }
    .chart-container {
      background: var(--ds-surface-primary);
      border: 1px solid var(--ds-border-primary);
      border-radius: var(--ds-radius-large);
      box-shadow: var(--ds-elevation-low);
      padding: var(--ds-space-200);
    }

    .no-agents {
      text-align: center;
      padding: var(--ds-space-500);
      color: var(--ds-foreground-faint);
      font-size: 0.875rem;
    }

    /* ── Orchestrator Panel ────────────────────────────────────── */
    .orchestrator-panel {
      background: var(--ds-surface-primary);
      border: 1px solid var(--ds-border-primary);
      border-radius: var(--ds-radius-large);
      box-shadow: var(--ds-elevation-mid);
      padding: var(--ds-space-300);
      margin-bottom: var(--ds-space-300);
      border-left: 4px solid var(--ds-foreground-action);
    }
    .orchestrator-panel.hidden { display: none; }
    .orchestrator-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: var(--ds-space-200);
      flex-wrap: wrap;
      gap: var(--ds-space-100);
    }
    .orchestrator-title {
      font-size: 1rem;
      font-weight: 700;
      color: var(--ds-foreground-strong);
      display: flex;
      align-items: center;
      gap: var(--ds-space-100);
    }
    .orchestrator-title .orch-icon {
      font-size: 1.1rem;
    }
    .orchestrator-body {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: var(--ds-space-200) var(--ds-space-400);
    }
    @media (max-width: 640px) {
      .orchestrator-body { grid-template-columns: 1fr; }
    }
    .orch-field {
      display: flex;
      flex-direction: column;
      gap: 2px;
    }
    .orch-field-label {
      font-size: 0.6875rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      color: var(--ds-foreground-faint);
    }
    .orch-field-value {
      font-size: 0.875rem;
      color: var(--ds-foreground-primary);
    }
    .orch-field-value strong { font-weight: 600; color: var(--ds-foreground-strong); }
    .orch-field-value a {
      color: var(--ds-foreground-action);
      text-decoration: underline;
    }
    .orch-goal {
      grid-column: 1 / -1;
    }
    .orch-progress {
      grid-column: 1 / -1;
      background: var(--ds-surface-faint);
      border-radius: var(--ds-radius-small);
      padding: var(--ds-space-100) var(--ds-space-150);
    }
    .orch-sub-agents {
      display: flex;
      gap: var(--ds-space-200);
      flex-wrap: wrap;
    }
    .orch-sub-stat {
      display: flex;
      align-items: baseline;
      gap: 4px;
    }
    .orch-sub-stat .count {
      font-size: 1.125rem;
      font-weight: 700;
      color: var(--ds-foreground-strong);
    }
    .orch-sub-stat .label {
      font-size: 0.75rem;
      color: var(--ds-foreground-faint);
    }

    .last-update-text {
      font-size: 0.75rem;
      color: var(--ds-foreground-faint);
      margin-top: var(--ds-space-200);
      text-align: right;
    }

    /* ── Orchestrator Filter Bar ─────────────────────────────── */
    .orch-filter-bar {
      display: flex;
      align-items: center;
      gap: var(--ds-space-150);
      margin-bottom: var(--ds-space-200);
      flex-wrap: wrap;
    }
    .orch-filter-label {
      font-size: 0.75rem;
      font-weight: 600;
      color: var(--ds-foreground-faint);
      text-transform: uppercase;
      letter-spacing: 0.04em;
      white-space: nowrap;
    }
    .orch-filter-options {
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
    }
    .orch-filter-btn {
      background: var(--ds-surface-primary);
      border: 1px solid var(--ds-border-primary);
      border-radius: var(--ds-radius-small);
      color: var(--ds-foreground-faint);
      font-size: 0.8125rem;
      font-family: var(--ds-font-text);
      padding: 4px 12px;
      cursor: pointer;
      transition: all 0.15s;
      line-height: 1.4;
    }
    .orch-filter-btn:hover {
      border-color: var(--ds-foreground-action);
      color: var(--ds-foreground-action);
    }
    .orch-filter-btn.active {
      background: var(--ds-foreground-action);
      border-color: var(--ds-foreground-action);
      color: #ffffff;
      font-weight: 600;
    }

    /* ── Lifecycle Modal ─────────────────────────────────────── */
    .lifecycle-overlay {
      position: fixed;
      inset: 0;
      background: rgba(0,0,0,0.55);
      display: flex;
      align-items: center;
      justify-content: center;
      z-index: 9000;
      backdrop-filter: blur(2px);
    }
    .lifecycle-modal {
      background: var(--ds-surface-primary);
      border: 1px solid var(--ds-border-primary);
      border-radius: var(--ds-radius-large);
      box-shadow: var(--ds-elevation-high);
      padding: var(--ds-space-400);
      max-width: 480px;
      width: calc(100% - 48px);
    }
    .lifecycle-modal-header {
      display: flex;
      align-items: center;
      gap: var(--ds-space-150);
      margin-bottom: var(--ds-space-200);
    }
    .lifecycle-modal-header h2 {
      font-size: 1.125rem;
      font-weight: 700;
      color: var(--ds-foreground-strong);
    }
    .lifecycle-modal-icon {
      font-size: 1.5rem;
      line-height: 1;
    }
    .lifecycle-modal-desc {
      font-size: 0.875rem;
      color: var(--ds-foreground-primary);
      margin-bottom: var(--ds-space-300);
      line-height: 1.5;
    }
    .lifecycle-modal-actions {
      display: flex;
      flex-direction: column;
      gap: var(--ds-space-150);
    }
    .lifecycle-btn {
      display: flex;
      flex-direction: column;
      align-items: flex-start;
      gap: 2px;
      padding: var(--ds-space-150) var(--ds-space-200);
      border-radius: var(--ds-radius-medium);
      border: 1px solid var(--ds-border-primary);
      background: var(--ds-surface-primary);
      cursor: pointer;
      font-family: var(--ds-font-text);
      text-align: left;
      transition: all 0.15s;
      width: 100%;
    }
    .lifecycle-btn:hover { box-shadow: var(--ds-elevation-mid); }
    .lifecycle-btn strong {
      font-size: 0.9375rem;
      font-weight: 600;
    }
    .lifecycle-btn span {
      font-size: 0.8125rem;
      line-height: 1.4;
    }
    .lifecycle-btn-keep strong  { color: var(--ds-foreground-action); }
    .lifecycle-btn-keep:hover   { border-color: var(--ds-foreground-action); background: var(--ds-surface-faint); }
    .lifecycle-btn-keep span    { color: var(--ds-foreground-faint); }
    .lifecycle-btn-stop strong  { color: var(--ds-foreground-warning); }
    .lifecycle-btn-stop:hover   { border-color: var(--ds-foreground-warning); background: var(--ds-surface-faint); }
    .lifecycle-btn-stop span    { color: var(--ds-foreground-faint); }
    .lifecycle-btn-delete strong { color: var(--ds-foreground-critical); }
    .lifecycle-btn-delete:hover  { border-color: var(--ds-foreground-critical); background: var(--ds-surface-faint); }
    .lifecycle-btn-delete span   { color: var(--ds-foreground-faint); }
  </style>
  <script>
    /* ── Theme Init (runs before render to prevent flash) ─── */
    (function() {
      var pref = localStorage.getItem('ds-theme') || 'system';
      function resolve(p) {
        if (p === 'system') return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
        return p;
      }
      document.documentElement.setAttribute('data-theme', resolve(pref));
      window.__dsPref = pref;
    })();
  </script>
</head>
<body>

  <!-- ── App Header ──────────────────────────────────────────── -->
  <div class="app-header">
    <div class="logo">
      {{ logo_svg | safe }}
      <div class="logo-divider"></div>
      <h1>{{ title }}</h1>
    </div>
    <div class="header-right">
      <span style="opacity:0.5;font-size:0.75rem;">v{{ version }}</span>
      <span><span class="refresh-indicator pulse"></span>&nbsp;Live</span>
      <span id="lastUpdate">--</span>
      <button class="theme-toggle" onclick="cycleTheme()" title="Toggle theme" aria-label="Toggle theme">
        <span class="icon-sun">&#x2600;&#xFE0F;</span>
        <span class="icon-moon">&#x1F319;</span>
        <span class="icon-auto">&#x1F5A5;&#xFE0F;</span>
      </button>
    </div>
  </div>

  <!-- ── Page Content ──────────────────────────────────────────── -->
  <div class="page-content">

    <!-- Stats Bar -->
    <div class="stats-bar">
      <div class="stat-card">
        <span class="stat-label">Currently Working</span>
        <span class="stat-value accent" id="workingAgents">0</span>
      </div>
      <div class="stat-card">
        <span class="stat-label">Max Concurrent</span>
        <span class="stat-value accent" id="maxConcurrentAgents">0</span>
      </div>
      <div class="stat-card">
        <span class="stat-label">Total Agents</span>
        <span class="stat-value" id="totalAgents">0</span>
      </div>
      <div class="stat-card">
        <span class="stat-label">Total Working Time</span>
        <span class="stat-value" id="totalWorkingTime">0s</span>
      </div>
      <div class="stat-card">
        <span class="stat-label">Total Duration</span>
        <span class="stat-value" id="totalDuration">0s</span>
      </div>
      <button class="refresh-btn" onclick="fetchData()">&#x21bb; Refresh</button>
    </div>

    <!-- Orchestrator Filter Bar (hidden when <2 orchestrators) -->
    <div class="orch-filter-bar hidden" id="orchFilterBar">
      <span class="orch-filter-label">&#x1F3AF; Orchestrator:</span>
      <div class="orch-filter-options" id="orchFilterOptions"></div>
    </div>

    <!-- Orchestrator Panels Container (populated by JS) -->
    <div id="orchestratorContainer"></div>

    <!-- Agent Cards -->
    <div class="section-heading" style="display:flex;align-items:center;gap:var(--ds-space-200);flex-wrap:wrap;">
      Agents
      <div class="sort-controls">
        <span style="font-size:0.75rem;color:var(--ds-foreground-faint);font-weight:400;">Sort by:</span>
        <button class="sort-btn active" data-sort="name" onclick="setSort('name')">Name</button>
        <button class="sort-btn" data-sort="status" onclick="setSort('status')">Status</button>
        <button class="sort-btn" data-sort="timestamp" onclick="setSort('timestamp')">Last Update</button>
        <button class="sort-btn" data-sort="working" onclick="setSort('working')">Working Time</button>
        <button class="reset-btn" onclick="resetAllAgents()">Reset All</button>
      </div>
    </div>
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
    /* ── Theme Toggle ─────────────────────────────────────── */
    function resolveTheme(pref) {
      if (pref === 'system') return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
      return pref;
    }
    function applyTheme(pref) {
      document.documentElement.setAttribute('data-theme', resolveTheme(pref));
      localStorage.setItem('ds-theme', pref);
      window.__dsPref = pref;
    }
    function cycleTheme() {
      var order = ['light', 'dark', 'system'];
      var idx = order.indexOf(window.__dsPref || 'system');
      applyTheme(order[(idx + 1) % 3]);
      if (typeof renderConcurrencyChart === 'function' && window.__lastConcData) renderConcurrencyChart(window.__lastConcData);
    }
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function() {
      if ((window.__dsPref || 'system') === 'system') applyTheme('system');
    });
    function isDark() { return document.documentElement.getAttribute('data-theme') === 'dark'; }

    /* ── Status colors (theme-aware) ──────────────────────── */
    const STATUS_COLORS_LIGHT = {
      working:   '#008a22',
      waiting:   '#b35900',
      completed: '#0c56e9',
      idle:      '#656a76',
      blocked:   '#c00005',
      error:     '#c00005',
    };
    const STATUS_COLORS_DARK = {
      working:   '#2EB67D',
      waiting:   '#ecb22e',
      completed: '#5990ff',
      idle:      '#8c909c',
      blocked:   '#f47174',
      error:     '#f47174',
    };
    const STATUS_SURFACES_LIGHT = {
      working:   '#e4f7e6',
      waiting:   '#fff3d6',
      completed: '#e1ecff',
      idle:      '#f5f5f6',
      blocked:   '#ffe0e0',
      error:     '#ffe0e0',
    };
    const STATUS_SURFACES_DARK = {
      working:   'rgba(46,182,125,0.15)',
      waiting:   'rgba(236,178,46,0.15)',
      completed: 'rgba(89,144,255,0.15)',
      idle:      'rgba(140,144,156,0.10)',
      blocked:   'rgba(244,113,116,0.15)',
      error:     'rgba(244,113,116,0.15)',
    };

    function statusColor(s)   { var c = isDark() ? STATUS_COLORS_DARK : STATUS_COLORS_LIGHT; return c[(s||'').toLowerCase()] || (isDark() ? '#8c909c' : '#656a76'); }
    function statusSurface(s) { var c = isDark() ? STATUS_SURFACES_DARK : STATUS_SURFACES_LIGHT; return c[(s||'').toLowerCase()] || (isDark() ? 'rgba(140,144,156,0.10)' : '#f5f5f6'); }

    /* ── Orchestrator filter state ──────────────────────────── */
    let selectedOrchestrator = null; // null = "All"

    function setOrchestratorFilter(name) {
      selectedOrchestrator = name;
      // Update button active states
      document.querySelectorAll('.orch-filter-btn').forEach(b => {
        b.classList.toggle('active', b.dataset.orch === (name || ''));
      });
      if (window.__lastStatusData) {
        const { current, max_concurrent_agents, total_duration_seconds, orchestrators } = window.__lastStatusData;
        renderOrchestrators(current, orchestrators || []);
        renderCards(current);
        updateCounters(current, max_concurrent_agents || 0, total_duration_seconds || 0);
      }
    }

    function renderOrchestratorFilter(orchestrators) {
      const bar = document.getElementById('orchFilterBar');
      const opts = document.getElementById('orchFilterOptions');
      if (orchestrators.length < 2) { bar.classList.add('hidden'); return; }
      bar.classList.remove('hidden');
      let html = `<button class="orch-filter-btn${selectedOrchestrator === null ? ' active' : ''}" data-orch="" onclick="setOrchestratorFilter(null)">All</button>`;
      orchestrators.forEach(name => {
        const active = selectedOrchestrator === name ? ' active' : '';
        html += `<button class="orch-filter-btn${active}" data-orch="${name}" onclick="setOrchestratorFilter('${name.replace(/'/g, "\\'")}')"> ${name}</button>`;
      });
      opts.innerHTML = html;
    }

    function fetchData() {
      Promise.all([
        fetch('/api/status').then(r => r.json()),
        fetch('/api/concurrency').then(r => r.json())
      ])
      .then(([statusData, concData]) => {
        window.__lastStatusData = statusData;
        const orchestrators = statusData.orchestrators || [];
        renderOrchestratorFilter(orchestrators);
        renderOrchestrators(statusData.current, orchestrators);
        renderCards(statusData.current);
        renderLog(statusData.log);
        window.__lastConcData = concData;
        renderConcurrencyChart(concData);
        updateCounters(statusData.current, statusData.max_concurrent_agents || 0, statusData.total_duration_seconds || 0);
        const ts = new Date().toLocaleTimeString();
        document.getElementById('lastUpdate').textContent = ts;
        document.getElementById('lastUpdateBottom').textContent = 'Last refreshed: ' + ts;
      })
      .catch(err => console.error('Fetch error:', err));
    }

    function filteredAgents(agents) {
      if (!selectedOrchestrator) return agents;
      const result = {};
      for (const [name, info] of Object.entries(agents)) {
        const isOrch = name === selectedOrchestrator && info.role === 'orchestrator';
        const belongsTo = info.orchestrator === selectedOrchestrator;
        if (isOrch || belongsTo) result[name] = info;
      }
      return result;
    }

    function updateCounters(agents, maxConcurrent, totalDuration) {
      const view = filteredAgents(agents);
      const total = Object.keys(view).length;
      const working = Object.values(view).filter(a => a.status === 'working').length;
      const totalSecs = Object.values(view).reduce((sum, a) => sum + (a.working_seconds || 0), 0);
      document.getElementById('totalAgents').textContent = total;
      document.getElementById('workingAgents').textContent = working;
      document.getElementById('totalWorkingTime').textContent = fmtDuration(totalSecs);
      document.getElementById('maxConcurrentAgents').textContent = maxConcurrent;
      document.getElementById('totalDuration').textContent = fmtDuration(totalDuration);
    }

    /* ── Sort state ─────────────────────────────────────────────── */
    let currentSort = 'name';
    let sortAsc = true;
    let lastAgentsData = null;

    const STATUS_ORDER = {working:0, waiting:1, blocked:2, error:3, idle:4, completed:5};

    function setSort(field) {
      if (currentSort === field) {
        sortAsc = !sortAsc;
      } else {
        currentSort = field;
        sortAsc = (field === 'name' || field === 'status');
      }
      document.querySelectorAll('.sort-btn').forEach(b => {
        const isActive = b.dataset.sort === field;
        b.classList.toggle('active', isActive);
        const existing = b.querySelector('.arrow');
        if (existing) existing.remove();
        if (isActive) {
          const arrow = document.createElement('span');
          arrow.className = 'arrow';
          arrow.textContent = sortAsc ? '▲' : '▼';
          b.appendChild(arrow);
        }
      });
      if (lastAgentsData) renderCards(lastAgentsData);
    }

    function resetAllAgents() {
      if (!confirm('Mark all currently-working agents as idle?')) {
        return;
      }
      fetch('/api/reset', { method: 'POST' })
        .then(r => r.json())
        .then(data => {
          if (data.ok) {
            console.log(`Reset ${data.count} agent(s):`, data.reset_agents);
            fetchData();
          } else {
            console.error('Reset failed:', data.error);
          }
        })
        .catch(err => console.error('Reset error:', err));
    }

    function sortEntries(entries) {
      return entries.sort((a, b) => {
        let cmp = 0;
        switch (currentSort) {
          case 'name':
            cmp = a[0].localeCompare(b[0]); break;
          case 'status':
            cmp = (STATUS_ORDER[a[1].status] ?? 9) - (STATUS_ORDER[b[1].status] ?? 9);
            if (cmp === 0) cmp = a[0].localeCompare(b[0]);
            break;
          case 'timestamp':
            cmp = (a[1].timestamp || '').localeCompare(b[1].timestamp || '');
            break;
          case 'working':
            cmp = (a[1].working_seconds || 0) - (b[1].working_seconds || 0);
            break;
        }
        return sortAsc ? cmp : -cmp;
      });
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

    function buildOrchPanelHTML(orchName, orchInfo, subAgents) {
      const fg = statusColor(orchInfo.status);
      const bg = statusSurface(orchInfo.status);
      const staleTag = orchInfo.stale ? ' (stale)' : '';
      const badgeHTML = `<span class="status-badge" style="background:${bg};color:${fg};border-color:${fg}"><span></span>${orchInfo.status || 'idle'}${staleTag}</span>`;

      const goalHTML = orchInfo.goal
        ? `<div class="orch-field orch-goal"><span class="orch-field-label">Goal</span><span class="orch-field-value"><strong>${orchInfo.goal}</strong></span></div>`
        : '';
      let taskHTML = '';
      if (orchInfo.task_name) {
        const link = orchInfo.task_url
          ? `<a href="${orchInfo.task_url}" target="_blank" rel="noopener">${orchInfo.task_name}</a>`
          : `<strong>${orchInfo.task_name}</strong>`;
        taskHTML = `<div class="orch-field"><span class="orch-field-label">Current Task</span><span class="orch-field-value">${link}</span></div>`;
      }
      const modelHTML = orchInfo.model
        ? `<div class="orch-field"><span class="orch-field-label">Model</span><span class="orch-field-value" style="font-style:italic;">${orchInfo.model}</span></div>`
        : '';
      const progHTML = orchInfo.progress
        ? `<div class="orch-field orch-progress"><span class="orch-field-label">Progress</span><span class="orch-field-value">${orchInfo.progress}</span></div>`
        : '';

      const total = subAgents.length;
      const working  = subAgents.filter(([,a]) => a.status === 'working').length;
      const waiting  = subAgents.filter(([,a]) => a.status === 'waiting').length;
      const completed= subAgents.filter(([,a]) => a.status === 'completed').length;
      const errored  = subAgents.filter(([,a]) => a.status === 'error' || a.status === 'blocked').length;
      let subHTML = `<div class="orch-sub-stat"><span class="count">${total}</span><span class="label">total</span></div>`;
      subHTML += `<div class="orch-sub-stat"><span class="count" style="color:${statusColor('working')}">${working}</span><span class="label">working</span></div>`;
      subHTML += `<div class="orch-sub-stat"><span class="count" style="color:${statusColor('waiting')}">${waiting}</span><span class="label">waiting</span></div>`;
      subHTML += `<div class="orch-sub-stat"><span class="count" style="color:${statusColor('completed')}">${completed}</span><span class="label">completed</span></div>`;
      if (errored > 0) subHTML += `<div class="orch-sub-stat"><span class="count" style="color:${statusColor('error')}">${errored}</span><span class="label">error/blocked</span></div>`;

      return `
        <div class="orchestrator-panel" style="border-left-color:${fg};margin-bottom:var(--ds-space-200)">
          <div class="orchestrator-header">
            <div class="orchestrator-title">
              <span class="orch-icon">&#x1F3AF;</span>
              <span>${orchName}</span>
              ${badgeHTML}
            </div>
            <div style="font-size:0.75rem;color:var(--ds-foreground-faint);">
              Last update: ${orchInfo.timestamp || 'never'}
              &nbsp;·&nbsp;Working time: ${fmtDuration(orchInfo.working_seconds)}
            </div>
          </div>
          <div class="orchestrator-body">
            ${goalHTML}
            ${taskHTML}
            ${modelHTML}
            ${progHTML}
            <div class="orch-field" style="grid-column:1/-1;">
              <span class="orch-field-label">Sub-Agents</span>
              <div class="orch-sub-agents">${subHTML}</div>
            </div>
          </div>
        </div>`;
    }

    function renderOrchestrators(agents, orchestratorNames) {
      const container = document.getElementById('orchestratorContainer');
      // Determine which orchestrators to show
      const toShow = selectedOrchestrator
        ? orchestratorNames.filter(n => n === selectedOrchestrator)
        : orchestratorNames;

      if (toShow.length === 0) { container.innerHTML = ''; return; }

      let html = '';
      toShow.forEach(orchName => {
        const orchInfo = agents[orchName];
        if (!orchInfo) return;
        // Sub-agents: agents whose orchestrator field matches this orch, or all non-orch agents when only 1 orch
        let subAgents;
        if (orchestratorNames.length === 1) {
          subAgents = Object.entries(agents).filter(([n, info]) => n !== orchName && info.role !== 'orchestrator');
        } else {
          subAgents = Object.entries(agents).filter(([n, info]) => info.orchestrator === orchName && n !== orchName);
        }
        html += buildOrchPanelHTML(orchName, orchInfo, subAgents);
      });
      container.innerHTML = html;
    }

    function renderCards(agents) {
      lastAgentsData = agents;
      const grid = document.getElementById('agentCards');
      grid.innerHTML = '';
      // Apply orchestrator filter, then exclude orchestrators from regular cards
      const view = filteredAgents(agents);
      const entries = Object.entries(view).filter(([, info]) => info.role !== 'orchestrator');
      if (entries.length === 0) {
        grid.innerHTML = '<div class="no-agents">No agents registered yet. Agents will appear when they post status updates.</div>';
        return;
      }
      sortEntries(entries);
      for (const [name, info] of entries) {
        const fg = statusColor(info.status);
        const bg = statusSurface(info.status);
        const staleTag = info.stale ? ' <span class="stale-tag">stale</span>' : '';
        const statusLabel = (info.status || 'idle') + (info.stale ? ' (stale)' : '');
        let taskHtml = '';
        if (info.task_name) {
          if (info.task_url) {
            taskHtml = `<div>Task: <a href="${info.task_url}" target="_blank" rel="noopener" style="color:var(--ds-foreground-action);text-decoration:underline;">${info.task_name}</a></div>`;
          } else {
            taskHtml = `<div>Task: <strong>${info.task_name}</strong></div>`;
          }
        }
        let modelHtml = '';
        if (info.model) {
          modelHtml = `<div>Model: <span style="color:var(--ds-foreground-faint);font-style:italic;">${info.model}</span></div>`;
        }
        grid.innerHTML += `
          <div class="card" style="border-left-color:${fg}">
            <div class="card-header">
              <span class="agent-name">${name}${staleTag}</span>
              <span class="status-badge" style="background:${bg};color:${fg};border-color:${fg}"><span></span>${statusLabel}</span>
            </div>
            <div class="card-meta">
              ${taskHtml}
              ${modelHtml}
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
        body.innerHTML = '<tr><td colspan="3" style="text-align:center;color:var(--ds-foreground-faint)">No activity yet</td></tr>';
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

    /* ── Lifecycle management ─────────────────────────────────── */
    let _lifecycleShown = false;

    function pollLifecycle() {
      fetch('/api/lifecycle/status')
        .then(r => r.json())
        .then(data => {
          if (data.prompt && !_lifecycleShown) showLifecycleModal();
          else if (!data.prompt && _lifecycleShown) hideLifecycleModal();
        })
        .catch(() => {});
    }

    function showLifecycleModal() {
      _lifecycleShown = true;
      document.getElementById('lifecycleOverlay').classList.remove('hidden');
    }

    function hideLifecycleModal() {
      _lifecycleShown = false;
      document.getElementById('lifecycleOverlay').classList.add('hidden');
    }

    function executeLifecycle(mode) {
      hideLifecycleModal();
      fetch('/api/lifecycle/execute?mode=' + mode, { method: 'POST' })
        .then(r => r.json())
        .then(data => {
          if (mode === 'keep_running') return; // stay on page
          if (mode === 'shutdown_keep' || mode === 'shutdown_delete') {
            document.body.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100vh;font-family:system-ui;flex-direction:column;gap:16px;color:#3b3d45;">' +
              '<span style="font-size:2rem;">&#x2705;</span>' +
              '<strong style="font-size:1.25rem;">Dashboard has shut down.</strong>' +
              (mode === 'shutdown_delete' ? '<span>All data has been deleted.</span>' : '<span>Your data is preserved on disk.</span>') +
              '</div>';
          }
        })
        .catch(() => {
          if (mode !== 'keep_running') {
            document.body.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100vh;font-family:system-ui;color:#3b3d45;"><strong>Dashboard stopped.</strong></div>';
          }
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

      /* Read theme-aware chart colors from CSS custom properties */
      const cs = getComputedStyle(document.documentElement);
      const cGrid     = cs.getPropertyValue('--ds-chart-grid').trim();
      const cLabel    = cs.getPropertyValue('--ds-chart-label').trim();
      const cTitle    = cs.getPropertyValue('--ds-chart-title').trim();
      const cLine     = cs.getPropertyValue('--ds-chart-line').trim();
      const cFillS    = cs.getPropertyValue('--ds-chart-fill-start').trim();
      const cFillE    = cs.getPropertyValue('--ds-chart-fill-end').trim();
      const cNow      = cs.getPropertyValue('--ds-chart-now').trim();

      const points = data.points || [];
      const maxAgents = Math.max(data.max_agents || 1, 1);
      const tMin = data.t_min || 0;
      const tMax = data.t_max || 1;

      const pad = {top: 24, right: 24, bottom: 36, left: 48};
      const plotW = W - pad.left - pad.right;
      const plotH = H - pad.top - pad.bottom;

      ctx.clearRect(0, 0, W, H);

      /* Grid lines — border-faint */
      ctx.strokeStyle = cGrid;
      ctx.lineWidth = 1;
      for (let i = 0; i <= maxAgents; i++) {
        const y = pad.top + plotH - (i / maxAgents) * plotH;
        ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(pad.left + plotW, y); ctx.stroke();
      }

      /* Y-axis labels */
      ctx.fillStyle = cLabel;
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
      ctx.fillStyle = cTitle;
      ctx.font = '500 12px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
      ctx.fillText('Agents', 0, 0);
      ctx.restore();

      /* X-axis labels */
      ctx.textAlign = 'center';
      ctx.textBaseline = 'top';
      ctx.fillStyle = cLabel;
      ctx.font = '11px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
      const span = tMax - tMin;
      const tickCount = Math.min(8, Math.max(points.length, 1));
      for (let i = 0; i <= tickCount; i++) {
        const t = tMin + (i / tickCount) * span;
        const x = pad.left + (i / tickCount) * plotW;
        const d = new Date(t * 1000);
        const lbl = d.toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'});
        ctx.fillText(lbl, x, pad.top + plotH + 8);
        ctx.strokeStyle = cGrid; ctx.lineWidth = 0.5;
        ctx.beginPath(); ctx.moveTo(x, pad.top); ctx.lineTo(x, pad.top + plotH); ctx.stroke();
      }

      if (points.length < 2) {
        ctx.fillStyle = cLabel;
        ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
        ctx.font = '13px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
        ctx.fillText('Waiting for data\u2026', W / 2, H / 2);
        return;
      }

      /* Now-line — warning colour */
      const nowFrac = (data.t_now - tMin) / span;
      const nowPx = pad.left + nowFrac * plotW;
      ctx.save();
      ctx.setLineDash([4, 4]);
      ctx.strokeStyle = cNow;
      ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(nowPx, pad.top); ctx.lineTo(nowPx, pad.top + plotH); ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = cNow;
      ctx.font = '500 10px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText('now', nowPx, pad.top - 10);
      ctx.restore();

      /* Stepped area fill — action colour (blue) */
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
      grad.addColorStop(0, cFillS);
      grad.addColorStop(1, cFillE);
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
      ctx.strokeStyle = cLine;
      ctx.lineWidth = 2;
      ctx.stroke();

      /* Dot at current value */
      ctx.beginPath();
      ctx.arc(nowPx, lastY, 4, 0, Math.PI * 2);
      ctx.fillStyle = cLine;
      ctx.fill();
      ctx.fillStyle = cTitle;
      ctx.font = 'bold 12px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
      ctx.textAlign = 'left';
      ctx.fillText(points[points.length - 1].count, nowPx + 8, lastY + 4);
    }

    fetchData();
    setInterval(fetchData, 5000);
    setInterval(pollLifecycle, 4000);
  </script>

  <!-- ── Lifecycle Modal ──────────────────────────────────────── -->
  <div class="lifecycle-overlay hidden" id="lifecycleOverlay">
    <div class="lifecycle-modal">
      <div class="lifecycle-modal-header">
        <span class="lifecycle-modal-icon">&#x26A1;</span>
        <h2>Session Ending</h2>
      </div>
      <p class="lifecycle-modal-desc">
        Your AI session is closing. What should happen to this dashboard?
      </p>
      <div class="lifecycle-modal-actions">
        <button class="lifecycle-btn lifecycle-btn-keep" onclick="executeLifecycle('keep_running')">
          <strong>Keep Running</strong>
          <span>Dashboard stays alive with all data intact</span>
        </button>
        <button class="lifecycle-btn lifecycle-btn-stop" onclick="executeLifecycle('shutdown_keep')">
          <strong>Shutdown &amp; Keep Data</strong>
          <span>Stop the dashboard — data remains on disk for next time</span>
        </button>
        <button class="lifecycle-btn lifecycle-btn-delete" onclick="executeLifecycle('shutdown_delete')">
          <strong>Shutdown &amp; Delete Data</strong>
          <span>Stop the dashboard and permanently remove all stored data</span>
        </button>
      </div>
    </div>
  </div>
</body>
</html>
"""


def init_db():
    """Initialize SQLite database, create schema, and import legacy CSV if needed."""
    db_dir = os.path.dirname(DB_PATH)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)
    
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    
    # Create schema
    conn.execute("""
        CREATE TABLE IF NOT EXISTS status_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            agent_name TEXT NOT NULL,
            status TEXT NOT NULL,
            task_name TEXT DEFAULT '',
            task_url TEXT DEFAULT '',
            model TEXT DEFAULT '',
            role TEXT DEFAULT '',
            goal TEXT DEFAULT '',
            progress TEXT DEFAULT '',
            orchestrator TEXT DEFAULT ''
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_status_log_agent ON status_log(agent_name)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_status_log_ts ON status_log(timestamp)")

    # Migrate: add task columns if upgrading from older schema
    try:
        conn.execute("SELECT task_name FROM status_log LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE status_log ADD COLUMN task_name TEXT DEFAULT ''")
        conn.execute("ALTER TABLE status_log ADD COLUMN task_url TEXT DEFAULT ''")

    # Migrate: add model column if upgrading from older schema
    try:
        conn.execute("SELECT model FROM status_log LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE status_log ADD COLUMN model TEXT DEFAULT ''")

    # Migrate: add orchestrator columns if upgrading from older schema
    try:
        conn.execute("SELECT role FROM status_log LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE status_log ADD COLUMN role TEXT DEFAULT ''")
        conn.execute("ALTER TABLE status_log ADD COLUMN goal TEXT DEFAULT ''")
        conn.execute("ALTER TABLE status_log ADD COLUMN progress TEXT DEFAULT ''")

    # Migrate: add orchestrator association column
    try:
        conn.execute("SELECT orchestrator FROM status_log LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE status_log ADD COLUMN orchestrator TEXT DEFAULT ''")

    conn.commit()
    
    # Import legacy CSV if DB is empty and CSV exists
    count = conn.execute("SELECT COUNT(*) FROM status_log").fetchone()[0]
    if count == 0 and os.path.exists(CSV_PATH):
        try:
            with open(CSV_PATH, "r", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    timestamp = row.get("timestamp", "")
                    agent_name = row.get("agent_name", "")
                    status = row.get("status", "")
                    if timestamp and agent_name and status:
                        # Normalize agent name during import
                        agent_name = normalize_agent_name(agent_name)
                        conn.execute(
                            "INSERT INTO status_log (timestamp, agent_name, status) VALUES (?, ?, ?)",
                            (timestamp, agent_name, status)
                        )
            conn.commit()
            print(f"  Imported legacy CSV data from {CSV_PATH}")
        except Exception as e:
            print(f"  Warning: Could not import CSV: {e}")
    
    conn.close()


def get_db():
    """Get a SQLite connection with Row factory for dict-like access."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_known_agents():
    """Get set of all agents that have ever posted status updates."""
    conn = get_db()
    rows = conn.execute("SELECT DISTINCT agent_name FROM status_log").fetchall()
    conn.close()
    return {row["agent_name"] for row in rows}


def write_status(agent_name, status, task_name="", task_url="", model="", role="", goal="", progress="", orchestrator=""):
    """Insert a status row into the database."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    db_dir = os.path.dirname(DB_PATH)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)
    conn = get_db()
    conn.execute(
        "INSERT INTO status_log (timestamp, agent_name, status, task_name, task_url, model, role, goal, progress, orchestrator) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (ts, agent_name, status, task_name, task_url, model, role, goal, progress, orchestrator)
    )
    conn.commit()
    conn.close()


def get_current_status():
    """Get the most recent status for each agent, including total working time."""
    conn = get_db()
    rows = conn.execute("SELECT id, timestamp, agent_name, status, task_name, task_url, model, role, goal, progress, orchestrator FROM status_log ORDER BY id").fetchall()
    conn.close()
    
    known_agents = get_known_agents()

    # Initialize all known agents
    current = {}
    for name in known_agents:
        current[name] = {"status": "idle", "timestamp": "never", "working_seconds": 0, "task_name": "", "task_url": "", "model": "", "role": "", "goal": "", "progress": "", "orchestrator": ""}

    # Track working intervals per agent
    working_start = {}  # agent -> timestamp when "working" began
    working_totals = {name: 0.0 for name in known_agents}

    for row in rows:
        name = row["agent_name"]
        status = row["status"]
        ts_str = row["timestamp"]
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

        # Preserve previous task/model/orchestrator info before overwriting
        prev_task = current[name].get("task_name", "")
        prev_url = current[name].get("task_url", "")
        prev_model = current[name].get("model", "")
        prev_role = current[name].get("role", "")
        prev_goal = current[name].get("goal", "")
        prev_progress = current[name].get("progress", "")
        prev_orchestrator = current[name].get("orchestrator", "")

        current[name] = {"status": status, "timestamp": ts_str}

        # Use new task info if provided, otherwise carry forward previous
        # Exception: terminal statuses (idle, completed, error) with no explicit
        # task should clear the carried-forward values — the agent is done.
        row_task = row["task_name"] or ""
        row_url = row["task_url"] or ""
        row_model = row["model"] or ""
        row_role = row["role"] or ""
        row_goal = row["goal"] or ""
        row_progress = row["progress"] or ""
        row_orchestrator = row["orchestrator"] or ""
        terminal = status in ("idle", "completed", "error")
        if row_task:
            current[name]["task_name"] = row_task
            current[name]["task_url"] = row_url
        elif terminal:
            current[name]["task_name"] = ""
            current[name]["task_url"] = ""
        else:
            current[name]["task_name"] = prev_task
            current[name]["task_url"] = prev_url
        current[name]["model"] = row_model if row_model else ("" if terminal else prev_model)

        # Role is sticky — once set, it persists
        current[name]["role"] = row_role if row_role else prev_role
        # Goal and progress carry forward, clear on terminal if not re-sent
        current[name]["goal"] = row_goal if row_goal else ("" if terminal else prev_goal)
        current[name]["progress"] = row_progress if row_progress else ("" if terminal else prev_progress)
        # Orchestrator association is sticky — once set, it persists
        current[name]["orchestrator"] = row_orchestrator if row_orchestrator else prev_orchestrator

    # Add any still-working time up to now
    now = datetime.now(timezone.utc).timestamp()
    for name, start in working_start.items():
        working_totals[name] += now - start

    for name in known_agents:
        current[name]["working_seconds"] = round(working_totals.get(name, 0))

    # Mark stale agents: if status is "working" but last update is older than threshold
    now = datetime.now(timezone.utc).timestamp()
    for name in known_agents:
        if current[name]["status"] == "working":
            ts_str = current[name].get("timestamp", "")
            try:
                last_ts = datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%SZ").replace(
                    tzinfo=timezone.utc
                ).timestamp()
            except (ValueError, TypeError):
                last_ts = 0
            if now - last_ts > STALE_THRESHOLD:
                current[name]["status"] = "idle"
                current[name]["stale"] = True

    return current


@app.route("/")
def index():
    return render_template_string(DASHBOARD_HTML, title=DASHBOARD_TITLE, logo_svg=LOGO_SVG, version=APP_VERSION)


def get_max_concurrent_agents():
    """Calculate the maximum number of agents that were working concurrently."""
    conn = get_db()
    rows = conn.execute("SELECT timestamp, agent_name, status FROM status_log ORDER BY timestamp, id").fetchall()
    conn.close()
    
    events = []
    for row in rows:
        name = row["agent_name"]
        status = row["status"]
        ts_str = row["timestamp"]
        try:
            ts = datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=timezone.utc
            ).timestamp()
        except (ValueError, TypeError):
            continue
        events.append((ts, name, status))
    
    working_set = set()
    max_concurrent = 0
    for _, name, status in events:
        if status == "working":
            working_set.add(name)
        else:
            working_set.discard(name)
        max_concurrent = max(max_concurrent, len(working_set))
    return max_concurrent


def get_total_duration_seconds():
    """Wall-clock seconds from the first log entry to the last."""
    conn = get_db()
    row = conn.execute(
        "SELECT MIN(timestamp) AS first_ts, MAX(timestamp) AS last_ts FROM status_log"
    ).fetchone()
    conn.close()
    if not row or not row["first_ts"] or not row["last_ts"]:
        return 0
    def parse_ts(ts_str):
        for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(ts_str, fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        return None
    first = parse_ts(row["first_ts"])
    last = parse_ts(row["last_ts"])
    if not first or not last:
        return 0
    return max(0, (last - first).total_seconds())


@app.route("/api/status")
def api_status():
    current = get_current_status()
    conn = get_db()
    rows = conn.execute("SELECT timestamp, agent_name, status FROM status_log ORDER BY id DESC LIMIT 100").fetchall()
    conn.close()
    log = [dict(row) for row in rows]
    max_concurrent = get_max_concurrent_agents()
    total_duration = get_total_duration_seconds()
    # Collect the set of known orchestrators (agents with role=orchestrator)
    orchestrators = sorted({name for name, info in current.items() if info.get("role") == "orchestrator"})
    return jsonify({"current": current, "log": log, "max_concurrent_agents": max_concurrent, "total_duration_seconds": total_duration, "orchestrators": orchestrators})


@app.route("/api/update/<agent_name>/<status>", methods=["POST"])
def api_update(agent_name, status):
    """API endpoint to update agent status. Agents self-register by posting.
    
    Optional query params:
        task  - Name/description of the current task
        task_url - URL to the task (e.g. GitHub issue link)
        model - AI model being used (e.g. Claude Sonnet 4.5, GPT-4.1)
        role - Agent role: 'orchestrator' for the orchestrating agent
        goal - Overall objective of the workflow (orchestrator only)
        progress - Brief progress summary (orchestrator only)
        orchestrator - Name of the orchestrator this sub-agent reports to
    """
    from flask import request
    status_lower = status.lower()
    if status_lower not in VALID_STATUSES:
        return jsonify({
            "ok": False,
            "error": f"Invalid status '{status}'. Valid: {', '.join(sorted(VALID_STATUSES))}"
        }), 400
    canonical = normalize_agent_name(agent_name)
    task_name = request.args.get("task", "")
    task_url = request.args.get("task_url", "")
    model = request.args.get("model", "")
    role = request.args.get("role", "")
    goal = request.args.get("goal", "")
    progress = request.args.get("progress", "")
    orchestrator_param = request.args.get("orchestrator", "")
    if orchestrator_param:
        orchestrator_param = normalize_agent_name(orchestrator_param)
    write_status(canonical, status_lower, task_name=task_name, task_url=task_url, model=model, role=role, goal=goal, progress=progress, orchestrator=orchestrator_param)
    resp = {"ok": True, "agent": canonical, "status": status_lower}
    if task_name:
        resp["task"] = task_name
    if task_url:
        resp["task_url"] = task_url
    if model:
        resp["model"] = model
    if role:
        resp["role"] = role
    if goal:
        resp["goal"] = goal
    if progress:
        resp["progress"] = progress
    if orchestrator_param:
        resp["orchestrator"] = orchestrator_param
    return jsonify(resp)


@app.route("/api/reset", methods=["POST"])
def api_reset_all():
    """Mark all currently-working agents as idle by inserting new idle status rows."""
    current_status = get_current_status()
    reset_agents = []
    
    for agent_name, info in current_status.items():
        if info["status"] == "working":
            write_status(agent_name, "idle")
            reset_agents.append(agent_name)
    
    return jsonify({
        "ok": True,
        "reset_agents": reset_agents,
        "count": len(reset_agents)
    })


@app.route("/api/reset/<agent_name>", methods=["POST"])
def api_reset_agent(agent_name):
    """Mark a specific agent as idle by inserting a new idle status row."""
    canonical = normalize_agent_name(agent_name)
    current_status = get_current_status()
    
    if canonical not in current_status:
        return jsonify({
            "ok": False,
            "error": f"Agent '{canonical}' not found"
        }), 404
    
    if current_status[canonical]["status"] != "working":
        return jsonify({
            "ok": True,
            "reset_agents": [],
            "count": 0,
            "message": f"Agent '{canonical}' was not working"
        })
    
    write_status(canonical, "idle")
    return jsonify({
        "ok": True,
        "reset_agents": [canonical],
        "count": 1
    })


@app.route("/api/lifecycle/status")
def api_lifecycle_status():
    """Return whether a lifecycle prompt is pending."""
    return jsonify({"prompt": _lifecycle_prompt_pending})


@app.route("/api/lifecycle/prompt", methods=["POST"])
def api_lifecycle_prompt():
    """Signal the dashboard to show a lifecycle management modal.

    Called by the AI session when it is about to close, so the human operator
    can decide what to do with the dashboard and its data.
    """
    global _lifecycle_prompt_pending
    _lifecycle_prompt_pending = True
    return jsonify({"ok": True, "message": "Lifecycle prompt triggered — user will be presented with options."})


@app.route("/api/lifecycle/execute", methods=["POST"])
def api_lifecycle_execute():
    """Execute the chosen lifecycle action.

    Query params:
        mode - One of:
            keep_running    : dismiss the prompt, dashboard stays running
            shutdown_keep   : stop the dashboard process, keep the database
            shutdown_delete : delete the database, then stop the dashboard process
    """
    from flask import request
    import threading
    import signal
    global _lifecycle_prompt_pending
    mode = request.args.get("mode", "keep_running")
    if mode == "keep_running":
        _lifecycle_prompt_pending = False
        return jsonify({"ok": True, "mode": mode})
    elif mode in ("shutdown_keep", "shutdown_delete"):
        _lifecycle_prompt_pending = False
        if mode == "shutdown_delete" and os.path.exists(DB_PATH):
            try:
                os.remove(DB_PATH)
            except OSError as e:
                return jsonify({"ok": False, "error": f"Could not delete database: {e}"}), 500
        def _do_shutdown():
            import time
            time.sleep(0.4)
            os.kill(os.getpid(), signal.SIGTERM)
        threading.Thread(target=_do_shutdown, daemon=True).start()
        return jsonify({"ok": True, "mode": mode, "message": "Dashboard is shutting down."})
    else:
        return jsonify({"ok": False, "error": f"Unknown mode '{mode}'. Valid: keep_running, shutdown_keep, shutdown_delete"}), 400


@app.route("/api/export/csv")
def api_export_csv():
    """Export all status data as a CSV download."""
    import io
    conn = get_db()
    rows = conn.execute("SELECT timestamp, agent_name, status, task_name, task_url, model, role, goal, progress, orchestrator FROM status_log ORDER BY id").fetchall()
    conn.close()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["timestamp", "agent_name", "status", "task_name", "task_url", "model", "role", "goal", "progress", "orchestrator"])
    for row in rows:
        writer.writerow([row["timestamp"], row["agent_name"], row["status"], 
                        row["task_name"] or "", row["task_url"] or "", row["model"] or "",
                        row["role"] or "", row["goal"] or "", row["progress"] or "",
                        row["orchestrator"] or ""])
    return Response(output.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=agent_status.csv"})


@app.route("/api/concurrency")
def api_concurrency():
    """Return time-series data of concurrent working agents for the chart."""
    conn = get_db()
    rows = conn.execute("SELECT timestamp, agent_name, status FROM status_log ORDER BY id").fetchall()
    conn.close()
    
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
        ts_str = row["timestamp"]
        try:
            ts = datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=timezone.utc
            ).timestamp()
        except (ValueError, TypeError):
            continue
        events.append((ts, row["agent_name"], row["status"]))

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
    init_db()
    print("\n" + "=" * 60)
    print(f"  {DASHBOARD_TITLE}")
    print(f"  Open http://localhost:{DASHBOARD_PORT} in your browser")
    print(f"  Database: {DB_PATH}")
    print("=" * 60 + "\n")
    app.run(host="0.0.0.0", port=DASHBOARD_PORT, debug=False)
