"""Sync incrementale Garmin -> SQLite (+ FIT delle corse)."""

import zipfile
from collections.abc import Callable
from datetime import date, timedelta
from io import BytesIO

from coach.db import connect, upsert_activity, upsert_health
from coach.garmin.client import call, garmin_client
from coach.metrics import fields as F
from coach.settings import FIT_DIR

PAGE = 100          # limit=200 dà HTTP 500
HEALTH_CHUNK = 14   # giorni per richiesta
OVERLAP_DAYS = 3    # rilegge gli ultimi giorni (dati che Garmin aggiorna a posteriori)


def _chunks(start: date, end: date, size: int):
    cur = start
    while cur <= end:
        stop = min(cur + timedelta(days=size - 1), end)
        yield cur, stop
        cur = stop + timedelta(days=1)


def _last_activity_date(conn) -> date | None:
    row = conn.execute("SELECT MAX(substr(start_local, 1, 10)) FROM activity_raw").fetchone()
    return date.fromisoformat(row[0]) if row[0] else None


def _last_health_date(conn, kind: str) -> date | None:
    row = conn.execute("SELECT MAX(date) FROM health_raw WHERE kind = ?", (kind,)).fetchone()
    return date.fromisoformat(row[0]) if row[0] else None


def sync_activities(client, conn, since: date, today: date) -> int:
    n, offset = 0, 0
    while True:
        page = call(
            client.search_activities,
            start=offset, limit=PAGE, start_date=since, end_date=today,
        )
        for act in page:
            upsert_activity(conn, act)
        conn.commit()
        n += len(page)
        if len(page) < PAGE:
            return n
        offset += PAGE


def sync_fit(client, conn) -> int:
    """Scarica lo zip FIT delle corse non ancora scaricate (lo zip resta chiuso, si estrae al parsing)."""
    types = ",".join("?" * len(F.FIT_TYPES))
    rows = conn.execute(
        f"SELECT activity_id FROM activity_raw WHERE fit_path IS NULL AND type_key IN ({types})",
        tuple(F.FIT_TYPES),
    ).fetchall()
    for r in rows:
        data = call(client.download_activity, r["activity_id"])
        if not zipfile.is_zipfile(BytesIO(data)):
            raise RuntimeError(f"download attività {r['activity_id']}: non è uno zip")
        path = FIT_DIR / f"{r['activity_id']}.zip"
        path.write_bytes(data)
        conn.execute(
            "UPDATE activity_raw SET fit_path = ? WHERE activity_id = ?",
            (str(path), r["activity_id"]),
        )
        conn.commit()
    return len(rows)


def _health(client, conn, kind: str, fetch: Callable, extract: Callable, date_key: str,
            since: date, today: date) -> int:
    n = 0
    start = max(since, (_last_health_date(conn, kind) or since) - timedelta(days=OVERLAP_DAYS))
    for a, b in _chunks(start, today, HEALTH_CHUNK):
        for item in extract(call(fetch, a, b)) or []:
            if not item.get(date_key):  # es. sonno non confermato: nessun giorno associabile
                continue
            upsert_health(conn, kind, item[date_key][:10], item)
            n += 1
        conn.commit()
    return n


def sync_all(days: int = 365, fit: bool = True, on_step: Callable[[str], None] = print) -> None:
    today = date.today()
    since = today - timedelta(days=days)
    with garmin_client() as client, connect() as conn:
        last = _last_activity_date(conn)
        act_since = max(since, last - timedelta(days=OVERLAP_DAYS)) if last else since
        on_step(f"attività dal {act_since}: {sync_activities(client, conn, act_since, today)}")

        specs = [
            ("hrv", client.get_daily_hrv_summaries, lambda r: r["hrvSummaries"], "calendarDate"),
            ("sleep", client.get_daily_sleep_summaries, lambda r: r, "calendarDate"),
            ("daily", client.get_daily_summaries, lambda r: r["data"], "calendarDate"),
        ]
        for kind, fetch, extract, date_key in specs:
            on_step(f"{kind}: {_health(client, conn, kind, fetch, extract, date_key, since, today)} giorni")

        if fit:
            on_step(f"FIT scaricati: {sync_fit(client, conn)}")
