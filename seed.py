"""
seed.py — Seed all historical incidents from data/incidents.json into Hindsight.

Run once during setup (or whenever you add new incidents):
    python seed.py
"""

import json
from memory import ensure_bank, retain_incident

if __name__ == "__main__":
    print("Creating / verifying Hindsight memory bank...")
    ensure_bank()
    print("Bank ready.\n")

    with open("data/incidents.json") as f:
        incidents = json.load(f)

    print(f"Seeding {len(incidents)} incidents into Hindsight memory bank:")
    print("-" * 60)

    for inc in incidents:
        retain_incident(inc)
        print(
            f"  ✓ {inc['id']:10s}  {inc['service']:22s}  "
            f"outcome={inc['outcome']:7s}  ({inc['minutes_to_resolve']}m)"
        )

    print("-" * 60)
    print(f"✅ Seeded {len(incidents)} incidents.")
