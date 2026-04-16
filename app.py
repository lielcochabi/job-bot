"""
Job Bot — Streamlit Web UI
Run with: streamlit run app.py
"""
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))
import database

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Job Bot",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

PYTHON = str(Path(sys.executable))
BOT_DIR = Path(__file__).parent
CONFIG_PATH = BOT_DIR / "config.json"

# ---------------------------------------------------------------------------
# Global CSS
# ---------------------------------------------------------------------------

st.markdown("""
<style>
    html, body, [class*="css"] { font-family: 'Inter', 'Segoe UI', sans-serif; }
    .block-container { padding-top: 1.5rem !important; padding-bottom: 2rem !important; }

    [data-testid="stSidebar"] { background: #0f172a; padding: 1.5rem 1rem; }
    [data-testid="stSidebar"] * { color: #e2e8f0 !important; }
    [data-testid="stSidebar"] hr { border-color: #334155; }

    .stat-card {
        background: linear-gradient(135deg, #1e293b, #0f172a);
        border: 1px solid #334155; border-radius: 14px;
        padding: 22px 16px; text-align: center;
        width: 100%; box-sizing: border-box;
    }
    .stat-card .value { font-size: 2.2rem; font-weight: 800; line-height: 1.1; }
    .stat-card .label {
        font-size: 0.78rem; letter-spacing: 0.05em; text-transform: uppercase;
        margin-top: 6px; opacity: 0.7; color: #94a3b8;
    }

    .job-card {
        background: #1e293b; border: 1px solid #334155;
        border-radius: 14px; padding: 20px 24px;
        margin-bottom: 14px; width: 100%; box-sizing: border-box;
    }
    .job-card:hover { border-color: #6366f1; }
    .job-card .job-title {
        font-size: 1.05rem; font-weight: 700; color: #e2e8f0;
        margin-bottom: 4px; white-space: normal; word-break: break-word;
    }
    .job-card .job-meta { font-size: 0.82rem; color: #94a3b8; margin-bottom: 10px; }
    .job-card .score-badge {
        display: inline-block; padding: 3px 12px;
        border-radius: 99px; font-size: 0.8rem; font-weight: 700; margin-right: 8px;
    }
    .skill-tag {
        display: inline-block; background: #1e3a5f; color: #93c5fd;
        border-radius: 6px; padding: 2px 9px; font-size: 0.75rem; margin: 2px 2px 0 0;
    }
    .job-card .desc {
        font-size: 0.82rem; color: #94a3b8; margin-top: 10px;
        line-height: 1.55; white-space: normal; word-break: break-word;
    }

    .stButton > button {
        border-radius: 10px !important; font-weight: 600 !important;
        padding: 0.5rem 1.2rem !important; transition: all 0.2s !important;
    }
    .stButton > button:hover { transform: translateY(-1px); }

    .page-title { font-size: 1.8rem; font-weight: 800; color: #e2e8f0; margin-bottom: 0.2rem; }
    .page-sub { font-size: 0.9rem; color: #64748b; margin-bottom: 1.5rem; }
    .section-divider { border: none; border-top: 1px solid #334155; margin: 1.5rem 0; }

    /* ── Task Panel ── */
    .task-panel {
        background: #0f172a; border: 1px solid #334155;
        border-radius: 12px; overflow: hidden; margin-top: 1rem;
    }
    .task-panel-header {
        display: flex; align-items: center; gap: 10px;
        padding: 12px 18px; border-bottom: 1px solid #1e293b;
    }
    .task-panel-header.running { border-left: 3px solid #f59e0b; }
    .task-panel-header.done    { border-left: 3px solid #34d399; }
    .task-panel-header.error   { border-left: 3px solid #f87171; }
    .task-panel-body {
        padding: 14px 18px; font-family: 'Courier New', monospace;
        font-size: 0.8rem; max-height: 380px; overflow-y: auto;
        line-height: 1.6;
    }

    @keyframes spin {
        from { transform: rotate(0deg); }
        to   { transform: rotate(360deg); }
    }
    .spinner-icon {
        display: inline-block;
        animation: spin 1s linear infinite;
        font-style: normal;
    }
    @keyframes blink {
        0%, 100% { opacity: 1; }
        50%       { opacity: 0.2; }
    }
    .dot-pulse {
        display: inline-block; width: 8px; height: 8px;
        background: #f59e0b; border-radius: 50%;
        animation: blink 1.1s infinite; margin-right: 4px;
    }

    #MainMenu { visibility: hidden; }
    footer    { visibility: hidden; }
    header    { visibility: hidden; }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Background task helpers
# ---------------------------------------------------------------------------

def launch_task(cmd: list, task_key: str):
    """Start a subprocess in a background thread; track output in session_state."""
    st.session_state[task_key] = {
        "running": True,
        "lines": [],
        "returncode": None,
        "visible": True,
    }

    def _run():
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=str(BOT_DIR),
            )
            for raw in proc.stdout:
                line = raw.rstrip()
                if line:
                    st.session_state[task_key]["lines"].append(line)
            proc.wait()
            st.session_state[task_key]["running"] = False
            st.session_state[task_key]["returncode"] = proc.returncode
        except Exception as exc:
            st.session_state[task_key]["lines"].append(f"Launch error: {exc}")
            st.session_state[task_key]["running"] = False
            st.session_state[task_key]["returncode"] = 1

    threading.Thread(target=_run, daemon=True).start()


def _colorize(line: str) -> str:
    """Wrap a log line in a color span based on its content."""
    esc = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    lo = line.lower()
    if any(k in lo for k in ("[match]", "✓", "complete", "success", "done", "applied")):
        return f'<span style="color:#34d399">{esc}</span>'
    if any(k in lo for k in ("error", "fail", "❌", "exception", "traceback")):
        return f'<span style="color:#f87171">{esc}</span>'
    if any(k in lo for k in ("skip", "busy", "retry", "rate")):
        return f'<span style="color:#64748b">{esc}</span>'
    if any(k in lo for k in ("searching", "source", "fetching", "🔍")):
        return f'<span style="color:#60a5fa">{esc}</span>'
    if any(k in lo for k in ("match", "score", "🎯", "found")):
        return f'<span style="color:#c084fc">{esc}</span>'
    if any(k in lo for k in ("warn", "⚠", "skip")):
        return f'<span style="color:#fbbf24">{esc}</span>'
    return f'<span style="color:#94a3b8">{esc}</span>'


def render_task_panel(task_key: str, title: str) -> bool:
    """
    Render the output panel for a running/completed task.
    Returns True if the task is still running (caller should rerun).
    """
    state = st.session_state.get(task_key)
    if not state or not state.get("visible", True):
        return False

    running  = state["running"]
    lines    = state["lines"]
    rc       = state["returncode"]

    # ── Header row ──────────────────────────────────────────────────────────
    header_col, close_col = st.columns([11, 1])
    with header_col:
        if running:
            st.markdown(
                f'<div class="task-panel-header running">'
                f'<i class="spinner-icon">⏳</i>'
                f'<span style="color:#f59e0b;font-weight:700">{title}</span>'
                f'<span style="color:#64748b;font-size:0.8rem"> &nbsp;— running, please wait…</span>'
                f'</div>',
                unsafe_allow_html=True,
            )
        elif rc == 0:
            st.markdown(
                f'<div class="task-panel-header done">'
                f'<span style="color:#34d399;font-weight:700">✅ {title} — Completed!</span>'
                f'</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f'<div class="task-panel-header error">'
                f'<span style="color:#f87171;font-weight:700">❌ {title} — Failed (exit {rc})</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

    with close_col:
        if st.button("✕ Close", key=f"close_{task_key}", use_container_width=True):
            st.session_state[task_key]["visible"] = False
            st.rerun()

    # ── Output box ──────────────────────────────────────────────────────────
    if not lines:
        placeholder = '<span style="color:#475569;font-style:italic">Starting process…</span>'
        st.markdown(
            f'<div class="task-panel-body">{placeholder}</div>',
            unsafe_allow_html=True,
        )
    else:
        colored = "<br>".join(_colorize(l) for l in lines[-100:])
        st.markdown(
            f'<div class="task-panel-body">{colored}</div>',
            unsafe_allow_html=True,
        )

    # ── Auto-refresh while running ──────────────────────────────────────────
    if running:
        time.sleep(0.8)
        st.rerun()

    return running


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------

def load_config() -> dict:
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    return {}


def save_config(cfg: dict):
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")


def score_color(score: float) -> str:
    if score >= 85: return "#22c55e"
    if score >= 75: return "#f59e0b"
    return "#6366f1"


def stat_card(col, label: str, value, color: str, icon: str = ""):
    col.markdown(
        f'<div class="stat-card">'
        f'<div class="value" style="color:{color}">{icon} {value}</div>'
        f'<div class="label">{label}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

database.init_db()
stats = database.get_stats()

with st.sidebar:
    st.markdown("## 🤖 Job Bot")
    st.markdown("---")
    page = st.radio(
        "nav",
        ["🏠  Dashboard", "🔍  Search", "🎯  Matched Jobs", "🚀  Apply", "⚙️  Settings"],
        label_visibility="collapsed",
    )
    st.markdown("---")
    st.markdown(f"**Total jobs:** &nbsp;`{stats['total']}`", unsafe_allow_html=True)
    st.markdown(f"**Matched:** &nbsp;&nbsp;&nbsp;`{stats['matched']}`", unsafe_allow_html=True)
    st.markdown(f"**Applied:** &nbsp;&nbsp;&nbsp;`{stats['applied']}`", unsafe_allow_html=True)
    st.markdown(f"**Avg score:** &nbsp;`{stats['avg_score']}%`", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

if "Dashboard" in page:
    st.markdown('<div class="page-title">🏠 Dashboard</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-sub">Your automated job application pipeline at a glance.</div>', unsafe_allow_html=True)

    c1, c2, c3, c4, c5 = st.columns(5)
    stat_card(c1, "Total Found",  stats["total"],           "#60a5fa")
    stat_card(c2, "Matched ≥70%", stats["matched"],         "#34d399")
    stat_card(c3, "Applied",      stats["applied"],         "#a78bfa")
    stat_card(c4, "Skipped",      stats["skipped"],         "#94a3b8")
    stat_card(c5, "Avg Score",    f"{stats['avg_score']}%", "#fb923c")

    st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
    st.markdown("### ⚡ Quick Actions")

    col1, col2, col3, col4 = st.columns(4)

    if col1.button("🔍 Search Jobs",   use_container_width=True):
        launch_task([PYTHON, "main.py", "search"], "task_search")
    if col2.button("🎯 Match Jobs",    use_container_width=True):
        launch_task([PYTHON, "main.py", "match"],  "task_match")
    if col3.button("🚀 Full Pipeline", use_container_width=True, type="primary"):
        launch_task([PYTHON, "main.py", "run"],    "task_run")
    if col4.button("🔄 Refresh Stats", use_container_width=True):
        st.rerun()

    # Show whichever task panel is active
    for key, label in [("task_run", "Full Pipeline"), ("task_search", "Search Jobs"), ("task_match", "Match Jobs")]:
        render_task_panel(key, label)

    # Recent matches preview
    st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
    st.markdown("### 🎯 Recent Matches")

    matched = database.get_jobs_by_status("matched")[:5]
    if matched:
        for job in matched:
            score   = job.get("match_score") or 0
            title   = (job.get("title")   or "Unknown")[:60]
            company = (job.get("company") or "Unknown")[:30]
            url     = job.get("url") or ""
            col1, col2, col3 = st.columns([5, 1, 1])
            col1.markdown(f"**{title}** &nbsp;·&nbsp; *{company}*", unsafe_allow_html=True)
            col2.markdown(
                f'<span style="color:{score_color(score)};font-weight:700">{score:.0f}%</span>',
                unsafe_allow_html=True,
            )
            if url:
                col3.link_button("Open →", url, use_container_width=True)
    else:
        st.info("No matched jobs yet. Run **Search** then **Match**.")


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

elif "Search" in page:
    st.markdown('<div class="page-title">🔍 Search Jobs</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-sub">Search free job boards for new listings matching your profile.</div>', unsafe_allow_html=True)

    cfg = load_config()
    queries = cfg.get("job_titles", [])

    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown("**Active search queries:**")
        tags_html = " ".join(f'<span class="skill-tag">{q}</span>' for q in queries)
        st.markdown(tags_html, unsafe_allow_html=True)
    with col2:
        remote_only = st.checkbox("Remote only", value=cfg.get("remote_only", False))

    st.markdown('<hr class="section-divider">', unsafe_allow_html=True)

    sources = [
        "RemoteOK", "Arbeitnow", "The Muse", "HN Who's Hiring",
        "Remotive", "Jobicy", "Working Nomads", "Himalayas",
    ]
    cols = st.columns(4)
    for i, src in enumerate(sources):
        cols[i % 4].markdown(
            f'<div style="background:#1e293b;border:1px solid #334155;border-radius:8px;'
            f'padding:8px 12px;text-align:center;font-size:0.8rem;color:#94a3b8;margin-bottom:8px">'
            f'✓ {src}</div>',
            unsafe_allow_html=True,
        )

    st.markdown('<hr class="section-divider">', unsafe_allow_html=True)

    if st.button("🔍  Start Search", type="primary"):
        launch_task([PYTHON, "main.py", "search"], "task_search")

    render_task_panel("task_search", "Search Jobs")

    found = database.get_jobs_by_status("found")
    if found:
        st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
        st.markdown(f"### Unscored Jobs ({len(found)})")
        st.caption("These jobs were found but not yet matched. Run **Match Jobs** from the Dashboard.")
        import pandas as pd
        df = pd.DataFrame([{
            "Title":    (j["title"]   or "")[:50],
            "Company":  (j["company"] or "")[:25],
            "Location": (j["location"] or "")[:20],
            "Source":   j["source"],
        } for j in found[:100]])
        st.dataframe(df, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# Matched Jobs
# ---------------------------------------------------------------------------

elif "Matched" in page:
    st.markdown('<div class="page-title">🎯 Matched Jobs</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-sub">Jobs scoring ≥70% against your profile — grouped by source site.</div>', unsafe_allow_html=True)

    matched = database.get_jobs_by_status("matched")

    if not matched:
        st.warning("No matched jobs yet. Run **Search** then **Match Jobs** from the Dashboard.")
    else:
        # Filters
        col1, col2 = st.columns(2)
        with col1:
            min_score = st.slider("Min score", 70, 100, 70)
        with col2:
            sort_by = st.selectbox("Sort by", ["Score (high→low)", "Company A→Z"])

        filtered = [j for j in matched if (j.get("match_score") or 0) >= min_score]
        if "Company" in sort_by:
            filtered.sort(key=lambda j: (j.get("company") or "").lower())
        else:
            filtered.sort(key=lambda j: j.get("match_score") or 0, reverse=True)

        # Group by source
        from collections import defaultdict
        grouped: dict[str, list] = defaultdict(list)
        for job in filtered:
            grouped[job.get("source") or "Unknown"].append(job)

        # Source icons
        SOURCE_ICONS = {
            "RemoteOK":      "🟢",
            "Arbeitnow":     "🔵",
            "TheMuse":       "🟣",
            "HN Hiring":     "🟠",
            "Remotive":      "🔴",
            "Jobicy":        "🟡",
            "WorkingNomads": "🌍",
            "Himalayas":     "🏔️",
        }

        st.markdown(
            f'<div class="page-sub">Showing <b>{len(filtered)}</b> jobs across <b>{len(grouped)}</b> sources</div>',
            unsafe_allow_html=True,
        )

        def render_job_card(job, page_key="matched"):
            score    = job.get("match_score") or 0
            title    = job.get("title")   or "Unknown"
            company  = job.get("company") or "Unknown"
            location = job.get("location") or ""
            url      = job.get("url") or ""
            salary   = job.get("salary") or ""
            desc     = (job.get("description") or "")[:400]

            matched_skills: list[str] = []
            try:
                rd = json.loads(job.get("match_reason") or "{}")
                matched_skills = rd.get("matched", [])
            except Exception:
                pass

            sc = score_color(score)
            skills_html = " ".join(
                f'<span class="skill-tag">{s}</span>' for s in matched_skills[:10]
            )
            salary_html = (
                f'<span style="color:#34d399;font-size:0.82rem">💰 {salary}</span>&nbsp;&nbsp;'
                if salary else ""
            )

            st.markdown(f"""
            <div class="job-card">
                <div class="job-title">{title}</div>
                <div class="job-meta">🏢 {company}&nbsp;&nbsp;📍 {location}</div>
                <span class="score-badge" style="background:{sc}22;color:{sc};border:1px solid {sc}44">
                    {score:.0f}% match
                </span>
                {salary_html}
                <div style="margin-top:10px">{skills_html}</div>
                <div class="desc">{desc}{"..." if len(job.get("description") or "") > 400 else ""}</div>
            </div>
            """, unsafe_allow_html=True)

            btn1, btn2, _ = st.columns([1, 1, 5])
            if url:
                btn1.link_button("🌐 Open Job", url, use_container_width=True)
            if btn2.button("✕ Skip", key=f"skip_{page_key}_{job['id']}", use_container_width=True):
                database.set_match(job["id"], 0, json.dumps({"reason": "Manually skipped"}))
                st.rerun()
            st.markdown("")

        # Render each source as a collapsible section
        for source, jobs in sorted(grouped.items(), key=lambda x: -len(x[1])):
            icon = SOURCE_ICONS.get(source, "🔷")
            with st.expander(f"{icon} {source}  —  {len(jobs)} job{'s' if len(jobs) != 1 else ''}", expanded=True):
                for job in jobs:
                    render_job_card(job, page_key=source)


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------

elif "Apply" in page:
    st.markdown('<div class="page-title">🚀 Apply to Jobs</div>', unsafe_allow_html=True)

    matched = database.get_jobs_by_status("matched")
    applied_count = stats.get("applied", 0)
    remaining_count = len(matched)
    total_pipeline = applied_count + remaining_count

    st.markdown(
        f'<div class="page-sub">📊 {applied_count} applied · {remaining_count} remaining</div>',
        unsafe_allow_html=True,
    )

    if total_pipeline > 0:
        st.progress(applied_count / total_pipeline)

    if not matched:
        st.warning("No matched jobs. Run **Search** then **Match Jobs** first.")
    else:
        for job in matched:
            job_id   = job["id"]
            score    = job.get("match_score") or 0
            title    = job.get("title")   or "Unknown"
            company  = job.get("company") or "Unknown"
            location = job.get("location") or ""
            url      = job.get("url") or ""
            salary   = job.get("salary") or ""
            desc     = (job.get("description") or "")[:350]

            matched_skills: list[str] = []
            try:
                rd = json.loads(job.get("match_reason") or "{}")
                matched_skills = rd.get("matched", [])
            except Exception:
                pass

            sc = score_color(score)
            skills_html = " ".join(
                f'<span class="skill-tag">{s}</span>' for s in matched_skills[:10]
            )
            salary_html = (
                f'<span style="color:#34d399;font-size:0.82rem">💰 {salary}</span>&nbsp;&nbsp;'
                if salary else ""
            )

            st.markdown(f"""
            <div class="job-card">
                <div class="job-title">{title}</div>
                <div class="job-meta">🏢 {company}&nbsp;&nbsp;📍 {location}</div>
                <span class="score-badge" style="background:{sc}22;color:{sc};border:1px solid {sc}44">
                    {score:.0f}% match
                </span>
                {salary_html}
                <div style="margin-top:10px">{skills_html}</div>
                <div class="desc">{desc}{"..." if len(job.get("description") or "") > 350 else ""}</div>
            </div>
            """, unsafe_allow_html=True)

            btn_open, btn_applied, btn_later, btn_skip = st.columns(4)

            if url:
                btn_open.link_button("🌐 Open Job", url, use_container_width=True)
            else:
                btn_open.button("🌐 Open Job", key=f"open_{job_id}", disabled=True, use_container_width=True)

            if btn_applied.button("✅ Mark as Applied", key=f"applied_{job_id}", use_container_width=True):
                database.set_applied(job_id)
                st.rerun()

            btn_later.button("⏭ Keep for Later", key=f"later_{job_id}", use_container_width=True)

            if btn_skip.button("✕ Not Interested", key=f"skip_{job_id}", use_container_width=True):
                database.set_match(job_id, 0, json.dumps({"reason": "Not interested"}))
                st.rerun()

            st.markdown("")


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

elif "Settings" in page:
    st.markdown('<div class="page-title">⚙️ Settings</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-sub">Configure your job search, profile, and matching preferences.</div>', unsafe_allow_html=True)

    cfg = load_config()

    with st.expander("📄 Resume", expanded=True):
        existing_resume = database.get_resume_content()
        if existing_resume:
            st.caption(f"✅ Resume in system — {len(existing_resume):,} characters detected")
        else:
            st.caption("⚠️ No resume uploaded yet.")

        uploaded = st.file_uploader(
            "Upload your resume to auto-fill your profile and improve matching",
            type=["pdf", "docx"],
            label_visibility="collapsed",
        )

        if uploaded is not None:
            import tempfile
            import resume_parser as rp
            suffix = Path(uploaded.name).suffix.lower()
            resume_path = BOT_DIR / f"uploaded_resume{suffix}"
            resume_path.write_bytes(uploaded.getvalue())

            text = rp.extract_text(resume_path)
            if text and not text.startswith("["):
                database.save_resume(str(resume_path), text)
                profile_data = rp.extract_resume_profile(text)
                st.session_state["auto_profile"] = profile_data

                st.success(f"✅ Parsed **{uploaded.name}** — {len(text):,} characters")

                if profile_data.get("skills"):
                    st.markdown("**Detected skills:**")
                    skills_html = " ".join(
                        f'<span class="skill-tag">{s}</span>'
                        for s in profile_data["skills"]
                    )
                    st.markdown(skills_html, unsafe_allow_html=True)

                col_a, col_b = st.columns(2)
                if col_a.button("⬇️ Auto-fill Profile from Resume", type="primary"):
                    st.rerun()
            else:
                st.error(f"Could not parse {uploaded.name}. Try a different file.")

    with st.expander("🔍 Job Search Queries", expanded=True):
        titles_raw = st.text_area(
            "One search query per line",
            value="\n".join(cfg.get("job_titles", [])),
            height=320,
            label_visibility="collapsed",
        )
        st.caption(f"{len([t for t in titles_raw.splitlines() if t.strip()])} queries active")

    with st.expander("🎯 Matching Settings", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            threshold = st.slider("Match threshold (%)", 50, 95, int(cfg.get("match_threshold", 70)))
        with col2:
            remote_only = st.checkbox("Remote jobs only", value=cfg.get("remote_only", False))

    with st.expander("👤 Your Profile", expanded=True):
        auto_profile = st.session_state.get("auto_profile", {})
        profile = {**cfg.get("profile", {}), **auto_profile}  # session_state takes priority
        col1, col2 = st.columns(2)
        with col1:
            name     = st.text_input("Full Name",  value=profile.get("name", ""))
            email    = st.text_input("Email",      value=profile.get("email", ""))
            phone    = st.text_input("Phone",      value=profile.get("phone", ""))
        with col2:
            city     = st.text_input("City",       value=profile.get("city", ""))
            website  = st.text_input("Website",    value=profile.get("website", ""))
            linkedin = st.text_input("LinkedIn handle", value=profile.get("linkedin_handle", ""))
        summary = st.text_area("Professional Summary", value=profile.get("summary", ""), height=120)

    st.markdown('<hr class="section-divider">', unsafe_allow_html=True)

    if st.button("💾  Save Settings", type="primary"):
        cfg["job_titles"]      = [t.strip() for t in titles_raw.splitlines() if t.strip()]
        cfg["match_threshold"] = threshold
        cfg["remote_only"]     = remote_only
        cfg["profile"] = {
            "name": name, "email": email, "phone": phone,
            "city": city, "website": website,
            "linkedin_handle": linkedin, "summary": summary,
        }
        save_config(cfg)
        st.success("✅ Settings saved!")
