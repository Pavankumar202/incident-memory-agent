import json
import os
import re
import time

from dotenv import load_dotenv
from groq import Groq

from memory import recall_similar

load_dotenv()

MODEL = "openai/gpt-oss-120b"
groq_client = Groq(api_key=os.environ["GROQ_API_KEY"])

SYSTEM_PROMPT = """You are an on-call incident response assistant for an engineering team.
You receive a new production alert and, when available, memories of past incidents.

Rules:
- Base your advice on the provided memories. Do not invent past incidents.
- Never recommend an action that is listed under "warnings" as failed, or any smaller or partial version of it.
- If memories conflict (a fix worked in one incident but a later incident or live feedback says it failed for the same service and symptom), the failure wins: do not repeat the fix. List the failed action under "warnings", and recommend diagnostics for other likely causes instead.
- Do not state current settings or values (pool size, hosts, key names) as facts unless they appear in the new alert. Past values are evidence from past incidents, not facts about this one. Never claim current settings like "pool size is currently 10" unless that exact number appears in the new alert.
- Confidence rules: Use confidence "high" ONLY if the exact root cause is explicitly stated in the alert text itself. If the alert only reports symptoms (such as high latency, Redis connections at 100%, 5xx errors, or timeouts), the root cause is merely an inference or hypothesis, so confidence MUST be at most "medium" (or "low"). In that case, word likely_root_cause as a hypothesis (e.g., "Hypothesis: ..."), and the very first recommended step MUST be a diagnostic check that would confirm or rule it out.
- Each memories_used entry must be "INC-xxx: what it taught you" (or "LIVE-xxx: ..." for feedback), never just an ID.
- If no memory is clearly relevant, set no_history true, confidence "low", say so plainly, and give general first-response steps. Never invent a past incident.
- Attribute every past outcome to the exact incident and service it came from. Never describe an outcome from one service as if it happened in another.

Respond with ONLY a JSON object with these keys:
"likely_root_cause": string,
"recommended_steps": list of short strings, in order,
"memories_used": list of strings (each formatted as "INC-xxx: what it taught you" or "LIVE-xxx: what it taught you", empty if none),
"warnings": list of strings (for example fixes that failed before),
"confidence": "low", "medium", or "high",
"no_history": true or false
"""


def _parse_json(text: str) -> dict:
    """Parse the model output, tolerating stray text around the JSON."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise


def _find_source_id(step: str, warnings: list[str]) -> str | None:
    """Find the specific incident or live feedback ID responsible for failing this step."""
    s_lower = step.lower()
    for w in warnings:
        w_lower = w.lower()
        overlap = False
        if (("increase" in s_lower or "raise" in s_lower) and "pool" in s_lower) and (
            ("increase" in w_lower or "raise" in w_lower) and "pool" in w_lower
        ):
            overlap = True
        elif "restart" in s_lower and "restart" in w_lower:
            overlap = True
        elif ("rollback" in s_lower or "roll back" in s_lower) and (
            "rollback" in w_lower or "roll back" in w_lower
        ):
            overlap = True
        elif any(
            act in s_lower and act in w_lower
            for act in ("increase pool", "raise pool", "restart", "rollback", "roll back")
        ):
            overlap = True

        if overlap:
            match = re.search(r"\b(INC-\d+|LIVE-\w+)\b", w, re.IGNORECASE)
            if match:
                return match.group(1).upper()

    for w in warnings:
        match = re.search(r"\b(INC-\d+|LIVE-\w+)\b", w, re.IGNORECASE)
        if match:
            return match.group(1).upper()
    return None


def _guard_plan(plan: dict) -> dict:
    """Defensive guard to clean output and remove failed actions from recommendations."""
    # Drop empty strings from list fields and unpack conjoined items
    for key in ("recommended_steps", "memories_used", "warnings"):
        if isinstance(plan.get(key), list):
            cleaned = []
            for s in plan[key]:
                if isinstance(s, str) and '","' in s:
                    cleaned.extend([part.strip().strip('"') for part in s.split('","') if part.strip()])
                elif isinstance(s, str) and s.strip():
                    cleaned.append(s.strip())
            plan[key] = cleaned

    # Remove recommended steps that repeat actions that warnings note as failed
    warnings_text = " ".join(plan.get("warnings", [])).lower()
    actions = ["increase pool", "raise pool", "increasing pool", "raising pool", "restart", "rollback", "roll back"]
    failed_actions = [a for a in actions if a in warnings_text]
    pool_failed = ("increase" in warnings_text or "raise" in warnings_text) and "pool" in warnings_text
    restart_failed = "restart" in warnings_text
    rollback_failed = "rollback" in warnings_text or "roll back" in warnings_text

    clean_steps = []
    removed_warnings = []
    for step in plan.get("recommended_steps", []):
        s_lower = step.lower()
        step_pool = ("increase" in s_lower or "raise" in s_lower) and "pool" in s_lower
        step_restart = "restart" in s_lower
        step_rollback = "rollback" in s_lower or "roll back" in s_lower
        if (
            any(a in s_lower for a in failed_actions)
            or (pool_failed and step_pool)
            or (restart_failed and step_restart)
            or (rollback_failed and step_rollback)
        ):
            source_id = _find_source_id(step, plan.get("warnings", []))
            if source_id:
                removed_warnings.append(f"Removed step '{step}' because it failed before ({source_id}).")
            else:
                removed_warnings.append(f"Removed step '{step}' because it failed before.")
            continue
        clean_steps.append(step)

    for rw in removed_warnings:
        plan.setdefault("warnings", []).append(rw)
    plan["recommended_steps"] = clean_steps
    return plan


def _ask_llm(user_prompt: str, retries: int = 3) -> dict:
    last_error = None
    for attempt in range(retries):
        try:
            resp = groq_client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0,
                response_format={"type": "json_object"},
            )
            parsed = _parse_json(resp.choices[0].message.content)
            return _guard_plan(parsed)
        except Exception as e:  # rate limit, bad JSON, function-call errors
            last_error = e
            time.sleep(1.5 * (attempt + 1))
    return _guard_plan({
        "likely_root_cause": f"LLM call failed: {last_error}",
        "recommended_steps": ["Check logs and recent deploys manually."],
        "memories_used": [],
        "warnings": ["The assistant could not generate a response."],
        "confidence": "low",
        "no_history": True,
    })


def respond_to_alert(service: str, alert: str, use_memory: bool = True) -> dict:
    """Main entry point used by the UI. Returns the plan plus the raw memories."""
    memories = []
    if use_memory:
        try:
            memories = recall_similar(f"{service}: {alert}")
        except Exception as e:
            print(f"[agent] recall failed: {e}")

    if memories:
        memory_block = "\n".join(f"- {m}" for m in memories)
    else:
        memory_block = "(no relevant past incidents found)"

    prompt = (
        f"NEW ALERT\nService: {service}\nAlert: {alert}\n\n"
        f"PAST INCIDENT MEMORIES\n{memory_block}"
    )
    plan = _ask_llm(prompt)
    plan["recalled_memories"] = memories
    plan["used_memory"] = use_memory
    return plan


if __name__ == "__main__":
    with open("data/demo_alerts.json") as f:
        alerts = json.load(f)

    # Pick the search-service alert: the best before/after moment
    demo = next(a for a in alerts if a["service"] == "search-service")

    for use_memory in (False, True):
        print("=" * 70)
        print("MEMORY ON" if use_memory else "MEMORY OFF")
        print("=" * 70)
        result = respond_to_alert(demo["service"], demo["alert"], use_memory)
        print(json.dumps(result, indent=2))