"""SQLite database for tracking job applications."""
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).parent / "jobs.db"


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS jobs (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                source          TEXT NOT NULL,
                external_id     TEXT,
                title           TEXT NOT NULL,
                company         TEXT,
                url             TEXT UNIQUE,
                location        TEXT,
                salary          TEXT,
                description     TEXT,
                requirements    TEXT,
                match_score     REAL,
                match_reason    TEXT,
                status          TEXT DEFAULT 'found',
                found_at        TEXT DEFAULT (datetime('now')),
                applied_at      TEXT,
                notes           TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
            CREATE INDEX IF NOT EXISTS idx_jobs_score  ON jobs(match_score);

            CREATE TABLE IF NOT EXISTS resumes (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                path        TEXT UNIQUE NOT NULL,
                content     TEXT,
                parsed_at   TEXT DEFAULT (datetime('now'))
            );
        """)


def upsert_job(
    source: str,
    title: str,
    url: str,
    company: str = "",
    location: str = "",
    salary: str = "",
    description: str = "",
    external_id: str = "",
) -> Optional[int]:
    """Insert a job if it doesn't already exist. Returns row id or None if duplicate."""
    with get_conn() as conn:
        existing = conn.execute("SELECT id FROM jobs WHERE url = ?", (url,)).fetchone()
        if existing:
            return None
        cur = conn.execute(
            """INSERT INTO jobs (source, external_id, title, company, url, location,
                                 salary, description)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (source, external_id, title, company, url, location, salary, description),
        )
        return cur.lastrowid


def set_match(job_id: int, score: float, reason: str) -> None:
    status = "matched" if score >= 70 else "skipped"
    with get_conn() as conn:
        conn.execute(
            "UPDATE jobs SET match_score=?, match_reason=?, status=? WHERE id=?",
            (score, reason, status, job_id),
        )


def set_applied(job_id: int, notes: str = "") -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE jobs SET status='applied', applied_at=?, notes=? WHERE id=?",
            (datetime.now().isoformat(), notes, job_id),
        )


def set_failed(job_id: int, reason: str = "") -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE jobs SET status='failed', notes=? WHERE id=?",
            (reason, job_id),
        )


def get_jobs_by_status(status: str) -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM jobs WHERE status=? ORDER BY match_score DESC",
            (status,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_recent_jobs(hours: int = 24, limit: int = 200) -> list:
    """Return jobs added in the last N hours, newest first."""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT * FROM jobs
               WHERE found_at >= datetime('now', ?)
               ORDER BY found_at DESC
               LIMIT ?""",
            (f"-{hours} hours", limit),
        ).fetchall()
    return [dict(r) for r in rows]


def get_unmatched_jobs() -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM jobs WHERE match_score IS NULL ORDER BY id",
        ).fetchall()
    return [dict(r) for r in rows]


def get_stats() -> dict:
    with get_conn() as conn:
        total   = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        found   = conn.execute("SELECT COUNT(*) FROM jobs WHERE status='found'").fetchone()[0]
        matched = conn.execute("SELECT COUNT(*) FROM jobs WHERE status='matched'").fetchone()[0]
        skipped = conn.execute("SELECT COUNT(*) FROM jobs WHERE status='skipped'").fetchone()[0]
        applied = conn.execute("SELECT COUNT(*) FROM jobs WHERE status='applied'").fetchone()[0]
        failed  = conn.execute("SELECT COUNT(*) FROM jobs WHERE status='failed'").fetchone()[0]
        avg_score = conn.execute(
            "SELECT AVG(match_score) FROM jobs WHERE match_score IS NOT NULL"
        ).fetchone()[0]
    return {
        "total": total,
        "found": found,
        "matched": matched,
        "skipped": skipped,
        "applied": applied,
        "failed": failed,
        "avg_score": round(avg_score or 0, 1),
    }


def expire_old_jobs(days: int = 30) -> int:
    """Delete jobs older than `days` days that haven't been applied to. Returns count deleted."""
    with get_conn() as conn:
        cur = conn.execute(
            """DELETE FROM jobs
               WHERE status NOT IN ('applied')
               AND found_at < datetime('now', ?)""",
            (f"-{days} days",),
        )
        return cur.rowcount


def reset_scores_for_rematch() -> int:
    """Reset all non-applied jobs back to unscored so they can be re-matched. Returns count reset."""
    with get_conn() as conn:
        cur = conn.execute(
            """UPDATE jobs
               SET match_score = NULL, match_reason = NULL, status = 'found'
               WHERE status NOT IN ('applied')"""
        )
        return cur.rowcount


def save_resume(path: str, content: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO resumes (path, content, parsed_at) VALUES (?, ?, ?)",
            (path, content, datetime.now().isoformat()),
        )


def get_resume_content() -> str:
    """Return the combined text of all parsed resumes."""
    with get_conn() as conn:
        rows = conn.execute("SELECT content FROM resumes ORDER BY parsed_at DESC").fetchall()
    return "\n\n---RESUME VERSION---\n\n".join(r[0] for r in rows if r[0])
