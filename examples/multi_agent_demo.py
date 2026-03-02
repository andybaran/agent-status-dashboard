#!/usr/bin/env python3
"""
Multi-Agent Workflow Demo — Agent Status Dashboard
===================================================

Simulates a realistic data-pipeline workflow with 8 agents that start, work,
wait, and complete over ~3 minutes.  Run alongside the dashboard to see
real-time status cards, concurrency chart, and activity log populate live.

Agents and their roles:
  1. Orchestrator    — coordinates the pipeline, starts first, finishes last
  2. Data Collector  — gathers raw data from "sources"
  3. Data Validator  — validates collected data
  4. Transform Agent — transforms validated data
  5. ML Trainer      — trains a model on transformed data
  6. QA Agent        — runs quality-assurance checks
  7. Report Builder  — generates final report
  8. Notifier        — sends notifications when pipeline completes

Prerequisites:
  pip install requests          # only external dependency
  # Dashboard must be running at DASHBOARD_URL (default http://localhost:5050)

Usage:
  python multi_agent_demo.py                           # defaults
  DASHBOARD_URL=http://myhost:8080 python multi_agent_demo.py
"""

from __future__ import annotations

import os
import sys
import time
import random
import threading
import urllib.parse
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Only dependency beyond stdlib
# ---------------------------------------------------------------------------
try:
    import requests
except ImportError:
    print("ERROR: 'requests' is required.  Install with:  pip install requests")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DASHBOARD_URL = os.environ.get("DASHBOARD_URL", "http://localhost:5050").rstrip("/")

# Speed multiplier — 1.0 = normal (~3 min total), 0.5 = fast (~90 s)
SPEED = float(os.environ.get("DEMO_SPEED", "1.0"))

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def post_status(agent_name: str, status: str, task: str = "", task_url: str = "", model: str = "") -> None:
    """Post a status update to the dashboard API."""
    encoded = urllib.parse.quote(agent_name, safe="")
    url = f"{DASHBOARD_URL}/api/update/{encoded}/{status}"
    params = {}
    if task:
        params["task"] = task
    if task_url:
        params["task_url"] = task_url
    if model:
        params["model"] = model
    try:
        r = requests.post(url, params=params, timeout=5)
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        task_info = f"  [{task}]" if task else ""
        model_info = f"  ({model})" if model else ""
        print(f"  [{ts}]  {agent_name:20s} → {status:12s}{task_info}{model_info}  ({r.status_code})")
    except requests.RequestException as exc:
        print(f"  ⚠  {agent_name}: {exc}", file=sys.stderr)


def sleep(seconds: float) -> None:
    """Sleep scaled by SPEED multiplier."""
    time.sleep(seconds * SPEED)


def jitter(base: float, variance: float = 0.3) -> float:
    """Return base ± variance*base (randomised)."""
    return base * (1 + random.uniform(-variance, variance))

# ---------------------------------------------------------------------------
# Agent behaviours  (each runs in its own thread)
# ---------------------------------------------------------------------------

def orchestrator(barrier: threading.Barrier, done_event: threading.Event):
    post_status("Orchestrator", "working", task="Coordinate pipeline",
                task_url="https://github.com/acme/data-pipeline/issues/10", model="Claude Opus 4.6")
    sleep(jitter(5))
    # Signal all agents to start
    barrier.wait()
    # Wait for everyone else to finish
    done_event.wait()
    sleep(jitter(3))
    post_status("Orchestrator", "completed", task="Coordinate pipeline",
                task_url="https://github.com/acme/data-pipeline/issues/10")


def data_collector(barrier: threading.Barrier, collected: threading.Event):
    barrier.wait()
    post_status("Data Collector", "working", task="Fetch raw data from sources",
                task_url="https://github.com/acme/data-pipeline/issues/11", model="Claude Sonnet 4.5")
    sleep(jitter(20))
    post_status("Data Collector", "waiting",
                task_url="https://github.com/acme/data-pipeline/issues/11")
    sleep(jitter(5))
    collected.set()
    post_status("Data Collector", "completed", task="Fetch raw data from sources",
                task_url="https://github.com/acme/data-pipeline/issues/11")


def data_validator(barrier: threading.Barrier, collected: threading.Event,
                   validated: threading.Event):
    barrier.wait()
    post_status("Data Validator", "waiting", model="Claude Haiku 4.5")
    collected.wait()
    post_status("Data Validator", "working", task="Validate schema and integrity",
                task_url="https://github.com/acme/data-pipeline/issues/12")
    sleep(jitter(15))
    validated.set()
    post_status("Data Validator", "completed", task="Validate schema and integrity",
                task_url="https://github.com/acme/data-pipeline/issues/12")


def transform_agent(barrier: threading.Barrier, validated: threading.Event,
                    transformed: threading.Event):
    barrier.wait()
    post_status("Transform Agent", "waiting", model="GPT-4.1")
    validated.wait()
    post_status("Transform Agent", "working", task="Normalize and transform data",
                task_url="https://github.com/acme/data-pipeline/pull/45")
    sleep(jitter(20))
    transformed.set()
    post_status("Transform Agent", "completed", task="Normalize and transform data",
                task_url="https://github.com/acme/data-pipeline/pull/45")


