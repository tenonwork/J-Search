# J-Search — Smart Job Triage Pipeline

A local-first job hunting tool: it scrapes global remote feeds and East African job boards, scores every posting against a configurable keyword model, stores results in SQLite, and serves a dashboard where you filter and sort the results live — no re-scraping required.

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
* **Frontend:** vanilla HTML/CSS/JS — no frameworks, no bundler

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

Weights live in `DEFAULT_SCORING_CONFIG` in `app/job_dashboard.py` and are no longer hardcoded into the matching loop.

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

Presets are applied in the browser by the strictness toggle; the server scores every job once so the toggle is instant.

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
| `/api/decisions` | GET | Decisions as JSON; optional `?status=applied\|dismissed` |
| `/api/decisions` | POST | `{"key": "...", "status": "applied"\|"dismissed", "reason": "...", "note": "...", "job": {...}}` |
| `/api/decisions/delete` | POST | `{"key": "..."}` — restore a job to the dashboard |

## Database

`data/jsearch.db`, created automatically on first run.

| Table | Columns |
| :-- | :-- |
| `keywords` | `id`, `type` (`focus`/`exclude`), `value`, `enabled` (1 = active, 0 = paused) — unique per type |
| `jobs` | `id`, `title`, `company`, `location`, `url` (unique), `description`, `source`, `score`, `matches`, `redflags`, `fetched_at` |
| `decisions` | `job_key` (primary key), `status` (`applied`/`dismissed`), `reason`, `note`, `title`, `company`, `location`, `url`, `source`, `score`, `applied_at`, `created_at`, `updated_at` |

Default keywords are seeded the first time the database is created.

Decision snapshots (title, company, score, etc.) are stored alongside the key, so the tracker pages do not depend on the `jobs` row still existing.

## Getting Started

### 1. Prerequisites

```bash
pip install -r requirements.txt
```

### 2. File Structure

```text
├── run.py                           # HTTP server, pipeline orchestration, API routes
├── requirements.txt                 # Runtime dependencies
├── app/
│   ├── paths.py                     # Project paths (database, generated output)
│   ├── db.py                        # SQLite layer (keywords, jobs, decisions)
│   ├── job_dashboard.py             # Scoring engine, presets, dashboard template
│   └── applied_page.py              # Applied and hidden tracker page templates
├── fetchers/
│   ├── fetch_live_jobs.py           # Global API sources
│   ├── fetch_rss_jobs.py            # Global RSS feeds
│   └── fetch_local_merchants.py     # Local Kenyan board scrapers
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

The server starts on `http://localhost:8765` and opens your default browser. Pick your keywords, then use a run button to scrape. Results and your applied/hidden decisions are stored in SQLite, so restarting the server does not lose them.

## Known Limitations

* Several public job APIs are intermittently blocked or rate-limited depending on network; the fetchers degrade gracefully but the Global count will vary between runs.
* DuckDuckGo search scraping now often returns a bot-challenge page (HTTP 202). It is treated as an optional source, never a required one.
* HTML scrapers depend on BrighterMonday/JobsInKenya markup and will need selector updates if those sites redesign.
* Job identity is the normalised URL (host + path). A reposted job with a new slug/URL will reappear, the same role listed on two sources with different URLs is treated as two jobs, and boards that put the job ID only in query parameters can collide.
* Decisions live in `data/jsearch.db`; deleting the database deletes the application history.
* Keyword changes affect visibility only. The scoring profile (core skills, AI skills, weights, dealbreakers) is built in and is not edited by the keyword manager.
* Everything is single-user and local. There is no authentication and the server binds to all interfaces on port 8765.

## Roadmap

- [ ] **Keyword-driven queries:** feed highlight keywords into DuckDuckGo/BrighterMonday search URLs so filters shape the scrape, not just the view.
- [ ] **Editable scoring profile:** move core/AI skill weights and dealbreakers into the UI so ranking can be tuned without editing Python.
- [ ] **Saved searches / history:** keep past result sets to compare listings across runs.
- [ ] **AI-assisted summaries:** optional local LLM pass, behind a review gate, to condense long descriptions into three bullet points on each card.
- [ ] **Export to CSV/Markdown:** write top-tier matches to a tracking document.
- [x] **Application tracker:** applied and dismissed states with reasons, plus `/applied` and `/hidden` pages.
- [ ] **Interview pipeline:** rejected / interviewing / offer states and follow-up dates.
- [ ] **Reason analytics:** rejection-reason counts on the hidden page.
