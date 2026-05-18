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
        padding: 6px 4px;
        max-height: 340px; overflow-y: auto;
        background: #090e1a;
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

    /* ── Kill the rerun dim/flash ── */
    .stApp, .stApp > *, .main, .stMain,
    [data-testid="stAppViewContainer"],
    [data-testid="stAppViewContainer"] > *,
    [data-stale="true"], [data-stale="true"] > * {
        opacity: 1 !important;
        transition: none !important;
    }
    [data-testid="stStatusWidget"] { display: none !important; }

    /* ── Step cards ── */
    .step-row {
        display: flex; gap: 10px; margin-bottom: 2rem;
    }
    .step-card {
        flex: 1; padding: 16px 18px;
        background: #0c1220; border: 1px solid #161e2e;
        border-radius: 10px; cursor: pointer;
        transition: border-color 0.15s;
        position: relative;
    }
    .step-card:hover { border-color: #2a3a55; }
    .step-card.active { border-color: #4f8ef7; }
    .step-card.done   { border-color: #1a3a2a; }
    .step-card .step-num {
        font-size: 0.65rem; font-weight: 600; letter-spacing: 0.1em;
        text-transform: uppercase; margin-bottom: 6px;
    }
    .step-card .step-title {
        font-size: 0.88rem; font-weight: 600; color: #dde6f0;
        margin-bottom: 3px;
    }
    .step-card .step-desc {
        font-size: 0.74rem; color: #3d5070; line-height: 1.4;
    }
    .step-card .step-status {
        position: absolute; top: 12px; right: 14px;
        font-size: 0.68rem; font-weight: 500;
    }

    /* ── Native bordered containers ── */
    [data-testid="stVerticalBlockBorderWrapper"] {
        background: #0c1220 !important;
        border-color: #1e2c42 !important;
        border-radius: 10px !important;
    }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Auth initialisation & cookie check
# ---------------------------------------------------------------------------

auth.init_auth_db()

try:
    import extra_streamlit_components as stx
    from datetime import datetime as _dt, timedelta as _td
    _cookie_mgr = stx.CookieManager(key="jobbot_cookies")
    _cookie_available = True
except Exception:
    _cookie_mgr = None
    _cookie_available = False


def _do_login(username: str, remember: bool):
    token = auth.create_token(username, days=30 if remember else 1)
    st.session_state["username"]   = username
    st.session_state["auth_token"] = token
    if remember and _cookie_available:
        try:
            _cookie_mgr.set(
                "job_bot_auth", token,
                expires_at=_dt.now() + _td(days=30),
            )
        except Exception:
            pass


def _do_logout():
    auth.revoke_token(st.session_state.get("auth_token", ""))
    if _cookie_available:
        try:
            _cookie_mgr.delete("job_bot_auth")
        except Exception:
            pass
    for k in ["username", "auth_token", "page_loaded"]:
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


# Auto-login from cookie
if "username" not in st.session_state and _cookie_available:
    try:
        token = _cookie_mgr.get("job_bot_auth")
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

def _format_log_line(raw: str) -> str:
    """Strip ANSI, classify the line, return a styled HTML row."""
    line = _ANSI_RE.sub("", raw).strip()
    if not line:
        return ""

    esc = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    lo  = line.lower()

    # Classify
    if any(k in lo for k in ("error", "fail", "exception", "traceback", "exit 1")):
        dot   = '#f87171'
        color = '#f87171'
        bg    = 'rgba(248,113,113,0.06)'
    elif any(k in lo for k in ("[ok]", "done", "complete", "success", "added", "matched", "applied")):
        dot   = '#34d399'
        color = '#c8efe2'
        bg    = 'rgba(52,211,153,0.05)'
    elif any(k in lo for k in ("searching", "loading", "phase", "────", "──")):
        dot   = '#4f8ef7'
        color = '#7fb3f7'
        bg    = 'rgba(79,142,247,0.05)'
    elif any(k in lo for k in ("found", "jobs found", "score", "reset", "skipped")):
        dot   = '#a78bfa'
        color = '#c4b5fd'
        bg    = 'rgba(167,139,250,0.05)'
    elif any(k in lo for k in ("warn", "skipping", "busy", "rate limit", "retry")):
        dot   = '#f59e0b'
        color = '#fcd34d'
        bg    = 'rgba(245,158,11,0.05)'
    else:
        dot   = '#2d3d55'
        color = '#4f6a8a'
        bg    = 'transparent'

    return (
        f'<div style="display:flex;align-items:baseline;gap:10px;padding:5px 0;'
        f'background:{bg};border-radius:5px;margin:1px 0;padding-left:10px">'
        f'<span style="width:5px;height:5px;border-radius:50%;background:{dot};'
        f'flex-shrink:0;margin-top:5px;display:inline-block"></span>'
        f'<span style="color:{color};font-size:0.78rem;line-height:1.5;'
        f'font-family:ui-monospace,\'SF Mono\',Menlo,monospace;word-break:break-all">{esc}</span>'
        f'</div>'
    )


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
        header_col, stop_col, close_col = st.columns([11, 0.6, 0.6])
    else:
        header_col, close_col = st.columns([13, 0.6])

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
            if st.button("■", key=f"stop_{task_key}", use_container_width=True,
                         help="Stop process"):
                stop_task(task_key, status_path)
                st.rerun()

    with close_col:
        if st.button("✕", key=f"close_{task_key}", use_container_width=True,
                     help="Dismiss"):
            st.session_state[task_key]["visible"] = False
            st.rerun()

    # ── Output box ──────────────────────────────────────────────────────────
    if not lines:
        st.markdown(
            '<div class="task-panel-body">'
            '<span style="color:#2d3d55;font-size:0.78rem;font-style:italic">Starting…</span>'
            '</div>',
            unsafe_allow_html=True,
        )
    else:
        rows = "".join(_format_log_line(l) for l in lines[-120:] if l.strip())
        st.markdown(
            f'<div class="task-panel-body" style="padding:8px 12px">{rows}</div>',
            unsafe_allow_html=True,
        )

    return running


# ---------------------------------------------------------------------------
# Live task panel — only this fragment reruns, not the whole page
# ---------------------------------------------------------------------------

@st.fragment(run_every=0.5)
def live_task_panel(task_key: str, title: str):
    render_task_panel(task_key, title)


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------

def load_config() -> dict:
    return _load_config_cached(_username)


def save_config(cfg: dict):
    database.save_config(cfg)
    _load_config_cached.clear()   # invalidate cache after save


def score_color(score: float) -> str:
    if score >= 85: return "#34d399"
    if score >= 70: return "#60a5fa"
    return "#5c6a82"


def _card(job: dict, key_prefix: str = "card", *,
          show_score: bool = False, show_status: bool = False,
          skip_btn: bool = False, apply_btns: bool = False) -> None:
    """Render a single job listing as a native Streamlit bordered container."""
    score    = job.get("match_score") or 0
    title    = (job.get("title")    or "Unknown")[:80]
    company  = job.get("company")   or ""
    location = job.get("location")  or ""
    source   = job.get("source")    or ""
    url      = job.get("url")       or ""
    salary   = job.get("salary")    or ""
    desc     = (job.get("description") or "")[:280]
    status   = job.get("status")    or "found"
    jid      = job.get("id", "")

    matched_skills: list[str] = []
    try:
        matched_skills = json.loads(job.get("match_reason") or "{}").get("matched", [])
    except Exception:
        pass

    _STATUS_COLOR = {"found": "gray", "matched": "green", "skipped": "gray", "applied": "blue"}
    _STATUS_LABEL = {"found": "Unscored", "matched": "Matched", "skipped": "Skipped", "applied": "Applied"}

    with st.container(border=True):
        _ha, _hb = st.columns([5, 1])
        with _ha:
            st.markdown(f"**{title}**")
            _meta = [p for p in [company, location, source] if p]
            if salary:
                _meta.append(salary)
            if _meta:
                st.caption(" · ".join(_meta))
        with _hb:
            if show_score and score:
                if score >= 85:
                    st.markdown(f'<div style="text-align:right;color:#34d399;font-size:1.1rem;font-weight:700;padding-top:4px">{score:.0f}%</div>', unsafe_allow_html=True)
                elif score >= 70:
                    st.markdown(f'<div style="text-align:right;color:#4f8ef7;font-size:1.1rem;font-weight:700;padding-top:4px">{score:.0f}%</div>', unsafe_allow_html=True)
                else:
                    st.markdown(f'<div style="text-align:right;color:#5c6a82;font-size:1.1rem;font-weight:700;padding-top:4px">{score:.0f}%</div>', unsafe_allow_html=True)
            elif show_status:
                st.badge(
                    _STATUS_LABEL.get(status, status),
                    color=_STATUS_COLOR.get(status, "gray"),
                )

        if matched_skills:
            st.markdown("  ".join(f":blue-badge[{s}]" for s in matched_skills[:8]))

        if desc:
            st.caption(desc + ("…" if len(job.get("description") or "") > 280 else ""))

        # Action buttons
        _btn_keys: list[str] = []
        if url:          _btn_keys.append("open")
        if apply_btns:   _btn_keys += ["applied", "later", "notint"]
        elif skip_btn:   _btn_keys.append("skip")

        if _btn_keys:
            _bcols = st.columns([1] * len(_btn_keys) + [max(1, 6 - len(_btn_keys))])
            _bi = 0
            if url:
                _bcols[_bi].link_button(":material/open_in_new: Open", url, use_container_width=True)
                _bi += 1
            if apply_btns:
                if _bcols[_bi].button("Mark applied",   key=f"ma_{key_prefix}_{jid}", use_container_width=True):
                    database.set_applied(jid); st.rerun()
                _bi += 1
                if _bcols[_bi].button("Keep for later", key=f"kl_{key_prefix}_{jid}", use_container_width=True):
                    st.session_state.setdefault("snoozed_jobs", set()).add(jid); st.rerun()
                _bi += 1
                if _bcols[_bi].button("Not interested", key=f"ni_{key_prefix}_{jid}", use_container_width=True):
                    database.set_match(jid, 0, json.dumps({"reason": "Not interested"})); st.rerun()
            elif skip_btn:
                if _bcols[_bi].button("Skip", key=f"sk_{key_prefix}_{jid}", use_container_width=True):
                    database.set_match(jid, 0, json.dumps({"reason": "Manually skipped"})); st.rerun()


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

@st.cache_resource(show_spinner=False)
def _init_db_once():
    database.init_db()
    return True

@st.cache_data(ttl=30, show_spinner=False)
def _get_stats(username: str) -> dict:
    return database.get_stats()

@st.cache_data(ttl=10, show_spinner=False)
def _has_resume_cached(username: str) -> bool:
    return bool(database.get_resume_content())

@st.cache_data(ttl=3600, show_spinner=False)   # run at most once per hour
def _cleanup_once(username: str, expiry_days: int = 30) -> int:
    return database.cleanup_old_jobs(days=expiry_days)

@st.cache_data(ttl=60, show_spinner=False)
def _load_config_cached(username: str) -> dict:
    return database.load_config()

_init_db_once()
_startup_cfg = database.load_config()
_cleanup_once(_username, int(_startup_cfg.get("job_expiry_days", 30)))
stats = _get_stats(_username)

_PAGES = ["Dashboard", "Search", "Matched Jobs", "Apply", "Tracker", "Settings", "Help"]

def _go(page_fragment: str):
    for p in _PAGES:
        if page_fragment in p:
            st.session_state["nav_page"]    = p
            st.session_state["sidebar_nav"] = p   # sync radio widget before rerun
            st.session_state["_nav_from_go"] = True
            break
    st.rerun()

if "nav_page" not in st.session_state:
    st.session_state["nav_page"] = _PAGES[0]

with st.sidebar:
    st.markdown("**:material/robot: Job Bot**")

    # If _go() was called, force the radio to the target page before it renders
    if st.session_state.pop("_nav_from_go", False):
        st.session_state["sidebar_nav"] = st.session_state["nav_page"]

    page = st.radio(
        "nav",
        _PAGES,
        label_visibility="collapsed",
        key="sidebar_nav",
    )
    st.session_state["nav_page"] = page
    st.divider()
    st.caption(
        f"{stats['total']} found · {stats['matched']} matched\n\n"
        f"{stats['applied']} applied · avg {stats['avg_score']}%"
    )
    st.divider()
    if _is_guest:
        st.caption("Browsing as guest")
        if st.button("Log in", use_container_width=True, type="primary"):
            st.session_state.pop("username", None)
            st.session_state.pop("is_guest", None)
            st.rerun()
    else:
        st.caption(f":material/person: {_username}")
        if st.button("Log out", use_container_width=True):
            _do_logout()
            st.rerun()


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

if "Dashboard" in page:
    st.title(":material/dashboard: Dashboard")

    if _is_guest:
        st.info("You're browsing as a guest. Log in to use all features.")

    _has_resume  = _has_resume_cached(_username)
    _has_jobs    = stats["total"] > 0
    _has_matches = stats["matched"] > 0
    _has_ai      = bool(os.environ.get("OPENROUTER_API_KEY"))

    if not _has_resume:   _active = 0
    elif not _has_jobs:   _active = 1
    elif not _has_matches: _active = 2
    else:                  _active = 3

    def _step(i):
        if i < _active:  return "done",   "#34d399", "Done"
        if i == _active: return "active",  "#4f8ef7", "Up next"
        return "",         "#2d3d55",      ""

    s0,c0,l0 = _step(0); s1,c1,l1 = _step(1)
    s2,c2,l2 = _step(2); s3,c3,l3 = _step(3)
    _mlabel = "Score with AI" if _has_ai else "Score matches"
    _mcmd   = ["rematch", "--ai"] if _has_ai else ["rematch"]

    sc1, sc2, sc3, sc4 = st.columns(4)
    with sc1:
        with st.container(border=True):
            _ic0 = ":material/check_circle:" if s0 == "done" else ":material/radio_button_checked:" if s0 == "active" else ":material/radio_button_unchecked:"
            st.markdown(f"{_ic0} **Step 1 — Upload resume**")
            st.caption("Settings → Resume tab. Needed for scoring.")
            if l0: st.badge(l0, color="green" if s0 == "done" else "blue" if s0 == "active" else "gray")
        if st.button("Open Settings →", key="sc1", use_container_width=True): _go("Settings")
    with sc2:
        with st.container(border=True):
            _ic1 = ":material/check_circle:" if s1 == "done" else ":material/radio_button_checked:" if s1 == "active" else ":material/radio_button_unchecked:"
            st.markdown(f"{_ic1} **Step 2 — Search jobs**")
            st.caption("Scan Israeli job boards and global remote listings.")
            if l1: st.badge(l1, color="green" if s1 == "done" else "blue" if s1 == "active" else "gray")
        if st.button("Open Search →", key="sc2", use_container_width=True): _go("Search")
    with sc3:
        with st.container(border=True):
            _ic2 = ":material/check_circle:" if s2 == "done" else ":material/radio_button_checked:" if s2 == "active" else ":material/radio_button_unchecked:"
            st.markdown(f"{_ic2} **Step 3 — Score matches**")
            st.caption("AI scoring (Llama 3)." if _has_ai else "Rule-based scoring (free).")
            if l2: st.badge(l2, color="green" if s2 == "done" else "blue" if s2 == "active" else "gray")
        if st.button(_mlabel, key="sc3_btn", use_container_width=True, disabled=not _has_jobs):
            if _has_resume:
                launch_task([PYTHON, "-u", "main.py"] + _mcmd, "task_rematch")
    with sc4:
        with st.container(border=True):
            _ic3 = ":material/check_circle:" if s3 == "done" else ":material/radio_button_checked:" if s3 == "active" else ":material/radio_button_unchecked:"
            st.markdown(f"{_ic3} **Step 4 — Apply**")
            st.caption("Review matched jobs and send applications.")
            if l3: st.badge(l3, color="green" if s3 == "done" else "blue" if s3 == "active" else "gray")
        if st.button("Open Apply →", key="sc4", use_container_width=True, disabled=not _has_matches): _go("Apply")

    with st.container(horizontal=True):
        st.metric(":material/search: Found",    stats["total"],           border=True)
        st.metric(":material/stars: Matched",   stats["matched"],         border=True)
        st.metric(":material/send: Applied",    stats["applied"],         border=True)
        st.metric(":material/block: Skipped",   stats["skipped"],         border=True)
        st.metric(":material/percent: Avg score", f'{stats["avg_score"]}%', border=True)

    if not _has_resume:
        st.caption(":material/info: Start by uploading your resume in **Settings → Resume**.")

    col1, col2, col3, col4 = st.columns(4)
    if col1.button("Search jobs",    use_container_width=True,
                   type="primary" if _active == 1 else "secondary"): _go("Search")
    if col2.button(_mlabel, use_container_width=True,
                   type="primary" if _active == 2 else "secondary",
                   disabled=not _has_jobs):
        if not _has_resume:
            st.warning("Upload your resume in Settings first.")
        else:
            launch_task([PYTHON, "-u", "main.py"] + _mcmd, "task_rematch")
    if col3.button("Review matches", use_container_width=True,
                   type="primary" if _active == 3 else "secondary",
                   disabled=not _has_matches): _go("Matched")
    if col4.button("Full pipeline",  use_container_width=True, disabled=not _has_resume):
        launch_task([PYTHON, "-u", "main.py", "run", "--auto"], "task_run")

    for key, label in [("task_run", "Full Pipeline"), ("task_rematch", "Score"), ("task_search", "Search")]:
        if st.session_state.get(key):   # only register fragment when task exists
            live_task_panel(key, label)

    if _has_matches:
        st.divider()
        st.caption("Recent matches")
        for job in database.get_jobs_by_status("matched")[:5]:
            _card(job, key_prefix=f"dash_{job.get('id','')}", show_score=True, skip_btn=True)


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

elif "Search" in page:
    _guest_block()
    st.title(":material/search: Search")
    st.caption("Search job boards for new listings. Configure sources in Settings.")

    cfg = load_config()
    all_titles = cfg.get("job_titles", [])
    selected_titles = []

    if not all_titles:
        st.info(
            "No job titles configured yet. "
            "Go to **Settings → Job categories**, pick your categories, then click **Save settings**."
        )
    else:
        st.caption("Job titles")

        # Version counter: incrementing forces the multiselect to re-init with the new default
        if "search_title_ver" not in st.session_state:
            st.session_state["search_title_ver"] = 0
        if "search_title_default" not in st.session_state:
            st.session_state["search_title_default"] = list(all_titles)
        # Drop stale entries if config changed
        st.session_state["search_title_default"] = [
            t for t in st.session_state["search_title_default"] if t in all_titles
        ]

        _tc1, _tc2, _ = st.columns([1, 1, 8])
        if _tc1.button("Select all", key="btn_sel_all"):
            st.session_state["search_title_default"] = list(all_titles)
            st.session_state["search_title_ver"] += 1
            st.rerun()
        if _tc2.button("Clear all", key="btn_clr_all"):
            st.session_state["search_title_default"] = []
            st.session_state["search_title_ver"] += 1
            st.rerun()

        selected_titles = st.multiselect(
            "titles",
            options=all_titles,
            default=st.session_state["search_title_default"],
            label_visibility="collapsed",
            key=f"search_ms_{st.session_state['search_title_ver']}",
        )
        # Persist current selection so it survives navigation and reruns
        st.session_state["search_title_default"] = list(selected_titles)

    _loc_opts = ["Israel (on-site + remote)", "Remote only", "Worldwide"]
    if "search_loc" not in st.session_state:
        _saved = cfg.get("location_mode", "Israel (on-site + remote)")
        st.session_state["search_loc"] = _saved if _saved in _loc_opts else "Israel (on-site + remote)"

    st.caption("Location")
    _loc_mode = st.segmented_control(
        "loc_mode",
        _loc_opts,
        default=st.session_state["search_loc"],
        label_visibility="collapsed",
        key="search_loc_radio",
    )
    if _loc_mode:
        st.session_state["search_loc"] = _loc_mode

    st.divider()

    _can_search = bool(selected_titles)
    if all_titles and not selected_titles:
        st.warning("Select at least one job title.")

    if st.button("Start search", type="primary", disabled=not _can_search):
        enabled_sources = cfg.get("selected_sources", [])
        cmd = [PYTHON, "-u", "main.py", "search"]
        for q in selected_titles:
            cmd.extend(["-q", q])
        if enabled_sources:
            cmd.extend(["--sources", ",".join(enabled_sources)])
        if _loc_mode == "Israel (on-site + remote)":
            cmd.extend(["--location", "israel"])
        elif _loc_mode == "Remote only":
            cmd.append("--remote")
        st.session_state.pop("search_result_shown", None)   # clear so results refresh after this new search
        launch_task(cmd, "task_search")

    live_task_panel("task_search", "Search")
    task_still_running = bool(st.session_state.get("task_search", {}).get("visible"))

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
        st.divider()
        st.caption(f"{stats['total']} total · {stats['found']} unscored · {stats['matched']} matched")

        if recent:
            st.caption(f":material/schedule: Found in last 24h — {len(recent)} jobs")

            search_filter = st.text_input("Filter", placeholder="Filter by title or company...", label_visibility="collapsed")

            display = recent
            if search_filter:
                fl = search_filter.lower()
                display = [j for j in recent if fl in (j.get("title") or "").lower()
                           or fl in (j.get("company") or "").lower()]

            for job in display[:150]:
                _card(job, key_prefix=f"srch_{job.get('id','')}", show_status=True)
        else:
            st.caption("No jobs found in the last 24 hours.")


# ---------------------------------------------------------------------------
# Matched Jobs
# ---------------------------------------------------------------------------

elif "Matched" in page:
    _guest_block()
    st.title(":material/stars: Matched Jobs")
    st.caption("Jobs scoring ≥70% against your profile.")

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

        st.caption(f":material/work: {len(filtered)} jobs across {len(grouped)} sources")

        for source, jobs in sorted(grouped.items(), key=lambda x: -len(x[1])):
            n = len(jobs)
            with st.expander(f"{source}  ·  {n} {'job' if n == 1 else 'jobs'}", expanded=True):
                for job in jobs:
                    _card(job, key_prefix=f"{source}_{job.get('id','')}", show_score=True, skip_btn=True)


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------

elif "Apply" in page:
    _guest_block()
    st.title(":material/send: Apply")

    matched = database.get_jobs_by_status("matched")
    snoozed = st.session_state.get("snoozed_jobs", set())
    matched = [j for j in matched if j["id"] not in snoozed]

    st.caption(f"{stats.get('applied', 0)} applied · {len(matched)} remaining")

    if not matched:
        st.info("No matched jobs to apply to. Run a search first.")
    else:
        for job in matched:
            _card(job, key_prefix="apply", show_score=True, apply_btns=True)


# ---------------------------------------------------------------------------
# Tracker
# ---------------------------------------------------------------------------

elif "Tracker" in page:
    _guest_block()
    import tracker as _tracker

    st.title(":material/track_changes: Tracker")
    st.caption("Update outcomes as you hear back from companies.")

    jobs = _tracker.get_all_jobs(username=_username)

    if not jobs:
        st.info("No applications tracked yet.")
    else:
        from collections import Counter
        sc = Counter(j.get("Status", "") for j in jobs)
        with st.container(horizontal=True):
            st.metric(":material/work: Total",      len(jobs),              border=True)
            st.metric(":material/send: Applied",    sc.get("Applied", 0),   border=True)
            st.metric(":material/chat: Interview",  sc.get("Interview", 0), border=True)
            st.metric(":material/check: Accepted",  sc.get("Accepted", 0),  border=True)
            st.metric(":material/close: Denied",    sc.get("Denied", 0),    border=True)

        import re as _re
        _safe_user = _re.sub(r"[^\w]", "_", _username.lower())
        _user_tracker = _tracker.TRACKER_DIR / f"tracker_{_safe_user}.xlsx"
        if _user_tracker.exists():
            with open(_user_tracker, "rb") as f:
                st.download_button("Download Excel", data=f.read(), file_name=_user_tracker.name,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

        st.divider()

        status_filter = st.selectbox("Filter", ["All"] + _tracker.STATUS_OPTIONS, label_visibility="collapsed")
        filtered = jobs if status_filter == "All" else [j for j in jobs if j.get("Status") == status_filter]

        st.caption(f"{len(filtered)} job{'s' if len(filtered) != 1 else ''}")

        status_color_map = {
            "Applied": "#60a5fa", "Manual - Pending": "#f59e0b",
            "Interview": "#34d399", "Accepted": "#34d399", "Denied": "#f87171",
        }

        _STATUS_BADGE_COLOR = {
            "Applied": "blue", "Manual - Pending": "orange",
            "Interview": "green", "Accepted": "green", "Denied": "red",
        }

        for i, job in enumerate(filtered):
            url     = job.get("URL", "")
            title   = job.get("Job Title", "Unknown")
            company = job.get("Company", "Unknown")
            status  = job.get("Status", "Applied")
            date    = job.get("Date Applied", "")
            score   = job.get("Match Score", "")
            meta    = " · ".join(p for p in [company, date, score] if p)

            with st.container(border=True):
                _ta, _tb = st.columns([5, 1])
                with _ta:
                    st.markdown(f"**{title}**")
                    if meta:
                        st.caption(meta)
                with _tb:
                    st.badge(status, color=_STATUS_BADGE_COLOR.get(status, "gray"))

                col_status, col_notes, col_save, col_open = st.columns([2, 3, 1, 1])
                with col_status:
                    new_status = st.selectbox("Status", _tracker.STATUS_OPTIONS,
                        index=_tracker.STATUS_OPTIONS.index(status) if status in _tracker.STATUS_OPTIONS else 0,
                        key=f"status_{i}", label_visibility="collapsed")
                with col_notes:
                    notes = st.text_input("Notes", value=job.get("Notes", "") or "",
                        key=f"notes_{i}", label_visibility="collapsed", placeholder="Notes...")
                with col_save:
                    if st.button(":material/save:", key=f"save_{i}", use_container_width=True, help="Save status & notes"):
                        _tracker.update_status(url, new_status, notes, username=_username)
                        st.toast("Saved.", icon=":material/check:")
                with col_open:
                    if url:
                        st.link_button(":material/open_in_new:", url, use_container_width=True, help="Open job posting")


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

elif "Settings" in page:
    _guest_block()
    st.title(":material/settings: Settings")
    st.caption("Configure your search, profile, and matching preferences.")

    cfg = load_config()

    # Save button at the top — all widget values are still collected below before saving
    _save_top = st.button("Save settings", type="primary", key="save_settings_top",
                          use_container_width=False)
    st.caption("Changes take effect after saving.")

    with st.expander(":material/description: Resume", expanded=True):
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
                st.toast(f"Parsed {uploaded.name} — {len(text):,} characters", icon=":material/check:")
                if profile_data.get("skills"):
                    st.markdown("  ".join(f":blue-badge[{s}]" for s in profile_data["skills"]))
            else:
                st.error(f"Could not parse {uploaded.name}.")

    with st.expander(":material/category: Job categories", expanded=True):
        st.caption("Select categories to populate your search titles, then click Save settings.")
        _cats = json.loads((BOT_DIR / "job_categories.json").read_text(encoding="utf-8"))
        saved_cats = cfg.get("selected_categories", [])
        selected_cats = []
        cat_cols = st.columns(3)
        for i, cat in enumerate(_cats.keys()):
            if cat_cols[i % 3].checkbox(cat, value=cat in saved_cats, key=f"cat_{i}"):
                selected_cats.append(cat)
        # Titles from selected categories
        cat_titles = []
        for cat in selected_cats:
            cat_titles.extend(_cats.get(cat, []))
        cat_titles = list(dict.fromkeys(cat_titles))  # deduplicate, preserve order
        if cat_titles:
            st.caption(f":material/check_circle: {len(cat_titles)} titles from selected categories")

    with st.expander(":material/edit: Custom job titles", expanded=False):
        st.caption("Extra titles to search for on top of the categories above. One per line.")
        custom_raw = st.text_area("Custom titles", value="\n".join(cfg.get("custom_job_titles", [])),
            height=140, label_visibility="collapsed", placeholder="e.g. Prompt Engineer\nAI Product Manager")
        custom_titles = [t.strip() for t in custom_raw.splitlines() if t.strip()]
        titles_raw = "\n".join(cat_titles + [t for t in custom_titles if t not in cat_titles])
        all_titles = cat_titles + [t for t in custom_titles if t not in cat_titles]
        st.caption(f"{len(all_titles)} total titles active")

    with st.expander(":material/public: Job sources", expanded=False):
        st.caption("Select which job boards to search. All 8 sources are enabled by default.")
        _SOURCE_MAP = {
            "Drushim (IL)":    "drushim",
            "Indeed Israel":   "indeed_il",
            "AllJobs (IL)":    "alljobs",
            "RemoteOK":        "remoteok",
            "Remotive":        "remotive",
            "Jobicy":          "jobicy",
            "Himalayas":       "himalayas",
            "Arbeitnow":       "arbeitnow",
            "The Muse":        "themuse",
            "HN Who's Hiring": "hn",
            "Working Nomads":  "workingnomads",
        }
        _all_src_keys = list(_SOURCE_MAP.values())
        _saved_sources = cfg.get("selected_sources", _all_src_keys)
        selected_sources_settings = []
        _src_cols = st.columns(3)
        for _si, (_slabel, _skey) in enumerate(_SOURCE_MAP.items()):
            if _src_cols[_si % 3].checkbox(_slabel, value=_skey in _saved_sources, key=f"src_{_skey}"):
                selected_sources_settings.append(_skey)

    with st.expander(":material/block: Company blacklist", expanded=False):
        st.caption("Jobs from these companies will be skipped automatically.")
        blacklist_raw = st.text_area("One per line", value="\n".join(cfg.get("blacklisted_companies", [])),
            height=120, label_visibility="collapsed", placeholder="Amazon\nUber\nMeta")

    with st.expander(":material/tune: Matching", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            threshold   = st.slider("Score threshold (%)", 50, 95, int(cfg.get("match_threshold", 70)))
        with col2:
            expiry_days = st.number_input("Expire jobs after (days)", min_value=7, max_value=90, value=int(cfg.get("job_expiry_days", 30)))
        _loc_opts_s = ["Israel (on-site + remote)", "Remote only", "Worldwide"]
        _cur_loc    = cfg.get("location_mode", "Israel (on-site + remote)")
        if _cur_loc not in _loc_opts_s:
            _cur_loc = "Israel (on-site + remote)"
        location_mode = st.segmented_control(
            "Default location for searches",
            _loc_opts_s,
            default=_cur_loc,
        )

    with st.expander(":material/person: Your profile", expanded=True):
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

    st.divider()

    if st.button("Save settings", type="primary", key="save_settings_bottom") or _save_top:
        cfg["selected_categories"]   = selected_cats
        cfg["custom_job_titles"]     = custom_titles
        cfg["job_titles"]            = all_titles
        cfg["selected_sources"]      = selected_sources_settings
        cfg["blacklisted_companies"] = [t.strip() for t in blacklist_raw.splitlines() if t.strip()]
        cfg["location_mode"]    = location_mode
        cfg["remote_only"]      = location_mode == "Remote only"   # keep for backward compat
        cfg["match_threshold"]  = threshold
        cfg["job_expiry_days"]  = expiry_days
        cfg["profile"] = {
            "name": name, "email": email, "phone": phone,
            "city": city, "website": website,
            "linkedin_handle": linkedin, "summary": summary,
        }
        save_config(cfg)
        st.toast("Settings saved.", icon=":material/check:")

    st.divider()
    with st.expander(":material/storage: Database", expanded=False):
        st.caption(f"Total jobs stored: {stats['total']} · Applied (kept forever): {stats['applied']}")
        col_a, col_b = st.columns(2)
        if col_a.button("Clean jobs older than 7 days", use_container_width=True):
            deleted = database.cleanup_old_jobs(days=7)
            _get_stats.clear()
            st.success(f"Removed {deleted} old jobs.")
            st.rerun()
        if col_b.button("Reset all scores for re-matching", use_container_width=True):
            count = database.reset_scores_for_rematch()
            _get_stats.clear()
            st.success(f"Reset {count} jobs.")
            st.rerun()


# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------

elif "Help" in page:
    st.title(":material/help: Help")
    st.caption("How to use Job Bot from start to finish.")

    st.markdown("""
    ### How it works

    Job Bot automates job searching in 4 steps. Follow them in order.

    ---

    **Step 1 — Upload your resume** (Settings → Resume)

    Upload a PDF or DOCX. The bot reads your skills, experience, and role title from it
    and uses this to score how well each job matches your profile.

    ---

    **Step 2 — Search jobs** (Search page)

    The bot scans up to 8 job boards simultaneously:
    RemoteOK, Arbeitnow, The Muse, HN Who's Hiring, Remotive, Jobicy, Working Nomads, Himalayas.

    Pick which job titles to search for and which sites to include, then click **Start search**.
    Results are saved to the database — running search again only adds new listings.

    ---

    **Step 3 — Score matches** (Dashboard → Score matches)

    Each saved job gets a score from 0–100 based on how well it matches your resume.

    - **Rule-based scoring** — fast, free, works always. Checks skills, seniority, location, language.
    - **AI scoring (Llama 3)** — smarter, uses your OpenRouter API key. Reads the full job description.

    Jobs scoring ≥70% are marked as **Matched** and appear in the Matched Jobs page.

    ---

    **Step 4 — Apply** (Apply page)

    Review each matched job. For every listing you can:
    - **Open** — go to the job posting
    - **Mark applied** — records it as applied, removes from the queue
    - **Keep for later** — hides it this session
    - **Not interested** — removes it permanently

    ---

    ### Pages

    | Page | What it does |
    |---|---|
    | Dashboard | Overview, step guide, quick actions |
    | Search | Run job searches across multiple boards |
    | Matched Jobs | Browse jobs that scored ≥70%, grouped by source |
    | Apply | Work through matched jobs one by one |
    | Tracker | Update application status (Interview, Accepted, Denied) |
    | Settings | Configure job titles, matching threshold, profile, resume |

    ---

    ### Tips

    - Run **Search** once a day or every few days to keep listings fresh.
    - Old jobs (not applied) are automatically deleted after 7 days.
    - Adjust the **score threshold** in Settings if too many or too few jobs match.
    - Add companies to the **blacklist** in Settings to automatically skip them.
    - The **Full pipeline** button on the Dashboard runs all 3 steps (search + score + apply queue) in one go.
    """)

