# 🎬 Incident Memory Agent — 2-Minute Demo Script

Use this walkthrough to record your submission video or present live to judges.

---

### ⏱️ Timeline Summary (2:15 total)
* **0:00 – 0:30:** The Problem & Architecture (Why standard LLMs fail on-call)
* **0:30 – 1:15:** The Showcase (Memory OFF vs. Memory ON side-by-side)
* **1:15 – 1:45:** Negative Knowledge & Warnings (Preventing repeated mistakes)
* **1:45 – 2:15:** Interactive Learning & Custom Alerts (Real-time feedback loop)

---

## 🎙️ Step-by-Step Walkthrough

### Part 1: The Problem (0:00 – 0:30)
> *"Hi everyone, this is **Incident Memory Agent** — an on-call copilot that remembers what worked, warns against what failed, and continuously learns from engineer feedback.*
>
> *During critical outages, tribal knowledge is buried in past postmortems. When engineers ask a standard LLM for help, it gives textbook suggestions that often repeat fixes that already failed in production.*
>
> *We solved this by pairing **Groq's** high-speed inference with **Hindsight's** semantic long-term memory layer."*

*(Action: Show the Streamlit UI with the Sidebar highlighting the connected Hindsight memory bank and 15 seeded incident postmortems).*

---

### Part 2: The Showcase — Memory OFF vs. Memory ON (0:30 – 1:15)
1. In the **"Simulate an incoming alert"** dropdown, select:
   `search-service: Search latency above 8s, Redis connections maxed out`
2. Keep Mode on **"Compare both"** and click **"Analyze alert"**.
3. Point to the left column (**Without memory**):
   > *"Without memory, the LLM gives generic advice: it guesses that connection pool size is too small and recommends raising REDIS_POOL_SIZE and restarting pods. It has low confidence and no organizational context."*
4. Point to the right column (**With Hindsight memory**):
   > *"With Hindsight memory ON, the agent recalls incidents INC-006 and INC-007. It discovers that pool size was a red herring — the real root cause was wildcard SCAN queries on 600,000 keys without TTL. It recommends adding a 1-hour TTL, replacing SCAN with keyed lookups, and flushing stale keys."*

---

### Part 3: Negative Knowledge & Failure Warnings (1:15 – 1:45)
1. Highlight the red warning box under **With Hindsight memory**:
   `⚠️ INC-006: increasing REDIS_POOL_SIZE from 10 to 50 FAILED`
2. Explain:
   > *"Notice the negative knowledge: the agent explicitly warns the on-call engineer NOT to increase REDIS_POOL_SIZE because it was tried in INC-006 and failed. This prevents MTTR from doubling due to repeating past mistakes."*

---

### Part 4: Real-Time Learning & Custom Alerts (1:45 – 2:15)
1. Scroll down to **"Did this work? Teach the agent"**:
   * Click **✅ Worked** (or ❌ Failed).
   * Point out the confirmation message:
     > *"The outcome is retained immediately into Hindsight's memory bank without retraining, making the system smarter for the next engineer."*
2. Select **"✍️ Custom alert (type your own)..."** in the dropdown:
   * Show that judges can type any service name and symptom to test their own incident scenarios.
3. Conclude:
   > *"With Hindsight as the semantic memory backbone and Groq delivering instant triage, Incident Memory Agent turns every incident into persistent operational knowledge. Thank you!"*
