# Job Bot — Project Guide

Automated job search, AI scoring, and application assistant.
Live at: https://jobfindingbot.streamlit.app

---

## Folder layout

```
job_bot/                  ← Python package (all business logic)
  auth.py                 ← User registration, login, session tokens
  cli.py                  ← Typer CLI: search / match / rematch / run
  database.py             ← MongoDB helpers (jobs, resumes, configs, tracker)
  job_matcher.py          ← Rule-based + AI scoring (0–100)
  job_searcher.py         ← Scrapes 11 job boards in parallel threads
  job_submitter.py        ← Playwright browser automation for ATS forms
  paths.py                ← Central path constants (ROOT, CONFIG_DIR, etc.)
  resume_parser.py        ← PDF/DOCX text + profile extraction
  secrets_manager.py      ← Injects st.secrets → os.environ at startup
  tracker.py              ← Per-user Excel tracker (legacy, mostly superseded by DB)

ui/
  app.py                  ← Full Streamlit UI (~100 KB). Pages:
                            Dashboard | Search | Apply | Tracker | Settings | Help

config/
  config.json             ← Default user config (seed for new accounts)
  job_categories.json     ← Category → job title lists used in Search page

scripts/
  run.bat                 ← Local: python main.py
  start_ui.bat            ← Local: streamlit run app.py
  schedule_daily.bat      ← Windows Task Scheduler setup (run as admin once)

tests/
  conftest.py
  test_tracker_stats.py

app.py                    ← Thin wrapper: runs ui/app.py via runpy (Streamlit entry point)
main.py                   ← Thin wrapper: imports job_bot.cli.main (CLI entry point)
requirements.txt          ← Python deps
packages.txt              ← System packages for Streamlit Cloud / Docker (Chromium deps)
Dockerfile                ← For Google Cloud Run deployment
.github/workflows/
  keep_awake.yml          ← Headless Chrome pings app every 30 min to prevent sleep
```

---

## Key architecture decisions

- **MongoDB Atlas** for all persistent data (jobs, users, configs, resumes, tracker).  
  No SQLite — `jobs.db` was removed.
- **Per-user data isolation** via `database.set_username(username)` which sets a thread-local.  
  Every DB query automatically scopes to the current user.
- **Caching** — all expensive DB calls go through `@st.cache_data` helpers:
  - `_get_stats(username)` TTL 30 s — bust with `_get_stats.clear()` after any job status change
  - `_load_config_cached(username)` TTL 60 s — bust with `_load_config_cached.clear()` after `save_config()`
  - `_has_resume_cached(username)` TTL 30 s — bust after resume upload
- **Login persistence** — 90-day token stored in MongoDB sessions collection.  
  Cookie written via `st.components.v1.html()` JS on the first main-app render (not during login rerun).  
  Cookie read via `st.context.cookies.get()` on every page load.
- **Seniority filter** — applied at search time in `main.py` (not just at scoring time).  
  Keyword sets live in `job_matcher.py` (`SENIOR_TITLE_WORDS`, `JUNIOR_TITLE_WORDS`) and are imported by `main.py`.
- **Title relevance filter** — in `main.py`, jobs whose title shares no domain keyword with the searched queries are dropped before DB insert (prevents "Full Stack" appearing when searching "Python Developer").
- **Playwright** for ATS form filling — installed at runtime via `_ensure_playwright()`.  
  Falls back to cheat sheet for forms that require login / CAPTCHA.

---

## Environment variables / secrets

Set these in Streamlit Cloud → Settings → Secrets (TOML format):

```toml
ANTHROPIC_API_KEY    = "..."   # unused currently (OpenRouter used instead)
MONGODB_URI          = "mongodb+srv://..."
NOTIFY_EMAIL         = "lielcochabi@gmail.com"   # Gmail sender account
GMAIL_APP_PASSWORD   = "..."   # Gmail App Password (not account password)
OPENROUTER_API_KEY   = "..."   # Llama 3.1 free tier for AI scoring + cover letters
GOOGLE_CLIENT_ID     = "..."   # OAuth
GOOGLE_CLIENT_SECRET = "..."   # OAuth
APP_URL              = "https://jobfindingbot.streamlit.app"
```

Local development: copy `.env.example` → `.env` and fill in values.

---

## Running locally

```bash
# Install deps
pip install -r requirements.txt
playwright install chromium

# Start UI
streamlit run app.py

# CLI commands
python main.py search -q "Python Developer" --location israel
python main.py match
python main.py rematch --ai
python main.py run --auto   # full pipeline
```

---

## Database collections (MongoDB `job_bot` DB)

| Collection    | Contents |
|---------------|----------|
| `users`       | username, email, password_hash, auth_provider |
| `sessions`    | auth tokens with expiry (90-day remember-me) |
| `jobs`        | all scraped jobs — status, score, tracker_status, tracker_notes |
| `resumes`     | resume text + raw file bytes per user |
| `configs`     | per-user settings (thresholds, categories, profile, seniority) |
| `rate_limits` | per-source rate-limit expiry timestamps |

---

## Common tasks

**Clear all jobs for a user (from Python):**
```python
from dotenv import load_dotenv; load_dotenv(".env")
import secrets_manager; secrets_manager.inject_all_into_env()
import database; db = database._get_db()
db.jobs.delete_many({"username": "lielc"})
```

**Add a new job source:**
1. Add a `search_XYZ(queries)` generator in `job_bot/job_searcher.py`
2. Register it in the `source_map` dict inside `search_all_sources()`
3. Add it to `_ISRAEL_SOURCES` if it has Israeli listings
4. Add a checkbox in Settings → Job sources in `ui/app.py`

**Modify AI scoring prompt:**
Edit `ai_score_job()` in `job_bot/job_matcher.py`.

**Modify skill weights:**
Edit `DEFAULT_SKILL_WEIGHTS` dict at the top of `job_bot/job_matcher.py`.
