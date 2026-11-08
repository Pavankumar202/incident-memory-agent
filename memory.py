import os
from dotenv import load_dotenv
from hindsight_client import Hindsight

load_dotenv()

BANK_ID = "oncall-payments-team"

client = Hindsight(
    base_url=os.environ["HINDSIGHT_BASE_URL"],
    api_key=os.environ["HINDSIGHT_API_KEY"],
    timeout=60.0,
)


def ensure_bank():
    """Create the memory bank once; ignore the error if it already exists."""
    try:
        client.banks.create(bank_id=BANK_ID, name="On-call incident memory")
    except Exception as e:
        print(f"[memory] bank create skipped: {e}")


def retain_incident(inc: dict):
    """Store one past incident as a plain-text memory."""
    content = (
        f"Incident {inc['id']} on {inc['service']}. "
        f"Alert: {inc['alert']}. "
        f"Logs: {inc['logs']}. "
        f"Root cause: {inc['root_cause']}. "
        f"Fix steps: {inc['fix_steps']}. "
        f"Outcome: {inc['outcome']} (resolved in {inc['minutes_to_resolve']} minutes)."
    )
    client.retain_batch(
        bank_id=BANK_ID,
        items=[{"content": content, "context": "incident"}],
        retain_async=False,
    )
    print(f"[memory] retained {inc['id']}")


def retain_outcome(incident_id: str, service: str, fix: str, outcome: str):
    """Called when the engineer marks a recommended fix as worked / failed / partial."""
    content = (
        f"For incident {incident_id} on {service}, the recommended fix "
        f"'{fix}' had outcome: {outcome}."
    )
    client.retain_batch(
        bank_id=BANK_ID,
        items=[{"content": content, "context": "outcome-feedback"}],
        retain_async=False,
    )


def recall_similar(alert_text: str, max_tokens: int = 2048) -> list[str]:
    """Return the text of the memories most relevant to a new alert."""
    results = client.recall(
        bank_id=BANK_ID,
        query=alert_text,
        max_tokens=max_tokens,
        budget="mid",
    )
    return [r.text for r in results.results]