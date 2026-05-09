"""User authentication for Job Bot using MongoDB."""
from __future__ import annotations

import hashlib
import os
import secrets
from datetime import datetime, timedelta
from typing import Optional

from pymongo import MongoClient

_client = None
_mongo_db = None


def _get_db():
    global _client, _mongo_db
    if _mongo_db is None:
        uri = os.environ.get("MONGODB_URI", "mongodb://localhost:27017")
        _client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        _mongo_db = _client["job_bot"]
    return _mongo_db


def init_auth_db():
    db = _get_db()
    db.users.create_index("username", unique=True)
    db.users.create_index("email", unique=True)
    db.sessions.create_index("token", unique=True)
    db.sessions.create_index("expires_at")


_SALT = b"job_bot_2024_auth"


def _hash(password: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), _SALT, 260_000).hex()


def register(username: str, email: str, password: str) -> tuple[bool, str]:
    username = username.strip().lower()
    email    = email.strip().lower()

    if len(username) < 3:
        return False, "Username must be at least 3 characters."
    if len(password) < 6:
        return False, "Password must be at least 6 characters."
    if "@" not in email or "." not in email:
        return False, "Enter a valid email address."

    db = _get_db()
    if db.users.find_one({"username": username}):
        return False, "Username already taken."
    if db.users.find_one({"email": email}):
        return False, "Email already registered."

    try:
        db.users.insert_one({
            "username":      username,
            "email":         email,
            "password_hash": _hash(password),
            "created_at":    datetime.utcnow().isoformat(),
        })
        _seed_config(db, username)
        return True, "Account created!"
    except Exception as e:
        return False, f"Could not create account: {e}"


def _seed_config(db, username: str):
    """Copy root config.json into MongoDB configs collection for new user."""
    if db.configs.find_one({"username": username}):
        return
    from pathlib import Path
    import json
    root_cfg = Path(__file__).parent / "config.json"
    if root_cfg.exists():
        cfg = json.loads(root_cfg.read_text(encoding="utf-8"))
        db.configs.insert_one({"username": username, "config": cfg})


def login(username: str, password: str) -> tuple[bool, str]:
    """Returns (ok, username_or_error_message)."""
    username = username.strip().lower()
    db = _get_db()
    user = db.users.find_one({"username": username})
    if not user or user["password_hash"] != _hash(password):
        return False, "Incorrect username or password."
    return True, user["username"]


def create_token(username: str, days: int = 30) -> str:
    token   = secrets.token_urlsafe(40)
    expires = (datetime.utcnow() + timedelta(days=days)).isoformat()
    db = _get_db()
    db.sessions.insert_one({
        "token":      token,
        "username":   username,
        "expires_at": expires,
        "created_at": datetime.utcnow().isoformat(),
    })
    return token


def validate_token(token: str) -> Optional[str]:
    """Return username if token is valid and not expired, else None."""
    if not token:
        return None
    db = _get_db()
    now = datetime.utcnow().isoformat()
    session = db.sessions.find_one({"token": token, "expires_at": {"$gt": now}})
    return session["username"] if session else None


def revoke_token(token: str):
    if token:
        db = _get_db()
        db.sessions.delete_one({"token": token})


def get_all_users() -> list[dict]:
    """Return list of all registered users (for admin view)."""
    db = _get_db()
    return [
        {"username": u["username"], "email": u["email"], "created_at": u.get("created_at", "")}
        for u in db.users.find({}, sort=[("created_at", -1)])
    ]
