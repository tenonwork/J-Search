# J-Search — Smart Job Triage Pipeline

A local-first job hunting tool: it scrapes global remote feeds and East African job boards, scores every posting against a configurable keyword model, stores results in SQLite, and serves a dashboard where you filter and sort the results live — no re-scraping required.

You can tune the scoring profile by hand, or import a CV (PDF, DOCX or pasted text) into the dashboard and let an optional local or hosted model propose the skills, highlight keywords, hide keywords and weights for you to review.

Instead of deploying blind "spray-and-pray" auto-apply bots that trigger platform bans and flood applicant tracking systems with noise, this system acts as a data gatekeeper. It pulls a deliberately oversized bundle of listings, then lets you narrow it down at your own discretion.

## Project Overview & Philosophy

As an independent developer who builds complete systems (and actively uses governed AI-assisted workflows), I built this to fix the inefficiencies of the modern tech job hunt.

The pipeline is split into five decoupled layers:

1. **Ingestion** — Parallel fetchers for global APIs/RSS and local Kenyan job boards. Each source fails independently, so one dead endpoint never empties the dashboard.
2. **Normalisation & Deduplication** — Every source is mapped to one shape (`title`, `company`, `location`, `url`, `desc`), then deduplicated on a stable job key (host + path, query and `www.` stripped).
3. **Calibration Engine** — Whole-word (`\b`) regex scoring with weighted keyword groups and a configurable dealbreaker penalty.
4. **Decision Filter** — Jobs marked as applied for or dismissed are excluded from the triage list. Raw postings stay in SQLite, so restoring a decision does not require a re-scrape.
5. **Presentation** — A single-page dashboard served over a local HTTP server. Scoring runs server-side; filtering, strictness and sorting run in the browser, so toggling a control changes the result count instantly.

## Architecture & Core Stack

```text
[Global sources]  ─┐
                   ├─> [Normalise + Deduplicate] ─> [Scoring Engine] ─> [SQLite] ─> [Decision Filter] ─> [dashboard.html]
[Local sources]   ─┘                                                                                                    │
                                                          [Browser] <── HTTP ───────────────────────────────────────────┘
```

* **Language:** Python 3
* **Server:** `http.server` (no framework, no build step)
* **Storage:** SQLite via the stdlib `sqlite3` module (`data/jsearch.db`)
* **HTTP client:** `requests`
* **HTML parsing:** `BeautifulSoup` (`bs4`) with the stdlib `html.parser`
* **Feed parsing:** `feedparser`
* **CV file parsing:** `pypdf` for text-based PDFs; stdlib `zipfile` + `ElementTree` for DOCX
* **Frontend:** vanilla HTML/CSS/JS — no frameworks, no bundler
* **Optional CV import:** any OpenAI-compatible model endpoint, local or hosted (Ollama by default; configure a hosted provider in `.env`), called with `requests`

## Data Sources

| Scope | Source | Method | Notes |
| :-- | :-- | :-- | :-- |
| Global | Working Nomads | Public JSON API | Most reliable source in practice |
| Global | Remotive | Public JSON API | Occasionally times out |
| Global | Jobicy | Public JSON API | Occasionally times out |
| Global | Arbeitnow | Public JSON API | Often unreachable |
| Global | We Work Remotely, Jobspresso, EU Remote | RSS feeds | Fragile; treated as bonus sources |
| Local | BrighterMonday | HTML scraping | Software/Data, IT and Engineering categories |
| Local | JobsInKenya | HTML scraping | Filtered to tech-relevant titles |
| Local | DuckDuckGo HTML | Search scraping | Optional extra; frequently returns bot-challenge pages |

Local listings are filtered by a tech-title regex before scoring, so HR, supply-chain and sales roles from the boards don't leak into the dashboard.

## Scoring Engine

Weights live in `DEFAULT_SCORING_CONFIG` in `app/job_dashboard.py` and are no longer hardcoded into the matching loop. A saved profile in the `settings` table overrides the lists and weights; `DEFAULT_SCORING_CONFIG` remains the fallback. Profiles are normalised on read: values are lowercased, de-duplicated, length-capped and unknown keys are dropped.

Matching uses word boundaries for plain terms (`\bpostgres\b`), so `postgres` does not match *postgresql*, while terms that cannot be expressed with `\b` (`c++`, `c#`, `.net`, `node.js`) use literal matching. The dashboard's highlight/hide filter uses the same rules as the scorer.

