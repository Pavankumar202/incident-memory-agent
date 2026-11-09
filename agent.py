import json
import os
import re
import time

from dotenv import load_dotenv
from groq import Groq

from memory import recall_similar

load_dotenv()

INCIDENTS_BY_ID = {}
try:
    with open("data/incidents.json") as f:
        for inc in json.load(f):
            INCIDENTS_BY_ID[inc["id"]] = inc["service"]
except Exception:
    pass

MODEL = "openai/gpt-oss-120b"
groq_client = Groq(api_key=os.environ["GROQ_API_KEY"])

SYSTEM_PROMPT = """You are an on-call incident response assistant for an engineering team.
You receive a new production alert and, when available, memories of past incidents.

Rules:
- Base your advice on the provided memories. Do not invent past incidents.
- Never recommend an action that is listed under "warnings" as failed, or any smaller or partial version of it.
- If memories conflict (a fix worked in one incident but a later incident or live feedback says it failed for the same service and symptom), the failure wins: do not repeat the fix. List the failed action under "warnings", and recommend diagnostics for other likely causes instead.
- Do not treat diagnostic steps (check, inspect, verify, compare, review, collect, monitor logs/metrics/diffs) as "failed fixes". If a memory describes a diagnostic failure, show nothing as a warning and do not remove any step because of it. Diagnostics are never failures of a fix; they are just information-gathering. Never warn against diagnostic steps.
- Do not state current settings or values (pool size, hosts, key names) as facts unless they appear in the new alert. Past values are evidence from past incidents, not facts about this one. Never claim current settings like "pool size is currently 10" unless that exact number appears in the new alert.
- Confidence rules: Use confidence "high" ONLY if the exact root cause is explicitly stated in the alert text itself. If the alert only reports symptoms (such as high latency, Redis connections at 100%, 5xx errors, or timeouts), the root cause is merely an inference or hypothesis, so confidence MUST be at most "medium" (or "low"). In that case, word likely_root_cause as a hypothesis (e.g., "Hypothesis: ..."), and the very first recommended step MUST be a diagnostic check that would confirm or rule it out.
- Every warning that cites a past failure must explicitly include the service it happened in: "... failed in <service> (<INC-xxx or LIVE-xxx>)". Never cite a past failure without stating which service it occurred in.
- If a past failure occurred in a DIFFERENT service than the current alert's service, do not advise against that action blindly; instead phrase it as a caution: "Caution: <action> failed in <other-service> (<ID>); verify it applies to <alert-service> before applying."
- Each memories_used entry must be "INC-xxx: what it taught you" (or "LIVE-xxx: ..." for feedback), never just an ID.
- Any INC- or LIVE- ID cited in "warnings" MUST also appear in "memories_used".
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


def _find_service_for_memory(mem_id: str, recalled_memories: list[str]) -> str | None:
    """Identify the originating service for an incident or live feedback ID."""
    if mem_id in INCIDENTS_BY_ID:
        return INCIDENTS_BY_ID[mem_id]

    for m in recalled_memories:
        if mem_id in m:
            m_where = re.search(r"Where:\s*([\w\-]+)", m)
            if m_where:
                return m_where.group(1).strip()
            m_on = re.search(r"(?:for\s+" + re.escape(mem_id) + r"\s+on|on)\s+([\w\-]+)", m)
            if m_on:
                return m_on.group(1).strip()
            m_issue = re.search(r"([\w\-]+)\s+issue\s+" + re.escape(mem_id), m)
            if m_issue:
                return m_issue.group(1).strip()
            m_inc = re.search(re.escape(mem_id) + r"\s+(?:occurred\s+)?on\s+([\w\-]+)", m)
            if m_inc:
                return m_inc.group(1).strip()
    return None


def _is_diagnostic_action(text: str) -> bool:
    """Return True if text describes diagnostic / information-gathering steps rather than a remediation fix."""
    t = text.lower()

    # Concrete remediation keywords take precedence
    remediation_keywords = (
        "rollback", "roll back", "rolling back", "rollout undo",
        "restart", "restarting",
        "scale", "scaling",
        "config change", "configuration change",
        "patch", "patching",
        "hotfix",
        "redeploy", "redeploying",
        "increase pool", "raise pool", "pool size", "pool_size",
        "revert", "reverting",
    )
    if any(rk in t for rk in remediation_keywords):
        return False

    diagnostic_verbs = (
        "check", "checking",
        "inspect", "inspecting",
        "verify", "verifying",
        "compare", "comparing",
        "review", "reviewing",
        "collect", "collecting",
        "monitor", "monitoring",
        "examine", "examining",
        "analyze", "analyzing",
        "investigate", "investigating",
        "audit", "auditing",
        "observe", "observing",
        "search", "searching",
        "tail", "tailing",
        "query", "querying",
    )

    diagnostic_nouns = (
        "log", "logs",
        "metric", "metrics",
        "diff", "diffs",
        "env", "environment",
        "credential", "credentials",
        "configmap", "configuration", "config",
        "trace", "traces",
        "dashboard", "dashboards",
        "latency",
        "status",
        "health",
        "slowlog",
        "commit", "commits",
        "pr", "pull request",
        "dump", "dumps",
        "diagnostic", "diagnostics",
    )

    has_verb = any(re.search(rf"\b{re.escape(v)}\b", t) for v in diagnostic_verbs)
    has_noun = any(re.search(rf"\b{re.escape(n)}\b", t) for n in diagnostic_nouns)

    if has_verb and has_noun:
        return True

    if "diagnostic" in t:
        return True

    return False


def _guard_plan(plan: dict, alert_service: str = "", recalled_memories: list[str] = None) -> dict:
    """Service-aware defensive guard to clean output, enforce consistency, and check failed actions."""
    if recalled_memories is None:
        recalled_memories = []

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

    # Catalog all failure memories from warnings and recalled_memories
    # Diagnostic steps are NEVER treated as failed fixes
    failed_sources = {}
    for text in (plan.get("warnings", []) + recalled_memories):
        t_lower = text.lower()
        if "fail" in t_lower:
            if _is_diagnostic_action(t_lower):
                continue
            m_id = re.search(r"\b(INC-\d+|LIVE-\w+)\b", text, re.IGNORECASE)
            if m_id:
                cid = m_id.group(1).upper()
                svc = _find_service_for_memory(cid, recalled_memories)
                if cid not in failed_sources and svc:
                    failed_sources[cid] = (svc, t_lower)

    # Normalize existing warnings to ensure every cited failure includes the service it happened in
    normalized_warnings = []
    for w in plan.get("warnings", []):
        w_lower = w.lower()
        if _is_diagnostic_action(w_lower):
            continue
        id_match = re.search(r"\b(INC-\d+|LIVE-\w+)\b", w, re.IGNORECASE)
        if id_match and ("fail" in w_lower):
            cid = id_match.group(1).upper()
            # If the underlying memory for this ID is diagnostic, drop the warning
            if any(cid in m.upper() and _is_diagnostic_action(m) for m in recalled_memories):
                continue
            svc = _find_service_for_memory(cid, recalled_memories)
            if svc and svc.lower() not in w_lower:
                if f"({id_match.group(1)})" in w:
                    w = w.replace(f"({id_match.group(1)})", f"in {svc} ({cid})")
                elif f"({cid})" in w:
                    w = w.replace(f"({cid})", f"in {svc} ({cid})")
                elif "failed" in w:
                    w = re.sub(rf"failed(?:\s+before)?(?:\s+for\s+{cid})?", f"failed in {svc} ({cid})", w)
                else:
                    w = f"{w} (failed in {svc})"
            # If the failure came from a different service, format as caution
            if svc and alert_service and svc.lower() != alert_service.lower():
                if not w.startswith("Caution:"):
                    w = f"Caution: fix failed in {svc} ({cid}); verify it applies to {alert_service} before applying."
        normalized_warnings.append(w)
    plan["warnings"] = normalized_warnings

    # Inspect recommended steps against failed actions
    clean_steps = []
    removed_warnings = []
    caution_warnings = []

    for step in plan.get("recommended_steps", []):
        # Diagnostic steps are information-gathering and must never be removed
        if _is_diagnostic_action(step):
            clean_steps.append(step)
            continue

        s_lower = step.lower()
        # Full action match 1: increase pool size AND restart
        step_is_pool_and_restart = (
            (("increase" in s_lower or "raise" in s_lower) and "pool" in s_lower)
            and "restart" in s_lower
        )
        # Full action match 2: rollback to previous version / rollout undo
        step_is_rollback = (
            "rollback" in s_lower or "roll back" in s_lower or "rolling back" in s_lower or "rollout undo" in s_lower
        )

        remove_this_step = False

        if step_is_pool_and_restart:
            matched_id, matched_svc = None, None
            for cid, (svc, t_lower) in failed_sources.items():
                if ("pool" in t_lower) and ("restart" in t_lower or "fail" in t_lower):
                    matched_id, matched_svc = cid, svc
                    if alert_service and svc.lower() == alert_service.lower():
                        break

            if matched_id:
                if alert_service and matched_svc and matched_svc.lower() == alert_service.lower():
                    removed_warnings.append(
                        f"'{step}' failed before in {matched_svc} ({matched_id}). Removed from recommended steps."
                    )
                    remove_this_step = True
                else:
                    caution_msg = f"Caution: increasing pool size and restarting pods failed in {matched_svc} ({matched_id}); verify it applies to {alert_service} before applying."
                    if caution_msg not in plan["warnings"] and caution_msg not in caution_warnings:
                        caution_warnings.append(caution_msg)

        elif step_is_rollback:
            matched_id, matched_svc = None, None
            for cid, (svc, t_lower) in failed_sources.items():
                if "rollback" in t_lower or "roll back" in t_lower or "rolling back" in t_lower or "rollout undo" in t_lower:
                    matched_id, matched_svc = cid, svc
                    if alert_service and svc.lower() == alert_service.lower():
                        break

            if matched_id:
                if alert_service and matched_svc and matched_svc.lower() == alert_service.lower():
                    removed_warnings.append(
                        f"'{step}' failed before in {matched_svc} ({matched_id}). Removed from recommended steps."
                    )
                    remove_this_step = True
                else:
                    caution_msg = f"Caution: rollback failed in {matched_svc} ({matched_id}); verify it applies to {alert_service} before applying."
                    if caution_msg not in plan["warnings"] and caution_msg not in caution_warnings:
                        caution_warnings.append(caution_msg)
        else:
            # Check if this exact remediation step matches a recorded failed action in failed_sources
            for cid, (svc, t_lower) in failed_sources.items():
                if s_lower in t_lower:
                    if alert_service and svc.lower() == alert_service.lower():
                        removed_warnings.append(
                            f"'{step}' failed before in {svc} ({cid}). Removed from recommended steps."
                        )
                        remove_this_step = True
                        break

        if not remove_this_step:
            clean_steps.append(step)

    # Collect IDs already covered by step-loop warnings so we don't duplicate from normalized_warnings
    removed_ids = set(re.findall(r"\b(INC-\d+|LIVE-\w+)\b", " ".join(removed_warnings), re.IGNORECASE))
    caution_ids = set(re.findall(r"\b(INC-\d+|LIVE-\w+)\b", " ".join(caution_warnings), re.IGNORECASE))
    skip_ids = removed_ids | caution_ids

    # Build final warnings list:
    #   - normalized_warnings: skip any whose ID is already in skip_ids (removed or caution already emitted)
    #   - then caution_warnings (cross-service, step kept)
    #   - then removed_warnings (same-service, step removed)
    all_warnings = []
    seen_w = set()
    for w in normalized_warnings:
        id_in_w = re.search(r"\b(INC-\d+|LIVE-\w+)\b", w, re.IGNORECASE)
        if id_in_w and id_in_w.group(1).upper() in skip_ids:
            continue  # already covered by caution_warnings or removed_warnings; don't duplicate
        w_clean = " ".join(w.split())
        if w_clean not in seen_w:
            seen_w.add(w_clean)
            all_warnings.append(w_clean)
    for w in (caution_warnings + removed_warnings):
        w_clean = " ".join(w.split())
        if w_clean not in seen_w:
            seen_w.add(w_clean)
            all_warnings.append(w_clean)

    plan["warnings"] = all_warnings
    plan["recommended_steps"] = clean_steps

    # Ensure any INC- or LIVE- ID cited in warnings appears in memories_used
    cited_ids = set(re.findall(r"\b(INC-\d+|LIVE-\w+)\b", " ".join(plan.get("warnings", [])), re.IGNORECASE))
    existing_memories_text = " ".join(plan.get("memories_used", []))
    for cid in cited_ids:
        cid_upper = cid.upper()
        if cid_upper not in existing_memories_text.upper():
            lesson = ""
            for m in recalled_memories:
                if cid_upper in m.upper():
                    lesson = m.split(" | ")[0].strip()
                    break
            svc = _find_service_for_memory(cid_upper, recalled_memories) or alert_service
            if not lesson:
                lesson = f"past failure noted in warnings for {svc}"
            if not lesson.startswith(cid_upper):
                entry = f"{cid_upper}: {lesson}"
            else:
                entry = lesson
            plan.setdefault("memories_used", []).append(entry)

    # Do not treat diagnostic steps as failed fixes in memories_used
    clean_memories_used = []
    for m in plan.get("memories_used", []):
        m_lower = m.lower()
        if "fail" in m_lower and _is_diagnostic_action(m_lower):
            continue
        clean_memories_used.append(m)
    plan["memories_used"] = clean_memories_used

    return plan


def _ask_llm(user_prompt: str, alert_service: str = "", recalled_memories: list[str] = None, retries: int = 3) -> dict:
    if recalled_memories is None:
        recalled_memories = []
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
            return _guard_plan(parsed, alert_service=alert_service, recalled_memories=recalled_memories)
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
    }, alert_service=alert_service, recalled_memories=recalled_memories)


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
    plan = _ask_llm(prompt, alert_service=service, recalled_memories=memories)
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