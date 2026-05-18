"""MongoDB database for tracking job applications."""
import os
import threading
from datetime import datetime, timedelta
from typing import Optional

import certifi
from pymongo import MongoClient, ASCENDING, DESCENDING

_client = None
_mongo_db = None
_local = threading.local()


def _get_db():
    global _client, _mongo_db
    if _mongo_db is None:
        uri = os.environ.get("MONGODB_URI", "mongodb://localhost:27017")
        _client = MongoClient(uri, tlsCAFile=certifi.where(), serverSelectionTimeoutMS=5000)
        _mongo_db = _client["job_bot"]
    return _mongo_db


def set_username(username: str):
    """Set the username for the current thread (per-user isolation)."""
    _local.username = username.lower()



def _uname() -> str:
    return getattr(_local, "username", "default")


def _doc(row) -> dict:
    """Convert MongoDB document to plain dict with string 'id' field."""
    d = dict(row)
    d["id"] = str(d.pop("_id"))
    return d


def init_db() -> None:
    db = _get_db()
    db.jobs.create_index([("username", ASCENDING), ("url", ASCENDING)], unique=True, sparse=True)
    db.jobs.create_index([("username", ASCENDING), ("status", ASCENDING)])
    db.jobs.create_index([("username", ASCENDING), ("match_score", DESCENDING)])
    db.resumes.create_index([("username", ASCENDING), ("path", ASCENDING)], unique=True)
    db.configs.create_index("username", unique=True)
    db.rate_limits.create_index("source", unique=True)


# ---------------------------------------------------------------------------
# Rate-limit registry (global — not per-user, limits apply to the shared IP)
# ---------------------------------------------------------------------------

def set_rate_limit(source: str, hours: float = 1.0) -> None:
    """Record that a source is rate-limited for `hours` hours."""
    db = _get_db()
    now        = datetime.utcnow()
    expires_at = (now + timedelta(hours=hours)).isoformat()
    db.rate_limits.update_one(
        {"source": source},
        {"$set": {"expires_at": expires_at, "blocked_at": now.isoformat(), "hours": hours}},
        upsert=True,
    )


def get_rate_limits() -> dict:
    """Return {source: {"expires_at": iso, "hours": n}} for all active limits."""
    db  = _get_db()
    now = datetime.utcnow().isoformat()
    return {
        doc["source"]: {"expires_at": doc["expires_at"], "hours": doc.get("hours", 1)}
        for doc in db.rate_limits.find({"expires_at": {"$gt": now}})
    }


def clear_rate_limit(source: str) -> None:
    """Remove the rate limit for a source (called after a successful request)."""
    _get_db().rate_limits.delete_one({"source": source})


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
    if not url:
        return None
    db = _get_db()
    username = _uname()
    # Single atomic insert — catches duplicate URL without a separate find_one round-trip.
    # PyMongo raises DuplicateKeyError when the unique index (username, url) is violated.
    try:
        result = db.jobs.insert_one({
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
            "found_at":     datetime.utcnow().isoformat(),
            "applied_at":   None,
            "notes":        "",
        })
        return str(result.inserted_id)
    except Exception:
        return None  # DuplicateKeyError or transient error — job already exists


def set_match(job_id, score: float, reason: str, threshold: float = 70.0) -> None:
    from bson import ObjectId
    db = _get_db()
    status = "matched" if score >= threshold else "skipped"
    db.jobs.update_one(
        {"_id": ObjectId(job_id)},
        {"$set": {"match_score": score, "match_reason": reason, "status": status}},
    )


def set_applied(job_id, notes: str = "") -> None:
    from bson import ObjectId
    db = _get_db()
    db.jobs.update_one(
        {"_id": ObjectId(job_id)},
        {"$set": {"status": "applied", "applied_at": datetime.utcnow().isoformat(), "notes": notes}},
    )


def set_failed(job_id, reason: str = "") -> None:
    from bson import ObjectId
    db = _get_db()
    db.jobs.update_one(
        {"_id": ObjectId(job_id)},
        {"$set": {"status": "failed", "notes": reason}},
    )


def get_jobs_by_status(status: str) -> list:
    db = _get_db()
    rows = db.jobs.find(
        {"username": _uname(), "status": status},
        sort=[("match_score", DESCENDING)],
    )
    return [_doc(r) for r in rows]


def get_recent_jobs(hours: int = 24, limit: int = 200) -> list:
    db = _get_db()
    cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
    rows = db.jobs.find(
        {"username": _uname(), "found_at": {"$gte": cutoff}},
        sort=[("found_at", DESCENDING)],
        limit=limit,
    )
    return [_doc(r) for r in rows]


def cleanup_old_jobs(days: int = 7) -> int:
    db = _get_db()
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
    result = db.jobs.delete_many({
        "username": _uname(),
        "status":   {"$ne": "applied"},
        "found_at": {"$lt": cutoff},
    })
    return result.deleted_count


def expire_old_jobs(days: int = 30) -> int:
    return cleanup_old_jobs(days)


def get_unmatched_jobs() -> list:
    db = _get_db()
    rows = db.jobs.find({"username": _uname(), "match_score": None})
    return [_doc(r) for r in rows]


def get_stats() -> dict:
    db = _get_db()
    username = _uname()
    total   = db.jobs.count_documents({"username": username})
    found   = db.jobs.count_documents({"username": username, "status": "found"})
    matched = db.jobs.count_documents({"username": username, "status": "matched"})
    skipped = db.jobs.count_documents({"username": username, "status": "skipped"})
    applied = db.jobs.count_documents({"username": username, "status": "applied"})
    failed  = db.jobs.count_documents({"username": username, "status": "failed"})
    pipeline = [
        {"$match": {"username": username, "match_score": {"$ne": None}}},
        {"$group": {"_id": None, "avg": {"$avg": "$match_score"}}},
    ]
    avg_result = list(db.jobs.aggregate(pipeline))
    avg_score = avg_result[0]["avg"] if avg_result else 0
    return {
        "total":     total,
        "found":     found,
        "matched":   matched,
        "skipped":   skipped,
        "applied":   applied,
        "failed":    failed,
        "avg_score": round(avg_score or 0, 1),
    }


def reset_scores_for_rematch() -> int:
    db = _get_db()
    result = db.jobs.update_many(
        {"username": _uname(), "status": {"$ne": "applied"}},
        {"$set": {"match_score": None, "match_reason": None, "status": "found"}},
    )
    return result.modified_count


def save_resume(path: str, content: str) -> None:
    db = _get_db()
    db.resumes.update_one(
        {"username": _uname(), "path": path},
        {"$set": {"content": content, "parsed_at": datetime.utcnow().isoformat()}},
        upsert=True,
    )


def get_resume_content() -> str:
    db = _get_db()
    rows = list(db.resumes.find(
        {"username": _uname()},
        sort=[("parsed_at", DESCENDING)],
    ))
    return "\n\n---RESUME VERSION---\n\n".join(r["content"] for r in rows if r.get("content"))


def load_config() -> dict:
    db = _get_db()
    doc = db.configs.find_one({"username": _uname()})
    if doc:
        return doc.get("config", {})
    from pathlib import Path
    root_cfg = Path(__file__).parent / "config.json"
    if root_cfg.exists():
        import json
        return json.loads(root_cfg.read_text(encoding="utf-8"))
    return {}


def save_config(cfg: dict) -> None:
    db = _get_db()
    db.configs.update_one(
        {"username": _uname()},
        {"$set": {"config": cfg}},
        upsert=True,
    )
