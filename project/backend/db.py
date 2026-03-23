"""
SQLite storage layer for transcripts, summaries, and actionables.
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).resolve().parent.parent.parent / "output" / "content_listener.db"


def _get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = _get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS transcripts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT NOT NULL,
            platform TEXT,
            title TEXT,
            transcript TEXT,
            source TEXT,
            duration_seconds REAL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS summaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transcript_id INTEGER REFERENCES transcripts(id),
            summary TEXT,
            key_points TEXT,
            context TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS actionables (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            objective TEXT,
            question TEXT,
            answer TEXT,
            actionables TEXT,
            confidence TEXT,
            transcript_ids TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_type TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            input_data TEXT,
            result_data TEXT,
            error TEXT,
            progress TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
    """)
    conn.commit()
    conn.close()


def save_transcript(url: str, platform: str, title: str, transcript: str,
                    source: str, duration_seconds: Optional[float] = None) -> int:
    conn = _get_conn()
    cur = conn.execute(
        """INSERT INTO transcripts (url, platform, title, transcript, source, duration_seconds, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (url, platform, title, transcript, source, duration_seconds,
         datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    row_id = cur.lastrowid
    conn.close()
    return row_id


def save_summary(transcript_id: int, summary: str, key_points: list[str],
                 context: str = "") -> int:
    conn = _get_conn()
    cur = conn.execute(
        """INSERT INTO summaries (transcript_id, summary, key_points, context, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (transcript_id, summary, json.dumps(key_points), context,
         datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    row_id = cur.lastrowid
    conn.close()
    return row_id


def save_actionable(objective: str, question: str, answer: str,
                    actionables: list[str], confidence: str,
                    transcript_ids: list[int]) -> int:
    conn = _get_conn()
    cur = conn.execute(
        """INSERT INTO actionables (objective, question, answer, actionables, confidence, transcript_ids, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (objective, question, answer, json.dumps(actionables), confidence,
         json.dumps(transcript_ids), datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    row_id = cur.lastrowid
    conn.close()
    return row_id


def create_job(job_type: str, input_data: dict) -> int:
    conn = _get_conn()
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        """INSERT INTO jobs (job_type, status, input_data, created_at, updated_at)
           VALUES (?, 'pending', ?, ?, ?)""",
        (job_type, json.dumps(input_data), now, now),
    )
    conn.commit()
    row_id = cur.lastrowid
    conn.close()
    return row_id


def update_job(job_id: int, status: str, result_data: Optional[dict] = None,
               error: Optional[str] = None):
    conn = _get_conn()
    conn.execute(
        """UPDATE jobs SET status=?, result_data=?, error=?, updated_at=?
           WHERE id=?""",
        (status, json.dumps(result_data) if result_data else None, error,
         datetime.now(timezone.utc).isoformat(), job_id),
    )
    conn.commit()
    conn.close()


def update_job_progress(job_id: int, progress: dict):
    """Update job with live progress info (stage, ETA, message)."""
    conn = _get_conn()
    conn.execute(
        """UPDATE jobs SET progress=?, updated_at=? WHERE id=?""",
        (json.dumps(progress), datetime.now(timezone.utc).isoformat(), job_id),
    )
    conn.commit()
    conn.close()


def get_job(job_id: int) -> Optional[dict]:
    conn = _get_conn()
    row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    conn.close()
    if row:
        d = dict(row)
        if d.get("input_data"):
            d["input_data"] = json.loads(d["input_data"])
        if d.get("result_data"):
            d["result_data"] = json.loads(d["result_data"])
        if d.get("progress"):
            d["progress"] = json.loads(d["progress"])
        return d
    return None


def get_active_jobs(limit: int = 20) -> list[dict]:
    """Get recent jobs, active (pending/processing) first, then recent completed/failed."""
    conn = _get_conn()
    rows = conn.execute(
        """SELECT * FROM jobs
           ORDER BY
             CASE status WHEN 'processing' THEN 0 WHEN 'pending' THEN 1 ELSE 2 END,
             updated_at DESC
           LIMIT ?""",
        (limit,),
    ).fetchall()
    conn.close()
    results = []
    for row in rows:
        d = dict(row)
        if d.get("input_data"):
            d["input_data"] = json.loads(d["input_data"])
        if d.get("result_data"):
            d["result_data"] = json.loads(d["result_data"])
        if d.get("progress"):
            d["progress"] = json.loads(d["progress"])
        results.append(d)
    return results


def get_all_transcripts(limit: int = 50) -> list[dict]:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM transcripts ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_transcript(transcript_id: int) -> Optional[dict]:
    conn = _get_conn()
    row = conn.execute("SELECT * FROM transcripts WHERE id=?", (transcript_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_transcript_detail(transcript_id: int) -> Optional[dict]:
    """Get transcript with summary, actionables, and job timeline."""
    conn = _get_conn()
    row = conn.execute("SELECT * FROM transcripts WHERE id=?", (transcript_id,)).fetchone()
    if not row:
        conn.close()
        return None
    d = dict(row)

    # Attach summaries
    summaries = conn.execute(
        "SELECT summary, key_points, context, created_at FROM summaries WHERE transcript_id=? ORDER BY created_at DESC",
        (transcript_id,),
    ).fetchall()
    d["summaries"] = []
    for s in summaries:
        sd = dict(s)
        if sd.get("key_points"):
            sd["key_points"] = json.loads(sd["key_points"])
        d["summaries"].append(sd)

    # Attach actionables that reference this transcript
    actionables = conn.execute(
        "SELECT objective, question, answer, actionables, confidence, created_at FROM actionables WHERE transcript_ids LIKE ?",
        (f"%{transcript_id}%",),
    ).fetchall()
    d["actionables"] = []
    for a in actionables:
        ad = dict(a)
        if ad.get("actionables"):
            ad["actionables"] = json.loads(ad["actionables"])
        d["actionables"].append(ad)

    # Find the job that created this transcript (match by URL in input_data)
    d["timeline"] = {
        "requested_at": None,
        "transcribed_at": d["created_at"],
        "summarized_at": d["summaries"][0]["created_at"] if d["summaries"] else None,
        "kindle_sent": False,
        "kindle_summary_sent": False,
        "kindle_at": None,
    }
    url = d.get("url", "")
    if url:
        job_rows = conn.execute(
            "SELECT created_at, result_data FROM jobs WHERE input_data LIKE ? ORDER BY created_at DESC LIMIT 1",
            (f"%{url}%",),
        ).fetchall()
        if job_rows:
            jr = dict(job_rows[0])
            d["timeline"]["requested_at"] = jr["created_at"]
            if jr.get("result_data"):
                rd = json.loads(jr["result_data"])
                d["timeline"]["kindle_sent"] = rd.get("kindle_sent", False)
                d["timeline"]["kindle_summary_sent"] = rd.get("kindle_summary_sent", False)

    conn.close()
    return d


def search_transcripts(query: str, limit: int = 20) -> list[dict]:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM transcripts WHERE title LIKE ? OR transcript LIKE ? ORDER BY created_at DESC LIMIT ?",
        (f"%{query}%", f"%{query}%", limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _migrate_db():
    """Add columns that may be missing in older DBs."""
    conn = _get_conn()
    try:
        conn.execute("SELECT progress FROM jobs LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE jobs ADD COLUMN progress TEXT")
        conn.commit()
    conn.close()


# Initialize on import
init_db()
_migrate_db()
