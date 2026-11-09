import os
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv
from hindsight_client import Hindsight

load_dotenv()

for var in ("HINDSIGHT_API_KEY", "HINDSIGHT_BASE_URL"):
    if not os.environ.get(var):
        raise SystemExit(f"Missing {var} in .env. Fill it in and save the file.")

BANK_ID = os.environ.get("BANK_ID", "oncall-payments-team")


def _call(method: str, **kwargs):
    """Run one Hindsight call in its own thread with a fresh client.
    This avoids event-loop clashes inside Streamlit and closes sessions cleanly."""

    def work():
        with Hindsight(
            base_url=os.environ["HINDSIGHT_BASE_URL"],
            api_key=os.environ["HINDSIGHT_API_KEY"],
            timeout=60.0,
        ) as c:
            return getattr(c, method)(**kwargs)

    with ThreadPoolExecutor(max_workers=1) as ex:
        return ex.submit(work).result()


def ensure_bank():
    """Banks are created automatically on first retain."""
    pass


def retain_incident(inc: dict):
    """Store one past incident as a plain-text memory."""
    content = (
        f"Incident {inc['id']} on {inc['service']}. "
        f"Alert: {inc['alert']}. "
        f"Logs: {inc['logs']}. "
        f"Root cause: {inc['root_cause']}. "
        f"Fix steps: {inc['fix_steps']}. "
        f"RESULT: the fix {inc['outcome'].upper()} "
        f"(resolved in {inc['minutes_to_resolve']} minutes)."
    )
    _call(
        "retain_batch",
        bank_id=BANK_ID,
        items=[{"content": content, "context": "incident"}],
        retain_async=False,
    )
    print(f"[memory] retained {inc['id']}")


def retain_outcome(
    incident_id: str,
    service: str,
    fix: str,
    outcome: str,
    alert: str = "",
    root_cause: str = "",
    minutes: int | None = None,
):
    """Called when the engineer marks a recommended fix as worked / failed / partial."""
    content = f"Feedback for {incident_id} on {service}: the recommended fix '{fix}' RESULT: {outcome.upper()}."

    if alert:
        content += f" Original alert: {alert}."
    if root_cause:
        content += f" Confirmed root cause: {root_cause}."
    if minutes is not None:
        content += f" Resolved in {minutes} minutes."

    _call(
        "retain_batch",
        bank_id=BANK_ID,
        items=[{"content": content, "context": "outcome-feedback"}],
        retain_async=False,
    )


def recall_similar(alert_text: str, max_tokens: int = 1024, limit: int = 25) -> list[str]:
    """Return the most relevant memories, deduplicated and capped."""
    results = _call(
        "recall",
        bank_id=BANK_ID,
        query=alert_text,
        max_tokens=max_tokens,
        budget="mid",
    )
    seen, out = set(), []
    for r in results.results:
        key = r.text.split(" | ")[0].strip()
        if key not in seen:
            seen.add(key)
            out.append(r.text)
    return out[:limit]
