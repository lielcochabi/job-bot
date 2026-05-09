"""Supabase (PostgreSQL) database for tracking job applications."""
import os
import threading
from datetime import datetime, timedelta, timezone
from typing import Optional

_client = None
_local = threading.local()


def _get_client():
    global _client
    if _client is None:
        from supabase import create_client
        url = os.environ.get("SUPABASE_URL", "")
        key = os.environ.get("SUPABASE_KEY", "")
        if not url or not key:
            raise RuntimeError("SUPABASE_URL and SUPABASE_KEY environment variables must be set.")
        _client = create_client(url, key)
    return _client


def set_username(username: str):
    """Set the username for the current thread (per-user isolation)."""
    _local.username = username.lower()


def set_db_path(path):
    """No-op — kept for backward compatibility."""
    pass


def _uname() -> str:
    return getattr(_local, "username", "default")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db() -> None:
    """Tables are created via the Supabase SQL editor — nothing to do here."""
    pass


def upsert_job(
    source: str,
    title: str,
    url: str,
    company: str = "",
    location: str = "",
    salary: str = "",
    description: str = "",
    external_id: str = "",
) -> Optional[str]:
    """Insert a job if the URL doesn't already exist. Returns id or None if duplicate."""
    if not url:
        return None
    client  = _get_client()
    username = _uname()

    existing = client.table("jobs").select("id").eq("username", username).eq("url", url).execute()
    if existing.data:
        return None

    result = client.table("jobs").insert({
        "username":     username,
        "source":       source,
        "external_id":  external_id,
        "title":        title,
        "company":      company,
        "url":          url,
        "location":     location,
        "salary":       salary,
        "description":  description,
        "requirements": "",
        "match_score":  None,
        "match_reason": None,
        "status":       "found",
        "found_at":     _now(),
        "applied_at":   None,
        "notes":        "",
    }).execute()
    return result.data[0]["id"] if result.data else None


def set_match(job_id, score: float, reason: str) -> None:
    status = "matched" if score >= 70 else "skipped"
    _get_client().table("jobs").update({
        "match_score":  score,
        "match_reason": reason,
        "status":       status,
    }).eq("id", job_id).execute()


def set_applied(job_id, notes: str = "") -> None:
    _get_client().table("jobs").update({
        "status":     "applied",
        "applied_at": _now(),
        "notes":      notes,
    }).eq("id", job_id).execute()


def set_failed(job_id, reason: str = "") -> None:
    _get_client().table("jobs").update({
        "status": "failed",
        "notes":  reason,
    }).eq("id", job_id).execute()


def get_jobs_by_status(status: str) -> list:
    result = _get_client().table("jobs").select("*") \
        .eq("username", _uname()).eq("status", status) \
        .order("match_score", desc=True).execute()
    return result.data or []


def get_recent_jobs(hours: int = 24, limit: int = 200) -> list:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    result = _get_client().table("jobs").select("*") \
        .eq("username", _uname()).gte("found_at", cutoff) \
        .order("found_at", desc=True).limit(limit).execute()
    return result.data or []


def cleanup_old_jobs(days: int = 7) -> int:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    result = _get_client().table("jobs").delete() \
        .eq("username", _uname()).neq("status", "applied").lt("found_at", cutoff).execute()
    return len(result.data) if result.data else 0


def expire_old_jobs(days: int = 30) -> int:
    return cleanup_old_jobs(days)


def get_unmatched_jobs() -> list:
    result = _get_client().table("jobs").select("*") \
        .eq("username", _uname()).is_("match_score", "null").execute()
    return result.data or []


def get_stats() -> dict:
    client   = _get_client()
    username = _uname()

    def _count(status=None):
        q = client.table("jobs").select("*", count="exact").eq("username", username)
        if status:
            q = q.eq("status", status)
        return q.execute().count or 0

    total   = _count()
    found   = _count("found")
    matched = _count("matched")
    skipped = _count("skipped")
    applied = _count("applied")
    failed  = _count("failed")

    scores_res = client.table("jobs").select("match_score") \
        .eq("username", username).not_.is_("match_score", "null").execute()
    scores = [r["match_score"] for r in (scores_res.data or []) if r.get("match_score") is not None]
    avg_score = sum(scores) / len(scores) if scores else 0

    return {
        "total":   total,
        "found":   found,
        "matched": matched,
        "skipped": skipped,
        "applied": applied,
        "failed":  failed,
        "avg_score": round(avg_score, 1),
    }


def reset_scores_for_rematch() -> int:
    result = _get_client().table("jobs").update({
        "match_score":  None,
        "match_reason": None,
        "status":       "found",
    }).eq("username", _uname()).neq("status", "applied").execute()
    return len(result.data) if result.data else 0


def save_resume(path: str, content: str) -> None:
    _get_client().table("resumes").upsert({
        "username":  _uname(),
        "path":      path,
        "content":   content,
        "parsed_at": _now(),
    }, on_conflict="username,path").execute()


def get_resume_content() -> str:
    result = _get_client().table("resumes").select("content") \
        .eq("username", _uname()).order("parsed_at", desc=True).execute()
    return "\n\n---RESUME VERSION---\n\n".join(
        r["content"] for r in (result.data or []) if r.get("content")
    )


def load_config() -> dict:
    result = _get_client().table("configs").select("config") \
        .eq("username", _uname()).execute()
    if result.data:
        return result.data[0].get("config") or {}
    # Fall back to root config.json for defaults
    from pathlib import Path
    import json
    root_cfg = Path(__file__).parent / "config.json"
    if root_cfg.exists():
        return json.loads(root_cfg.read_text(encoding="utf-8"))
    return {}


def save_config(cfg: dict) -> None:
    _get_client().table("configs").upsert({
        "username":   _uname(),
        "config":     cfg,
        "updated_at": _now(),
    }, on_conflict="username").execute()
