"""demo_check.py - Automated verification and demo dry-run script.

Runs 3 scenarios against the current Hindsight memory bank:
1. checkout-service: Redis saturation (Memory OFF vs ON)
2. payment-gateway: 5xx errors after deploy (Memory ON, before feedback)
3. recommendations-worker: Unseen service/symptom (Memory ON)
"""
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from agent import respond_to_alert
from memory import BANK_ID


def print_summary(title: str, plan: dict):
    print(f"\n{'=' * 65}")
    print(f"SCENARIO: {title}")
    print(f"{'=' * 65}")
    print(f"Confidence:        {plan.get('confidence')}")
    print(f"No History:        {plan.get('no_history')}")
    print(f"Likely Root Cause: {plan.get('likely_root_cause')}")

    warnings = plan.get("warnings", [])
    print(f"Warnings ({len(warnings)}):")
    if warnings:
        for w in warnings:
            print(f"  * {w}")
    else:
        print("  (none)")

    memories_used = plan.get("memories_used", [])
    print(f"Memories Used ({len(memories_used)}):")
    if memories_used:
        for m in memories_used:
            print(f"  * {m}")
    else:
        print("  (none)")

    steps = plan.get("recommended_steps", [])
    print(f"Recommended Steps ({len(steps)}):")
    if steps:
        for i, s in enumerate(steps, 1):
            print(f"  {i}. {s}")
    else:
        print("  (none)")


def main():
    print(f"Running demo dry-run against Hindsight Bank ID: '{BANK_ID}'")

    # -------------------------------------------------------------
    # Scenario 1: checkout-service Redis saturation (Memory OFF & ON)
    # -------------------------------------------------------------
    svc_1 = "checkout-service"
    alert_1 = "p99 latency above 5s, Redis connections at 100%"

    print("\n>>> Scenario 1: checkout-service (Memory OFF)")
    res_1_off = respond_to_alert(svc_1, alert_1, use_memory=False)
    print_summary("1a. checkout-service (Memory OFF)", res_1_off)

    print("\n>>> Scenario 1: checkout-service (Memory ON)")
    res_1_on = respond_to_alert(svc_1, alert_1, use_memory=True)
    print_summary("1b. checkout-service (Memory ON)", res_1_on)

    # Check for leftover LIVE- memories in Scenario 1
    recalled_str = " ".join(res_1_on.get("recalled_memories", []))
    used_str = " ".join(res_1_on.get("memories_used", []))
    if "LIVE-" in recalled_str or "LIVE-" in used_str:
        print("\n[WARNING] LIVE- memory detected in Scenario 1!")
        print("          The current bank has leftover test feedback.")
        print("          For a clean presentation, set a fresh BANK_ID in .env and run python seed.py.")

    # -------------------------------------------------------------
    # Scenario 2: payment-gateway 5xx errors (Memory ON, before feedback)
    # -------------------------------------------------------------
    svc_2 = "payment-gateway"
    alert_2 = "5xx errors above 10% right after deploy v2.18.0"

    print("\n>>> Scenario 2: payment-gateway (Memory ON, before feedback)")
    res_2 = respond_to_alert(svc_2, alert_2, use_memory=True)
    print_summary("2. payment-gateway (Memory ON)", res_2)

    has_rollback = any(
        "rollback" in s.lower() or "roll back" in s.lower()
        for s in res_2.get("recommended_steps", [])
    )
    print(f"\nRollback step in recommended_steps: {has_rollback}")

    # -------------------------------------------------------------
    # Scenario 3: recommendations-worker GPU OOM (No history)
    # -------------------------------------------------------------
    svc_3 = "recommendations-worker"
    alert_3 = "GPU out of memory on worker-cuda-03"

    print("\n>>> Scenario 3: recommendations-worker (Memory ON, unseen alert)")
    res_3 = respond_to_alert(svc_3, alert_3, use_memory=True)
    print_summary("3. recommendations-worker (Memory ON)", res_3)

    is_expected_3 = (
        res_3.get("no_history") is True
        and res_3.get("confidence") == "low"
        and len(res_3.get("memories_used", [])) == 0
    )
    print(
        f"\nMatches expected (no_history=True, confidence='low', memories_used empty): {is_expected_3}"
    )


if __name__ == "__main__":
    main()