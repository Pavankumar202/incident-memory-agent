"""
test_guard.py -- offline unit tests for _guard_plan warning consistency.
No network calls; mocks recalled_memories directly.
"""
import sys
sys.stdout.reconfigure(encoding="utf-8")

import os
os.environ.setdefault("GROQ_API_KEY", "dummy")
os.environ.setdefault("HINDSIGHT_API_KEY", "dummy")
os.environ.setdefault("HINDSIGHT_BASE_URL", "https://dummy")

from agent import _guard_plan

PASS = "PASS"
FAIL = "FAIL"
results = []

def check(label, condition, detail=""):
    tag = PASS if condition else FAIL
    results.append((tag, label, detail))
    print(f"[{tag}] {label}" + (f"\n       {detail}" if detail else ""))

# --- Scenario 1: Same-service rollback removed ---
print("\n--- Scenario 1: same-service rollback removed ---")
plan1 = {
    "likely_root_cause": "Bad deploy v2.18.0",
    "recommended_steps": [
        "Check error logs for payment-gateway pods",
        "Roll back to previous version via kubectl rollout undo",
    ],
    "memories_used": ["LIVE-001: rollback failed on payment-gateway"],
    "warnings": ["Rolling back to previous version failed in payment-gateway (LIVE-001)."],
    "confidence": "medium",
    "no_history": False,
}
recalled1 = [
    "LIVE-001 on payment-gateway. Alert: 5xx errors after deploy v2.18.0. "
    "Fix steps: Roll back to previous version via kubectl rollout undo. RESULT: the fix FAILED.",
]
out1 = _guard_plan(plan1, alert_service="payment-gateway", recalled_memories=recalled1)
w1 = out1["warnings"]
steps1 = out1["recommended_steps"]
check("S1: rollback step removed", not any("roll back" in s.lower() or "rollout undo" in s.lower() for s in steps1))
check("S1: exactly one warning", len(w1) == 1, f"warnings={w1}")
check("S1: warning contains 'failed before in payment-gateway'", any("failed before in payment-gateway" in w for w in w1), str(w1))
check("S1: warning contains 'Removed from recommended steps'", any("Removed from recommended steps" in w for w in w1), str(w1))
check("S1: NO extra Caution warning", not any(w.startswith("Caution") for w in w1), str(w1))
check("S1: diagnostic step kept", any("Check error logs" in s for s in steps1), str(steps1))

# --- Scenario 2: Different-service failure — caution only, step kept ---
print("\n--- Scenario 2: cross-service pool+restart — caution only, step kept ---")
plan2 = {
    "likely_root_cause": "Redis connection exhaustion",
    "recommended_steps": [
        "Inspect Redis slow log",
        "Increase REDIS_POOL_SIZE and restart checkout-service pods",
    ],
    "memories_used": ["INC-006: pool size increase and pod restart failed on search-service"],
    "warnings": ["Increasing REDIS_POOL_SIZE from 10 to 50 and restarting pods failed in search-service (INC-006)."],
    "confidence": "medium",
    "no_history": False,
}
recalled2 = [
    "Incident INC-006 on search-service. Alert: search timeouts. "
    "Fix steps: Increase REDIS_POOL_SIZE from 10 to 50 and restart pods. RESULT: the fix FAILED.",
]
out2 = _guard_plan(plan2, alert_service="checkout-service", recalled_memories=recalled2)
w2 = out2["warnings"]
steps2 = out2["recommended_steps"]
check("S2: pool+restart step KEPT", any("pool" in s.lower() or "restart" in s.lower() for s in steps2), str(steps2))
check("S2: exactly one warning", len(w2) == 1, f"warnings={w2}")
check("S2: warning is a Caution", any(w.startswith("Caution") for w in w2), str(w2))
check("S2: Caution names search-service", any("search-service" in w for w in w2), str(w2))
check("S2: NO Removed in warnings", not any("Removed from recommended steps" in w for w in w2), str(w2))

# --- Scenario 3: No step matches failure — no Removed in warnings ---
print("\n--- Scenario 3: no step removed — no Removed in warnings ---")
plan3 = {
    "likely_root_cause": "High CPU",
    "recommended_steps": ["Check CPU metrics", "Scale up replicas to 5"],
    "memories_used": [],
    "warnings": [],
    "confidence": "low",
    "no_history": False,
}
out3 = _guard_plan(plan3, alert_service="payment-gateway", recalled_memories=[])
w3 = out3["warnings"]
check("S3: no warnings", len(w3) == 0, str(w3))
check("S3: no Removed word", not any("Removed" in w for w in w3), str(w3))

# --- Scenario 4: Diagnostic feedback fails — no step removed ---
print("\n--- Scenario 4: diagnostic feedback fails — no step removed ---")
plan4 = {
    "likely_root_cause": "Unknown",
    "recommended_steps": [
        "Check application logs for payment-gateway",
        "Verify FRAUD_API_URL environment variable",
        "Roll back to v2.17.0 via kubectl rollout undo",
    ],
    "memories_used": ["LIVE-002: checking logs and verifying env failed"],
    "warnings": ["Checking logs, verifying FRAUD_API_URL, and comparing code diffs failed in payment-gateway (LIVE-002)."],
    "confidence": "low",
    "no_history": False,
}
recalled4 = [
    "Feedback for LIVE-002 on payment-gateway: the recommended fix "
    "'checking logs, verifying FRAUD_API_URL, and comparing code diffs' RESULT: FAILED.",
]
out4 = _guard_plan(plan4, alert_service="payment-gateway", recalled_memories=recalled4)
steps4 = out4["recommended_steps"]
w4 = out4["warnings"]
check("S4: rollback step kept", any("roll back" in s.lower() or "rollout undo" in s.lower() for s in steps4), str(steps4))
check("S4: diagnostic steps kept", any("Check application logs" in s for s in steps4), str(steps4))
check("S4: no Removed from recommended steps", not any("Removed from recommended steps" in w for w in w4), str(w4))

# --- Summary ---
print()
total = len(results)
passed = sum(1 for r in results if r[0] == PASS)
print(f"Results: {passed}/{total} passed, {total-passed} failed")
if total - passed:
    sys.exit(1)
