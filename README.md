# J-Search — Smart Job Triage Pipeline

A local-first job hunting tool: it scrapes global remote feeds and East African job boards, scores every posting against a configurable keyword model, stores results in SQLite, and serves a dashboard where you filter and sort the results live — no re-scraping required.

You can tune keywords and the five shared weights in one workspace, with separate Global and Local sets, or import a CV (PDF, DOCX or pasted text) and let an optional local or hosted model propose the skills, highlight keywords, hide keywords and weights for you to review.

Instead of deploying blind "spray-and-pray" auto-apply bots that trigger platform bans and flood applicant tracking systems with noise, this system acts as a data gatekeeper. It pulls a deliberately oversized bundle of listings, then lets you narrow it down at your own discretion.

## Project Overview & Philosophy

As an independent developer who builds complete systems (and actively uses governed AI-assisted workflows), I built this to fix the inefficiencies of the modern tech job hunt.

The pipeline is split into five decoupled layers:

1. **Ingestion** — Parallel fetchers for global APIs/RSS and local Kenyan job boards. Each source fails independently, so one dead endpoint never empties the dashboard.
2. **Normalisation & Deduplication** — Every source is mapped to one shape (`title`, `company`, `location`, `url`, `desc`), then deduplicated on a stable job key (host + path, query and `www.` stripped).
3. **Calibration Engine** — Whole-word (`\b`) regex scoring with weighted keyword groups and a configurable dealbreaker penalty.
4. **Decision Filter** — Jobs marked as applied for or dismissed are excluded from the triage list. Raw postings stay in SQLite, so restoring a decision does not require a re-scrape.
5. **Presentation** — A React single-page dashboard served over a local HTTP server. Scoring runs server-side; filtering, strictness and sorting run in the browser, so toggling a control changes the result count instantly.

## Architecture & Core Stack

```text
[Global sources]  ─┐
                   ├─> [Normalise + Deduplicate] ─> [Scoring Engine] ─> [SQLite] ─> [Decision Filter] ─> [dashboard.html]
[Local sources]   ─┘                                                                                                    │
                                                          [Browser] <── HTTP ───────────────────────────────────────────┘
```

* **Language:** Python 3
* **Server:** `http.server` (no Python web framework)
* **Storage:** SQLite via the stdlib `sqlite3` module (`data/jsearch.db`)
* **HTTP client:** `requests`
* **HTML parsing:** `BeautifulSoup` (`bs4`) with the stdlib `html.parser`
* **Feed parsing:** `feedparser`
* **CV file parsing:** `pypdf` for text-based PDFs; stdlib `zipfile` + `ElementTree` for DOCX
* **Frontend:** React 18 + Vite 5 + Tailwind CSS 3 + Lucide icons, built to `app/dashboard_static/` and served by the Python server
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
| Local | Company career pages | HTML scraping | User-managed watchlist; short links resolved first; tech titles only |

Local listings are filtered by a tech-title regex before scoring, so HR, supply-chain and sales roles from the boards don't leak into the dashboard.

## Scoring Engine

The `keywords` table is the source of truth for which terms score and which terms highlight or hide. There is one row per keyword per scope (`global` or `local`). Global jobs are scored with Global rows; Local jobs with Local rows. The five weights are shared and stored on the scoring profile in `settings`. `DEFAULT_SCORING_CONFIG` in `app/job_dashboard.py` is the fallback when a weight is missing or a fresh database is seeded. Profiles are normalised on read: values are lowercased, de-duplicated, length-capped and unknown keys are dropped. Saved profiles keep only the five weights; keyword lists are not stored there.

Each row has a `weight_group` (`core_skills`, `ai_skills`, `good_matches`, `pos_skills`, `dealbreakers`, or empty) and a `type`:

* `focus` — highlight matching cards and, when the row has a weight group, add that group's points.
* `exclude` — hide matching cards and, when the row has a weight group, add that group's points.
* `score` — add points only. POS is seeded this way so `pos` scores without highlighting.
* An empty `weight_group` is visibility only: highlight or hide, with no score change.

Pausing a row stops both its score and its highlight/hide effect. New keywords in a positive group highlight; new dealbreakers hide.

Matching uses word boundaries for plain terms (`\bpostgres\b`), so `postgres` does not match *postgresql*, while terms that cannot be expressed with `\b` (`c++`, `c#`, `.net`, `node.js`) use literal matching. The dashboard's highlight/hide filter uses the same rules as the scorer. `pos` is an ordinary `pos_skills` term, not a separate hard-coded rule, so it still will not match *position* or *repository*.

