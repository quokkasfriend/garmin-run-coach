"""Feedback soggettivo (RPE, sensazioni, dolore) legato a un'attività Garmin o a un giorno."""

import json
import sqlite3
from datetime import date

from coach.metrics.fields import RUN_TYPES

FEELS = ("ottimo", "buono", "ok", "pesante", "pessimo")


def runs_on(conn: sqlite3.Connection, day: date) -> list[sqlite3.Row]:
    """Corse del giorno, la più recente per prima."""
    rows = conn.execute(
        "SELECT activity_id, start_local, type_key, json FROM activity_raw "
        "WHERE substr(start_local, 1, 10) = ? ORDER BY start_local DESC", (str(day),)).fetchall()
    return [r for r in rows if r["type_key"] in RUN_TYPES]


def add_feedback(conn: sqlite3.Connection, day: date, rpe: int | None, feel: str | None,
                 pain: str | None, activity_id: int | None = None) -> tuple[int, int | None]:
    """Salva il feedback. Senza activity_id lo lega alla corsa più recente del giorno (se c'è)."""
    if rpe is not None and not 1 <= rpe <= 10:
        raise ValueError("RPE tra 1 e 10")
    if feel is not None and feel not in FEELS:
        raise ValueError(f"feel deve essere uno tra: {', '.join(FEELS)}")
    if rpe is None and feel is None and not pain:
        raise ValueError("serve almeno uno tra RPE, feel, dolore")
    if activity_id is None:
        runs = runs_on(conn, day)
        activity_id = runs[0]["activity_id"] if runs else None
    elif not conn.execute("SELECT 1 FROM activity_raw WHERE activity_id = ?", (activity_id,)).fetchone():
        raise ValueError(f"attività {activity_id} non trovata: esegui `coach sync`")
    cur = conn.execute(
        "INSERT INTO session_feedback (activity_id, date, rpe, feel, pain) VALUES (?, ?, ?, ?, ?)",
        (activity_id, str(day), rpe, feel, pain or None))
    return cur.lastrowid, activity_id


def list_feedback(conn: sqlite3.Connection, last: int = 15) -> list[dict]:
    rows = conn.execute(
        "SELECT f.id, f.date, f.rpe, f.feel, f.pain, f.activity_id, a.json FROM session_feedback f "
        "LEFT JOIN activity_raw a USING (activity_id) ORDER BY f.date DESC, f.id DESC LIMIT ?", (last,))
    out = []
    for r in rows:
        act = json.loads(r["json"]) if r["json"] else {}
        out.append({"id": r["id"], "date": r["date"], "rpe": r["rpe"], "feel": r["feel"], "pain": r["pain"],
                    "activity_id": r["activity_id"], "km": round((act.get("distance") or 0) / 1000, 1),
                    "min": round((act.get("duration") or 0) / 60)})
    return out
