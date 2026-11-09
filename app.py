import json
import re
import time

import streamlit as st

from agent import respond_to_alert
from memory import BANK_ID, retain_outcome

# Incident MTTR lookup
INCIDENT_MINUTES = {}
try:
    with open("data/incidents.json") as f:
        for _inc in json.load(f):
            INCIDENT_MINUTES[_inc["id"]] = _inc.get("minutes_to_resolve", 15)
except Exception:
    pass

st.set_page_config(page_title="Incident Memory Agent", layout="wide")

# Sidebar: System Status & Hindsight Connection
with st.sidebar:
    st.subheader("⚡ System Status")
    st.markdown(f"**Hindsight Bank:** `{BANK_ID}`")
    try:
        with open("data/incidents.json") as f:
            inc_count = len(json.load(f))
    except Exception:
        inc_count = 15
    st.markdown(f"📁 **Seeded Incidents:** {inc_count} postmortems")
    st.markdown("⚡ **Inference Engine:** Groq (`gpt-oss-120b`)")
    st.markdown("---")
    st.markdown("🔗 [Hindsight Cloud Dashboard](https://ui.hindsight.vectorize.io)")
    st.markdown("📚 [Vectorize Hindsight Docs](https://hindsight.vectorize.io)")
    st.caption("Incident Copilot v1.0 • Hackathon 2026")

col_head, col_quick = st.columns([3, 2])
with col_head:
    st.title("On-Call Incident Copilot")
    st.caption(
        "An incident agent that remembers what worked, and what didn't, "
        "using Hindsight memory."
    )
with col_quick:
    st.write("")
    if st.button("🚀 1-Click Showcase Demo (Search Service)", type="secondary", use_container_width=True):
        with open("data/demo_alerts.json") as _f:
            _alerts = json.load(_f)
        _demo = next((a for a in _alerts if a["service"] == "search-service"), _alerts[0])
        st.session_state.alert = _demo
        st.session_state.inc_id = f"LIVE-{int(time.time())}"
        st.session_state.results = {}
        with st.spinner("Analyzing search-service alert with & without Hindsight memory..."):
            st.session_state.results["off"] = respond_to_alert(_demo["service"], _demo["alert"], use_memory=False)
            st.session_state.results["on"] = respond_to_alert(_demo["service"], _demo["alert"], use_memory=True)
        st.rerun()

with open("data/demo_alerts.json") as f:
    ALERTS = json.load(f)

custom_option = "✍️ Custom alert (type your own)..."
labels = [f"{a['service']}: {a['alert']}" for a in ALERTS] + [custom_option]
choice = st.selectbox("Simulate an incoming alert", labels)

if choice == custom_option:
    col_svc, col_alt = st.columns([1, 2])
    with col_svc:
        custom_service = st.text_input("Service name", placeholder="e.g. order-service")
    with col_alt:
        custom_alert_text = st.text_input("Alert message", placeholder="e.g. DB connection pool maxed out during checkout")
    alert = {
        "service": custom_service.strip() or "custom-service",
        "alert": custom_alert_text.strip() or "High error rate observed",
    }
else:
    alert = ALERTS[labels.index(choice)]

mode = st.radio(
    "Mode",
    ["Compare both", "Memory ON", "Memory OFF"],
    horizontal=True
)

if st.button("Analyze alert", type="primary"):
    st.session_state.alert = alert
    st.session_state.inc_id = f"LIVE-{int(time.time())}"
    st.session_state.results = {}

    with st.spinner("Recalling past incidents and thinking..."):
        if mode in ("Compare both", "Memory OFF"):
            st.session_state.results["off"] = respond_to_alert(
                alert["service"], alert["alert"], use_memory=False
            )

        if mode in ("Compare both", "Memory ON"):
            st.session_state.results["on"] = respond_to_alert(
                alert["service"], alert["alert"], use_memory=True
            )


