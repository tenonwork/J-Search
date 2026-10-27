# J-Search — Smart Job Triage Pipeline

A local-first job hunting tool: it scrapes global remote feeds and East African job boards, scores every posting against a configurable keyword model, stores results in SQLite, and serves a dashboard where you filter and sort the results live — no re-scraping required.

Instead of deploying blind "spray-and-pray" auto-apply bots that trigger platform bans and flood applicant tracking systems with noise, this system acts as a data gatekeeper. It pulls a deliberately oversized bundle of listings, then lets you narrow it down at your own discretion.

## Project Overview & Philosophy

As an independent developer who builds complete systems (and actively uses governed AI-assisted workflows), I built this to fix the inefficiencies of the modern tech job hunt.

The pipeline is split into four decoupled layers:

1. **Ingestion** — Parallel fetchers for global APIs/RSS and local Kenyan job boards. Each source fails independently, so one dead endpoint never empties the dashboard.
2. **Normalisation & Deduplication** — Every source is mapped to one shape (`title`, `company`, `location`, `url`, `desc`), then deduplicated on a normalised URL (scheme + host + path, query stripped).
3. **Calibration Engine** — Whole-word (`\b`) regex scoring with weighted keyword groups and a configurable dealbreaker penalty.
4. **Presentation** — A single-page dashboard served over a local HTTP server. Scoring runs server-side; filtering, strictness and sorting run in the browser, so toggling a control changes the result count instantly.

## Architecture & Core Stack

```text
[Global sources]  ─┐
                   ├─> [Normalise + Deduplicate] ─> [Scoring Engine] ─> [SQLite] ─> [dashboard.html]
[Local sources]   ─┘                                                              │
                                                          [Browser] <── HTTP ─────┘
```

* **Language:** Python 3
* **Server:** `http.server` (no framework, no build step)
* **Storage:** SQLite via the stdlib `sqlite3` module (`jsearch.db`)
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

Weights live in `DEFAULT_SCORING_CONFIG` in `job_dashboard.py` and are no longer hardcoded into the matching loop.

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
* **Keyword manager:** Focus keywords (highlight matching cards) and Exclude keywords (hide matching cards), with add, remove and a bulk-select modal (Select all / Select none / Delete selected). Persisted in SQLite.
* **Strictness toggle:** Strict / Balanced / Lenient.
* **Sort:** most recommended first, or least recommended first.
* **Run controls:** Run All, Run Global Only, and Run Local Only.
* **Full-page loading screen:** clicking a run button navigates to a dedicated loading page that polls `/status` and redirects to the dashboard only once the scrape has actually finished.

## HTTP Routes

| Route | Method | Purpose |
| :-- | :-- | :-- |
| `/` | GET | Rebuild and serve `dashboard.html` (falls back to SQLite if nothing is in memory) |
| `/run?mode=all\|global\|local` | GET | Start a scrape and serve the loading page |
| `/status` | GET | `{"running": true\|false}` for the loading page |
| `/refresh` | POST | Re-run all scrapers |
| `/api/jobs` | GET | Scored jobs as JSON |
| `/api/keywords` | GET | Current focus/exclude keywords |
| `/api/keywords/add` | POST | `{"type": "focus"\|"exclude", "value": "..."}` |
| `/api/keywords/delete` | POST | `{"type": "...", "values": ["..."]}` |

## Database

`jsearch.db`, created automatically on first run.

| Table | Columns |
| :-- | :-- |
| `keywords` | `id`, `type` (`focus`/`exclude`), `value` — unique per type |
| `jobs` | `id`, `title`, `company`, `location`, `url` (unique), `description`, `source`, `score`, `matches`, `redflags`, `fetched_at` |

Default keywords are seeded the first time the database is created.

## Getting Started

### 1. Prerequisites

```bash
pip install requests beautifulsoup4 feedparser
```

### 2. File Structure

```text
├── run.py                     # HTTP server, pipeline orchestration, API routes
├── job_dashboard.py           # Scoring engine, presets, dashboard template
├── db.py                      # SQLite layer (keywords + jobs)
├── fetch_live_jobs.py         # Global API sources
├── fetch_rss_jobs.py          # Global RSS feeds
├── fetch_local_merchants.py   # Local Kenyan board scrapers
├── local_directory_scraper.py # Legacy Playwright lead scraper (not used by the pipeline)
├── dashboard.html             # Generated output (rebuilt on every GET /)
└── jsearch.db                 # SQLite database (created on first run)
```

### 3. Run

```bash
python run.py
```

The server starts on `http://localhost:8765` and opens your default browser. Pick your keywords, then use a run button to scrape. Results are stored in SQLite, so restarting the server does not lose them.

## Known Limitations

* Several public job APIs are intermittently blocked or rate-limited depending on network; the fetchers degrade gracefully but the Global count will vary between runs.
* DuckDuckGo search scraping now often returns a bot-challenge page (HTTP 202). It is treated as an optional source, never a required one.
* HTML scrapers depend on BrighterMonday/JobsInKenya markup and will need selector updates if those sites redesign.
* Everything is single-user and local. There is no authentication and the server binds to all interfaces on port 8765.

## Roadmap

- [ ] **Keyword-driven queries:** feed focus keywords into DuckDuckGo/BrighterMonday search URLs so filters shape the scrape, not just the view.
- [ ] **Saved searches / history:** keep past result sets to compare listings across runs.
- [ ] **AI-assisted summaries:** optional local LLM pass, behind a review gate, to condense long descriptions into three bullet points on each card.
- [ ] **Export to CSV/Markdown:** write top-tier matches to a tracking document.
- [ ] **Application tracker:** mark listings as applied / rejected / follow-up.