| Group | Default weight | Default keywords |
| :-- | :-- | :-- |
| Core skills (`core_skills`) | +8 each | `postgresql`, `supabase`, `react native`, `electron`, `typescript`, `react`, `postgres`, `expo`, `fullstack`, `full-stack`, `backend` |
| AI & infrastructure (`ai_skills`) | +5 each | `mcp`, `model context protocol`, `llm`, `ai agent`, `claude`, `sqlite`, `data science`, `python` |
| Good matches (`good_matches`) | +5 each | `nairobi`, `remote`, `hybrid`, `mid-level`, `mid level`, `contract`, `point of sale` |
| POS systems (`pos_skills`) | +5 each | `pos` |
| Dealbreakers (`dealbreakers`) | −30 each | `senior`, `lead`, `staff`, `architect`, `manager`, `10+ years`, `8+ years`, `phd`, `clearance required` |

Older databases are migrated once, flagged by `keyword_workspace_version = 2`. Existing highlight and hide rows are copied into both scopes. A keyword that sat in more than one scoring list keeps the group with the largest absolute weight; ties follow Core → AI → Good → POS → Dealbreakers. That removes double-counting, so a few stored scores can shift. The migration is idempotent.

### Strictness presets

| Preset | Remote dealbreakers | Remote minimum | Local dealbreakers | Local minimum |
| :-- | :-- | :-- | :-- | :-- |
| Strict | Hard drop | 10 | Hard drop | 3 |
| Balanced | Hard drop | 5 | Penalty only | 0 |
| Lenient | Penalty only | 0 | Penalty only | −10 |

Presets are applied in the browser by the strictness toggle; the server scores every job once so the toggle is instant. Presets own the thresholds and whether dealbreakers are enforced, not the keyword lists or weights. Lists come from the keyword rows for that job's source; weights come from the shared profile.

### Engineering notes

* **Bounded word matching** — `r'\bkeyword\b'` prevents false positives such as `pos` matching *position*, *composition* or *repository*.
* **Hard drop vs penalty** — Remote listings with any dealbreaker are removed under Strict/Balanced. Local listings are only penalised, because board titles are terse and often miss obvious keywords.
* **Blocklist** — Paywalled/gated hosts (`linkedin.com`, `glassdoor.com`, `remotive.com` listing pages, etc.) are dropped before rendering, regardless of score.

## Dashboard

The dashboard is a dark, responsive React interface built around the J-Search cyan/blue brand mark. It keeps the original scoring and API behaviour while adding score rings, glass panels, keyword chips, and a role-detail drawer.

* **Two tabs:** Global and Local — each with its own result count, and each filtered with that scope's highlight and hide keywords.
* **Keywords & weights:** One modal with Global and Local tabs. All five weight cards stay visible. Each chip can change behaviour (highlight, hide, or score only), pause, move to another weight, or be deleted. Keywords with no weight sit in a visibility-only section. One Save writes both scopes and the shared weights, then rescores and rebuilds the dashboard. Persisted in SQLite.
* **Broad fetch:** Scrapers always fetch a wide set of postings. Keywords change scoring and what the dashboard shows; they do not change what is fetched.
* **Strictness toggle:** Strict / Balanced / Lenient.
* **Sort:** most recommended first, newest first, or lowest match first.
* **Export:** **Export JSON** and **Export Word** download every role in the current tab and filters, not just the page on screen. Each file includes the description, matched signals, red flags, and the highlight keywords that fit that posting.
* **Score rings:** emerald for 80+, cyan for 50–79, muted slate below 50.
* **Run controls:** Run All, Run Global Only, and Run Local Only, with live Applied/Hidden tallies in the header.
* **Job detail drawer:** Review Entry opens a slide-over with the full description, matched signals, red flags, score, and quick apply link.
* **Local Sources:** paste a company careers page or a whole WhatsApp message. Short links are resolved and the real destination is shown before anything is imported. Scans are review-gated: pick the tech roles to import and optionally watch the page on future Local runs. Watched pages can be paused or removed.
* **Full-page loading screen:** clicking a run button navigates to a dedicated loading page that polls `/status` and redirects to the dashboard only once the scrape has actually finished.
* **Per-job decisions:** each card has `Applied` and `Not for me` buttons. Applied removes the posting from triage and logs it on the applied page; Not for me opens a reason picker (preset + optional note) and logs it on the hidden page. Both actions show an Undo toast.

