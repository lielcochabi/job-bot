"""
Job Bot — Streamlit Web UI
Run with: streamlit run app.py
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))

# Load .env then push st.secrets — must happen before any env reads
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env", override=True)
import secrets_manager
secrets_manager.inject_all_into_env()

import auth
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

PYTHON  = str(Path(sys.executable))
BOT_DIR = Path(__file__).parent

# ---------------------------------------------------------------------------
# Global CSS
# ---------------------------------------------------------------------------

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap');

    /* ── Base ── */
    html, body, [class*="css"] {
        font-family: 'Inter', 'Segoe UI', system-ui, sans-serif;
    }
    .stApp {
        background: #080d18;
    }
    .block-container {
        padding-top: 2.5rem !important;
        padding-bottom: 3rem !important;
        max-width: 980px;
    }

    /* ── Sidebar ── */
    [data-testid="stSidebar"] {
        background: #0a0f1a !important;
        border-right: 1px solid #161e2e !important;
        padding: 2rem 1.2rem;
    }
    [data-testid="stSidebar"] * { color: #8b98b0 !important; }
    [data-testid="stSidebar"] hr { border-color: #161e2e !important; margin: 1.2rem 0; }

    /* active nav item */
    [data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) {
        color: #e6edf3 !important;
        background: rgba(79, 142, 247, 0.07) !important;
        border-radius: 6px !important;
        border-left: 2px solid #4f8ef7 !important;
        padding-left: 8px !important;
    }

    /* ── Page header ── */
    .page-title {
        font-size: 1.35rem; font-weight: 600;
        color: #e6edf3; margin-bottom: 0.2rem;
        letter-spacing: -0.025em;
    }
    .page-sub {
        font-size: 0.82rem; color: #3d5070;
        margin-bottom: 2rem; letter-spacing: 0.01em;
    }

    /* ── Section label ── */
    .section-label {
        font-size: 0.68rem; font-weight: 600;
        text-transform: uppercase; letter-spacing: 0.1em;
        color: #2d3d55; margin-bottom: 0.65rem;
    }
    .section-divider {
        border: none; border-top: 1px solid #111827;
        margin: 2rem 0;
    }

    /* ── Summary row ── */
    .summary-row {
        display: flex; gap: 0;
        border: 1px solid #161e2e;
        border-radius: 10px; overflow: hidden;
        margin-bottom: 2.5rem;
        background: #0c1220;
    }
    .summary-item {
        flex: 1; padding: 18px 22px;
        border-right: 1px solid #161e2e;
        transition: background 0.15s;
    }
    .summary-item:last-child { border-right: none; }
    .summary-item:hover { background: #0f1826; }
    .summary-item .num {
        font-size: 1.6rem; font-weight: 600;
        color: #e6edf3; line-height: 1;
        letter-spacing: -0.03em;
    }
    .summary-item .num.accent { color: #4f8ef7; }
    .summary-item .num.green  { color: #34d399; }
    .summary-item .lbl {
        font-size: 0.68rem; color: #3d5070;
        margin-top: 5px; text-transform: uppercase;
        letter-spacing: 0.08em;
    }

    /* ── Job card ── */
    .job-card {
        background: #0c1220;
        border: 1px solid #161e2e;
        border-radius: 10px;
        padding: 18px 22px;
        margin-bottom: 8px;
        box-shadow: 0 1px 4px rgba(0,0,0,0.35);
        transition: border-color 0.15s, box-shadow 0.15s;
    }
    .job-card:hover {
        border-color: #2a3a55;
        box-shadow: 0 4px 16px rgba(0,0,0,0.45);
    }
    .job-card .job-title {
        font-size: 0.95rem; font-weight: 600;
        color: #dde6f0; margin-bottom: 5px;
        letter-spacing: -0.01em;
    }
    .job-card .job-meta {
        font-size: 0.78rem; color: #3d5070;
        margin-bottom: 10px; letter-spacing: 0.01em;
    }
    .score-pill {
        display: inline-block;
        padding: 2px 9px; border-radius: 4px;
        font-size: 0.72rem; font-weight: 600;
        letter-spacing: 0.02em;
    }
    .job-card .desc {
        font-size: 0.78rem; color: #3d5070;
        line-height: 1.65; margin-top: 10px;
    }
    .skill-tag {
        display: inline-block;
        background: #0f1826; color: #4f6a8a;
        border: 1px solid #1a2538;
        border-radius: 4px; padding: 1px 8px;
        font-size: 0.7rem; margin: 2px 2px 0 0;
        letter-spacing: 0.02em;
    }

    /* ── Status badge ── */
    .status-badge {
        display: inline-block; padding: 2px 8px;
        border-radius: 4px; font-size: 0.7rem;
        font-weight: 500; letter-spacing: 0.02em;
    }

    /* ── Buttons ── */
    .stButton > button {
        border-radius: 7px !important;
        font-weight: 500 !important;
        font-size: 0.83rem !important;
        padding: 0.42rem 1.1rem !important;
        border: 1px solid #1e2c42 !important;
        background: #0f1826 !important;
        color: #8b98b0 !important;
        transition: background 0.15s, border-color 0.15s, color 0.15s !important;
        box-shadow: none !important;
    }
    .stButton > button:hover {
        background: #14203a !important;
        border-color: #2a3d5c !important;
        color: #c9d8e8 !important;
    }
    .stButton > button[kind="primary"] {
        background: #1a3a6e !important;
        border-color: #2a52a0 !important;
        color: #a8c4f0 !important;
    }
    .stButton > button[kind="primary"]:hover {
        background: #1e4280 !important;
        border-color: #3a62b0 !important;
        color: #c8daf8 !important;
    }

    /* ── Task output panel ── */
    .task-panel-header {
        display: flex; align-items: center; gap: 8px;
        padding: 11px 16px;
        border-left: 2px solid transparent;
        border-bottom: 1px solid #111827;
        border-radius: 9px 9px 0 0;
        background: #0c1220;
    }
    .task-panel-header.running { border-left-color: #f59e0b; }
    .task-panel-header.done    { border-left-color: #34d399; }
    .task-panel-header.error   { border-left-color: #f87171; }
    .task-panel-body {
        padding: 14px 18px;
        font-family: 'JetBrains Mono', 'Fira Code', 'Courier New', monospace;
        font-size: 0.77rem; max-height: 320px; overflow-y: auto;
        line-height: 1.7; background: #090e1a;
        border: 1px solid #111827; border-top: none;
        border-radius: 0 0 9px 9px;
    }

    @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.25} }
    .running-dot {
        display: inline-block; width: 6px; height: 6px;
        border-radius: 50%; background: #f59e0b;
        animation: pulse 1.6s ease-in-out infinite;
        margin-right: 7px; flex-shrink: 0;
    }

    /* ── Inputs ── */
    [data-testid="stTextInput"] input,
    [data-testid="stTextArea"] textarea {
        background: #0c1220 !important;
        border-color: #161e2e !important;
        color: #c9d8e8 !important;
    }

    /* ── Expanders ── */
    [data-testid="stExpander"] {
        border: 1px solid #161e2e !important;
        border-radius: 9px !important;
        background: #0c1220 !important;
        margin-bottom: 10px !important;
    }

    /* ── Auth card glow ── */
    .auth-wrap {
        max-width: 440px; margin: 56px auto 0 auto;
        background: #0c1220; border: 1px solid #161e2e;
        border-radius: 14px; padding: 40px 36px;
        box-shadow: 0 0 60px rgba(79, 142, 247, 0.06),
                    0 8px 32px rgba(0,0,0,0.5);
    }

    /* ── Hide Streamlit chrome ── */
    #MainMenu, footer, header { visibility: hidden; }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Auth initialisation & cookie check
# ---------------------------------------------------------------------------

auth.init_auth_db()

try:
    from streamlit_cookies_controller import CookieController
    _cookie = CookieController()
    _cookie_available = True
except Exception:
    _cookie = None
    _cookie_available = False


def _do_login(username: str, remember: bool):
    """Set session state and optionally a persistent cookie."""
    token = auth.create_token(username, days=30 if remember else 1)
    st.session_state["username"]   = username
    st.session_state["auth_token"] = token
    if remember and _cookie_available:
        try:
            _cookie.set("job_bot_auth", token, max_age=30 * 24 * 3600)
        except Exception:
            pass


def _do_logout():
    auth.revoke_token(st.session_state.get("auth_token", ""))
    if _cookie_available:
        try:
            _cookie.remove("job_bot_auth")
        except Exception:
            pass
    for k in ["username", "auth_token"]:
        st.session_state.pop(k, None)


# ---------------------------------------------------------------------------
# Google OAuth helpers
# ---------------------------------------------------------------------------

def _google_oauth_url() -> str:
    params = {
        "client_id":     os.environ.get("GOOGLE_CLIENT_ID", ""),
        "redirect_uri":  os.environ.get("APP_URL", "http://localhost:8501"),
        "response_type": "code",
        "scope":         "openid email profile",
        "access_type":   "offline",
        "prompt":        "select_account",
    }
    return "https://accounts.google.com/o/oauth2/auth?" + urllib.parse.urlencode(params)


def _handle_google_callback() -> bool:
    """If the URL has ?code=..., exchange it for user info and log in. Returns True if handled."""
    code = st.query_params.get("code")
    if not code:
        return False

    st.query_params.clear()

    client_id     = os.environ.get("GOOGLE_CLIENT_ID", "")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "")
    redirect_uri  = os.environ.get("APP_URL", "http://localhost:8501")

    try:
        import httpx
        token_resp = httpx.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code":          code,
                "client_id":     client_id,
                "client_secret": client_secret,
                "redirect_uri":  redirect_uri,
                "grant_type":    "authorization_code",
            },
            timeout=10,
        )
        token_data   = token_resp.json()
        access_token = token_data.get("access_token")
        if not access_token:
            st.error("Google login failed — no access token received.")
            return True

        user_resp = httpx.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        info  = user_resp.json()
        email = info.get("email", "")
        name  = info.get("name", "")

        if not email:
            st.error("Could not retrieve your email from Google.")
            return True

        ok, result = auth.google_login(email, name)
        if ok:
            _do_login(result, remember=True)
            st.rerun()
        else:
            st.error(f"Login failed: {result}")
    except Exception as exc:
        st.error(f"Google login error: {exc}")

    return True


# Auto-login from cookie (runs once per session)
if "username" not in st.session_state and _cookie_available:
    try:
        token = _cookie.get("job_bot_auth")
        if token:
            uname = auth.validate_token(token)
            if uname:
                st.session_state["username"]   = uname
                st.session_state["auth_token"] = token
    except Exception:
        pass

# Handle Google OAuth redirect callback
if "username" not in st.session_state:
    _handle_google_callback()


# ---------------------------------------------------------------------------
# Auth page (shown when not logged in)
# ---------------------------------------------------------------------------

def show_auth_page():
    st.markdown("""
    <div class="auth-wrap">
        <div style="font-size:1.3rem;font-weight:600;color:#e6edf3;
                    text-align:center;margin-bottom:0.25rem;letter-spacing:-0.025em">
            Job Bot
        </div>
        <div style="font-size:0.8rem;color:#3d5070;text-align:center;
                    margin-bottom:2rem;letter-spacing:0.01em">
            Automated job search assistant
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Centre the form using spacer columns
    _, mid, _ = st.columns([1, 1.6, 1])
    with mid:
        # Google sign-in (only shown if credentials are configured)
        if os.environ.get("GOOGLE_CLIENT_ID"):
            st.link_button(
                "Sign in with Google",
                _google_oauth_url(),
                use_container_width=True,
            )
            st.markdown(
                '<div style="text-align:center;color:#475569;font-size:0.8rem;margin:8px 0">or</div>',
                unsafe_allow_html=True,
            )

        tab_login, tab_signup = st.tabs(["Log In", "Sign Up"])

        with tab_login:
            lu  = st.text_input("Username", key="li_user", placeholder="your username")
            lp  = st.text_input("Password", type="password", key="li_pass", placeholder="••••••••")
            rem = st.checkbox("Remember me for 30 days", value=True, key="li_rem")
            if st.button("Log In", type="primary", use_container_width=True, key="li_btn"):
                if lu and lp:
                    ok, result = auth.login(lu, lp)
                    if ok:
                        _do_login(result, rem)
                        st.rerun()
                    else:
                        st.error(result)
                else:
                    st.warning("Please enter your username and password.")

        with tab_signup:
            su = st.text_input("Username",         key="su_user",  placeholder="choose a username")
            se = st.text_input("Email",            key="su_email", placeholder="you@example.com")
            sp = st.text_input("Password",         type="password", key="su_pass", placeholder="min 6 characters")
            sc = st.text_input("Confirm Password", type="password", key="su_conf", placeholder="repeat password")
            if st.button("Create Account", type="primary", use_container_width=True, key="su_btn"):
                if not (su and se and sp and sc):
                    st.warning("Please fill in all fields.")
                elif sp != sc:
                    st.error("Passwords don't match.")
                else:
                    ok, msg = auth.register(su, se, sp)
                    if ok:
                        ok2, uname = auth.login(su, sp)
                        if ok2:
                            _do_login(uname, remember=True)
                            st.success("Account created! Welcome.")
                            st.rerun()
                    else:
                        st.error(msg)

        # Guest access
        st.markdown("---")
        st.markdown(
            '<div style="text-align:center;color:#64748b;font-size:0.85rem;margin-bottom:8px">'
            'Just browsing? View the dashboard without an account.'
            '</div>',
            unsafe_allow_html=True,
        )
        if st.button("Continue as Guest", use_container_width=True, key="guest_btn"):
            st.session_state["username"] = "__guest__"
            st.session_state["is_guest"] = True
            st.rerun()


