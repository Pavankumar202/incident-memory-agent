import json
import time

import streamlit as st

from agent import respond_to_alert
from memory import BANK_ID, retain_outcome

st.set_page_config(page_title="Incident Memory Agent", layout="wide")
st.title("On-Call Incident Copilot")
st.caption("An incident agent that remembers what worked, and what didn't, using Hindsight memory.")
st.sidebar.markdown(f"**Hindsight Bank ID:** `{BANK_ID}`")

with open("data/demo_alerts.json") as f:
    ALERTS = json.load(f)

labels = [f"{a['service']}: {a['alert']}" for a in ALERTS]
choice = st.selectbox("Simulate an incoming alert", labels)
alert = ALERTS[labels.index(choice)]

mode = st.radio("Mode", ["Compare both", "Memory ON", "Memory OFF"], horizontal=True)

if st.button("Analyze alert", type="primary"):
    st.session_state.alert = alert
    st.session_state.results = {}
    with st.spinner("Recalling past incidents and thinking..."):
        if mode in ("Compare both", "Memory OFF"):
            st.session_state.results["off"] = respond_to_alert(alert["service"], alert["alert"], use_memory=False)
        if mode in ("Compare both", "Memory ON"):
            st.session_state.results["on"] = respond_to_alert(alert["service"], alert["alert"], use_memory=True)


def render_plan(plan: dict, key: str):
    if plan.get("no_history") and plan.get("used_memory"):
        st.warning("No similar past incidents found. Using cautious generic steps.")
    st.markdown(f"**Likely root cause:** {plan['likely_root_cause']}")
    st.markdown(f"**Confidence:** {plan['confidence']}")
    st.markdown("**Recommended steps**")
    for i, step in enumerate(plan["recommended_steps"], 1):
        st.markdown(f"{i}. {step}")
    for w in plan.get("warnings", []):
        st.error(f"⚠️ {w}")

    if plan["used_memory"]:
        st.markdown("**🧠 Memories used**")
        memories = plan.get("memories_used", [])
        if memories:
            for m in memories:
                st.info(str(m))
        else:
            st.info("(none cited)")
        with st.expander(f"All {len(plan['recalled_memories'])} recalled memories"):
            for m in plan["recalled_memories"]:
                st.write(f"- {m}")

        st.markdown("**Did this work? Teach the agent:**")
        steps = plan.get("recommended_steps", [])
        remediation_keywords = ("rollback", "roll back", "restart", "scale", "config change", "patch", "hotfix", "revert", "redeploy")
        default_idx = 0
        for idx, s in enumerate(steps):
            if any(kw in s.lower() for kw in remediation_keywords):
                default_idx = idx
                break

        selected_step = st.selectbox(
            "Which step did you try?",
            steps if steps else ["(no steps)"],
            index=default_idx,
            key=f"{key}-selected-step",
        )

        c1, c2, c3 = st.columns(3)
        svc = st.session_state.alert["service"]
        inc_id = f"LIVE-{int(time.time())}"
        for col, label, outcome in ((c1, "✅ Worked", "worked"), (c2, "❌ Failed", "failed"), (c3, "➖ Partial", "partial")):
            if col.button(label, key=f"{key}-{outcome}") and steps:
                retain_outcome(inc_id, svc, selected_step, outcome)
                result_label = {"worked": "✅ worked", "failed": "❌ failed", "partial": "➖ partial"}[outcome]
                st.session_state[f"{key}-feedback-msg"] = (
                    f"Saved to Hindsight memory: '{selected_step}' marked {result_label} for {svc}."
                )

        if st.session_state.get(f"{key}-feedback-msg"):
            st.success(st.session_state[f"{key}-feedback-msg"])
    else:
        st.caption("No memory used. This is the generic baseline.")


results = st.session_state.get("results", {})
if results:
    if "on" in results and "off" in results:
        left, right = st.columns(2)
        with left:
            st.subheader("Without memory")
            render_plan(results["off"], "off")
        with right:
            st.subheader("With Hindsight memory")
            render_plan(results["on"], "on")
    else:
        only = results.get("on") or results.get("off")
        render_plan(only, "single")