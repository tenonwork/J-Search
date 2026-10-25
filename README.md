# Smart Job Triage Pipeline

An automated, self-directed data pipeline that hooks into live remote developer feeds, evaluates raw job postings using a contextual regular-expression (Regex) scoring engine, and compiles a locally rendered, highly tailored Job Match Dashboard.

Instead of deploying blind "spray-and-pray" auto-apply bots that trigger platform bans and flood applicant tracking systems with noise, this system flips the script. It acts as an automated data gatekeeper—filtering out corporate bureaucracy and noisy false positives while bubbling up high-affinity, greenfield developer opportunities.

## 🎯 Project Overview & Philosophy

As an independent developer who builds complete systems (and actively utilizes governed AI-assisted workflows), I designed this tool to solve the common inefficiencies of the modern tech job hunt. 

The pipeline is split into three decoupled components:
1. **The Ingestion Layer:** Connects to stable, live REST API gateways (like Remotive) to pull clean, unstructured JSON text without breaking on fragile HTML DOM changes.
2. **The Calibration Engine:** Evaluates job titles and deep descriptions using whole-word boundary regular expressions (`\b`). It scores matches based on technical affinity while enforcing a hard-disqualification rule for explicit dealbreakers (e.g., corporate legacy systems or senior management overhead).
3. **The Presentation Layer:** Compiles data into a lightweight, local HTML dashboard that automatically triggers your default browser to launch an actionable triage review interface.

---

## 🛠️ Architecture & Core Stack

[Target JSON Endpoints] ───( Requests API )───> [Regex Calibration Engine]
│
[Local Default Browser] <───( Browser UI Launch ) <── [Static HTML Generator]

* **Language:** Python 3
* **Libraries Used:** `requests` (HTTP client), `re` (Regular Expressions engine), `json`, `webbrowser`, `os`
* **Data Origin:** Remotive Global Remote API gateway

---

## ⚙️ How the Calibration Engine Works

The core intelligence resides in `job_dashboard.py`. Jobs are processed through an explicit scoring weight matrix tailored to a production full-stack profile (React Native/Expo, Electron, TypeScript, Supabase, PostgreSQL, and Agentic AI Tooling):

```python
# Elite Core Stack (+8 points per isolated word match)
core_skills = ["postgresql", "supabase", "react native", "electron", "typescript", "react", "postgres", "expo"]

# Emerging AI Infrastructure (+5 points per match)
ai_and_infra = ["mcp", "model context protocol", "llm", "ai agent", "claude", "python"]

# Hard Disqualifiers (Instant Pipeline Drop)
dealbreakers = ["senior", "lead", "staff", "architect", "manager", "10+ years", "8+ years"]
```

### Key Engineering Features:
* **Bounded Word Matching:** Standard string matching fails on words like `pos` (triggering false positives on *position*, *composition*, or *repository*). This pipeline utilizes raw strings with word boundary anchors (`r'\bkeyword\b'`) to ensure absolute precision.
* **The Hard Drop Rule:** Even if a job listing mentions your entire technical stack perfectly, a single matching red flag keyword (like `Senior`) triggers a hard execution break (`if len(bads) > 0: continue`), instantly omitting it from the dashboard layout.
* **Minimum Viable Threshold:** Any job listing scoring below a net rating of `10` points is automatically filtered out to eliminate non-technical noise (e.g., content writing, translation, or data entry roles).

---

## 🚀 Getting Started & Execution

### 1. Prerequisites
Ensure you have Python 3 installed alongside the standard HTTP requests library:
```bash
pip install requests
```

### 2. File Structure
Keep both essential execution files within the exact same root directory:
```text
├── job_dashboard.py    # Scoring matrix, regex engine, and HTML compiler
└── fetch_live_jobs.py  # Ingestion script targeting the live API gateways
```

### 3. Run the Pipeline
Execute the live ingestion script from your terminal:
```bash
python fetch_live_jobs.py
```
The terminal will display real-time connection status and total fetched listings, filter the payload via the calibration rules, compile `dashboard.html` locally, and immediately launch it in your default web browser.

---

## 📈 Future Extensions & Roadmap

- [ ] **Local Logistics Directory Scraper:** Expand the ingestion layer using `Playwright` to extract business profiles from East African industrial/supply-chain directories to look for unadvertised point-of-sale or wholesale inventory digitization opportunities.
- [ ] **AI-Assisted Contextual Summary:** Integrate a local LLM under a strict review gate to summarize long text fields into punchy three-bullet-point overviews displayed directly on the UI dashboard card.
- [ ] **Export to CSV/Markdown:** Add an pipeline flag to write top-tier matched jobs into an active tracking document for simplified application analytics.