if "username" not in st.session_state:
    show_auth_page()
    st.stop()


# ---------------------------------------------------------------------------
# Per-user context (runs for every logged-in page render)
# ---------------------------------------------------------------------------

_username = st.session_state["username"]
_is_guest = st.session_state.get("is_guest", False)

# Point the database module at this user's data
database.set_username(_username)


def _guest_block():
    """Show a login prompt and stop rendering if the user is a guest."""
    if not _is_guest:
        return
    st.markdown("""
    <div style="max-width:480px;margin:80px auto;background:#1e293b;
                border:1px solid #6366f1;border-radius:16px;
                padding:40px 32px;text-align:center;">
        <div style="font-size:1.2rem;font-weight:700;color:#e2e8f0;margin-bottom:8px">
            Login Required
        </div>
        <div style="font-size:0.9rem;color:#94a3b8;margin-bottom:24px">
            Create a free account to access this feature.
        </div>
    </div>
    """, unsafe_allow_html=True)
    _, mid, _ = st.columns([1, 1.4, 1])
    with mid:
        if st.button("Log In / Sign Up", type="primary", use_container_width=True, key="guest_login_redirect"):
            st.session_state.pop("username", None)
            st.session_state.pop("is_guest", None)
            st.rerun()
    st.stop()


# ---------------------------------------------------------------------------
# Background task helpers
# ---------------------------------------------------------------------------