## CV Import

The **Import from CV** button opens a review-gated profile builder:

1. Upload a PDF or DOCX (or paste text) and, optionally, a free-text list of things to avoid.
2. The file is parsed locally and in memory — the upload is never written to disk or logged. The extracted text lands in the textarea so it can be reviewed or edited before analysis.
3. Contact details (email, phone, URLs, handles) are masked before the text is sent to the configured model. If the model is remote, the dashboard says so before analysis.
4. The model returns only allow-listed skills with evidence snippets. Unknown, unevidenced or generic terms are dropped.
5. The dashboard shows the proposed scoring profile, highlight keywords, hide keywords and an impact preview (`N visible now → M after applying`).
6. No scoring or keyword changes are written until **Apply selected**. The review step has an **Apply to** selector: Global, Local, or Both. It defaults to the dashboard tab you opened the import from. Applying saves the shared weights and writes the proposed lists plus the selected highlight and hide keywords into the chosen set or sets, then rescores. **Add** merges into those sets. **Replace** clears only the sets you selected.

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
| `/` | GET | Rebuild the React shell in `output/dashboard.html` with bootstrap data (falls back to SQLite if nothing is in memory) |
| `/static/*` | GET | Built JS/CSS and favicon assets from `app/dashboard_static/` |
| `/favicon-32.png`, `/apple-touch-icon.png` | GET | Brand icons for browser tabs and mobile home screens |
| `/run?mode=all\|global\|local` | GET | Start a scrape and serve the loading page |
| `/status` | GET | `{"running": true\|false}` for the loading page |
| `/refresh` | POST | Re-run all scrapers |
| `/applied` | GET | Applied-jobs tracker page |
| `/hidden` | GET | Dismissed-jobs tracker page |
| `/api/jobs` | GET | Scored jobs as JSON, excluding applied/hidden postings |
| `/api/export` | POST | `{"format": "json"\|"docx", "scope": "global"\|"local", "strictness": "...", "sort": "...", "highlight_keywords": [...], "jobs": [...]}` — download the roles currently shown, with descriptions, matches, red flags and fitting highlight keywords |
| `/api/keywords` | GET | Highlight and hide keywords for both scopes, each with enabled state and weight group. Top-level `focus` and `exclude` mirror Global |
| `/api/keywords/add` | POST | `{"type": "focus"\|"exclude"\|"score", "value": "...", "scope": "global"\|"local", "weight_group": "core_skills"\|...}` |
| `/api/keywords/state` | POST | `{"type": "...", "scope": "global"\|"local", "states": {"keyword": true\|false}}` — pause/enable without deleting |
| `/api/keywords/delete` | POST | `{"type": "...", "scope": "global"\|"local", "values": ["..."]}` |
| `/api/keyword-workspace` | GET | Shared weights, defaults, the five group definitions, and every keyword row for both scopes |
| `/api/keyword-workspace` | POST | `{"weights": {...}, "scopes": {"global": [...], "local": [...]}}` — replace both keyword sets and merge weights in one write, then rescore and rebuild the dashboard. Requires at least one valid weight and both scope lists |
| `/api/weights` | GET | Weights plus the enabled lists for one scope (`?scope=global` or `?scope=local`) |
| `/api/weights` | POST | `{"weights": {...}}` — save shared weights only, then rescore. Keyword rows are left as they are |
| `/api/profile` | GET | Saved weights, the effective config for each scope, candidate profile, dismissal counts and model configuration |
| `/api/llm/test` | POST | Send a tiny, CV-free prompt to verify the configured endpoint, key and model |
| `/api/profile/extract` | POST | Raw PDF/DOCX/TXT body (max 10 MB) — extracted text for review; nothing is stored |
| `/api/profile/analyze` | POST | `{"cv_text": "...", "preferences": "...", "scope": "global"\|"local"\|"both"}` — validated proposal plus impact preview; saves only the structured candidate profile |
| `/api/profile/preview` | POST | `{"profile": {...}, "focus": [...], "exclude": [...], "scope": "...", "mode": "add"\|"replace"}` — impact preview without saving |
| `/api/profile/apply` | POST | Same payload as preview. Persists the shared weights and writes keywords into the selected scope or both. `"mode": "replace"` clears only those scopes |
| `/api/profile/reset` | POST | Delete the saved scoring weights and restore default weights |
| `/api/local-sites` | GET | Watched company career pages with enabled state |
| `/api/local-sites/scan` | POST | `{"text": "..."}` — extract up to 3 URLs, resolve short links, preview tech roles; nothing is saved |
| `/api/local-sites/apply` | POST | `{"token": "...", "watch": true, "jobs": ["url"]}` — import selected roles and optionally watch the resolved page |
| `/api/local-sites/state` | POST | `{"url": "...", "enabled": true\|false}` — pause or re-enable a watched page |
| `/api/local-sites/delete` | POST | `{"url": "..."}` — remove a watched page |
| `/api/decisions` | GET | Decisions as JSON; optional `?status=applied\|dismissed` |
| `/api/decisions` | POST | `{"key": "...", "status": "applied"\|"dismissed", "reason": "...", "note": "...", "job": {...}}` |
| `/api/decisions/delete` | POST | `{"key": "..."}` — restore a job to the dashboard |

