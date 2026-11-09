# 🚨 Incident Memory Agent

> **An AI-powered On-Call Incident Copilot that remembers what worked, warns against what failed, and continuously learns from engineer feedback — powered by Hindsight semantic memory and Groq LLM inference.**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Streamlit](https://img.shields.io/badge/UI-Streamlit-FF4B4B.svg)](https://streamlit.io/)
[![Groq](https://img.shields.io/badge/LLM-Groq%20Cloud-f55036.svg)](https://groq.com/)
[![Hindsight](https://img.shields.io/badge/Memory-Hindsight-8A2BE2.svg)](https://hindsight.vectorize.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## 📖 Overview

During high-severity production incidents, on-call engineers are under immense pressure to triage and resolve outages quickly. Traditional approaches suffer from two major flaws:

1. **Tribal Knowledge Loss:** Past incident postmortems are buried across Jira tickets, Google Docs, or Slack threads. Engineers often repeat mistakes by applying fixes that previously failed.
2. **Generic LLM Hallucinations:** Standard LLMs lack organizational context and provide textbook troubleshooting advice that ignores your specific service architecture and incident history.

**Incident Memory Agent** solves this by pairing **Groq's** high-speed inference with **Hindsight's** semantic memory layer. The agent recalls past incident resolutions, warns engineers if a proposed fix has failed before, provides actionable step-by-step remediation plans, generates incident war room updates, and learns in real time from post-fix feedback.

---

## ✨ Key Features

- **🧠 Semantic Incident Memory (Hindsight):** Retains historical incidents (alerts, logs, root causes, remediation steps, and resolution outcomes) in a persistent memory bank.
- **⚡ Blazing-Fast LLM Inference (Groq):** Powered by `openai/gpt-oss-120b` via Groq for near-instant triage recommendations during critical outages.
- **⚖️ Side-by-Side Comparison:** Directly compare the baseline generic LLM suggestions ("Memory OFF") against memory-augmented recommendations ("Memory ON") to see the exact value of historical context.
- **⚠️ Negative Knowledge & Failure Warnings:** If a fix previously failed or only partially worked, the agent explicitly flags it so engineers don't waste MTTR repeating past mistakes.
- **🔴 Triage Priority & Benchmark MTTR:** Real-time priority classification (`🔴 P1 - CRITICAL`, `🟡 P2 - HIGH`, `🔵 P3 - MEDIUM`) and historical resolution duration estimates grounded in past incident benchmarks.
- **🔄 Interactive Continuous Learning:** On-call engineers can teach the agent directly from the Streamlit UI (marking fixes as `✅ Worked`, `❌ Failed`, or `➖ Partial`), automatically committing feedback to Hindsight memory.
- **📋 War Room & Slack Export:** One-click formatted snippet ready to paste into emergency Slack/Teams war room channels.
- **📥 Auto-Generated Postmortem Brief:** One-click download of a structured Markdown postmortem report (`.md`) closing the loop on incident documentation.
- **✍️ Custom Alert Testing Sandbox:** Lets evaluators and engineers test any custom service and alert message beyond the presets.
- **📚 In-App Knowledge Base Explorer:** Interactive directory of 15 seeded postmortems with outcome filters and keyword search.

---

## 🏛️ System Architecture

```mermaid
flowchart TD
    subgraph UI ["Streamlit Frontend (app.py)"]
        Alert["Incoming / Custom Alert"]
        QuickDemo["1-Click Showcase Demo"]
        CompareToggle{"Mode: Memory ON vs OFF"}
        Feedback["Feedback Actions (Worked / Failed / Partial)"]
        SlackExport["Copy for Slack War Room"]
        Postmortem["Download Postmortem Brief (.md)"]
    end

    subgraph Core ["Incident Copilot Agent (agent.py)"]
        Query["Alert Prompt Builder"]
        GroqLLM["Groq LLM (gpt-oss-120b)"]
        PlanOutput["Structured JSON Plan:
        - Likely Root Cause
        - Recommended Steps
        - Warnings (Failed Fixes)
        - Recalled Memories Used
        - Confidence Level"]
    end

    subgraph MemoryLayer ["Memory Bank (memory.py via Hindsight)"]
        Hindsight[("Hindsight Memory Bank")]
        SeedData["Seed Corpus (data/incidents.json)"]
    end

    QuickDemo --> Query
    Alert --> CompareToggle
    CompareToggle -->|Memory ON| Query
    CompareToggle -->|Memory OFF| GroqLLM

    Query <-->|recall_similar| Hindsight
    SeedData -->|seed.py retain_incident| Hindsight

    Query --> GroqLLM
    GroqLLM --> PlanOutput
    PlanOutput --> UI
    Feedback -->|retain_outcome| Hindsight
    PlanOutput --> SlackExport
    PlanOutput --> Postmortem
```

---

## 🧠 How Hindsight Memory Is Used

Hindsight is the **semantic long-term memory backbone** of this agent. It is integrated at three distinct points in the system:

### 1. `retain_incident(incident)` — Storing Historical Knowledge

Called by `seed.py` once during setup (and can be called any time new incidents occur). Each incident is serialized into a structured natural-language string containing the service name, alert text, error logs, confirmed root cause, fix steps, outcome (worked/failed/partial), and time to resolve. This is stored in a Hindsight **memory bank** (`oncall-demo-final` / `oncall-payments-team`) with the context tag `"incident"` and the incident ID as metadata.

```python
# memory.py
result = _call(
    "retain_batch",
    bank_id=BANK_ID,
    items=[{"content": content, "context": "incident", "metadata": {"incident_id": inc["id"]}}],
    retain_async=False,
)
```

### 2. `recall_similar(alert_text)` — Retrieving Relevant Memories at Triage Time

When a new alert fires, the agent calls `recall_similar` with the alert text as the query. Hindsight performs **multi-strategy retrieval (semantic, keyword, graph and temporal)** across the memory bank and returns the most relevant past incident chunks — not just keyword matches, but conceptually similar situations. These retrieved memories are injected into the LLM prompt as grounding context.

```python
# memory.py
results = _call(
    "recall",
    bank_id=BANK_ID,
    query=alert_text,
    max_tokens=1024,
    budget="mid",
)
```

This is the core of the **Memory ON vs. Memory OFF** toggle: without it, the LLM reasons from parametric knowledge only (generic advice); with it, the LLM reasons from your team's actual incident history.

### 3. `retain_outcome(incident_id, outcome)` — Continuous Learning from Feedback

After an engineer tries the recommended fix, they click one of the feedback buttons in the UI (`✅ Worked`, `❌ Failed`, `➖ Partial`). This stores a **feedback memory** in Hindsight with the outcome, confirmed root cause, and resolution time. Future `recall_similar` calls will surface this feedback, so the agent learns to warn against previously failed fixes.

```python
# memory.py
_call(
    "retain_batch",
    bank_id=BANK_ID,
    items=[{"content": content, "context": "outcome-feedback", "metadata": {...}}],
    retain_async=False,
)
```

---

### Why This Matters: The Showcase Demo Story

| Metric / Field | ❌ Without Memory (Baseline) | ✅ With Hindsight Memory (Copilot) |
|:---|:---|:---|
| **Priority & MTTR** | `🔴 P1 - CRITICAL` • MTTR Unknown | `🔴 P1 - CRITICAL` • Benchmark: ~35m (INC-007) |
| **Root Cause** | Redis pool exhaustion (generic textbook guess) | Wildcard `SCAN` on 600k keys without TTL |
| **Fix Steps** | Increase `REDIS_POOL_SIZE` and restart pods | Add 1h TTL, replace `SCAN` with keyed lookup, flush stale keys |
| **Warnings** | *(none)* | ⚠️ **INC-006: increasing REDIS_POOL_SIZE from 10 to 50 FAILED** |
| **Confidence** | Low | **High** (backed by INC-006 & INC-007) |
| **Actionable Outcome** | Repeats failed fix, doubles MTTR | Applies verified fix, avoids repeat mistake |

---

## 📂 Project Structure

```text
incident-memory-agent/
├── data/
│   ├── demo_alerts.json     # 7 production alerts across 7 microservices
│   └── incidents.json       # 15 historical incident postmortems (seed corpus)
├── agent.py                 # Core reasoning agent (Groq + Hindsight recall + failure guard)
├── app.py                   # Streamlit web app with comparison, feedback & export UI
├── memory.py                # Hindsight SDK wrappers: retain_incident, recall_similar, retain_outcome
├── seed.py                  # CLI utility to seed 15 incidents into Hindsight memory bank
├── test_memory.py           # Quick verification: retain 2 incidents, recall, confirm
├── DEMO_SCRIPT.md           # 2-minute timed video recording & presentation walkthrough
├── requirements.txt         # Python dependencies
├── .env.example             # Template for environment variables
└── README.md                # Project documentation
```

---

## 🚀 Quickstart Guide

### 1. Prerequisites

- Python 3.10+
- A [Groq Cloud API Key](https://console.groq.com/) (free tier works)
- A [Hindsight Cloud](https://ui.hindsight.vectorize.io) account and API key

### 2. Clone & Set Up

```bash
git clone https://github.com/Pavankumar202/incident-memory-agent.git
cd incident-memory-agent

# macOS/Linux
python3 -m venv .venv
source .venv/bin/activate

# Windows
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables

```bash
cp .env.example .env
```

Edit `.env`:

```dotenv
HINDSIGHT_API_KEY="your-hindsight-api-key"
HINDSIGHT_BASE_URL="https://api.hindsight.vectorize.io"
GROQ_API_KEY="your-groq-api-key"
BANK_ID="oncall-demo-final"   # optional memory bank partition ID
```

### 5. Verify Memory Connection

```bash
python test_memory.py
```

Expected: a retained incident echoed back in the recall output.

### 6. Seed Historical Incidents

```bash
python seed.py
```

Expected output: `✅ Seeded 15 incidents.`

### 7. Run CLI Comparison

```bash
python agent.py
```

Prints `MEMORY OFF` then `MEMORY ON` for the `search-service` alert, demonstrating the contrast in the terminal.

### 8. Launch the Streamlit Web Dashboard

```bash
streamlit run app.py
```

Navigate to `http://localhost:8501`. From the dashboard:
1. **1-Click Showcase Demo:** Click **"🚀 1-Click Showcase Demo (Search Service)"** at the top right to instantly load the before/after comparison.
2. **Preset & Custom Alerts:** Select any preset or choose **"✍️ Custom alert (type your own)..."** to test your own outage scenario.
3. **Inspect Priority & MTTR:** Review the calculated triage priority (`P1/P2/P3`) and historical benchmark resolution times.
4. **Copy for Slack:** Expand the **"📋 Copy for Slack / Incident War Room"** card for a ready-to-paste incident update.
5. **Download Postmortem:** Click **"📥 Download Postmortem Brief (.md)"** to save a complete postmortem markdown document.
6. **Continuous Learning:** Click **✅ Worked / ❌ Failed / ➖ Partial** to teach the agent in real time.
7. **Browse Knowledge Base:** Expand **"📚 Browse 15 Seeded Incident Postmortems"** at the bottom to filter and search past postmortems.

---

## ⚙️ Configuration Reference

| Variable | Required | Default | Description |
| :--- | :---: | :---: | :--- |
| `HINDSIGHT_API_KEY` | **Yes** | — | Authentication token for Hindsight |
| `HINDSIGHT_BASE_URL` | **Yes** | — | Hindsight API base URL |
| `GROQ_API_KEY` | **Yes** | — | Groq Cloud API key |
| `BANK_ID` | No | `oncall-payments-team` | Hindsight memory bank partition ID |

---

## 🧩 Output Schema

```json
{
  "likely_root_cause": "Wildcard Redis SCAN without TTL causing CPU saturation",
  "recommended_steps": [
    "Check slowlog to verify long-running SCAN queries",
    "Add 1h TTL to query cache keys",
    "Replace wildcard SCAN with keyed lookups",
    "Flush stale keys with redis-cli --scan"
  ],
  "memories_used": [
    "INC-006: search-service pool increase failed",
    "INC-007: search-service unindexed query scan fixed with TTL"
  ],
  "warnings": [
    "INC-006: increasing REDIS_POOL_SIZE from 10 to 50 FAILED"
  ],
  "confidence": "high",
  "no_history": false
}
```

---

## 🤝 Contributing

1. Fork the repository.
2. Create your feature branch: `git checkout -b feature/new-capability`
3. Commit your changes: `git commit -m 'Add new capability'`
4. Push and open a Pull Request.

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
