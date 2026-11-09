
import os

from dotenv import load_dotenv
from hindsight_client import Hindsight

load_dotenv()

BANK_ID = os.getenv("BANK_ID", "oncall-payments-team")


def _require_config():
    missing = [
        key
        for key in ("HINDSIGHT_API_KEY", "HINDSIGHT_BASE_URL")
        if not os.getenv(key)
    ]

    if missing:
        raise RuntimeError(
            f"Missing {', '.join(missing)} in .env"
        )


def _call(method: str, **kwargs):
    """Execute a synchronous Hindsight SDK operation."""

    _require_config()

    client = Hindsight(
        base_url=os.environ["HINDSIGHT_BASE_URL"],
        api_key=os.environ["HINDSIGHT_API_KEY"],
        timeout=60.0,
    )

    try:
        return getattr(client, method)(**kwargs)
    finally:
        client.close()


def ensure_bank():
    """Create the memory bank. Run during initial setup."""

    return _call(
        "create_bank",
        bank_id=BANK_ID,
        name="On-call Payments Team",
    )


def retain_incident(inc: dict):
    """Store a historical incident."""

    content = (
        f"Incident {inc['id']} on {inc['service']}. "
        f"Alert: {inc['alert']}. "
        f"Logs: {inc['logs']}. "
        f"Root cause: {inc['root_cause']}. "
        f"Fix steps: {inc['fix_steps']}. "
        f"RESULT: The fix {inc['outcome'].upper()} "
        f"(resolved in {inc['minutes_to_resolve']} minutes)."
    )

    result = _call(
        "retain_batch",
        bank_id=BANK_ID,
        items=[
            {
                "content": content,
                "context": "incident",
                "metadata": {"incident_id": inc["id"]},
            }
        ],
        retain_async=False,
    )

    print(f"[memory] retained {inc['id']}")
    return result


def retain_outcome(
    incident_id: str,
    service: str,
    fix: str,
    outcome: str,
    alert: str = "",
    root_cause: str = "",
    minutes: int | None = None,
):
    """Store engineer feedback for future incidents."""

    content = f"Feedback for {incident_id} on {service}."

    if alert:
        content += f" Original alert: {alert}."

    content += f" Recommended fix: {fix}."
    content += f" RESULT: {outcome.upper()}."

    if root_cause:
        content += f" Confirmed root cause: {root_cause}."

    if minutes is not None:
        content += f" Resolved in {minutes} minutes."

    return _call(
        "retain_batch",
        bank_id=BANK_ID,
        items=[
            {
                "content": content,
                "context": "outcome-feedback",
                "metadata": {
                    "incident_id": incident_id,
                    "service": service,
                    "outcome": outcome,
                },
            }
        ],
        retain_async=False,
    )


def recall_similar(
    alert_text: str,
    max_tokens: int = 1024,
    limit: int = 8,
) -> list[str]:
    """Retrieve relevant historical incident memories."""

    results = _call(
        "recall",
        bank_id=BANK_ID,
        query=alert_text,
        max_tokens=max_tokens,
        budget="mid",
    )

    seen = set()
    memories = []

    for result in results.results:
        text = result.text.strip()

        if text and text not in seen:
            seen.add(text)
            memories.append(text)

    return memories[:limit]