## Database

`data/jsearch.db`, created automatically on first run.

| Table | Columns |
| :-- | :-- |
| `keywords` | `id`, `scope` (`global`/`local`), `value`, `weight_group` (one of the five groups, or empty), `type` (`focus`/`exclude`/`score`), `enabled` (1 = active, 0 = paused) — unique on `(scope, value)` |
| `settings` | `key` (primary key), `value` (JSON), `updated_at` — shared scoring weights, `keyword_workspace_version`, candidate profile and watched local sources |
| `jobs` | `id`, `title`, `company`, `location`, `url` (unique), `description`, `source`, `score`, `matches`, `redflags`, `fetched_at` |
| `decisions` | `job_key` (primary key), `status` (`applied`/`dismissed`), `reason`, `note`, `title`, `company`, `location`, `url`, `source`, `score`, `applied_at`, `created_at`, `updated_at` |

Default keywords are seeded the first time the database is created, once into each scope. Older databases are migrated automatically to the workspace schema: highlight and hide rows are copied into both scopes, scoring-list membership is collapsed to one weight per keyword, and the profile is reduced to the five weights. Paused states are preserved. The `keyword_workspace_version` setting is `2` after that migration.

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

### 2. Build the frontend (one-time)

The compiled dashboard is served from `app/dashboard_static/`. Prebuilt assets are kept in the repository, so you only need Node.js when you change the UI:

```bash
cd frontend
npm install
npm run build
```

Node.js 18 or newer is required. The build writes fixed-name assets (`app.js`, `app.css`) plus favicons into `app/dashboard_static/`; Vite does not need to run while the Python server is running.

### 3. File Structure

```text
├── run.py                           # HTTP server, pipeline orchestration, API routes
├── requirements.txt                 # Runtime dependencies
├── .env.example                     # Hosted/local model configuration template
├── app/
│   ├── paths.py                     # Project paths (database, generated output, static assets)
│   ├── env.py                       # Dependency-free .env loader
│   ├── db.py                        # SQLite layer (keywords, jobs, decisions, settings)
│   ├── job_dashboard.py             # Scoring engine, presets, React shell + bootstrap
│   ├── export_results.py            # JSON and Word downloads of the visible results
│   ├── cv_profile.py                # CV scrubbing, validation, profile proposal
│   ├── cv_import.py                 # Local PDF/DOCX/TXT text extraction for uploads
│   ├── llm_client.py                # OpenAI-compatible chat client
│   ├── skills_taxonomy.json         # Allow-listed skills, aliases, generic blocklist
│   ├── applied_page.py              # Applied and hidden tracker page templates
│   └── dashboard_static/            # Built React bundle served at /static
├── frontend/
│   ├── index.html                   # Vite entry document
│   ├── package.json                 # React, Tailwind and build scripts
│   ├── vite.config.js               # Fixed app.js/app.css output
│   ├── tailwind.config.js           # Brand palette, fonts, shadows, animations
│   ├── public/                      # Favicon crops generated from assets/
│   └── src/
│       ├── App.jsx                  # Dashboard state, filters, decisions, modal wiring
│       ├── components/              # Header, keyword panel, cards, drawer, modals
│       └── lib/                     # API helper and client-side scoring/filter utilities
├── assets/
│   ├── Logo-J Search.png            # Brand source
│   └── Favicon-J Search.png         # Favicon source
├── fetchers/
│   ├── fetch_live_jobs.py           # Global API sources
│   ├── fetch_rss_jobs.py            # Global RSS feeds
│   ├── fetch_local_merchants.py     # Local Kenyan board scrapers
│   ├── fetch_career_sites.py        # Watched career pages and short-link resolution
│   └── local_common.py              # Shared local-source headers and tech-title filter
├── tests/
│   ├── test_profile.py              # Stdlib unittest suite for the profile pipeline
│   ├── test_cv_import.py            # PDF/DOCX/TXT extraction and limit tests
│   ├── test_env.py                  # .env parsing and precedence tests
│   ├── test_llm_client.py           # Config redaction and model error tests
│   ├── test_local_sites.py          # Career-page scanning, safety and watchlist tests
│   └── test_dashboard_shell.py      # React shell and bootstrap injection test
├── legacy/
│   └── local_directory_scraper.py   # Legacy Playwright scraper (not used by the pipeline)
├── data/
│   └── jsearch.db                   # SQLite database (created on first run)
└── output/
    └── dashboard.html               # Generated React shell (rebuilt on every GET /)
```