# Module-level process registry — safe to access from any thread
_PROCS: dict[str, subprocess.Popen] = {}


def launch_task(cmd: list, task_key: str):
    """Start a subprocess in a background thread.
    Output goes to a temp log file; status goes to a sidecar .status file.
    The thread NEVER writes to st.session_state (not thread-safe in Streamlit).
    """
    log_path    = Path(tempfile.mktemp(suffix=".log",    prefix="jobbot_"))
    status_path = Path(str(log_path) + ".status")

    # Write initial status file
    status_path.write_text(json.dumps({"running": True, "returncode": None}))

    # Only store paths in session_state — set from main thread, never from bg thread
    st.session_state[task_key] = {
        "log_file":    str(log_path),
        "status_file": str(status_path),
        "visible":     True,
    }

    def _run():
        try:
            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"
            env["JOB_BOT_USERNAME"] = _username
            with open(log_path, "w", encoding="utf-8", errors="replace") as f:
                proc = subprocess.Popen(
                    cmd,
                    stdout=f,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    cwd=str(BOT_DIR),
                    env=env,
                )
                _PROCS[task_key] = proc
                proc.wait()
            status_path.write_text(json.dumps({"running": False, "returncode": proc.returncode}))
        except Exception as exc:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"Error starting process: {exc}\n")
            status_path.write_text(json.dumps({"running": False, "returncode": 1}))
        finally:
            _PROCS.pop(task_key, None)

    threading.Thread(target=_run, daemon=True).start()


