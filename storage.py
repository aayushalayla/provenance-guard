"""
storage.py

SQLite persistence layer for Provenance Guard.

Tables:
    classifications  - one row per /submit decision
    appeals          - one row per /appeal
    audit_events      - append-only structured log of everything
    certificates      - one row per /certificate issued

Design note:
classifications and appeals are the "current state" tables
(a classification's status can be updated in place).
audit_events is append-only and is what GET /log reads from, so the audit trail is not updated by a status update.
"""

import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(
    os.getenv(
        "PROVENANCE_DB_PATH", Path(__file__).parent / "data" / "provenance_guard.db"
    )
)


def utc_timestamp():
    return datetime.now(timezone.utc).isoformat()


def new_id():
    return str(uuid.uuid4())


@contextmanager
def get_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with get_connection() as conn:
        cur = conn.cursor()

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS classifications (
                content_id TEXT PRIMARY KEY,
                creator_id TEXT NOT NULL,
                text_preview TEXT NOT NULL,
                content_type TEXT,
                attribution TEXT NOT NULL,
                ai_likelihood REAL NOT NULL,
                confidence REAL NOT NULL,
                signal_agreement REAL NOT NULL,
                llm_score REAL NOT NULL,
                llm_reason TEXT,
                stylometry_score REAL NOT NULL,
                stylometry_metrics TEXT NOT NULL,
                specificity_score REAL NOT NULL,
                specificity_metrics TEXT NOT NULL,
                label TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS appeals (
                appeal_id TEXT PRIMARY KEY,
                content_id TEXT NOT NULL,
                creator_id TEXT NOT NULL,
                creator_reasoning TEXT NOT NULL,
                optional_process_note TEXT,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (content_id) REFERENCES classifications (content_id)
            )
             """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_events (
                event_seq INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                event_type TEXT NOT NULL,
                content_id TEXT,
                creator_id TEXT,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS certificates (
                certificate_id TEXT PRIMARY KEY,
                content_id TEXT NOT NULL,
                creator_id TEXT NOT NULL,
                certificate_label TEXT NOT NULL,
                display_text TEXT NOT NULL,
                verification_note TEXT,
                created_at TEXT NOT NULL
            )
            """
        )

        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_classifications_created_at "
            "ON classifications (created_at)"
        )

        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_appeals_content_id ON appeals (content_id)"
        )

        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_audit_events_content_id "
            "ON audit_events (content_id)"
        )


# ---------------------------------------------------------------------------
# audit_events (append-only)
# ---------------------------------------------------------------------------


def write_audit_event(event_type, content_id, creator_id, payload):
    event_id = new_id()
    with get_connection() as conn:
        conn.execute(
            """
        INSERT INTO audit_events (event_id, event_type, content_id, creator_id, payload_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
            (
                event_id,
                event_type,
                content_id,
                creator_id,
                json.dumps(payload),
                utc_timestamp(),
            ),
        )
    return event_id


def read_audit_events(limit=50):
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM audit_events ORDER BY event_seq DESC LIMIT ?",
            (limit,),
        ).fetchall()

    entries = []
    for row in rows:
        entries.append(
            {
                "event_id": row["event_id"],
                "event_type": row["event_type"],
                "content_id": row["content_id"],
                "creator_id": row["creator_id"],
                "created_at": row["created_at"],
                "payload": json.loads(row["payload_json"]),
            }
        )
    return entries


# ---------------------------------------------------------------------------
# classifications
# ---------------------------------------------------------------------------


def insert_classification(record):
    with get_connection() as conn:
        conn.execute(
            """
        INSERT INTO classifications (
            content_id, creator_id, text_preview, content_type,
            attribution, ai_likelihood, confidence, signal_agreement,
            llm_score, llm_reason,
            stylometry_score, stylometry_metrics,
            specificity_score, specificity_metrics,
            label, status, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                record["content_id"],
                record["creator_id"],
                record["text_preview"],
                record.get("content_type"),
                record["attribution"],
                record["ai_likelihood"],
                record["confidence"],
                record["signal_agreement"],
                record["llm_score"],
                record.get("llm_reason", ""),
                record["stylometry_score"],
                json.dumps(record["stylometry_metrics"]),
                record["specificity_score"],
                json.dumps(record["specificity_metrics"]),
                record["label"],
                record["status"],
                record["created_at"],
            ),
        )


def get_classification(content_id):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM classifications WHERE content_id = ?", (content_id,)
        ).fetchone()

    if row is None:
        return None

    result = dict(row)
    result["stylometry_metrics"] = json.loads(result["stylometry_metrics"])
    result["specificity_metrics"] = json.loads(result["specificity_metrics"])
    return result


def update_classification_status(content_id, new_status):
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE classifications SET status = ? WHERE content_id = ?",
            (new_status, content_id),
        )
        updated = cur.rowcount > 0
    return updated


def all_classifications():
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM classifications ORDER BY created_at ASC"
        ).fetchall()
    return [dict(row) for row in rows]


# ---------------------------------------------------------------------------
# appeals
# ---------------------------------------------------------------------------


def insert_appeal(record):
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO appeals (
                appeal_id, content_id, creator_id, creator_reasoning,
                optional_process_note, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record["appeal_id"],
                record["content_id"],
                record["creator_id"],
                record["creator_reasoning"],
                record.get("optional_process_note"),
                record["status"],
                record["created_at"],
            ),
        )


def all_appeals():
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM appeals ORDER BY created_at DESC").fetchall()
    return [dict(row) for row in rows]


def has_open_appeal(content_id):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM appeals WHERE content_id = ? AND status = 'under_review' LIMIT 1",
            (content_id,),
        ).fetchone()
    return row is not None


# ---------------------------------------------------------------------------
# certificates
# ---------------------------------------------------------------------------


def insert_certificate(record):
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO certificates (
                certificate_id, content_id, creator_id,
                certificate_label, display_text, verification_note, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record["certificate_id"],
                record["content_id"],
                record["creator_id"],
                record["certificate_label"],
                record["display_text"],
                record.get("verification_note"),
                record["created_at"],
            ),
        )
