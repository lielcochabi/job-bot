"""
Job Bot — Streamlit Web UI
Run with: streamlit run app.py
"""
import json
import subprocess
import sys
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
    /* ── General ── */
    html, body, [class*="css"] { font-family: 'Inter', 'Segoe UI', sans-serif; }

    /* Remove default Streamlit top padding */
    .block-container { padding-top: 1.5rem !important; padding-bottom: 2rem !important; }

    /* ── Sidebar ── */
    [data-testid="stSidebar"] {
        background: #0f172a;
        padding: 1.5rem 1rem;
    }
    [data-testid="stSidebar"] * { color: #e2e8f0 !important; }
    [data-testid="stSidebar"] .stRadio label {
        font-size: 1rem;
        padding: 0.4rem 0;
    }
    [data-testid="stSidebar"] hr { border-color: #334155; }

    /* ── Stat card ── */
    .stat-card {
        background: linear-gradient(135deg, #1e293b, #0f172a);
        border: 1px solid #334155;
        border-radius: 14px;
        padding: 22px 16px;
        text-align: center;
        width: 100%;
        box-sizing: border-box;
    }
    .stat-card .value {
        font-size: 2.2rem;
        font-weight: 800;
        line-height: 1.1;
    }
    .stat-card .label {
        font-size: 0.78rem;
        letter-spacing: 0.05em;
        text-transform: uppercase;
        margin-top: 6px;
        opacity: 0.7;
        color: #94a3b8;
    }

    /* ── Job card ── */
    .job-card {
        background: #1e293b;
        border: 1px solid #334155;
        border-radius: 14px;
        padding: 20px 24px;
        margin-bottom: 14px;
        width: 100%;
        box-sizing: border-box;
    }
    .job-card:hover { border-color: #6366f1; }
    .job-card .job-title {
        font-size: 1.05rem;
        font-weight: 700;
        color: #e2e8f0;
        margin-bottom: 4px;
        white-space: normal;
        word-break: break-word;
    }
    .job-card .job-meta {
        font-size: 0.82rem;
        color: #94a3b8;
        margin-bottom: 10px;
    }
    .job-card .score-badge {
        display: inline-block;
        padding: 3px 12px;
        border-radius: 99px;
        font-size: 0.8rem;
        font-weight: 700;
        margin-right: 8px;
    }
    .job-card .skill-tag {
        display: inline-block;
        background: #1e3a5f;
        color: #93c5fd;
        border-radius: 6px;
        padding: 2px 9px;
        font-size: 0.75rem;
        margin: 2px 2px 0 0;
    }
    .job-card .desc {
        font-size: 0.82rem;
        color: #94a3b8;
        margin-top: 10px;
        line-height: 1.55;
        white-space: normal;
        word-break: break-word;
    }

    /* ── Buttons ── */
    .stButton > button {
        border-radius: 10px !important;
        font-weight: 600 !important;
        padding: 0.5rem 1.2rem !important;
        transition: all 0.2s !important;
    }
    .stButton > button:hover { transform: translateY(-1px); }

    /* ── Action bar ── */
    .action-bar {
        display: flex;
        gap: 12px;
        flex-wrap: wrap;
        margin-bottom: 1.5rem;
    }

    /* ── Page title ── */
    .page-title {
        font-size: 1.8rem;
        font-weight: 800;
        color: #e2e8f0;
        margin-bottom: 0.2rem;
    }
    .page-sub {
        font-size: 0.9rem;
        color: #64748b;
        margin-bottom: 1.5rem;
    }

    /* ── Log box ── */
    .log-box {
        background: #0f172a;
        border: 1px solid #334155;
        border-radius: 10px;
        padding: 14px 16px;
        font-family: 'Courier New', monospace;
        font-size: 0.8rem;
        color: #86efac;
        max-height: 380px;
        overflow-y: auto;
        white-space: pre-wrap;
        word-break: break-word;
    }

    /* ── Divider ── */
    .section-divider {
        border: none;
        border-top: 1px solid #334155;
        margin: 1.5rem 0;
    }

    /* ── Hide default Streamlit elements ── */
    #MainMenu { visibility: hidden; }
    footer { visibility: hidden; }
    header { visibility: hidden; }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_config() -> dict:
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    return {}


def save_config(cfg: dict):
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")


def run_command(cmd: list[str]):
    output_box = st.empty()
    lines: list[str] = []
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(BOT_DIR),
    )
    for line in proc.stdout:
        clean = line.rstrip()
        if clean:
            lines.append(clean)
        html_log = "\n".join(lines[-80:]).replace("<", "&lt;").replace(">", "&gt;")
        output_box.markdown(f'<div class="log-box">{html_log}</div>', unsafe_allow_html=True)
    proc.wait()
    return proc.returncode


def score_color(score: float) -> str:
    if score >= 85:
        return "#22c55e"
    if score >= 75:
        return "#f59e0b"
    return "#6366f1"


def stat_card(col, label: str, value, color: str, icon: str = ""):
    col.markdown(
        f"""
        <div class="stat-card">
            <div class="value" style="color:{color}">{icon} {value}</div>
            <div class="label">{label}</div>
        </div>
        """,
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
    stat_card(c1, "Total Found",  stats["total"],           "#60a5fa", "")
    stat_card(c2, "Matched ≥70%", stats["matched"],         "#34d399", "")
    stat_card(c3, "Applied",      stats["applied"],         "#a78bfa", "")
    stat_card(c4, "Skipped",      stats["skipped"],         "#94a3b8", "")
    stat_card(c5, "Avg Score",    f"{stats['avg_score']}%", "#fb923c", "")

    st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
    st.markdown("### ⚡ Quick Actions")

    col1, col2, col3, col4 = st.columns(4)
    search_clicked  = col1.button("🔍 Search Jobs",       use_container_width=True)
    match_clicked   = col2.button("🎯 Match Jobs",        use_container_width=True)
    pipeline_clicked= col3.button("🚀 Full Pipeline",     use_container_width=True, type="primary")
    status_clicked  = col4.button("🔄 Refresh Stats",     use_container_width=True)

    if search_clicked:
        st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
        st.markdown("### 🔍 Search Output")
        rc = run_command([PYTHON, "main.py", "search"])
        if rc == 0: st.success("Search complete!")
        st.rerun()

    if match_clicked:
        st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
        st.markdown("### 🎯 Match Output")
        rc = run_command([PYTHON, "main.py", "match"])
        if rc == 0: st.success("Matching complete!")
        st.rerun()

    if pipeline_clicked:
        st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
        st.markdown("### 🚀 Full Pipeline Output")
        rc = run_command([PYTHON, "main.py", "run"])
        if rc == 0: st.success("Pipeline complete!")
        st.rerun()

    if status_clicked:
        st.rerun()

    # Recent matched jobs preview
    st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
    st.markdown("### 🎯 Recent Matches")

    matched = database.get_jobs_by_status("matched")[:5]
    if matched:
        for job in matched:
            score  = job.get("match_score") or 0
            title  = (job.get("title")   or "Unknown")[:60]
            company= (job.get("company") or "Unknown")[:30]
            source = job.get("source") or ""
            url    = job.get("url") or ""
            col1, col2, col3 = st.columns([5, 1, 1])
            col1.markdown(f"**{title}** &nbsp;·&nbsp; *{company}*", unsafe_allow_html=True)
            col2.markdown(f"<span style='color:{score_color(score)};font-weight:700'>{score:.0f}%</span>", unsafe_allow_html=True)
            if url:
                col3.link_button("Open →", url, use_container_width=True)
    else:
        st.info("No matched jobs yet. Run **Search** then **Match**.")


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

elif "Search" in page:
    st.markdown('<div class="page-title">🔍 Search Jobs</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-sub">Search all 10 job boards for new listings matching your profile.</div>', unsafe_allow_html=True)

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
        "Remotive", "Jobicy", "We Work Remotely", "Working Nomads", "Himalayas"
    ]
    cols = st.columns(5)
    for i, src in enumerate(sources):
        cols[i % 5].markdown(
            f'<div style="background:#1e293b;border:1px solid #334155;border-radius:8px;'
            f'padding:8px 12px;text-align:center;font-size:0.8rem;color:#94a3b8;margin-bottom:8px">'
            f'✓ {src}</div>',
            unsafe_allow_html=True
        )

    st.markdown('<hr class="section-divider">', unsafe_allow_html=True)

    if st.button("🔍  Start Search", type="primary"):
        st.markdown("### Live Output")
        rc = run_command([PYTHON, "main.py", "search"])
        if rc == 0:
            st.success("Done! Go to **Matched Jobs** after running Match.")
        st.rerun()

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
    st.markdown('<div class="page-sub">Jobs scoring ≥70% against your profile — ready to apply.</div>', unsafe_allow_html=True)

    matched = database.get_jobs_by_status("matched")

    if not matched:
        st.warning("No matched jobs yet. Run **Search** then **Match Jobs** from the Dashboard.")
    else:
        col1, col2, col3 = st.columns(3)
        with col1:
            source_options = ["All"] + sorted(set(j["source"] for j in matched))
            source_filter = st.selectbox("Source", source_options)
        with col2:
            min_score = st.slider("Min score", 70, 100, 70)
        with col3:
            sort_by = st.selectbox("Sort by", ["Score (high→low)", "Company A→Z"])

        filtered = [
            j for j in matched
            if (source_filter == "All" or j["source"] == source_filter)
            and (j.get("match_score") or 0) >= min_score
        ]
        if "Company" in sort_by:
            filtered.sort(key=lambda j: (j.get("company") or "").lower())
        else:
            filtered.sort(key=lambda j: j.get("match_score") or 0, reverse=True)

        st.markdown(f'<div class="page-sub">Showing {len(filtered)} of {len(matched)} matched jobs</div>', unsafe_allow_html=True)

        for job in filtered:
            score   = job.get("match_score") or 0
            title   = (job.get("title")   or "Unknown")
            company = (job.get("company") or "Unknown")
            location= (job.get("location") or "")
            source  = job.get("source") or ""
            url     = job.get("url") or ""
            salary  = job.get("salary") or ""
            desc    = (job.get("description") or "")[:500]

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
            salary_html = f'<span style="color:#34d399;font-size:0.82rem">💰 {salary}</span>&nbsp;&nbsp;' if salary else ""

            card_html = f"""
            <div class="job-card">
                <div class="job-title">{title}</div>
                <div class="job-meta">
                    🏢 {company}&nbsp;&nbsp;
                    📍 {location}&nbsp;&nbsp;
                    🔗 {source}
                </div>
                <span class="score-badge" style="background:{sc}22;color:{sc};border:1px solid {sc}44">
                    {score:.0f}% match
                </span>
                {salary_html}
                <div style="margin-top:10px">{skills_html}</div>
                <div class="desc">{desc[:400]}{"..." if len(desc)>=400 else ""}</div>
            </div>
            """
            st.markdown(card_html, unsafe_allow_html=True)

            btn_col1, btn_col2, _ = st.columns([1, 1, 5])
            if url:
                btn_col1.link_button("🌐 Open Job", url, use_container_width=True)
            if btn_col2.button("✕ Skip", key=f"skip_{job['id']}", use_container_width=True):
                database.set_match(job["id"], 0, json.dumps({"reason": "Manually skipped by user"}))
                st.rerun()

            st.markdown("")


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------

elif "Apply" in page:
    st.markdown('<div class="page-title">🚀 Apply to Jobs</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-sub">Review matched jobs and submit applications.</div>', unsafe_allow_html=True)

    matched = database.get_jobs_by_status("matched")

    if not matched:
        st.warning("No matched jobs. Run **Search** then **Match Jobs** first.")
    else:
        st.markdown(
            f'<div style="background:#1e293b;border:1px solid #334155;border-radius:12px;'
            f'padding:16px 20px;margin-bottom:1rem">'
            f'<b style="color:#34d399;font-size:1.1rem">✅ {len(matched)} jobs ready to apply to</b><br>'
            f'<span style="color:#94a3b8;font-size:0.85rem">The bot will fill forms automatically and ask for your confirmation before submitting.</span>'
            f'</div>',
            unsafe_allow_html=True
        )

        max_apply = st.number_input("Max applications per run", 1, 50, 10)
        st.markdown('<hr class="section-divider">', unsafe_allow_html=True)

        st.markdown("### Jobs in Queue")
        for job in matched:
            score   = job.get("match_score") or 0
            title   = (job.get("title")   or "Unknown")[:55]
            company = (job.get("company") or "Unknown")[:25]
            location= (job.get("location") or "")[:20]
            url     = job.get("url") or ""
            sc      = score_color(score)

            col1, col2, col3, col4 = st.columns([4, 1, 1, 1])
            col1.markdown(
                f'<div style="padding:6px 0"><b style="color:#e2e8f0">{title}</b>'
                f'<span style="color:#64748b"> · {company}</span><br>'
                f'<span style="color:#475569;font-size:0.8rem">📍 {location}</span></div>',
                unsafe_allow_html=True
            )
            col2.markdown(
                f'<div style="padding-top:8px;font-weight:700;color:{sc}">{score:.0f}%</div>',
                unsafe_allow_html=True
            )
            if url:
                col3.link_button("View", url, use_container_width=True)

        st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
        st.info("💡 The apply process runs in your terminal so you can type **y/n** for each job. Click below to launch it.")

        if st.button("🚀 Start Applying", type="primary", use_container_width=False):
            st.markdown("### Output")
            run_command([PYTHON, "main.py", "apply", "--max", str(int(max_apply))])


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

elif "Settings" in page:
    st.markdown('<div class="page-title">⚙️ Settings</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-sub">Configure your job search, profile, and matching preferences.</div>', unsafe_allow_html=True)

    cfg = load_config()

    # Job queries
    with st.expander("🔍 Job Search Queries", expanded=True):
        titles_raw = st.text_area(
            "One search query per line",
            value="\n".join(cfg.get("job_titles", [])),
            height=320,
            label_visibility="collapsed",
        )
        st.caption(f"{len([t for t in titles_raw.splitlines() if t.strip()])} queries active")

    # Matching
    with st.expander("🎯 Matching Settings", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            threshold = st.slider("Match threshold (%)", 50, 95, int(cfg.get("match_threshold", 70)))
        with col2:
            remote_only = st.checkbox("Remote jobs only", value=cfg.get("remote_only", False))

    # Profile
    with st.expander("👤 Your Profile", expanded=True):
        profile = cfg.get("profile", {})
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