def stop_task(task_key: str, status_path: Path):
    """Kill the running process for task_key."""
    proc = _PROCS.get(task_key)
    if proc and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except Exception:
            proc.kill()
    status_path.write_text(json.dumps({"running": False, "returncode": -1}))


_ANSI_RE = re.compile(r'\x1b\[[0-9;]*[mGKHFABCDJn]|\r')

def _colorize(line: str) -> str:
    """Strip ANSI codes then wrap the line in a color span based on content."""
    line = _ANSI_RE.sub("", line).strip()
    if not line:
        return ""
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

    # Read running/returncode from sidecar status file (never from session_state)
    status_path = Path(state.get("status_file", ""))
    running, rc = True, None
    if status_path.exists():
        try:
            s = json.loads(status_path.read_text())
            running = s.get("running", True)
            rc      = s.get("returncode")
        except Exception:
            pass

    # Read log lines from log file
    log_path = Path(state.get("log_file", ""))
    lines: list[str] = []
    if log_path.exists():
        try:
            lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
            lines = [l for l in lines if l.strip()]
        except Exception:
            pass

    # ── Header row ──────────────────────────────────────────────────────────
    if running:
        header_col, stop_col, close_col = st.columns([9, 1.2, 1])
    else:
        header_col, close_col = st.columns([11, 1])

    with header_col:
        if running:
            st.markdown(
                f'<div class="task-panel-header running">'
                f'<span class="running-dot"></span>'
                f'<span style="color:#e6edf3;font-size:0.85rem;font-weight:500">{title}</span>'
                f'<span style="color:#3d4f6b;font-size:0.78rem"> — running</span>'
                f'</div>',
                unsafe_allow_html=True,
            )
        elif rc == -1:
            st.markdown(
                f'<div class="task-panel-header error">'
                f'<span style="color:#f59e0b;font-size:0.85rem;font-weight:500">{title} — stopped</span>'
                f'</div>',
                unsafe_allow_html=True,
            )
        elif rc == 0:
            st.markdown(
                f'<div class="task-panel-header done">'
                f'<span style="color:#34d399;font-size:0.85rem;font-weight:500">{title} — done</span>'
                f'</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f'<div class="task-panel-header error">'
                f'<span style="color:#f87171;font-size:0.85rem;font-weight:500">{title} — failed (exit {rc})</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

    if running:
        with stop_col:
            if st.button("Stop", key=f"stop_{task_key}", use_container_width=True):
                stop_task(task_key, status_path)
                st.rerun()

    with close_col:
        if st.button("Close", key=f"close_{task_key}", use_container_width=True):
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
    return database.load_config()


def save_config(cfg: dict):
    database.save_config(cfg)


def score_color(score: float) -> str:
    if score >= 85: return "#34d399"
    if score >= 70: return "#60a5fa"
    return "#5c6a82"


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

database.init_db()
# Auto-cleanup jobs older than 7 days (keeps applied jobs forever)
database.cleanup_old_jobs(days=7)
stats = database.get_stats()

_PAGES = ["Dashboard", "Search", "Matched Jobs", "Apply", "Tracker", "Settings"]

def _go(page_fragment: str):
    for p in _PAGES:
        if page_fragment in p:
            st.session_state["nav_page"] = p
            break
    st.rerun()

if "nav_page" not in st.session_state:
    st.session_state["nav_page"] = _PAGES[0]

with st.sidebar:
    st.markdown(
        '<div style="font-size:1rem;font-weight:600;color:#e6edf3;margin-bottom:1.5rem;letter-spacing:-0.01em">Job Bot</div>',
        unsafe_allow_html=True,
    )
    page = st.radio(
        "nav",
        _PAGES,
        index=_PAGES.index(st.session_state["nav_page"]),
        label_visibility="collapsed",
        key="nav_radio",
    )
    st.session_state["nav_page"] = page
    st.markdown("---")
    st.markdown(
        f'<div style="font-size:0.78rem;color:#3d4f6b;line-height:2">'
        f'{stats["total"]} jobs found &nbsp;·&nbsp; {stats["matched"]} matched<br>'
        f'{stats["applied"]} applied &nbsp;·&nbsp; avg {stats["avg_score"]}%'
        f'</div>',
        unsafe_allow_html=True,
    )
    st.markdown("---")
    if _is_guest:
        st.markdown('<div style="font-size:0.8rem;color:#5c6a82;margin-bottom:8px">Browsing as guest</div>', unsafe_allow_html=True)
        if st.button("Log in", use_container_width=True, type="primary"):
            st.session_state.pop("username", None)
            st.session_state.pop("is_guest", None)
            st.rerun()
    else:
        st.markdown(f'<div style="font-size:0.8rem;color:#5c6a82;margin-bottom:8px">{_username}</div>', unsafe_allow_html=True)
        if st.button("Log out", use_container_width=True):
            _do_logout()
            st.rerun()


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

if "Dashboard" in page:
    st.markdown('<div class="page-title">Dashboard</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-sub">Overview of your job search pipeline.</div>', unsafe_allow_html=True)

    if _is_guest:
        st.info("You're browsing as a guest. Log in to search jobs, run the pipeline, and track applications.")

    # Summary row
    st.markdown(f"""
    <div class="summary-row">
        <div class="summary-item">
            <div class="num">{stats["total"]}</div>
            <div class="lbl">Found</div>
        </div>
        <div class="summary-item">
            <div class="num accent">{stats["matched"]}</div>
            <div class="lbl">Matched</div>
        </div>
        <div class="summary-item">
            <div class="num green">{stats["applied"]}</div>
            <div class="lbl">Applied</div>
        </div>
        <div class="summary-item">
            <div class="num">{stats["skipped"]}</div>
            <div class="lbl">Skipped</div>
        </div>
        <div class="summary-item">
            <div class="num">{stats["avg_score"]}%</div>
            <div class="lbl">Avg score</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Navigation
    st.markdown('<div class="section-label">Go to</div>', unsafe_allow_html=True)
    nav1, nav2, nav3, nav4 = st.columns(4)
    if nav1.button("Search",       use_container_width=True): _go("Search")
    if nav2.button("Matched Jobs", use_container_width=True): _go("Matched")
    if nav3.button("Apply",        use_container_width=True): _go("Apply")
    if nav4.button("Tracker",      use_container_width=True): _go("Tracker")

    st.markdown('<hr class="section-divider">', unsafe_allow_html=True)

    # Actions
    st.markdown('<div class="section-label">Actions</div>', unsafe_allow_html=True)
    _has_ai = bool(os.environ.get("OPENROUTER_API_KEY"))
    col1, col2, col3, col4, col5 = st.columns(5)
    if col1.button("Run full pipeline", use_container_width=True, type="primary"):
        launch_task([PYTHON, "-u", "main.py", "run", "--auto"], "task_run")
    _match_label = "AI Match" if _has_ai else "Re-score all"
    _match_cmd   = ["rematch", "--ai"] if _has_ai else ["rematch"]
    if col2.button(_match_label, use_container_width=True):
        launch_task([PYTHON, "-u", "main.py"] + _match_cmd, "task_rematch")
    if col3.button("Rule-based match", use_container_width=True):
        launch_task([PYTHON, "-u", "main.py", "rematch"], "task_rematch2")
    if col4.button("Refresh", use_container_width=True):
        st.rerun()
    if col5.button("Clean old jobs", use_container_width=True):
        deleted = database.cleanup_old_jobs(days=7)
        st.toast(f"Removed {deleted} jobs older than 7 days.")
        st.rerun()
    if _has_ai:
        st.markdown('<div style="font-size:0.72rem;color:#2d3d55;margin-top:4px">AI Match uses OpenRouter (Llama 3) for smarter scoring</div>', unsafe_allow_html=True)

    for key, label in [("task_run", "Full Pipeline"), ("task_search", "Search"), ("task_match", "Match"), ("task_rematch", "Re-score")]:
        render_task_panel(key, label)

    # Recent matches
    st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
    st.markdown('<div class="section-label">Recent matches</div>', unsafe_allow_html=True)

    matched = database.get_jobs_by_status("matched")[:5]
    if matched:
        for job in matched:
            score   = job.get("match_score") or 0
            title   = (job.get("title")   or "Unknown")[:60]
            company = (job.get("company") or "Unknown")[:30]
            url     = job.get("url") or ""
            col1, col2, col3 = st.columns([5, 1, 1])
            col1.markdown(
                f'<div style="font-size:0.875rem;color:#e6edf3">{title}</div>'
                f'<div style="font-size:0.78rem;color:#5c6a82">{company}</div>',
                unsafe_allow_html=True,
            )
            col2.markdown(
                f'<div style="font-size:0.875rem;color:{score_color(score)};padding-top:4px">{score:.0f}%</div>',
                unsafe_allow_html=True,
            )
            if url:
                col3.link_button("Open", url, use_container_width=True)
    else:
        st.markdown('<div style="font-size:0.85rem;color:#3d4f6b">No matched jobs yet. Run a search to get started.</div>', unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

elif "Search" in page:
    _guest_block()
    st.markdown('<div class="page-title">Search</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-sub">Search → Match → Apply. Each step is separate.</div>', unsafe_allow_html=True)

    cfg = load_config()
    all_titles = cfg.get("job_titles", [])

    st.markdown('<div class="section-label">Job titles</div>', unsafe_allow_html=True)
    selected_titles = st.multiselect(
        "titles",
        options=all_titles,
        default=all_titles,
        label_visibility="collapsed",
    )

    remote_only = st.checkbox("Remote only", value=cfg.get("remote_only", False))

    st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
    st.markdown('<div class="section-label">Sources</div>', unsafe_allow_html=True)

    SOURCE_MAP = {
        "RemoteOK":        "remoteok",
        "Arbeitnow":       "arbeitnow",
        "The Muse":        "themuse",
        "HN Who's Hiring": "hn",
        "Remotive":        "remotive",
        "Jobicy":          "jobicy",
        "Working Nomads":  "workingnomads",
        "Himalayas":       "himalayas",
    }

    cols = st.columns(4)
    selected_sources = {}
    for i, (label, key) in enumerate(SOURCE_MAP.items()):
        selected_sources[key] = cols[i % 4].checkbox(label, value=True, key=f"src_{key}")

    enabled_sources = [k for k, v in selected_sources.items() if v]

    st.markdown('<hr class="section-divider">', unsafe_allow_html=True)

    can_search = bool(selected_titles and enabled_sources)
    if not selected_titles:
        st.warning("Select at least one job title.")
    elif not enabled_sources:
        st.warning("Select at least one source.")

    if st.button("Start search", type="primary", disabled=not can_search):
        cmd = [PYTHON, "-u", "main.py", "search"]
        for q in selected_titles:
            cmd.extend(["-q", q])
        cmd.extend(["--sources", ",".join(enabled_sources)])
        if remote_only:
            cmd.append("--remote")
        launch_task(cmd, "task_search")

    task_still_running = render_task_panel("task_search", "Search")

    if not task_still_running and st.session_state.get("task_search"):
        state = st.session_state.get("task_search", {})
        status_path = Path(state.get("status_file", ""))
        if status_path.exists():
            try:
                s = json.loads(status_path.read_text())
                if not s.get("running") and not st.session_state.get("search_result_shown"):
                    st.session_state["search_result_shown"] = True
                    st.rerun()
            except Exception:
                pass

    recent = database.get_recent_jobs(hours=24)
    stats  = database.get_stats()

    if stats["total"] > 0:
        st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
        st.markdown(
            f'<div style="font-size:0.78rem;color:#3d4f6b;margin-bottom:1rem">'
            f'{stats["total"]} total &nbsp;·&nbsp; {stats["found"]} unscored &nbsp;·&nbsp; {stats["matched"]} matched'
            f'</div>',
            unsafe_allow_html=True,
        )

        if recent:
            st.markdown(f'<div class="section-label">Found in last 24h — {len(recent)} jobs</div>', unsafe_allow_html=True)

            search_filter = st.text_input("Filter", placeholder="Filter by title or company...", label_visibility="collapsed")

            display = recent
            if search_filter:
                fl = search_filter.lower()
                display = [j for j in recent if fl in (j.get("title") or "").lower()
                           or fl in (j.get("company") or "").lower()]

            for job in display[:150]:
                title    = job.get("title")   or "Unknown"
                company  = job.get("company") or "Unknown"
                location = job.get("location") or ""
                source   = job.get("source") or ""
                url      = job.get("url") or ""
                salary   = job.get("salary") or ""
                desc     = (job.get("description") or "")[:250]
                status   = job.get("status") or "found"

                meta_parts = [p for p in [company, location, source] if p]
                salary_str = f' · {salary}' if salary else ""

                status_colors = {
                    "found":   ("background:#161d2b;color:#5c6a82", "Unscored"),
                    "matched": ("background:#0d2218;color:#34d399",  "Matched"),
                    "skipped": ("background:#161d2b;color:#3d4f6b",  "Skipped"),
                    "applied": ("background:#0d1829;color:#60a5fa",  "Applied"),
                }
                sc_style, sc_label = status_colors.get(status, ("background:#161d2b;color:#5c6a82", status))

                st.markdown(f"""
                <div class="job-card">
                    <div style="display:flex;align-items:flex-start;justify-content:space-between">
                        <div class="job-title">{title}</div>
                        <span class="status-badge" style="{sc_style}">{sc_label}</span>
                    </div>
                    <div class="job-meta">{' · '.join(meta_parts)}{salary_str}</div>
                    <div class="desc">{desc}{"…" if len(job.get("description") or "") > 250 else ""}</div>
                </div>
                """, unsafe_allow_html=True)

                if url:
                    btn_col, _ = st.columns([1, 7])
                    btn_col.link_button("Open", url, use_container_width=True)
        else:
            st.markdown('<div style="font-size:0.85rem;color:#3d4f6b">No jobs found in the last 24 hours.</div>', unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Matched Jobs
# ---------------------------------------------------------------------------

elif "Matched" in page:
    _guest_block()
    st.markdown('<div class="page-title">Matched Jobs</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-sub">Jobs scoring ≥70% against your profile.</div>', unsafe_allow_html=True)

    matched = database.get_jobs_by_status("matched")

    if not matched:
        st.info("No matched jobs yet. Run a search from the Dashboard first.")
    else:
        col1, col2 = st.columns(2)
        with col1:
            min_score = st.slider("Minimum score", 70, 100, 70)
        with col2:
            sort_by = st.selectbox("Sort by", ["Score (high to low)", "Company A–Z"])

        filtered = [j for j in matched if (j.get("match_score") or 0) >= min_score]
        if "Company" in sort_by:
            filtered.sort(key=lambda j: (j.get("company") or "").lower())
        else:
            filtered.sort(key=lambda j: j.get("match_score") or 0, reverse=True)

        from collections import defaultdict
        grouped: dict[str, list] = defaultdict(list)
        for job in filtered:
            grouped[job.get("source") or "Unknown"].append(job)

        st.markdown(
            f'<div style="font-size:0.78rem;color:#3d4f6b;margin-bottom:1.5rem">'
            f'{len(filtered)} jobs across {len(grouped)} sources</div>',
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
            skills_html = " ".join(f'<span class="skill-tag">{s}</span>' for s in matched_skills[:10])
            meta_parts  = [p for p in [company, location] if p]
            salary_str  = f' · {salary}' if salary else ""

            st.markdown(f"""
            <div class="job-card">
                <div style="display:flex;align-items:flex-start;justify-content:space-between">
                    <div class="job-title">{title}</div>
                    <span class="score-pill" style="background:{sc}18;color:{sc}">{score:.0f}%</span>
                </div>
                <div class="job-meta">{' · '.join(meta_parts)}{salary_str}</div>
                <div style="margin-bottom:8px">{skills_html}</div>
                <div class="desc">{desc}{"…" if len(job.get("description") or "") > 400 else ""}</div>
            </div>
            """, unsafe_allow_html=True)

            btn1, btn2, _ = st.columns([1, 1, 6])
            if url:
                btn1.link_button("Open", url, use_container_width=True)
            if btn2.button("Skip", key=f"skip_{page_key}_{job['id']}", use_container_width=True):
                database.set_match(job["id"], 0, json.dumps({"reason": "Manually skipped"}))
                st.rerun()

        for source, jobs in sorted(grouped.items(), key=lambda x: -len(x[1])):
            n = len(jobs)
            with st.expander(f"{source}  ·  {n} {'job' if n == 1 else 'jobs'}", expanded=True):
                for job in jobs:
                    render_job_card(job, page_key=source)


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------

elif "Apply" in page:
    _guest_block()
    st.markdown('<div class="page-title">Apply</div>', unsafe_allow_html=True)

    matched = database.get_jobs_by_status("matched")
    snoozed = st.session_state.get("snoozed_jobs", set())
    matched = [j for j in matched if j["id"] not in snoozed]

    st.markdown(
        f'<div class="page-sub">{stats.get("applied", 0)} applied · {len(matched)} remaining</div>',
        unsafe_allow_html=True,
    )

    if not matched:
        st.info("No matched jobs to apply to. Run a search first.")
    else:
        for job in matched:
            job_id = job["id"]
            score  = job.get("match_score") or 0
            title  = job.get("title")   or "Unknown"
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
            skills_html = " ".join(f'<span class="skill-tag">{s}</span>' for s in matched_skills[:10])
            meta_parts  = [p for p in [company, location] if p]
            salary_str  = f' · {salary}' if salary else ""

            st.markdown(f"""
            <div class="job-card">
                <div style="display:flex;align-items:flex-start;justify-content:space-between">
                    <div class="job-title">{title}</div>
                    <span class="score-pill" style="background:{sc}18;color:{sc}">{score:.0f}%</span>
                </div>
                <div class="job-meta">{' · '.join(meta_parts)}{salary_str}</div>
                <div style="margin-bottom:8px">{skills_html}</div>
                <div class="desc">{desc}{"…" if len(job.get("description") or "") > 350 else ""}</div>
            </div>
            """, unsafe_allow_html=True)

            b1, b2, b3, b4 = st.columns(4)
            if url:
                b1.link_button("Open", url, use_container_width=True)
            else:
                b1.button("Open", key=f"open_{job_id}", disabled=True, use_container_width=True)
            if b2.button("Mark applied", key=f"applied_{job_id}", use_container_width=True):
                database.set_applied(job_id)
                st.rerun()
            if b3.button("Keep for later", key=f"later_{job_id}", use_container_width=True):
                st.session_state.setdefault("snoozed_jobs", set()).add(job_id)
                st.rerun()
            if b4.button("Not interested", key=f"skip_{job_id}", use_container_width=True):
                database.set_match(job_id, 0, json.dumps({"reason": "Not interested"}))
                st.rerun()
            st.markdown("")


# ---------------------------------------------------------------------------
# Tracker
# ---------------------------------------------------------------------------

elif "Tracker" in page:
    _guest_block()
    import tracker as _tracker

    st.markdown('<div class="page-title">Tracker</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-sub">Update outcomes as you hear back from companies.</div>', unsafe_allow_html=True)

    jobs = _tracker.get_all_jobs()

    if not jobs:
        st.info("No applications tracked yet.")
    else:
        from collections import Counter
        sc = Counter(j.get("Status", "") for j in jobs)
        st.markdown(f"""
        <div class="summary-row" style="margin-bottom:1.5rem">
            <div class="summary-item"><div class="num">{len(jobs)}</div><div class="lbl">Total</div></div>
            <div class="summary-item"><div class="num">{sc.get("Applied", 0)}</div><div class="lbl">Applied</div></div>
            <div class="summary-item"><div class="num">{sc.get("Interview", 0)}</div><div class="lbl">Interview</div></div>
            <div class="summary-item"><div class="num">{sc.get("Accepted", 0)}</div><div class="lbl">Accepted</div></div>
            <div class="summary-item"><div class="num">{sc.get("Denied", 0)}</div><div class="lbl">Denied</div></div>
        </div>
        """, unsafe_allow_html=True)

        tracker_files = _tracker.list_tracker_files()
        if tracker_files:
            latest = tracker_files[-1]
            with open(latest, "rb") as f:
                st.download_button("Download Excel", data=f.read(), file_name=latest.name,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

        st.markdown('<hr class="section-divider">', unsafe_allow_html=True)

        status_filter = st.selectbox("Filter", ["All"] + _tracker.STATUS_OPTIONS, label_visibility="collapsed")
        filtered = jobs if status_filter == "All" else [j for j in jobs if j.get("Status") == status_filter]

        st.markdown(f'<div style="font-size:0.78rem;color:#3d4f6b;margin-bottom:1rem">{len(filtered)} job{"s" if len(filtered) != 1 else ""}</div>', unsafe_allow_html=True)

        status_color_map = {
            "Applied": "#60a5fa", "Manual - Pending": "#f59e0b",
            "Interview": "#34d399", "Accepted": "#34d399", "Denied": "#f87171",
        }

        for i, job in enumerate(filtered):
            url     = job.get("URL", "")
            title   = job.get("Job Title", "Unknown")
            company = job.get("Company", "Unknown")
            status  = job.get("Status", "Applied")
            date    = job.get("Date Applied", "")
            score   = job.get("Match Score", "")
            sc_col  = status_color_map.get(status, "#5c6a82")
            meta    = " · ".join(p for p in [company, date, score] if p)

            st.markdown(f"""
            <div class="job-card">
                <div style="display:flex;align-items:flex-start;justify-content:space-between">
                    <div class="job-title">{title}</div>
                    <span class="status-badge" style="background:{sc_col}18;color:{sc_col}">{status}</span>
                </div>
                <div class="job-meta">{meta}</div>
            </div>
            """, unsafe_allow_html=True)

            col_status, col_notes, col_save, col_open = st.columns([2, 3, 1, 1])
            with col_status:
                new_status = st.selectbox("Status", _tracker.STATUS_OPTIONS,
                    index=_tracker.STATUS_OPTIONS.index(status) if status in _tracker.STATUS_OPTIONS else 0,
                    key=f"status_{i}", label_visibility="collapsed")
            with col_notes:
                notes = st.text_input("Notes", value=job.get("Notes", "") or "",
                    key=f"notes_{i}", label_visibility="collapsed", placeholder="Notes...")
            with col_save:
                if st.button("Save", key=f"save_{i}", use_container_width=True):
                    _tracker.update_status(url, new_status, notes)
                    st.rerun()
            with col_open:
                if url:
                    st.link_button("Open", url, use_container_width=True)


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

elif "Settings" in page:
    _guest_block()
    st.markdown('<div class="page-title">Settings</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-sub">Configure your search, profile, and matching preferences.</div>', unsafe_allow_html=True)

    cfg = load_config()

    with st.expander("Resume", expanded=True):
        existing_resume = database.get_resume_content()
        st.caption(f"{len(existing_resume):,} characters stored" if existing_resume else "No resume uploaded yet.")
        uploaded = st.file_uploader("Upload PDF or DOCX", type=["pdf", "docx"], label_visibility="collapsed")
        if uploaded is not None:
            import resume_parser as rp
            suffix = Path(uploaded.name).suffix.lower()
            resume_path = BOT_DIR / f"uploaded_resume{suffix}"
            resume_path.write_bytes(uploaded.getvalue())
            text = rp.extract_text(resume_path)
            if text and not text.startswith("["):
                database.save_resume(str(resume_path), text)
                profile_data = rp.extract_resume_profile(text)
                st.session_state["auto_profile"] = profile_data
                st.success(f"Parsed {uploaded.name} — {len(text):,} characters")
                if profile_data.get("skills"):
                    skills_html = " ".join(f'<span class="skill-tag">{s}</span>' for s in profile_data["skills"])
                    st.markdown(skills_html, unsafe_allow_html=True)
            else:
                st.error(f"Could not parse {uploaded.name}.")

    with st.expander("Job titles", expanded=True):
        titles_raw = st.text_area("One per line", value="\n".join(cfg.get("job_titles", [])),
            height=280, label_visibility="collapsed")
        st.caption(f"{len([t for t in titles_raw.splitlines() if t.strip()])} titles active")

    with st.expander("Company blacklist", expanded=False):
        st.caption("Jobs from these companies will be skipped automatically.")
        blacklist_raw = st.text_area("One per line", value="\n".join(cfg.get("blacklisted_companies", [])),
            height=120, label_visibility="collapsed", placeholder="Amazon\nUber\nMeta")

    with st.expander("Matching", expanded=True):
        col1, col2, col3 = st.columns(3)
        with col1:
            threshold = st.slider("Score threshold (%)", 50, 95, int(cfg.get("match_threshold", 70)))
        with col2:
            remote_only = st.checkbox("Remote only", value=cfg.get("remote_only", False))
        with col3:
            expiry_days = st.number_input("Expire jobs after (days)", min_value=7, max_value=90, value=int(cfg.get("job_expiry_days", 30)))

    with st.expander("Your profile", expanded=True):
        auto_profile = st.session_state.get("auto_profile", {})
        profile = {**cfg.get("profile", {}), **auto_profile}
        col1, col2 = st.columns(2)
        with col1:
            name     = st.text_input("Full name",  value=profile.get("name", ""))
            email    = st.text_input("Email",      value=profile.get("email", ""))
            phone    = st.text_input("Phone",      value=profile.get("phone", ""))
        with col2:
            city     = st.text_input("City",       value=profile.get("city", ""))
            website  = st.text_input("Website",    value=profile.get("website", ""))
            linkedin = st.text_input("LinkedIn handle", value=profile.get("linkedin_handle", ""))
        summary = st.text_area("Summary", value=profile.get("summary", ""), height=100)

    st.markdown('<hr class="section-divider">', unsafe_allow_html=True)

    if st.button("Save settings", type="primary"):
        cfg["job_titles"]            = [t.strip() for t in titles_raw.splitlines() if t.strip()]
        cfg["blacklisted_companies"] = [t.strip() for t in blacklist_raw.splitlines() if t.strip()]
        cfg["match_threshold"]  = threshold
        cfg["remote_only"]      = remote_only
        cfg["job_expiry_days"]  = expiry_days
        cfg["profile"] = {
            "name": name, "email": email, "phone": phone,
            "city": city, "website": website,
            "linkedin_handle": linkedin, "summary": summary,
        }
        save_config(cfg)
        st.success("Settings saved.")
