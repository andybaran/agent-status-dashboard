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

def post_status(agent_name: str, status: str) -> None:
    """Post a status update to the dashboard API."""
    encoded = urllib.parse.quote(agent_name, safe="")
    url = f"{DASHBOARD_URL}/api/update/{encoded}/{status}"
    try:
        r = requests.post(url, timeout=5)
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        print(f"  [{ts}]  {agent_name:20s} → {status:12s}  ({r.status_code})")
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
    post_status("Orchestrator", "working")
    sleep(jitter(5))
    # Signal all agents to start
    barrier.wait()
    # Wait for everyone else to finish
    done_event.wait()
    sleep(jitter(3))
    post_status("Orchestrator", "completed")


def data_collector(barrier: threading.Barrier, collected: threading.Event):
    barrier.wait()
    post_status("Data Collector", "working")
    sleep(jitter(20))
    post_status("Data Collector", "waiting")   # "uploading" data
    sleep(jitter(5))
    collected.set()
    post_status("Data Collector", "completed")


def data_validator(barrier: threading.Barrier, collected: threading.Event,
                   validated: threading.Event):
    barrier.wait()
    post_status("Data Validator", "waiting")
    collected.wait()
    post_status("Data Validator", "working")
    sleep(jitter(15))
    validated.set()
    post_status("Data Validator", "completed")


def transform_agent(barrier: threading.Barrier, validated: threading.Event,
                    transformed: threading.Event):
    barrier.wait()
    post_status("Transform Agent", "waiting")
    validated.wait()
    post_status("Transform Agent", "working")
    sleep(jitter(20))
    transformed.set()
    post_status("Transform Agent", "completed")


def ml_trainer(barrier: threading.Barrier, transformed: threading.Event,
               trained: threading.Event):
    barrier.wait()
    post_status("ML Trainer", "waiting")
    transformed.wait()
    post_status("ML Trainer", "working")
    # Longest job — simulates model training
    sleep(jitter(30))
    trained.set()
    post_status("ML Trainer", "completed")


def qa_agent(barrier: threading.Barrier, trained: threading.Event,
             qa_done: threading.Event):
    barrier.wait()
    post_status("QA Agent", "waiting")
    trained.wait()
    post_status("QA Agent", "working")
    sleep(jitter(15))
    # Simulate a transient error + retry
    post_status("QA Agent", "error")
    sleep(jitter(4))
    post_status("QA Agent", "working")
    sleep(jitter(10))
    qa_done.set()
    post_status("QA Agent", "completed")


def report_builder(barrier: threading.Barrier, qa_done: threading.Event,
                   report_done: threading.Event):
    barrier.wait()
    post_status("Report Builder", "waiting")
    qa_done.wait()
    post_status("Report Builder", "working")
    sleep(jitter(12))
    report_done.set()
    post_status("Report Builder", "completed")


def notifier(barrier: threading.Barrier, report_done: threading.Event,
             done_event: threading.Event):
    barrier.wait()
    post_status("Notifier", "waiting")
    report_done.wait()
    post_status("Notifier", "working")
    sleep(jitter(5))
    post_status("Notifier", "completed")
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
