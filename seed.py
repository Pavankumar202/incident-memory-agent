import json
from memory import ensure_bank, retain_incident

if __name__ == "__main__":
    ensure_bank()
    with open("data/incidents.json") as f:
        incidents = json.load(f)
    for inc in incidents:
        retain_incident(inc)
    print(f"Seeded {len(incidents)} incidents.")