def render_plan(plan: dict, key: str):

    # Triage Priority & Benchmark MTTR Badges
    alert_info = st.session_state.get("alert", {})
    alert_txt = (alert_info.get("alert", "") + " " + alert_info.get("service", "")).lower()

    if any(k in alert_txt for k in ("5xx", "100%", "oom", "handshake", "above 5s", "above 8s", "crash")):
        severity = "🔴 P1 - CRITICAL"
    elif any(k in alert_txt for k in ("disk usage", "lag", "96%", "delayed", "warning")):
        severity = "🟡 P2 - HIGH"
    else:
        severity = "🔵 P3 - MEDIUM"

    if plan.get("used_memory"):
        cited_ids = re.findall(r"INC-\d+", " ".join(plan.get("memories_used", [])))
        durations = [INCIDENT_MINUTES[m_id] for m_id in cited_ids if m_id in INCIDENT_MINUTES]
        if durations:
            avg_m = sum(durations) // len(durations)
            mttr_badge = f"⏱️ Historical MTTR: ~{avg_m}m"
        else:
            mttr_badge = "⏱️ Historical MTTR: ~15m"
    else:
        mttr_badge = "⏱️ Historical MTTR: Unknown"

    b_col1, b_col2 = st.columns([1, 1])
    b_col1.markdown(f"**Priority:** `{severity}`")
    b_col2.markdown(f"**{mttr_badge}**")

    if plan.get("no_history") and plan.get("used_memory"):
        st.warning(
            "No similar past incidents found. Using cautious generic steps."
        )

    st.markdown(f"**Likely root cause:** {plan['likely_root_cause']}")
    st.markdown(f"**Confidence:** {plan['confidence']}")

    st.markdown("**Recommended steps**")

    for i, step in enumerate(plan["recommended_steps"], 1):
        st.markdown(f"{i}. {step}")

    for warning in plan.get("warnings", []):
        st.error(f"⚠️ {warning}")

    if plan["used_memory"]:

        st.markdown("**🧠 Memories used**")

        for memory in plan.get("memories_used", []) or ["(none cited)"]:
            st.info(memory)

        recalled = plan.get("recalled_memories", [])

        with st.expander(f"All {len(recalled)} recalled memories"):
            for memory in recalled:
                st.write(f"- {memory}")

        st.markdown("**Did this work? Teach the agent:**")

        root = st.text_input(
            "Confirmed root cause (optional)",
            key=f"{key}-root"
        )

        mins = st.number_input(
            "Minutes to resolve (optional)",
            min_value=0,
            value=0,
            key=f"{key}-mins"
        )

        c1, c2, c3 = st.columns(3)

        fix = "; ".join(plan["recommended_steps"][:3])
        svc = st.session_state.alert["service"]
        alert_text = st.session_state.alert["alert"]
        inc_id = st.session_state.inc_id

        outcomes = (
            (c1, "✅ Worked", "worked"),
            (c2, "❌ Failed", "failed"),
            (c3, "➖ Partial", "partial")
        )

        for col, label, outcome in outcomes:
            if col.button(label, key=f"{key}-{outcome}"):

                retain_outcome(
                    inc_id,
                    svc,
                    fix,
                    outcome,
                    alert=alert_text,
                    root_cause=root,
                    minutes=int(mins) or None
                )

                st.success(
                    f"Saved to Hindsight memory: {outcome}"
                )

    else:
        st.caption("No memory used. This is the generic baseline.")

    # 📋 Slack / Incident War Room formatted snippet
    steps_txt = "\n".join(f"{i}. {s}" for i, s in enumerate(plan["recommended_steps"][:4], 1))
    warns_txt = ("\n⚠️ *Warning:* " + "\n⚠️ *Warning:* ".join(plan.get("warnings", []))) if plan.get("warnings") else ""
    mems_txt = ", ".join(plan.get("memories_used", [])) or "None"

    slack_snippet = (
        f"🚨 *[INCIDENT COPILOT TRIAGE: {st.session_state.get('alert', {}).get('service', 'service')}]*\n"
        f"• *Root Cause:* {plan.get('likely_root_cause', 'Under investigation')}\n"
        f"• *Confidence:* {plan.get('confidence', 'low').upper()}\n"
        f"• *Past Memories:* {mems_txt}\n"
        f"• *Action Steps:*\n{steps_txt}"
        f"{warns_txt}"
    )
    with st.expander("📋 Copy for Slack / Incident War Room"):
        st.code(slack_snippet, language="markdown")

    # 📥 Download Postmortem Markdown Button
    cur_svc = st.session_state.get("alert", {}).get("service", "service")
    cur_alt = st.session_state.get("alert", {}).get("alert", "")
    timestamp_str = time.strftime("%Y-%m-%d %H:%M:%S UTC")

    steps_list = "\n".join(f"{i}. {step}" for i, step in enumerate(plan.get("recommended_steps", []), 1))
    warns_list = "\n".join(f"- ⚠️ {w}" for w in plan.get("warnings", [])) if plan.get("warnings") else "- None"

    postmortem_md = (
        f"# Incident Postmortem Brief: {cur_svc}\n"
        f"**Generated:** {timestamp_str}\n"
        f"**Triage Priority:** {severity}\n"
        f"**Alert:** {cur_alt}\n"
        f"**Mode:** {'With Hindsight Memory' if plan.get('used_memory') else 'Baseline (Without Memory)'}\n\n"
        f"---\n\n"
        f"## 1. Executive Summary & Root Cause\n"
        f"- **Hypothesis:** {plan.get('likely_root_cause', 'Unknown')}\n"
        f"- **Confidence:** {plan.get('confidence', 'low').upper()}\n"
        f"- **Resolution Benchmark:** {mttr_badge}\n\n"
        f"## 2. Recommended Action Steps\n"
        f"{steps_list}\n\n"
        f"## 3. Past Incident Intelligence\n"
        f"- **Historical Memories Cited:** {mems_txt}\n"
        f"- **Warnings & Prevented Actions:**\n"
        f"{warns_list}\n\n"
        f"---\n"
        f"*Generated by Incident Memory Agent • Powered by Hindsight semantic memory & Groq LLM.*\n"
    )

    st.download_button(
        label="📥 Download Postmortem Brief (.md)",
        data=postmortem_md,
        file_name=f"POSTMORTEM_{cur_svc}_{int(time.time())}.md",
        mime="text/markdown",
        key=f"{key}-download-pm",
        use_container_width=True,
    )


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

