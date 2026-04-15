"""
Job Bot — Streamlit Web UI
Run with: streamlit run app.py
"""
import json
import subprocess
import sys
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
# Helpers
# ---------------------------------------------------------------------------

def load_config() -> dict:
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    return {}


def save_config(cfg: dict):
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")


def run_command(cmd: list[str]):
    """Run a bot command and stream output into a Streamlit container."""
    with st.spinner("Running..."):
        output_box = st.empty()
        lines = []
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
            lines.append(line.rstrip())
            output_box.code("\n".join(lines[-60:]), language="bash")
        proc.wait()
        if proc.returncode == 0:
            st.success("Done!")
        else:
            st.error(f"Finished with exit code {proc.returncode}")


def stat_card(col, label, value, color):
    col.markdown(
        f"""
        <div style="background:{color};padding:18px 20px;border-radius:12px;text-align:center">
            <div style="font-size:2rem;font-weight:700;color:white">{value}</div>
            <div style="font-size:0.85rem;color:rgba(255,255,255,0.85);margin-top:4px">{label}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Sidebar navigation
# ---------------------------------------------------------------------------

database.init_db()
stats = database.get_stats()

with st.sidebar:
    st.markdown("## 🤖 Job Bot")
    st.markdown("---")
    page = st.radio(
        "Navigation",
        ["Dashboard", "Search Jobs", "Matched Jobs", "Apply", "Settings"],
        label_visibility="collapsed",
    )
    st.markdown("---")
    st.markdown(f"**Total jobs:** {stats['total']}")
    st.markdown(f"**Matched:** {stats['matched']}")
    st.markdown(f"**Applied:** {stats['applied']}")


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

if page == "Dashboard":
    st.title("🤖 Job Bot Dashboard")
    st.markdown("Automated job search, matching, and application pipeline.")
    st.markdown("---")

    # Stat cards
    c1, c2, c3, c4, c5 = st.columns(5)
    stat_card(c1, "Total Found",   stats["total"],   "#4A90D9")
    stat_card(c2, "Matched ≥70%",  stats["matched"], "#27AE60")
    stat_card(c3, "Applied",       stats["applied"], "#8E44AD")
    stat_card(c4, "Skipped",       stats["skipped"], "#7F8C8D")
    stat_card(c5, "Avg Score",     f"{stats['avg_score']}%", "#E67E22")

    st.markdown("---")
    st.subheader("⚡ Quick Actions")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        if st.button("🔍 Search Jobs", use_container_width=True):
            st.markdown("### Search Output")
            run_command([PYTHON, "main.py", "search"])
            st.rerun()

    with col2:
        if st.button("🎯 Match Jobs", use_container_width=True):
            st.markdown("### Match Output")
            run_command([PYTHON, "main.py", "match"])
            st.rerun()

    with col3:
        if st.button("🚀 Full Pipeline", use_container_width=True, type="primary"):
            st.markdown("### Pipeline Output")
            run_command([PYTHON, "main.py", "run"])
            st.rerun()

    with col4:
        if st.button("📧 Apply to Matched", use_container_width=True):
            st.switch_page = "Apply"
            st.info("Go to the **Apply** tab to review and apply to matched jobs.")

    st.markdown("---")
    st.subheader("📊 Status Breakdown")

    import pandas as pd
    breakdown = {
        "Status":  ["Found", "Matched", "Skipped", "Applied", "Failed"],
        "Count":   [stats["found"], stats["matched"], stats["skipped"], stats["applied"], stats["failed"]],
    }
    df = pd.DataFrame(breakdown)
    st.bar_chart(df.set_index("Status"))


# ---------------------------------------------------------------------------
# Search Jobs
# ---------------------------------------------------------------------------

elif page == "Search Jobs":
    st.title("🔍 Search Jobs")
    cfg = load_config()

    st.markdown("Search all job boards for new listings matching your profile.")

    queries = cfg.get("job_titles", [])
    st.markdown(f"**Searching for:** {', '.join(queries)}")
    st.markdown(f"**Sources:** RemoteOK, Arbeitnow, The Muse, HN Hiring, Remotive, Jobicy, We Work Remotely, Working Nomads, Himalayas")

    col1, col2 = st.columns([1, 3])
    with col1:
        remote_only = st.checkbox("Remote jobs only", value=cfg.get("remote_only", False))

    if st.button("🔍 Start Search", type="primary", use_container_width=False):
        run_command([PYTHON, "main.py", "search"])
        st.rerun()

    st.markdown("---")
    st.subheader("Recently Found Jobs")

    all_jobs = database.get_jobs_by_status("found")
    if all_jobs:
        import pandas as pd
        df = pd.DataFrame([{
            "Title":    (j["title"] or "")[:50],
            "Company":  (j["company"] or "")[:25],
            "Location": (j["location"] or "")[:20],
            "Source":   j["source"],
            "URL":      j["url"] or "",
        } for j in all_jobs[:50]])
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("No unscored jobs — run **Match** to score them or **Search** to find new ones.")


# ---------------------------------------------------------------------------
# Matched Jobs
# ---------------------------------------------------------------------------

elif page == "Matched Jobs":
    st.title("🎯 Matched Jobs")
    st.markdown("Jobs scoring ≥70% against your profile — ready to apply.")

    matched = database.get_jobs_by_status("matched")

    if not matched:
        st.warning("No matched jobs yet. Run **Search** then **Match** first.")
    else:
        # Filters
        col1, col2 = st.columns(2)
        with col1:
            source_options = ["All"] + sorted(set(j["source"] for j in matched))
            source_filter = st.selectbox("Filter by source", source_options)
        with col2:
            min_score = st.slider("Minimum score", 70, 100, 70)

        filtered = [
            j for j in matched
            if (source_filter == "All" or j["source"] == source_filter)
            and (j["match_score"] or 0) >= min_score
        ]

        st.markdown(f"**{len(filtered)} jobs** match your filters")
        st.markdown("---")

        for job in filtered:
            score = job.get("match_score") or 0
            title = (job.get("title") or "Unknown")[:60]
            company = job.get("company") or "Unknown"
            location = job.get("location") or "Unknown"
            source = job.get("source") or ""
            url = job.get("url") or ""
            salary = job.get("salary") or ""

            # Parse matched skills
            matched_skills = []
            try:
                reason_data = json.loads(job.get("match_reason") or "{}")
                matched_skills = reason_data.get("matched", [])
            except Exception:
                pass

            score_color = "#27AE60" if score >= 80 else "#E67E22" if score >= 70 else "#E74C3C"

            with st.expander(f"**{title}** @ {company}  —  Score: {score:.0f}%", expanded=False):
                col1, col2, col3 = st.columns(3)
                col1.metric("Score", f"{score:.0f}%")
                col2.metric("Location", location[:20])
                col3.metric("Source", source)

                if salary:
                    st.markdown(f"💰 **Salary:** {salary}")

                if matched_skills:
                    st.markdown(f"✅ **Matched skills:** {', '.join(matched_skills[:10])}")

                desc = (job.get("description") or "")[:800]
                if desc:
                    st.markdown("**Description preview:**")
                    st.markdown(f"> {desc}...")

                col_a, col_b = st.columns(2)
                with col_a:
                    if url:
                        st.link_button("🌐 Open Job Posting", url, use_container_width=True)
                with col_b:
                    if st.button(f"Skip this job", key=f"skip_{job['id']}"):
                        database.set_match(job["id"], score, job.get("match_reason") or "")
                        st.rerun()


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------

elif page == "Apply":
    st.title("🚀 Apply to Jobs")

    matched = database.get_jobs_by_status("matched")

    if not matched:
        st.warning("No matched jobs. Run **Search** then **Match** first.")
    else:
        st.markdown(f"**{len(matched)} matched jobs** ready to apply to.")
        st.info("The bot will open each job, fill the form automatically, and ask for your confirmation before submitting.")

        col1, col2 = st.columns(2)
        with col1:
            max_apply = st.number_input("Max applications per run", 1, 50, 10)

        st.markdown("---")
        st.subheader("Jobs in queue")

        for job in matched:
            score = job.get("match_score") or 0
            title = (job.get("title") or "Unknown")[:55]
            company = job.get("company") or "Unknown"
            url = job.get("url") or ""

            col1, col2, col3 = st.columns([4, 1, 1])
            col1.markdown(f"**{title}** @ {company}")
            col2.markdown(f"**{score:.0f}%**")
            if url:
                col3.link_button("View", url)

        st.markdown("---")
        st.warning("⚠️ The apply command runs in your terminal (requires browser automation). Click below to launch it.")

        if st.button("🚀 Start Applying (opens terminal)", type="primary"):
            run_command([PYTHON, "main.py", "apply", "--max", str(int(max_apply))])


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

elif page == "Settings":
    st.title("⚙️ Settings")
    cfg = load_config()

    st.subheader("Job Search Queries")
    titles_raw = st.text_area(
        "One search query per line",
        value="\n".join(cfg.get("job_titles", [])),
        height=300,
    )

    st.subheader("Matching")
    threshold = st.slider("Match threshold (%)", 50, 95, int(cfg.get("match_threshold", 70)))
    remote_only = st.checkbox("Remote jobs only", value=cfg.get("remote_only", False))

    st.subheader("Your Profile")
    profile = cfg.get("profile", {})
    col1, col2 = st.columns(2)
    with col1:
        name    = st.text_input("Name",   value=profile.get("name", ""))
        email   = st.text_input("Email",  value=profile.get("email", ""))
        phone   = st.text_input("Phone",  value=profile.get("phone", ""))
    with col2:
        city    = st.text_input("City",    value=profile.get("city", ""))
        website = st.text_input("Website", value=profile.get("website", ""))
        linkedin = st.text_input("LinkedIn handle", value=profile.get("linkedin_handle", ""))

    summary = st.text_area("Summary", value=profile.get("summary", ""), height=120)

    if st.button("💾 Save Settings", type="primary"):
        cfg["job_titles"]      = [t.strip() for t in titles_raw.splitlines() if t.strip()]
        cfg["match_threshold"] = threshold
        cfg["remote_only"]     = remote_only
        cfg["profile"] = {
            "name": name, "email": email, "phone": phone,
            "city": city, "website": website,
            "linkedin_handle": linkedin, "summary": summary,
        }
        save_config(cfg)
        st.success("Settings saved!")