### 4. Run

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
* Local Sources reads static HTML. JavaScript-only career pages, logins and infinite-scroll listings are not supported; the scanner follows the first page of role links and caps each site at 25 detail pages. A redesign can require selector or link-heuristic changes.
* WhatsApp messages are pasted into the dashboard, not read automatically. WhatsApp Desktop/Web has no supported local API, and its local message store is encrypted; scraping it is fragile and against its terms.
* Short links are resolved and the final destination is shown before import. Local/private addresses, credentials in URLs and non-standard ports are rejected; only `http`/`https` pages are fetched.
* Job identity is the normalised URL (host + path). A reposted job with a new slug/URL will reappear, the same role listed on two sources with different URLs is treated as two jobs, and boards that put the job ID only in query parameters can collide.
* Decisions live in `data/jsearch.db`; deleting the database deletes the application history.
* Saving the keyword workspace or applying a CV import rescores jobs and rebuilds the dashboard. Scrapers still ignore keywords; only the view and the score change.
* CV import accepts text-based PDFs, DOCX, TXT and Markdown. Scanned/image-only PDFs and legacy `.doc` files are not supported; scanned CVs would need OCR. Two-column PDF layouts can scramble reading order, so review the extracted text before analysing. The candidate's name is not masked — only email, phone, URLs and handles are — so use a zero-retention, no-training provider (Cloudflare Workers AI) or a local model when the CV contains sensitive details.
* CV extraction quality depends on the model. Small local models handle obvious stacks well but are weaker on nuance; hosted models vary. Every proposal is validated against the taxonomy and must be reviewed before it is applied.
* `gpt-oss` models can return empty content when a provider enforces JSON mode. J-Search skips JSON mode for them and retries without it if another model returns an empty answer. Reasoning tokens count toward the output budget, so J-Search defaults `JSEARCH_LLM_REASONING_EFFORT` to `low` for `gpt-oss`. If the model still runs out of output tokens, increase `JSEARCH_LLM_MAX_TOKENS` or use a shorter CV.
* Everything is single-user and local. There is no authentication. The server binds to `127.0.0.1` by default; `JSEARCH_HOST=0.0.0.0` exposes the CV import endpoint to the LAN.

## Roadmap

- [ ] **Keyword-driven queries:** feed highlight keywords into DuckDuckGo/BrighterMonday search URLs so filters shape the scrape, not just the view.
- [x] **Company career pages:** a user-managed Local watchlist with short-link resolution and review-gated imports.
- [x] **Editable scoring profile:** all five weights, including Good matches and POS, are edited in the keyword workspace or during CV import. Weights are shared; keyword lists are per scope.
- [x] **PDF/DOCX CV parsing:** extract text from uploaded files instead of requiring paste.
- [ ] **OCR for scanned CVs:** read image-only PDFs; keep this last because it adds a heavy dependency.
- [ ] **Candidate profile editor:** show and edit the stored candidate profile without re-running the model.
- [ ] **Saved searches / history:** keep past result sets to compare listings across runs.
- [ ] **AI-assisted summaries:** optional local LLM pass, behind a review gate, to condense long descriptions into three bullet points on each card.
- [ ] **Export to CSV/Markdown:** write top-tier matches to a tracking document.
- [x] **Application tracker:** applied and dismissed states with reasons, plus `/applied` and `/hidden` pages.
- [ ] **Interview pipeline:** rejected / interviewing / offer states and follow-up dates.
- [ ] **Reason analytics:** rejection-reason counts on the hidden page.