# 📚 Collapsible Incident Knowledge Base Explorer
st.markdown("---")
with st.expander("📚 Browse 15 Seeded Incident Postmortems (Hindsight Memory Bank)"):
    try:
        with open("data/incidents.json") as f:
            incidents = json.load(f)

        f_col1, f_col2 = st.columns([1, 2])
        with f_col1:
            outcome_filter = st.selectbox(
                "Filter by outcome",
                ["All outcomes", "worked", "failed", "partial"]
            )
        with f_col2:
            svc_search = st.text_input(
                "Search service or alert keyword",
                placeholder="e.g. redis, checkout, search, deploy"
            )

        filtered = [
            inc for inc in incidents
            if (outcome_filter == "All outcomes" or inc["outcome"].lower() == outcome_filter.lower())
            and (
                not svc_search
                or svc_search.lower() in inc["service"].lower()
                or svc_search.lower() in inc["alert"].lower()
                or svc_search.lower() in inc["root_cause"].lower()
            )
        ]

        st.caption(f"Showing **{len(filtered)}** of **{len(incidents)}** historical incidents stored in memory bank `{BANK_ID}`:")
        for inc in filtered:
            outcome_badge = {
                "worked": "✅ Worked",
                "failed": "❌ Failed",
                "partial": "➖ Partial",
            }.get(inc["outcome"].lower(), inc["outcome"])

            with st.container(border=True):
                c_title, c_badge, c_mttr = st.columns([3, 1, 1])
                c_title.markdown(f"**{inc['id']}** — `{inc['service']}`")
                c_badge.markdown(f"**{outcome_badge}**")
                c_mttr.caption(f"⏱️ {inc['minutes_to_resolve']}m MTTR")
                st.markdown(f"**Alert:** {inc['alert']}")
                st.markdown(f"**Root Cause:** {inc['root_cause']}")
                st.markdown(f"**Fix Steps:** {inc['fix_steps']}")
    except Exception as e:
        st.error(f"Could not load incidents: {e}")
