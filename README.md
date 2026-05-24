# Job Bot

An automated job application bot that searches multiple job boards, scores listings against your profile, and applies or queues applications — with email notifications and an Excel tracker.

**Live:** [jobfindingbot.streamlit.app](https://jobfindingbot.streamlit.app)

---

## Features

| Feature | Details |
|---|---|
| **Multi-source search** | RemoteOK, Arbeitnow, The Muse, Remotive, Jobicy, HN Hiring, Working Nomads, Himalayas, **Drushim 🇮🇱** |
| **Rule-based matching** | Scores jobs 0–100 by skills, seniority, location, language, and role type — no API needed |
| **Location filter** | Hard-blocks non-remote jobs outside Israel |
| **Company blacklist** | Skip jobs from companies you don't want |
| **Auto-apply** | LinkedIn Easy Apply (Playwright) or email when a contact address is found |
| **Manual queue** | Falls back to `data/manual_apply.csv` for jobs that need human action |
| **Email notifications** | Clear subject line: ✅ auto-applied vs ⚠️ action required |
| **Excel tracker** | Per-user `.xlsx` with status tracking (Applied / Interview / Accepted / Denied) |
| **Streamlit UI** | Dashboard, search, matched jobs, apply, tracker, and settings pages |
| **Daily auto-run** | Windows Task Scheduler script included |
| **Auto-expire** | Removes job listings older than N days automatically |

---

## Quick Start

```bash
# 1. Clone
git clone https://github.com/lielcochabi/job-bot.git
cd job-bot

# 2. Install dependencies
pip install -r requirements.txt
playwright install chromium

# 3. Configure
cp .env.example .env
# Fill in NOTIFY_EMAIL, GMAIL_APP_PASSWORD in .env

# 4. Launch UI
scripts/start_ui.bat   # Windows
# or: streamlit run app.py
```

---

## Configuration

### `.env`
| Variable | Purpose |
|---|---|
| `NOTIFY_EMAIL` | Where to send job notifications |
| `GMAIL_APP_PASSWORD` | Gmail App Password for notifications |
| `EMAIL_ADDRESS` | Sender address for email applications |
| `EMAIL_PASSWORD` | Gmail App Password for sending applications |
| `LINKEDIN_EMAIL` | LinkedIn login (for Easy Apply) |
| `LINKEDIN_PASSWORD` | LinkedIn password |

### `config/config.json` (seed) / Settings UI
Per-user settings live in MongoDB. The default template is `config/config.json`. Set up via the **Settings** page in the UI, or run:
```bash
python main.py setup
```

Key settings: `job_titles`, `match_threshold` (default 70%), `remote_only`, `blacklisted_companies`, `job_expiry_days`.

---

## CLI Commands

```bash
python main.py search      # Search all job boards
python main.py match       # Score unmatched jobs
python main.py apply       # Apply to matched jobs (interactive)
python main.py rematch     # Reset scores and re-match everything
python main.py status      # Show dashboard stats
python main.py jobs        # List jobs by status
python main.py run --auto  # Full pipeline (non-interactive)
python main.py setup       # First-time setup wizard
```

---

## Application Tracker

CLI apply also logs to `data/trackers/tracker_<username>.xlsx`. The UI Tracker uses MongoDB. Excel columns:

`Date Applied` · `Job Title` · `Company` · `Location` · `Match Score` · `Salary` · `URL` · `Method` · **`Status`** · `Notes`

Status options: **Applied** → **Interview** → **Accepted / Denied**

Update statuses from the **📊 Tracker** page in the UI, or directly in the Excel file.

---

## Daily Auto-Run

Right-click `scripts/schedule_daily.bat` → **Run as administrator** to register a Windows Task Scheduler job that runs the full pipeline every day at 8:00 AM.

---

## Running Tests

```bash
pip install pytest
pytest tests/ -v
```

---

## Project Structure

```
job-bot/
├── app.py                 # Streamlit entry (imports ui/app.py)
├── main.py                # CLI entry (Typer)
├── job_bot/               # Core Python package
│   ├── cli.py             # CLI commands
│   ├── database.py        # MongoDB persistence
│   ├── job_searcher.py    # Multi-source job search
│   ├── job_matcher.py     # Rule-based scoring engine
│   ├── job_submitter.py   # Apply via LinkedIn / email / manual queue
│   ├── tracker.py         # Excel application tracker (CLI)
│   ├── resume_parser.py   # PDF/DOCX resume parser
│   ├── auth.py            # User accounts & sessions
│   └── secrets_manager.py # .env / Streamlit Cloud secrets
├── ui/
│   └── app.py             # Streamlit UI implementation
├── config/
│   ├── config.json        # Default settings template
│   └── job_categories.json
├── data/                  # Runtime files (git-ignored)
│   ├── trackers/          # Per-user Excel files (CLI)
│   └── manual_apply.csv
├── scripts/
│   ├── start_ui.bat
│   ├── schedule_daily.bat
│   └── run.bat
├── tests/
├── .streamlit/
└── requirements.txt
```
