"""
User authentication for Job Bot.
- Users stored in auth.db (shared)
- Per-user data in user_data/{username}/
"""
from __future__ import annotations

import hashlib
import secrets
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

AUTH_DB = Path(__file__).parent / "auth.db"
USER_DATA_ROOT = Path(__file__).parent / "user_data"


# ---------------------------------------------------------------------------
# DB setup
# ---------------------------------------------------------------------------

def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(AUTH_DB)
    c.row_factory = sqlite3.Row
    return c


def init_auth_db():
    with _conn() as c:
        c.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                username      TEXT UNIQUE NOT NULL COLLATE NOCASE,
                email         TEXT UNIQUE NOT NULL COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                created_at    TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token      TEXT PRIMARY KEY,
                username   TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            );
        """)


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

_SALT = b"job_bot_2024_auth"


def _hash(password: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), _SALT, 260_000).hex()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def register(username: str, email: str, password: str) -> tuple[bool, str]:
    username = username.strip().lower()
    email    = email.strip().lower()

    if len(username) < 3:
        return False, "Username must be at least 3 characters."
    if not username.isalnum() and "-" not in username and "_" not in username:
        return False, "Username can only contain letters, numbers, - and _."
    if len(password) < 6:
        return False, "Password must be at least 6 characters."
    if "@" not in email or "." not in email:
        return False, "Enter a valid email address."

    try:
        with _conn() as c:
            c.execute(
                "INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)",
                (username, email, _hash(password)),
            )
        # Create user data directory with default config
        user_dir = get_user_dir(username)
        _seed_config(user_dir)
        return True, "Account created!"
    except sqlite3.IntegrityError as e:
        err = str(e).lower()
        if "username" in err:
            return False, "Username already taken."
        if "email" in err:
            return False, "Email already registered."
        return False, "Could not create account."


def login(username: str, password: str) -> tuple[bool, str]:
    """Returns (ok, username_or_error_message)."""
    username = username.strip().lower()
    with _conn() as c:
        row = c.execute(
            "SELECT username, password_hash FROM users WHERE username = ?",
            (username,),
        ).fetchone()

    if not row or row["password_hash"] != _hash(password):
        return False, "Incorrect username or password."

    return True, row["username"]


def create_token(username: str, days: int = 30) -> str:
    token = secrets.token_urlsafe(40)
    expires = (datetime.utcnow() + timedelta(days=days)).isoformat()
    with _conn() as c:
        c.execute(
            "INSERT INTO sessions (token, username, expires_at) VALUES (?, ?, ?)",
            (token, username, expires),
        )
    return token


def validate_token(token: str) -> str | None:
    """Return username if token is valid, else None."""
    if not token:
        return None
    with _conn() as c:
        row = c.execute(
            "SELECT username FROM sessions WHERE token = ? AND expires_at > datetime('now')",
            (token,),
        ).fetchone()
    return row["username"] if row else None


def revoke_token(token: str):
    if token:
        with _conn() as c:
            c.execute("DELETE FROM sessions WHERE token = ?", (token,))


def get_user_dir(username: str) -> Path:
    """Return (and create) the per-user data directory."""
    d = USER_DATA_ROOT / username.lower()
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _seed_config(user_dir: Path):
    """Copy root config.json to user dir if they don't have one yet."""
    user_cfg = user_dir / "config.json"
    if user_cfg.exists():
        return
    root_cfg = Path(__file__).parent / "config.json"
    if root_cfg.exists():
        import shutil
        shutil.copy(root_cfg, user_cfg)
