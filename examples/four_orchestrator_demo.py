#!/usr/bin/env python3
"""
four_orchestrator_demo.py — v1.2.0 multi-orchestrator filter demo

Simulates 4 concurrent orchestrators, each with 2–3 sub-agents, running
overlapping pipelines. Demonstrates the orchestrator filter bar and
lifecycle modal.

Usage:
    python3 examples/four_orchestrator_demo.py [--url http://localhost:5555]
"""

import time
import threading
import argparse
import sys

try:
    import requests
except ImportError:
    print("pip install requests")
    sys.exit(1)

parser = argparse.ArgumentParser()
parser.add_argument("--url", default="http://localhost:5555")
args = parser.parse_args()
BASE = args.url.rstrip("/")

# ── helpers ──────────────────────────────────────────────────────────────────

def post(agent, status, **params):
    try:
        requests.post(f"{BASE}/api/update/{agent.replace(' ', '%20')}/{status}",
                      params=params, timeout=5)
    except Exception as e:
        print(f"  [warn] {agent} → {status}: {e}")

def pause(s):
    time.sleep(s)

def banner(text):
    print(f"\n{'─'*60}")
    print(f"  {text}")
    print(f"{'─'*60}")

# ── orchestrator A: Infrastructure Deploy ────────────────────────────────────

def run_infra_deploy():
    orch = "Infra Orchestrator"
    banner("▶ Infra Orchestrator — Deploy cloud infrastructure")

    post(orch, "working", role="orchestrator",
         goal="Deploy cloud infrastructure to prod",
         progress="Initializing pipeline",
         task="Plan infrastructure rollout", model="Claude Opus 4.6")

    # Spawn Terraform agent
    print("  [Infra] Spawning Terraform Agent")
    post("Terraform Agent", "working",
         task="Apply VPC + subnets", orchestrator=orch, model="Claude Haiku 4.5")
    pause(3)

    # Spawn Security agent
    print("  [Infra] Spawning Security Agent")
    post("Security Agent", "working",
         task="Scan IAM policies", orchestrator=orch, model="Claude Haiku 4.5")
    post(orch, "waiting", role="orchestrator",
         progress="Waiting for Terraform + Security agents")
    pause(4)

    post("Terraform Agent", "completed",
         task="Apply VPC + subnets", orchestrator=orch)
    print("  [Infra] Terraform Agent completed")
    pause(2)

    post("Security Agent", "completed",
         task="Scan IAM policies", orchestrator=orch)
    print("  [Infra] Security Agent completed")

    post(orch, "working", role="orchestrator",
         progress="Infra applied — running smoke tests",
         task="Run smoke tests")
    pause(3)

    post("Terraform Agent", "working",
         task="Run health checks", orchestrator=orch)
    pause(2)
    post("Terraform Agent", "completed",
         task="Run health checks", orchestrator=orch)

    post(orch, "completed", role="orchestrator",
         progress="Infrastructure deployed successfully",
         task="Deploy cloud infrastructure to prod")
    banner("✅ Infra Orchestrator — DONE")

# ── orchestrator B: ML Training Pipeline ─────────────────────────────────────

def run_ml_pipeline():
    orch = "ML Orchestrator"
    banner("▶ ML Orchestrator — Train and evaluate model")

    pause(1)  # slight offset from Infra
    post(orch, "working", role="orchestrator",
         goal="Train and evaluate GPT fine-tune on customer data",
         progress="Initializing",
         task="Coordinate ML pipeline", model="GPT-5.2")

    print("  [ML] Spawning Data Agent")
    post("Data Agent", "working",
         task="Load + validate training dataset", orchestrator=orch, model="GPT-5 mini")
    pause(3)

    post("Data Agent", "completed",
         task="Load + validate training dataset", orchestrator=orch)
    print("  [ML] Dataset ready — spawning Training Agent")

    post("Training Agent", "working",
         task="Fine-tune on customer corpus", orchestrator=orch, model="GPT-5.2")
    post(orch, "waiting", role="orchestrator",
         progress="Training in progress (est. 8 min)")
    pause(5)

    post("Training Agent", "working",
         task="Fine-tune on customer corpus (epoch 2/3)", orchestrator=orch)
    pause(4)

    post("Training Agent", "completed",
         task="Fine-tune complete", orchestrator=orch)
    print("  [ML] Training complete — evaluating")

    post("Eval Agent", "working",
         task="Evaluate on holdout set", orchestrator=orch, model="GPT-5 mini")
    post(orch, "working", role="orchestrator",
         progress="Evaluating model quality",
         task="Review eval metrics")
    pause(4)

    post("Eval Agent", "completed",
         task="Accuracy 94.2% — PASS", orchestrator=orch)
    post(orch, "completed", role="orchestrator",
         progress="Model trained, evaluated, and ready for staging",
         task="ML pipeline complete")
    banner("✅ ML Orchestrator — DONE")

# ── orchestrator C: Frontend Release ─────────────────────────────────────────

