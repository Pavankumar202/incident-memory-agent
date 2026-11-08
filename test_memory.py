from memory import ensure_bank, retain_incident, recall_similar

ensure_bank()
retain_incident({
    "id": "INC-001",
    "service": "checkout-service",
    "alert": "p99 latency above 5s, Redis connections at 100%",
    "logs": "redis.exceptions.ConnectionError: Too many connections",
    "root_cause": "Redis connection pool size of 10 was too low",
    "fix_steps": "Raised pool size to 50 and restarted pods",
    "outcome": "worked",
    "minutes_to_resolve": 4,
})

for m in recall_similar("checkout latency spiking, Redis connections maxed out"):
    print("-", m)