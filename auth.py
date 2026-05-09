"""User authentication for Job Bot using Supabase."""
from __future__ import annotations

import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional


def _get_client():
    from supabase import create_client
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_KEY", "")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_KEY environment variables must be set.")
    return create_client(url, key)


def init_auth_db():
    """Tables are created via the Supabase SQL editor — nothing to do here."""
    pass


_SALT = b"job_bot_2024_auth"


def _hash(password: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), _SALT, 260_000).hex()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def register(username: str, email: str, password: str) -> tuple[bool, str]:
    username = username.strip().lower()
    email    = email.strip().lower()

    if len(username) < 3:
        return False, "Username must be at least 3 characters."
    if len(password) < 6:
        return False, "Password must be at least 6 characters."
    if "@" not in email or "." not in email:
        return False, "Enter a valid email address."

    client = _get_client()

    if client.table("users").select("id").eq("username", username).execute().data:
        return False, "Username already taken."
    if client.table("users").select("id").eq("email", email).execute().data:
        return False, "Email already registered."

    try:
        client.table("users").insert({
            "username":      username,
            "email":         email,
            "password_hash": _hash(password),
            "created_at":    _now(),
        }).execute()
        _seed_config(client, username)
        return True, "Account created!"
    except Exception as e:
        return False, f"Could not create account: {e}"


def _seed_config(client, username: str):
    """Copy root config.json into Supabase configs table for new user."""
    if client.table("configs").select("id").eq("username", username).execute().data:
        return
    from pathlib import Path
    import json
    root_cfg = Path(__file__).parent / "config.json"
    if root_cfg.exists():
        cfg = json.loads(root_cfg.read_text(encoding="utf-8"))
        client.table("configs").insert({"username": username, "config": cfg}).execute()


def login(username: str, password: str) -> tuple[bool, str]:
    """Returns (ok, username_or_error_message)."""
    username = username.strip().lower()
    client   = _get_client()
    result   = client.table("users").select("username,password_hash").eq("username", username).execute()
    if not result.data:
        return False, "Incorrect username or password."
    user = result.data[0]
    if user["password_hash"] != _hash(password):
        return False, "Incorrect username or password."
    return True, user["username"]


def create_token(username: str, days: int = 30) -> str:
    token   = secrets.token_urlsafe(40)
    expires = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()
    _get_client().table("sessions").insert({
        "token":      token,
        "username":   username,
        "expires_at": expires,
        "created_at": _now(),
    }).execute()
    return token


def validate_token(token: str) -> Optional[str]:
    """Return username if token is valid and not expired, else None."""
    if not token:
        return None
    now    = _now()
    result = _get_client().table("sessions").select("username") \
        .eq("token", token).gt("expires_at", now).execute()
    return result.data[0]["username"] if result.data else None


def revoke_token(token: str):
    if token:
        _get_client().table("sessions").delete().eq("token", token).execute()


def get_all_users() -> list[dict]:
    result = _get_client().table("users").select("username,email,created_at") \
        .order("created_at", desc=True).execute()
    return result.data or []
