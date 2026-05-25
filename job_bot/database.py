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
    # Per-user rate limits — drop the old global index first (safe to ignore if missing)
    try:
        db.rate_limits.drop_index("source_1")
    except Exception:
        pass
    db.rate_limits.create_index(
        [("username", ASCENDING), ("source", ASCENDING)], unique=True
    )


# ---------------------------------------------------------------------------
# Rate-limit registry — per-user so one user's block doesn't affect others
# ---------------------------------------------------------------------------

def set_rate_limit(source: str, hours: float = 1.0) -> None:
    """Record that a source is rate-limited for this user for `hours` hours."""
    db       = _get_db()
    username = _uname()
    now      = datetime.utcnow()
    expires_at = (now + timedelta(hours=hours)).isoformat()
    db.rate_limits.update_one(
        {"username": username, "source": source},
        {"$set": {"username": username, "expires_at": expires_at,
                  "blocked_at": now.isoformat(), "hours": hours}},
        upsert=True,
    )


def get_rate_limits() -> dict:
    """Return {source: {"expires_at": iso, "hours": n}} for this user's active limits."""
    db       = _get_db()
    username = _uname()
    now      = datetime.utcnow().isoformat()
    return {
        doc["source"]: {"expires_at": doc["expires_at"], "hours": doc.get("hours", 1)}
        for doc in db.rate_limits.find({"username": username, "expires_at": {"$gt": now}})
    }


def clear_rate_limit(source: str) -> None:
    """Remove the rate limit for this user on a source (called after a successful request)."""
    _get_db().rate_limits.delete_one({"username": _uname(), "source": source})


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


def set_applied(job_id, method: str = "") -> None:
    from bson import ObjectId
    db = _get_db()
    db.jobs.update_one(
        {"_id": ObjectId(job_id)},
        {"$set": {
            "status":         "applied",
            "applied_at":     datetime.utcnow().isoformat(),
            "method":         method,          # e.g. "AI Email", "AI Form"
            "tracker_status": "Applied",       # follow-up status (editable in Tracker)
            "tracker_notes":  "",              # user notes (editable in Tracker)
        }},
    )


def update_tracker_status(job_id: str, tracker_status: str, tracker_notes: str = "") -> None:
    """Update the follow-up status and notes for a tracked (applied) job."""
    from bson import ObjectId
    db = _get_db()
    db.jobs.update_one(
        {"_id": ObjectId(job_id)},
        {"$set": {"tracker_status": tracker_status, "tracker_notes": tracker_notes}},
    )


def get_applied_jobs() -> list:
    """Return all applied jobs sorted by most-recently applied."""
    db = _get_db()
    rows = db.jobs.find(
        {"username": _uname(), "status": "applied"},
        sort=[("applied_at", DESCENDING)],
    )
    return [_doc(r) for r in rows]


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




def get_unmatched_jobs() -> list:
    db = _get_db()
    rows = db.jobs.find({"username": _uname(), "match_score": None})
    return [_doc(r) for r in rows]


def get_stats() -> dict:
    """Single aggregation pipeline — one DB round-trip instead of 6."""
    db       = _get_db()
    username = _uname()
    pipeline = [
        {"$match": {"username": username}},
        {"$facet": {
            "by_status": [{"$group": {"_id": "$status", "n": {"$sum": 1}}}],
            "avg_score": [
                {"$match": {"match_score": {"$ne": None}}},
                {"$group": {"_id": None, "avg": {"$avg": "$match_score"}}},
            ],
        }},
    ]
    result   = list(db.jobs.aggregate(pipeline))
    facet    = result[0] if result else {"by_status": [], "avg_score": []}
    counts   = {doc["_id"]: doc["n"] for doc in facet.get("by_status", [])}
    avg_raw  = facet.get("avg_score", [])
    avg_score = avg_raw[0]["avg"] if avg_raw else 0
    return {
        "total":     sum(counts.values()),
        "found":     counts.get("found",   0),
        "matched":   counts.get("matched", 0),
        "skipped":   counts.get("skipped", 0),
        "applied":   counts.get("applied", 0),
        "failed":    counts.get("failed",  0),
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


def save_resume_file(filename: str, data: bytes) -> None:
    """Store the original resume file bytes so they can be attached to form applications."""
    from bson import Binary
    db = _get_db()
    db.resumes.update_one(
        {"username": _uname()},
        {"$set": {
            "filename":     filename,
            "file_bytes":   Binary(data),
            "file_updated": datetime.utcnow().isoformat(),
        }},
        upsert=True,
    )


def get_resume_file() -> tuple:
    """Return (filename, bytes) for the stored resume file, or ('', b'')."""
    db = _get_db()
    doc = db.resumes.find_one(
        {"username": _uname(), "file_bytes": {"$exists": True}},
        sort=[("file_updated", DESCENDING)],
    )
    if doc and doc.get("file_bytes"):
        try:
            return doc.get("filename", "resume.pdf"), bytes(doc["file_bytes"])
        except Exception:
            pass
    return "", b""


def has_resume() -> bool:
    """Cheap existence check — doesn't load resume text."""
    return _get_db().resumes.count_documents({"username": _uname()}) > 0


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
    from job_bot.paths import DEFAULT_CONFIG_PATH
    if DEFAULT_CONFIG_PATH.exists():
        root_cfg = DEFAULT_CONFIG_PATH
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
