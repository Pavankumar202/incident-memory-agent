# 🚨 Incident Memory Agent

> **An AI-powered On-Call Incident Copilot that remembers what worked, warns against what failed, and continuously learns from engineer feedback.**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Streamlit](https://img.shields.io/badge/UI-Streamlit-FF4B4B.svg)](https://streamlit.io/)
[![Groq](https://img.shields.io/badge/LLM-Groq%20Cloud-f55036.svg)](https://groq.com/)
[![Hindsight](https://img.shields.io/badge/Memory-Hindsight-8A2BE2.svg)](https://github.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## 📖 Overview

During high-severity production incidents, on-call engineers are under immense pressure to triage and resolve outages quickly. Traditional approaches suffer from two major flaws:

1. **Tribal Knowledge Loss:** Past incident postmortems are buried across Jira tickets, Google Docs, or Slack threads. Engineers often repeat mistakes by applying fixes that previously failed.
2. **Generic LLM Hallucinations:** Standard LLMs lack organizational context and provide generic, textbook troubleshooting advice that does not account for your specific service architecture or past incident history.

**Incident Memory Agent** solves this by pairing **Groq's** high-speed inference with **Hindsight's** semantic memory layer. The agent recalls past incident resolutions, warns engineers if a proposed fix has failed before, provides actionable step-by-step remediation plans, and learns in real time from post-fix feedback.

---

## ✨ Key Features

- **🧠 Semantic Incident Memory (Hindsight):** Retains historical incidents (alerts, logs, root causes, remediation steps, and resolution outcomes) in a persistent memory bank.
- **⚡ Blazing-Fast LLM Inference (Groq):** Powered by `openai/gpt-oss-120b` via Groq for near-instant triage recommendations during critical outages.
- **⚖️ Side-by-Side Comparison ("Memory ON" vs. "Memory OFF"):** Directly compare the baseline generic LLM suggestions against memory-augmented recommendations to see the exact value of historical context.
- **⚠️ Negative Knowledge & Failure Warnings:** If a fix previously failed or only partially worked, the agent explicitly flags it with warnings so engineers do not waste precious MTTR repeating past mistakes.
- **🔄 Interactive Continuous Learning:** On-call engineers can teach the agent directly from the Streamlit UI (marking fixes as `✅ Worked`, `❌ Failed`, or `➖ Partial`), automatically committing feedback to the memory bank.
- **🛡️ Concurrency-Safe Architecture:** Uses thread-isolated client sessions (`ThreadPoolExecutor`) to eliminate event-loop conflicts inside Streamlit.

---

## 🏛️ System Architecture

```mermaid
flowchart TD
    subgraph UI ["Streamlit Frontend (app.py)"]
        Alert["Incoming / Simulated Alert"]
        CompareToggle{"Mode: Memory ON vs OFF"}
        Feedback["Feedback Actions (Worked / Failed / Partial)"]
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

    subgraph MemoryLayer ["Memory Bank (memory.py)"]
        Hindsight[("Hindsight Memory Bank")]
        SeedData["Seed Corpus (data/incidents.json)"]
    end

    Alert --> CompareToggle
    CompareToggle -->|Memory ON| Query
    CompareToggle -->|Memory OFF| GroqLLM
    
    Query <-->|Recall Similar Incidents| Hindsight
    SeedData -->|seed.py| Hindsight
    
    Query --> GroqLLM
    GroqLLM --> PlanOutput
    PlanOutput --> UI
    Feedback -->|Retain Live Outcome| Hindsight
```

---

## 💡 The Showcase Scenario: Why Memory Matters

Consider an alert for the `search-service`:

> **Alert:** `Search latency above 8s, Redis connections maxed out`

| Metric / Aspect | ❌ Without Memory (Memory OFF) | ✅ With Hindsight Memory (Memory ON) |
| :--- | :--- | :--- |
| **Diagnosed Root Cause** | Suspects Redis connection pool exhaustion (generic assumption). | Identifies **unindexed wildcard `SCAN`** and missing cache TTL. |
| **Recommended Action** | Increase `REDIS_POOL_SIZE` and restart pods. | Add 1h TTL to cache keys, replace `SCAN` with keyed lookup, flush stale keys. |
| **Warnings & History** | None. | ⚠️ **Warns that increasing pool size was attempted in INC-006 and failed!** |
| **Confidence** | Low / Medium (Generic guess). | **High** (Backed by INC-006 and INC-007). |

---

## 📂 Project Structure

```text
incident-memory-agent/
├── data/
│   ├── demo_alerts.json     # Sample alerts used for UI simulation
│   └── incidents.json       # Historical incident postmortem corpus for seeding
├── agent.py                 # Core reasoning agent with Groq API integration
├── app.py                   # Streamlit web application & feedback interface
├── memory.py                # Hindsight client wrappers (retain, recall, outcome feedback)
├── seed.py                  # CLI utility to seed historical incidents into Hindsight
├── test_memory.py           # Quick verification script for Hindsight retain & recall
├── requirements.txt         # Project dependencies
├── .env.example             # Template for required environment variables
└── README.md                # Project documentation
```

---

## 🚀 Quickstart Guide

### 1. Prerequisites

- Python 3.10 or higher
- A [Groq Cloud API Key](https://console.groq.com/)
- A [Hindsight](https://github.com/) instance / API key

### 2. Clone the Repository & Set Up Environment

```bash
# Clone the repository
git clone https://github.com/Pavankumar202/incident-memory-agent.git
cd incident-memory-agent

# Create and activate a virtual environment
# On Windows (PowerShell):
python -m venv .venv
.venv\Scripts\Activate.ps1

# On macOS/Linux:
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Create a `.env` file in the root directory by copying `.env.example`:

```bash
cp .env.example .env
```

Populate the `.env` file with your credentials:

```dotenv
HINDSIGHT_API_KEY="your-hindsight-api-key"
HINDSIGHT_BASE_URL="https://your-hindsight-instance.com"
GROQ_API_KEY="your-groq-api-key"
BANK_ID="oncall-payments-team" # Optional: defaults to 'oncall-payments-team'
```

---

## 🧪 Usage & Workflows

### Step 1: Verify Memory Connection

Run the standalone memory verification test to ensure your Hindsight connection is working:

```bash
python test_memory.py
```

### Step 2: Seed Historical Incidents

Seed the initial incident corpus (`data/incidents.json`) into your Hindsight memory bank:

```bash
python seed.py
```
*Expected output:* `Seeded 11 incidents.`

### Step 3: Run the CLI Baseline Comparison

Test the agent in terminal mode to observe the contrast between `MEMORY OFF` and `MEMORY ON`:

```bash
python agent.py
```

### Step 4: Launch the Streamlit Web UI

Start the interactive web application:

```bash
streamlit run app.py
```

Once running, navigate to `http://localhost:8501` in your browser. From the dashboard:
1. **Select an alert** from the dropdown (e.g., `search-service: Search latency above 8s...`).
2. Choose **"Compare both"** mode and click **"Analyze alert"**.
3. Inspect the side-by-side comparison.
4. Use the feedback buttons (`✅ Worked`, `❌ Failed`, `➖ Partial`) under the memory column to teach the agent in real time.

---

## ⚙️ Configuration Reference

| Variable | Required | Default | Description |
| :--- | :---: | :---: | :--- |
| `HINDSIGHT_API_KEY` | **Yes** | — | Authentication token for the Hindsight memory service. |
| `HINDSIGHT_BASE_URL` | **Yes** | — | Base URL of the Hindsight API instance. |
| `GROQ_API_KEY` | **Yes** | — | API key for Groq Cloud. |
| `BANK_ID` | No | `oncall-payments-team` | Identifier for the Hindsight memory bank partition. |

---

## 🧩 Output Schema

The copilot responds strictly with structured JSON conforming to the following schema:

```json
{
  "likely_root_cause": "Wildcard Redis SCAN without TTL causing CPU saturation",
  "recommended_steps": [
    "Check slowlog to verify long-running SCAN queries",
    "Add 1h TTL to cache keys",
    "Replace wildcard SCAN with keyed lookups"
  ],
  "memories_used": [
    "INC-006: search-service pool increase failed",
    "INC-007: search-service unindexed query scan"
  ],
  "warnings": [
    "Do NOT simply increase REDIS_POOL_SIZE; this was attempted in INC-006 and failed."
  ],
  "confidence": "high",
  "no_history": false
}
```

---

## 🤝 Contributing

Contributions, bug reports, and suggestions are welcome!
1. Fork the repository.
2. Create your feature branch (`git checkout -b feature/new-capability`).
3. Commit your changes (`git commit -m 'Add new capability'`).
4. Push to the branch (`git push origin feature/new-capability`).
5. Open a Pull Request.

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
