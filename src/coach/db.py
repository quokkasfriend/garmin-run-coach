"""SQLite: JSON grezzi Garmin + tabelle del piano."""

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

from coach.settings import DB_PATH, ensure_dirs

SCHEMA = """
CREATE TABLE IF NOT EXISTS activity_raw (
    activity_id  INTEGER PRIMARY KEY,
    start_local  TEXT NOT NULL,
    type_key     TEXT NOT NULL,
    json         TEXT NOT NULL,
    fit_path     TEXT
);
CREATE INDEX IF NOT EXISTS idx_activity_start ON activity_raw(start_local);

CREATE TABLE IF NOT EXISTS health_raw (
    kind  TEXT NOT NULL,          -- hrv | sleep | daily | body_battery
    date  TEXT NOT NULL,          -- YYYY-MM-DD
    json  TEXT NOT NULL,
    PRIMARY KEY (kind, date)
);

CREATE TABLE IF NOT EXISTS block (
    block_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    phase       TEXT NOT NULL,
    start_date  TEXT NOT NULL,
    weeks       INTEGER NOT NULL,
    json        TEXT NOT NULL,    -- blocco completo (settimane, sessioni)
    created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS session_match (
    block_id       INTEGER NOT NULL REFERENCES block(block_id),
    session_id     TEXT NOT NULL,
    activity_id    INTEGER,
    compliance     REAL,
    target_hit     INTEGER,
    PRIMARY KEY (block_id, session_id)
);

CREATE TABLE IF NOT EXISTS session_feedback (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    activity_id  INTEGER,
    date         TEXT NOT NULL,
    rpe          INTEGER,
    feel         TEXT,
    pain         TEXT,
    created_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS block_review (
    block_id   INTEGER PRIMARY KEY REFERENCES block(block_id),
    metrics    TEXT NOT NULL,
    decision   TEXT NOT NULL,
    reasons    TEXT NOT NULL,
    narrative  TEXT
);

CREATE TABLE IF NOT EXISTS thresholds (
    valid_from  TEXT NOT NULL,
    name        TEXT NOT NULL,    -- es. hr_threshold, hr_max, pace_threshold
    value       REAL NOT NULL,
    source      TEXT,
    PRIMARY KEY (valid_from, name)
);
"""


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    ensure_dirs()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def upsert_activity(conn: sqlite3.Connection, act: dict) -> None:
    conn.execute(
        """INSERT INTO activity_raw (activity_id, start_local, type_key, json)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(activity_id) DO UPDATE SET
             start_local=excluded.start_local, type_key=excluded.type_key, json=excluded.json""",
        (act["activityId"], act["startTimeLocal"], act["activityType"]["typeKey"], json.dumps(act)),
    )


def upsert_health(conn: sqlite3.Connection, kind: str, date: str, payload: dict) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO health_raw (kind, date, json) VALUES (?, ?, ?)",
        (kind, date, json.dumps(payload)),
    )
