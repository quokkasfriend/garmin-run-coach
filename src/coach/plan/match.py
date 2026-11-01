"""Abbina le sessioni pianificate alle corse Garmin e calcola compliance e obiettivo centrato."""

import json
from dataclasses import dataclass
from datetime import date

from coach.db import connect
from coach.metrics import fields as F
from coach.plan.models import Block, Intensity, Session

DURATION_TOLERANCE = (0.80, 1.20)   # durata reale / pianificata accettata per "obiettivo centrato"
EASY_Z3PLUS_MAX = 0.20              # una sessione facile non deve passare il 20% in Z3+
HARD_Z3PLUS_MIN = 0.50              # una sessione dura deve fare almeno metà dei minuti Z3+ pianificati


@dataclass
class Run:
    activity_id: int
    day: date
    minutes: float
    z3plus_min: float


@dataclass
class Match:
    session_id: str
    session: Session
    run: Run | None
    compliance: float        # durata reale / pianificata, tra 0 e 1.5
    target_hit: bool
    is_key: bool


def session_id(s: Session, index: int) -> str:
    return f"{s.date}#{index}"


def is_key(s: Session) -> bool:
    return s.is_hard or s.kind.value == "long"


def target_hit(s: Session, r: Run | None) -> bool:
    if r is None:
        return False
    lo, hi = DURATION_TOLERANCE
    if not lo <= r.minutes / s.duration_min <= hi:
        return False
    if s.intensity in (Intensity.easy,):
        return r.z3plus_min <= EASY_Z3PLUS_MAX * r.minutes
    if s.is_hard and s.z3plus_min > 0:
        return r.z3plus_min >= HARD_Z3PLUS_MIN * s.z3plus_min
    return True


def load_runs() -> list[Run]:
    with connect() as conn:
        rows = conn.execute("SELECT json FROM activity_raw").fetchall()
    out = []
    for r in rows:
        a = json.loads(r["json"])
        if a[F.A_TYPE[0]][F.A_TYPE[1]] not in F.RUN_TYPES:
            continue
        zones = [a.get(k) or 0.0 for k in F.A_HR_ZONE_S]
        out.append(Run(a[F.A_ID], date.fromisoformat(a[F.A_START_LOCAL][:10]),
                       (a.get(F.A_DURATION_S) or 0.0) / 60, sum(zones[2:]) / 60))
    return out


def match_block(block: Block, runs: list[Run], today: date) -> list[Match]:
    """Solo sessioni già passate (oggi escluso: potrebbe non essere ancora fatta)."""
    by_day: dict[date, list[Run]] = {}
    for r in runs:
        by_day.setdefault(r.day, []).append(r)
    sessions = sorted((s for w in block.weeks for s in w.sessions), key=lambda s: s.date)
    out: list[Match] = []
    for d in sorted({s.date for s in sessions}):
        if d >= today:
            continue
        todays = [s for s in sessions if s.date == d]
        avail = sorted(by_day.get(d, []), key=lambda r: -r.minutes)
        # abbina per durata: la sessione più lunga alla corsa più lunga
        for i, s in sorted(enumerate(todays), key=lambda t: -t[1].duration_min):
            run = avail.pop(0) if avail else None
            comp = min(run.minutes / s.duration_min, 1.5) if run else 0.0
            out.append(Match(session_id(s, i), s, run, comp, target_hit(s, run), is_key(s)))
    return out


def summarize(matches: list[Match]) -> tuple[float, float]:
    """(compliance 0-1, key_hit_pct 0-1) per BlockMetrics."""
    if not matches:
        return 0.0, 0.0
    comp = sum(min(m.compliance, 1.0) for m in matches) / len(matches)
    keys = [m for m in matches if m.is_key]
    return comp, (sum(m.target_hit for m in keys) / len(keys) if keys else 1.0)


def save_matches(block_id: int, matches: list[Match]) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM session_match WHERE block_id = ?", (block_id,))
        conn.executemany(
            "INSERT INTO session_match (block_id, session_id, activity_id, compliance, target_hit) "
            "VALUES (?, ?, ?, ?, ?)",
            [(block_id, m.session_id, m.run.activity_id if m.run else None, m.compliance, int(m.target_hit))
             for m in matches])


def load_block(block_id: int | None = None) -> tuple[int, Block]:
    with connect() as conn:
        row = conn.execute(
            "SELECT block_id, json FROM block " + ("WHERE block_id = ?" if block_id else "ORDER BY block_id DESC")
            + " LIMIT 1", (block_id,) if block_id else ()).fetchone()
    if not row:
        raise SystemExit("Nessun blocco: esegui `coach plan-block`.")
    return row["block_id"], Block.model_validate_json(row["json"])
