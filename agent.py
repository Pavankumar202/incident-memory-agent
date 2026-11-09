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
- If a past fix FAILED or only partially worked, say so and do not recommend it blindly.
- If a past incident shows the real root cause was different from the first guess, use that.
- If there are no relevant memories, say so plainly and give cautious generic first steps.
- In "memories_used", write each entry as "<ID> (<service>): <one line on what happened and whether the fix worked or failed>".
- Memories whose ID starts with LIVE- are engineer feedback on earlier recommendations. Treat them like past incidents.
- Only attribute a detail (numbers, fix steps, outcomes) to an incident ID if the memory text states it for that exact ID. Never merge details from different incidents.
- If a memory says a fix FAILED, "did NOT work", or is a LESSON about a failed fix, never include that fix in "recommended_steps". Put it in "warnings" with the incident ID, e.g. "INC-006: raising REDIS_POOL_SIZE FAILED".
- When a root cause is identified from a successful incident, recommend that incident's fix steps first.
- If a memory says a fix FAILED, put it in "warnings" and name the incident ID, e.g. "INC-006: raising the pool size FAILED".
- "warnings" is only for cautions about failed or risky fixes. Never put successful fixes in warnings.
- Prefer memories from the same service as the alert. Ignore details from other services unless they clearly match the logs and symptoms.
- Set confidence to "high" when two or more memories from the same service directly match the alert's symptoms.
- A LESSON or failed fix applies ONLY to the service named in it. Ignore it entirely when the alert is for a different service, and never put it in "warnings" for a different service.
- Never recommend a step that you also list as a failed fix in "warnings". "warnings" and "recommended_steps" must not contradict each other.
- If successful incidents for the SAME service as the alert show a fix worked, recommend that fix.

Respond with ONLY a JSON object with these keys:
"likely_root_cause": string,
"recommended_steps": list of short strings, in order,
"memories_used": list of incident IDs or short descriptions you relied on (empty if none),
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
                temperature=0.2,
                response_format={"type": "json_object"},
            )
            return _parse_json(resp.choices[0].message.content)
        except Exception as e:  # rate limit, bad JSON, function-call errors
            last_error = e
            time.sleep(1.5 * (attempt + 1))
    return {
        "likely_root_cause": f"LLM call failed: {last_error}",
        "recommended_steps": ["Check logs and recent deploys manually."],
        "memories_used": [],
        "warnings": ["The assistant could not generate a response."],
        "confidence": "low",
        "no_history": True,
    }


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