| Group | Default weight | Default keywords |
| :-- | :-- | :-- |
| Core stack | +8 each | `postgresql`, `supabase`, `react native`, `electron`, `typescript`, `react`, `postgres`, `expo`, `fullstack`, `full-stack`, `backend` |
| AI & infrastructure | +5 each | `mcp`, `model context protocol`, `llm`, `ai agent`, `claude`, `sqlite`, `data science`, `python` |
| Location & level | +5 each | `nairobi`, `remote`, `hybrid`, `mid-level`, `mid level`, `contract`, `point of sale` |
| Isolated `pos` | +5 | Word-boundary match only |
| Dealbreakers | −30 each | `senior`, `lead`, `staff`, `architect`, `manager`, `10+ years`, `8+ years`, `phd`, `clearance required` |

### Strictness presets

| Preset | Remote dealbreakers | Remote minimum | Local dealbreakers | Local minimum |
| :-- | :-- | :-- | :-- | :-- |
| Strict | Hard drop | 10 | Hard drop | 3 |
| Balanced | Hard drop | 5 | Penalty only | 0 |
| Lenient | Penalty only | 0 | Penalty only | −10 |

Presets are applied in the browser by the strictness toggle; the server scores every job once so the toggle is instant. Presets own the thresholds and whether dealbreakers are enforced, not the keyword lists or weights — those come from the saved profile.

### Engineering notes

* **Bounded word matching** — `r'\bkeyword\b'` prevents false positives such as `pos` matching *position*, *composition* or *repository*.
* **Hard drop vs penalty** — Remote listings with any dealbreaker are removed under Strict/Balanced. Local listings are only penalised, because board titles are terse and often miss obvious keywords.
* **Blocklist** — Paywalled/gated hosts (`linkedin.com`, `glassdoor.com`, `remotive.com` listing pages, etc.) are dropped before rendering, regardless of score.

## Dashboard

* **Two tabs:** Global and Local — each with its own result count.
* **Keyword manager:** Highlight keywords (blue outline on matching cards) and Hide keywords (remove matching cards), with add, pause/enable, and delete. The Manage modal has a `Save changes` button; unchecking a keyword pauses it without deleting it. Permanent deletion happens from the `x` on a tag and requires confirmation. Persisted in SQLite.
* **Broad-fetch filtering:** Scrapers always fetch a wide set of postings. Keywords only change what the dashboard shows, not what is fetched or how jobs are scored.
* **Strictness toggle:** Strict / Balanced / Lenient.
* **Sort:** most recommended first, or least recommended first.
* **Run controls:** Run All, Run Global Only, and Run Local Only.
* **Full-page loading screen:** clicking a run button navigates to a dedicated loading page that polls `/status` and redirects to the dashboard only once the scrape has actually finished.
* **Per-job decisions:** each card has `Applied` and `Not for me` buttons. Applied removes the posting from triage and logs it on the applied page; Not for me opens a reason picker (preset + optional note) and logs it on the hidden page. Both actions show an Undo toast.

## CV Import

The **Import from CV** button opens a review-gated profile builder:

1. Upload a PDF or DOCX (or paste text) and, optionally, a free-text list of things to avoid.
2. The file is parsed locally and in memory — the upload is never written to disk or logged. The extracted text lands in the textarea so it can be reviewed or edited before analysis.
3. Contact details (email, phone, URLs, handles) are masked before the text is sent to the configured model. If the model is remote, the dashboard says so before analysis.
4. The model returns only allow-listed skills with evidence snippets. Unknown, unevidenced or generic terms are dropped.
5. The dashboard shows the proposed scoring profile, highlight keywords, hide keywords and an impact preview (`N visible now → M after applying`).
6. No scoring or keyword changes are written until **Apply selected**. Applying saves the scoring profile and adds the selected keywords; existing keywords are not deleted.

The CV is treated as untrusted data: it is delimited in the prompt, the model has no tools, and the output is validated against `app/skills_taxonomy.json`. The structured candidate profile is stored in `settings`; the raw CV and uploaded file are not persisted. Text-based PDFs are limited to the first 40 pages and 20,000 characters; scanned PDFs and legacy `.doc` files are rejected with a clear message.

### Model setup

The client speaks the OpenAI-compatible `/v1/chat/completions` protocol. Ollama is the default, but **you do not need a local model**; any hosted provider that implements the same API works.

#### Option A: hosted (no local model)