def ml_trainer(barrier: threading.Barrier, transformed: threading.Event,
               trained: threading.Event):
    barrier.wait()
    post_status("ML Trainer", "waiting", model="Claude Opus 4.5")
    transformed.wait()
    post_status("ML Trainer", "working", task="Train prediction model",
                task_url="https://github.com/acme/data-pipeline/issues/13")
    # Longest job — simulates model training with heartbeat check-ins
    sleep(jitter(10))
    # Heartbeat: re-post working status to reset staleness timer
    post_status("ML Trainer", "working", task="Train prediction model",
                task_url="https://github.com/acme/data-pipeline/issues/13", model="Claude Opus 4.5")
    sleep(jitter(10))
    # Second heartbeat
    post_status("ML Trainer", "working", task="Train prediction model",
                task_url="https://github.com/acme/data-pipeline/issues/13", model="Claude Opus 4.5")
    sleep(jitter(10))
    trained.set()
    post_status("ML Trainer", "completed", task="Train prediction model",
                task_url="https://github.com/acme/data-pipeline/issues/13")


def qa_agent(barrier: threading.Barrier, trained: threading.Event,
             qa_done: threading.Event):
    barrier.wait()
    post_status("QA Agent", "waiting", model="Claude Haiku 4.5")
    trained.wait()
    qa_url = "https://github.com/acme/data-pipeline/issues/14"
    post_status("QA Agent", "working", task="Run quality checks", task_url=qa_url)
    sleep(jitter(15))
    # Simulate a transient error + retry
    post_status("QA Agent", "error", task="Run quality checks", task_url=qa_url)
    sleep(jitter(4))
    post_status("QA Agent", "working", task="Retry quality checks", task_url=qa_url)
    sleep(jitter(10))
    qa_done.set()
    post_status("QA Agent", "completed", task="Quality checks passed", task_url=qa_url)


def report_builder(barrier: threading.Barrier, qa_done: threading.Event,
                   report_done: threading.Event):
    barrier.wait()
    post_status("Report Builder", "waiting", model="Claude Sonnet 4.5")
    qa_done.wait()
    post_status("Report Builder", "working", task="Generate final report",
                task_url="https://github.com/acme/data-pipeline/issues/15")
    sleep(jitter(12))
    report_done.set()
    post_status("Report Builder", "completed", task="Generate final report",
                task_url="https://github.com/acme/data-pipeline/issues/15")


def notifier(barrier: threading.Barrier, report_done: threading.Event,
             done_event: threading.Event):
    barrier.wait()
    post_status("Notifier", "waiting", model="GPT-5 Mini")
    report_done.wait()
    post_status("Notifier", "working", task="Send notifications",
                task_url="https://github.com/acme/data-pipeline/issues/16")
    sleep(jitter(5))
    post_status("Notifier", "completed", task="Send notifications",
                task_url="https://github.com/acme/data-pipeline/issues/16")
    # Signal orchestrator that the pipeline is complete
    done_event.set()

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("  Agent Status Dashboard — Multi-Agent Demo")
    print(f"  Dashboard: {DASHBOARD_URL}")
    print(f"  Speed:     {SPEED}x  (set DEMO_SPEED env var to change)")
    print("=" * 60)

    # Verify dashboard is reachable
    try:
        r = requests.get(f"{DASHBOARD_URL}/api/status", timeout=5)
        r.raise_for_status()
        print(f"\n✓ Dashboard is reachable ({r.status_code})\n")
    except requests.RequestException as exc:
        print(f"\n✗ Cannot reach dashboard at {DASHBOARD_URL}")
        print(f"  Error: {exc}")
        print("  Make sure the dashboard is running first.  See README.md.\n")
        sys.exit(1)

    # Synchronisation primitives
    barrier      = threading.Barrier(8)       # all 8 agents sync at start
    collected    = threading.Event()
    validated    = threading.Event()
    transformed  = threading.Event()
    trained      = threading.Event()
    qa_done      = threading.Event()
    report_done  = threading.Event()
    done_event   = threading.Event()          # final signal to orchestrator

    agents = [
        ("Orchestrator",   orchestrator,    (barrier, done_event)),
        ("Data Collector",  data_collector,  (barrier, collected)),
        ("Data Validator",  data_validator,  (barrier, collected, validated)),
        ("Transform Agent", transform_agent, (barrier, validated, transformed)),
        ("ML Trainer",      ml_trainer,      (barrier, transformed, trained)),
        ("QA Agent",        qa_agent,        (barrier, trained, qa_done)),
        ("Report Builder",  report_builder,  (barrier, qa_done, report_done)),
        ("Notifier",        notifier,        (barrier, report_done, done_event)),
    ]

    print("Starting 8 agents…\n")
    start = time.monotonic()
    threads: list[threading.Thread] = []
    for name, fn, args in agents:
        t = threading.Thread(target=fn, args=args, name=name, daemon=True)
        t.start()
        threads.append(t)

    # Wait for all threads
    for t in threads:
        t.join()

    elapsed = time.monotonic() - start
    print(f"\n{'=' * 60}")
    print(f"  Pipeline complete in {elapsed:.1f}s")
    print(f"  Open {DASHBOARD_URL} to see results")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