def run_frontend_release():
    orch = "Frontend Orchestrator"
    banner("▶ Frontend Orchestrator — Ship v3.1 UI release")

    pause(2)  # offset
    post(orch, "working", role="orchestrator",
         goal="Ship v3.1 UI release to production",
         progress="Kicking off build + test",
         task="Coordinate v3.1 release", model="Claude Sonnet 4.6")

    print("  [FE] Spawning Build Agent + Test Agent in parallel")
    post("Build Agent", "working",
         task="Bundle React app (prod)", orchestrator=orch, model="Claude Haiku 4.5")
    post("Test Agent", "working",
         task="Run Playwright E2E suite", orchestrator=orch, model="Claude Haiku 4.5")
    post(orch, "waiting", role="orchestrator",
         progress="Parallel: building + running E2E tests")
    pause(4)

    post("Build Agent", "completed",
         task="Bundle complete — 1.2 MB gzip", orchestrator=orch)
    print("  [FE] Build done")
    pause(3)

    post("Test Agent", "error",
         task="2 E2E tests failed (login flow)", orchestrator=orch)
    print("  [FE] Test Agent hit errors — retrying")

    post(orch, "working", role="orchestrator",
         progress="2 test failures — investigating",
         task="Fix failing E2E tests")
    pause(2)

    post("Test Agent", "working",
         task="Retry login flow tests (fixed auth token)", orchestrator=orch)
    pause(3)

    post("Test Agent", "completed",
         task="All 147 E2E tests passing", orchestrator=orch)
    print("  [FE] Tests passing — deploying")

    post("Build Agent", "working",
         task="Deploy to CDN", orchestrator=orch)
    pause(3)
    post("Build Agent", "completed",
         task="v3.1 live on CDN", orchestrator=orch)

    post(orch, "completed", role="orchestrator",
         progress="v3.1 shipped — all tests green, CDN updated",
         task="v3.1 release complete")
    banner("✅ Frontend Orchestrator — DONE")

# ── orchestrator D: Security Audit ───────────────────────────────────────────

def run_security_audit():
    orch = "Security Orchestrator"
    banner("▶ Security Orchestrator — Quarterly security audit")

    pause(3)  # offset
    post(orch, "working", role="orchestrator",
         goal="Complete Q1 security audit across all services",
         progress="Starting audit agents",
         task="Coordinate security audit", model="Claude Sonnet 4.6")

    print("  [Sec] Spawning SAST + DAST + Dependency agents")
    post("SAST Agent", "working",
         task="Static code analysis", orchestrator=orch, model="Claude Haiku 4.5")
    post("DAST Agent", "working",
         task="Dynamic pen-test scan", orchestrator=orch, model="Claude Haiku 4.5")
    post("Dependency Agent", "working",
         task="Audit npm + pip dependencies", orchestrator=orch, model="Claude Haiku 4.5")
    post(orch, "waiting", role="orchestrator",
         progress="3 audit agents running in parallel")
    pause(4)

    post("SAST Agent", "completed",
         task="SAST: 0 critical, 3 medium findings", orchestrator=orch)
    print("  [Sec] SAST done")
    pause(2)

    post("Dependency Agent", "completed",
         task="2 CVEs found — filed tickets", orchestrator=orch)
    print("  [Sec] Dependency audit done")
    pause(3)

    post("DAST Agent", "completed",
         task="DAST: no critical vulns found", orchestrator=orch)
    print("  [Sec] DAST done")

    post(orch, "working", role="orchestrator",
         progress="Compiling audit report",
         task="Write audit summary report")
    pause(3)

    post(orch, "completed", role="orchestrator",
         progress="Audit complete — report filed, 2 CVE tickets created",
         task="Q1 security audit complete")
    banner("✅ Security Orchestrator — DONE")

# ── main ─────────────────────────────────────────────────────────────────────

def main():
    print(f"\n{'═'*60}")
    print(f"  Agent Status Dashboard v1.2.0 — 4-Orchestrator Demo")
    print(f"  Dashboard: {BASE}")
    print(f"{'═'*60}")
    print("\nSpawning 4 orchestrators in parallel threads...\n")

    # Verify dashboard is reachable
    try:
        requests.get(f"{BASE}/api/status", timeout=5).raise_for_status()
    except Exception as e:
        print(f"✗ Dashboard not reachable at {BASE}: {e}")
        sys.exit(1)

    threads = [
        threading.Thread(target=run_infra_deploy,     name="infra",    daemon=True),
        threading.Thread(target=run_ml_pipeline,      name="ml",       daemon=True),
        threading.Thread(target=run_frontend_release, name="frontend", daemon=True),
        threading.Thread(target=run_security_audit,   name="security", daemon=True),
    ]

    for t in threads:
        t.start()

    for t in threads:
        t.join()

    print(f"\n{'═'*60}")
    print("  All 4 orchestrators complete.")
    print("  Triggering lifecycle prompt on the dashboard...")
    print(f"{'═'*60}\n")

    try:
        requests.post(f"{BASE}/api/lifecycle/prompt", timeout=5)
        print("  ✓ Lifecycle modal triggered — check the dashboard!")
    except Exception as e:
        print(f"  [warn] lifecycle prompt: {e}")

if __name__ == "__main__":
    main()