[Cloudflare Workers AI](https://developers.cloudflare.com/workers-ai/) is the recommended hosted option for CV import:

- Free allocation of 10,000 Neurons per day, which is enough for personal use.
- Zero data retention for standard inference requests.
- Cloudflare does not train on customer content.

1. Copy `.env.example` to `.env` in the project root.
2. Fill in your Cloudflare **Account ID** and an API token with **Account → Workers AI → Read** permission:
   ```dotenv
   JSEARCH_LLM_BASE_URL=https://api.cloudflare.com/client/v4/accounts/<ACCOUNT_ID>/ai/v1
   JSEARCH_LLM_MODEL=@cf/openai/gpt-oss-20b
   JSEARCH_LLM_API_KEY=<CLOUDFLARE_API_TOKEN>
   JSEARCH_LLM_TIMEOUT=120
   JSEARCH_LLM_MAX_TOKENS=8192
   ```
3. Restart `python run.py`.

If `JSEARCH_LLM_API_KEY` is empty and the endpoint is remote, `python run.py` asks for the key at startup with hidden input. The key is kept in memory for that run only and is never written to `.env`, the database, or logs. To skip the prompt, set the key in `.env` or the environment. Local endpoints such as Ollama never prompt.

`gpt-oss` is a reasoning model. J-Search deliberately skips forced JSON mode for it because some OpenAI-compatible servers return HTTP 200 with empty content when JSON mode is enabled; the prompt still asks for JSON and the parser extracts it. It sends the output budget as `max_completion_tokens` (the OpenAI reasoning-model field) and defaults `JSEARCH_LLM_REASONING_EFFORT` to `low` to leave more of the budget for the JSON answer. If an analysis is cut off, raise `JSEARCH_LLM_MAX_TOKENS`. For other providers with a broken JSON mode, set `JSEARCH_LLM_JSON_MODE=0`; if a provider rejects `reasoning_effort` or the budget field, J-Search retries with a compatible payload.

`.env` is gitignored, and real environment variables override its values. It is plaintext, so use a scoped token and rotate it if it is ever exposed. The dashboard shows a **Remote** badge and can test the connection before you analyse a CV; the test sends only a short "Reply with OK" prompt, never CV content.

**Groq** is a fast, low-cost alternative:

```dotenv
JSEARCH_LLM_BASE_URL=https://api.groq.com/openai/v1
JSEARCH_LLM_MODEL=openai/gpt-oss-20b
JSEARCH_LLM_API_KEY=<GROQ_API_KEY>
```

**Privacy:** the CV text leaves your machine when you use a hosted provider. J-Search masks email, phone, URLs and handles, but **not** your name, employers, education or dates. Cloudflare's zero-retention/no-training policy is why it is the recommendation. Review the extracted text before clicking **Analyse CV**.

#### Option B: local Ollama

```bash
ollama pull qwen2.5:7b-instruct
ollama serve
```

No `.env` is needed for the local default.

| Variable | Default | Purpose |
| :-- | :-- | :-- |
| `JSEARCH_LLM_BASE_URL` | `http://127.0.0.1:11434/v1` | Any OpenAI-compatible base URL |
| `JSEARCH_LLM_MODEL` | `qwen2.5:7b-instruct` | Model name understood by that endpoint |
| `JSEARCH_LLM_API_KEY` | empty | Bearer token for remote providers; prompted at startup if missing |
| `JSEARCH_LLM_TIMEOUT` | `90` | Request timeout in seconds |
| `JSEARCH_LLM_MAX_TOKENS` | `8192` | Output budget per CV analysis |
| `JSEARCH_LLM_REASONING_EFFORT` | `low` for gpt-oss | `low`, `medium` or `high`; unset for other models |
| `JSEARCH_LLM_MAX_TOKENS_FIELD` | auto | `max_tokens` or `max_completion_tokens`; gpt-oss uses the latter automatically |
| `JSEARCH_LLM_JSON_MODE` | auto | `0` forces prompt-only JSON; gpt-oss models skip JSON mode automatically |

If the endpoint is unreachable, the import fails with a provider-aware message. It never silently falls back to a different provider.

## Application Tracker

* **`/applied`** — every job marked as applied for, newest first, with the score it had when you decided. Restore returns it to the dashboard.
* **`/hidden`** — every dismissed job with its reason and note. Restore returns it to the dashboard.
* Both pages are rendered from the `decisions` table, not from the in-memory scrape, so they survive restarts and source removals.
* Decisions are applied when the dashboard and `/api/jobs` are built, not when jobs are saved. Raw postings remain archived, so Undo is instant.

## HTTP Routes

| Route | Method | Purpose |
| :-- | :-- | :-- |
| `/` | GET | Rebuild and serve `output/dashboard.html` (falls back to SQLite if nothing is in memory) |
| `/run?mode=all\|global\|local` | GET | Start a scrape and serve the loading page |
| `/status` | GET | `{"running": true\|false}` for the loading page |
| `/refresh` | POST | Re-run all scrapers |
| `/applied` | GET | Applied-jobs tracker page |
| `/hidden` | GET | Dismissed-jobs tracker page |
| `/api/jobs` | GET | Scored jobs as JSON, excluding applied/hidden postings |
| `/api/keywords` | GET | Current highlight/hide keywords with enabled state |
| `/api/keywords/add` | POST | `{"type": "focus"\|"exclude", "value": "..."}` |
| `/api/keywords/state` | POST | `{"type": "...", "states": {"keyword": true\|false}}` — pause/enable without deleting |
| `/api/keywords/delete` | POST | `{"type": "...", "values": ["..."]}` |
| `/api/profile` | GET | Saved scoring profile, candidate profile, dismissal counts and model configuration |
| `/api/llm/test` | POST | Send a tiny, CV-free prompt to verify the configured endpoint, key and model |
| `/api/profile/extract` | POST | Raw PDF/DOCX/TXT body (max 10 MB) — extracted text for review; nothing is stored |
| `/api/profile/analyze` | POST | `{"cv_text": "...", "preferences": "..."}` — validated proposal plus impact preview; saves only the structured candidate profile |
| `/api/profile/preview` | POST | `{"profile": {...}, "focus": [...], "exclude": [...]}` — impact preview without saving |
| `/api/profile/apply` | POST | Same payload as preview; persists the profile and adds keywords. Optional `"mode": "replace"` replaces both keyword lists |
| `/api/profile/reset` | POST | Delete the saved scoring profile and restore defaults |
| `/api/decisions` | GET | Decisions as JSON; optional `?status=applied\|dismissed` |
| `/api/decisions` | POST | `{"key": "...", "status": "applied"\|"dismissed", "reason": "...", "note": "...", "job": {...}}` |
| `/api/decisions/delete` | POST | `{"key": "..."}` — restore a job to the dashboard |

## Database

`data/jsearch.db`, created automatically on first run.

| Table | Columns |
| :-- | :-- |
| `keywords` | `id`, `type` (`focus`/`exclude`), `value`, `enabled` (1 = active, 0 = paused) — unique per type |
| `settings` | `key` (primary key), `value` (JSON), `updated_at` — scoring profile and candidate profile |
| `jobs` | `id`, `title`, `company`, `location`, `url` (unique), `description`, `source`, `score`, `matches`, `redflags`, `fetched_at` |
| `decisions` | `job_key` (primary key), `status` (`applied`/`dismissed`), `reason`, `note`, `title`, `company`, `location`, `url`, `source`, `score`, `applied_at`, `created_at`, `updated_at` |

Default keywords are seeded the first time the database is created. Older databases that used a single-column unique constraint on `keywords.value` are migrated automatically to the current `(type, value)` constraint; saved keywords and paused states are preserved.

Decision snapshots (title, company, score, etc.) are stored alongside the key, so the tracker pages do not depend on the `jobs` row still existing.

## Local Data and Privacy

`data/jsearch.db` and `output/dashboard.html` are runtime artifacts, not source files. Both are ignored by git and must never be committed or force-added.

* `data/jsearch.db` stores fetched jobs, decisions, keywords, and the scoring/candidate profile. It may contain personal job-search data. Back it up separately; deleting it loses your decisions and saved profile.
* `output/dashboard.html` is regenerated from the database on startup and whenever the dashboard is rebuilt. It is safe to delete.

The `data/` and `output/` directories are created automatically on first run, so a fresh clone works without them. Keep any database backups outside the repository.

## Getting Started

### 1. Prerequisites

```bash
pip install -r requirements.txt
```

### 2. File Structure

```text
├── run.py                           # HTTP server, pipeline orchestration, API routes
├── requirements.txt                 # Runtime dependencies
├── .env.example                     # Hosted/local model configuration template
├── app/
│   ├── paths.py                     # Project paths (database, generated output)
│   ├── env.py                       # Dependency-free .env loader
│   ├── db.py                        # SQLite layer (keywords, jobs, decisions, settings)
│   ├── job_dashboard.py             # Scoring engine, presets, dashboard template
│   ├── cv_profile.py                # CV scrubbing, validation, profile proposal
│   ├── cv_import.py                 # Local PDF/DOCX/TXT text extraction for uploads
│   ├── llm_client.py                # OpenAI-compatible chat client
│   ├── skills_taxonomy.json         # Allow-listed skills, aliases, generic blocklist
│   └── applied_page.py              # Applied and hidden tracker page templates
├── fetchers/
│   ├── fetch_live_jobs.py           # Global API sources
│   ├── fetch_rss_jobs.py            # Global RSS feeds
│   └── fetch_local_merchants.py     # Local Kenyan board scrapers
├── tests/
│   ├── test_profile.py              # Stdlib unittest suite for the profile pipeline
│   ├── test_cv_import.py            # PDF/DOCX/TXT extraction and limit tests
│   ├── test_env.py                  # .env parsing and precedence tests
│   └── test_llm_client.py           # Config redaction and model error tests
├── legacy/
│   └── local_directory_scraper.py   # Legacy Playwright scraper (not used by the pipeline)
├── data/
│   └── jsearch.db                   # SQLite database (created on first run)
└── output/
    └── dashboard.html               # Generated output (rebuilt on every GET /)
```

### 3. Run

```bash
python run.py
```

The server starts on `http://localhost:8765` and opens your default browser. It binds to `127.0.0.1` by default because the CV importer handles personal data; set `JSEARCH_HOST=0.0.0.0` if you deliberately want LAN access. Pick your keywords, then use a run button to scrape. Results and your applied/hidden decisions are stored in SQLite, so restarting the server does not lose them.

To use a hosted model instead of Ollama, copy `.env.example` to `.env`, fill in the provider block and restart the server.

```bash
python -m unittest discover -s tests -v
```

## Known Limitations

* Several public job APIs are intermittently blocked or rate-limited depending on network; the fetchers degrade gracefully but the Global count will vary between runs.
* DuckDuckGo search scraping now often returns a bot-challenge page (HTTP 202). It is treated as an optional source, never a required one.
* HTML scrapers depend on BrighterMonday/JobsInKenya markup and will need selector updates if those sites redesign.
* Job identity is the normalised URL (host + path). A reposted job with a new slug/URL will reappear, the same role listed on two sources with different URLs is treated as two jobs, and boards that put the job ID only in query parameters can collide.
* Decisions live in `data/jsearch.db`; deleting the database deletes the application history.
* Keyword changes affect visibility only. The scoring profile (core skills, AI skills, weights, dealbreakers) is edited through the CV import review or the settings API, not by the keyword manager.
* CV import accepts text-based PDFs, DOCX, TXT and Markdown. Scanned/image-only PDFs and legacy `.doc` files are not supported; scanned CVs would need OCR. Two-column PDF layouts can scramble reading order, so review the extracted text before analysing. The candidate's name is not masked — only email, phone, URLs and handles are — so use a zero-retention, no-training provider (Cloudflare Workers AI) or a local model when the CV contains sensitive details.
* CV extraction quality depends on the model. Small local models handle obvious stacks well but are weaker on nuance; hosted models vary. Every proposal is validated against the taxonomy and must be reviewed before it is applied.
* `gpt-oss` models can return empty content when a provider enforces JSON mode. J-Search skips JSON mode for them and retries without it if another model returns an empty answer. Reasoning tokens count toward the output budget, so J-Search defaults `JSEARCH_LLM_REASONING_EFFORT` to `low` for `gpt-oss`. If the model still runs out of output tokens, increase `JSEARCH_LLM_MAX_TOKENS` or use a shorter CV.
* Everything is single-user and local. There is no authentication. The server binds to `127.0.0.1` by default; `JSEARCH_HOST=0.0.0.0` exposes the CV import endpoint to the LAN.

## Roadmap

- [ ] **Keyword-driven queries:** feed highlight keywords into DuckDuckGo/BrighterMonday search URLs so filters shape the scrape, not just the view.
- [x] **Editable scoring profile:** core/AI skill weights and dealbreakers can be reviewed and edited during CV import, then saved to `settings`.
- [x] **PDF/DOCX CV parsing:** extract text from uploaded files instead of requiring paste.
- [ ] **OCR for scanned CVs:** read image-only PDFs; keep this last because it adds a heavy dependency.
- [ ] **Candidate profile editor:** show and edit the stored candidate profile without re-running the model.
- [ ] **Saved searches / history:** keep past result sets to compare listings across runs.
- [ ] **AI-assisted summaries:** optional local LLM pass, behind a review gate, to condense long descriptions into three bullet points on each card.
- [ ] **Export to CSV/Markdown:** write top-tier matches to a tracking document.
- [x] **Application tracker:** applied and dismissed states with reasons, plus `/applied` and `/hidden` pages.
- [ ] **Interview pipeline:** rejected / interviewing / offer states and follow-up dates.
- [ ] **Reason analytics:** rejection-reason counts on the hidden page.
