"""Revisione di fine blocco: metriche deterministiche -> BlockMetrics -> decisione (adapt.decide)."""

import json
from datetime import date, timedelta

from coach.db import connect
from coach.plan.adapt import BlockMetrics, Decision, decide
from coach.plan.match import Match, summarize
from coach.plan.methodology import load_methodology, thresholds_from_methodology
from coach.plan.models import Block

BASELINE_DAYS = 28
RPE_EASY_TOO_HIGH = 7   # RPE >= 7 su una sessione facile = sopra le attese (default di progetto)


def _avg(vals: list[float]) -> float | None:
    return sum(vals) / len(vals) if vals else None


def _health_series(conn, kind: str, key, start: date, end: date) -> list[float]:
    out = []
    for r in conn.execute("SELECT json FROM health_raw WHERE kind=? AND date>=? AND date<=?",
                          (kind, str(start), str(end))):
        d = json.loads(r["json"])
        v = key(d)
        if v:
            out.append(float(v))
    return out


def health_changes(start: date, end: date) -> tuple[float | None, float | None]:
    """(variazione % HRV, variazione bpm FC a riposo): media del blocco vs 28 giorni prima."""
    base_start, base_end = start - timedelta(days=BASELINE_DAYS), start - timedelta(days=1)
    hrv_k = lambda d: d.get("lastNightAvg")
    rhr_k = lambda d: (d.get("heartRate") or {}).get("restingValue")
    with connect() as conn:
        hrv_b, hrv_n = (_health_series(conn, "hrv", hrv_k, *w) for w in ((base_start, base_end), (start, end)))
        rhr_b, rhr_n = (_health_series(conn, "daily", rhr_k, *w) for w in ((base_start, base_end), (start, end)))
    hb, hn, rb, rn = _avg(hrv_b), _avg(hrv_n), _avg(rhr_b), _avg(rhr_n)
    return ((hn - hb) / hb * 100 if hb and hn else None), (rn - rb if rb is not None and rn is not None else None)


def feedback_in(start: date, end: date) -> list[dict]:
    with connect() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT activity_id, date, rpe, feel, pain FROM session_feedback WHERE date>=? AND date<=?",
            (str(start), str(end)))]


def build_metrics(block: Block, matches: list[Match], today: date) -> tuple[BlockMetrics, dict]:
    start = block.start_date
    end = min(today - timedelta(days=1), block.weeks[-1].start + timedelta(days=6))
    comp, key_hit = summarize(matches)
    fb = feedback_in(start, end)
    pains = [f for f in fb if f["pain"]]
    easy_days = {m.session.date for m in matches if m.session.intensity.value == "easy"}
    rpe_high = [f for f in fb if f["rpe"] and f["rpe"] >= RPE_EASY_TOO_HIGH and date.fromisoformat(f["date"]) in easy_days]
    hrv, rhr = health_changes(start, end)
    m = BlockMetrics(pain_reports=len(pains), hrv_change_pct=hrv, rhr_change_bpm=rhr,
                     rpe_above_expected=bool(rpe_high), compliance=comp, key_hit_pct=key_hit, sick_days=0)
    extra = {"sessioni_valutate": len(matches), "fino_al": str(end), "feedback": len(fb),
             "dolori": [f"{f['date']}: {f['pain']}" for f in pains]}
    return m, extra


def review(block: Block, matches: list[Match], today: date) -> tuple[BlockMetrics, Decision, dict]:
    m, extra = build_metrics(block, matches, today)
    return m, decide(m, thresholds_from_methodology(load_methodology())), extra


def narrative(m: BlockMetrics, d: Decision, extra: dict) -> str:
    def f(v, fmt):
        return "n.d." if v is None else fmt.format(v)

    lines = [
        f"Decisione: {d.name.value.upper()} (volume del prossimo blocco {d.volume_change:+.0%} sul precedente).",
        "Motivi: " + "; ".join(d.reasons) + ".",
        f"Dati: compliance {m.compliance:.0%} su {extra['sessioni_valutate']} sessioni, "
        f"sessioni chiave centrate {m.key_hit_pct:.0%}, HRV {f(m.hrv_change_pct, '{:+.1f}%')}, "
        f"FC a riposo {f(m.rhr_change_bpm, '{:+.1f} bpm')}, {m.pain_reports} segnalazioni di dolore, "
        f"{extra['feedback']} feedback registrati.",
        "Limiti: giorni di malattia non rilevati (assunti 0); HRV e soglie di compliance sono default di progetto.",
    ]
    if extra["dolori"]:
        lines.append("Dolori: " + "; ".join(extra["dolori"]))
    return "\n".join(lines)


def save_review(block_id: int, m: BlockMetrics, d: Decision, text: str) -> None:
    with connect() as conn:
        conn.execute("INSERT OR REPLACE INTO block_review (block_id, metrics, decision, reasons, narrative) "
                     "VALUES (?, ?, ?, ?, ?)",
                     (block_id, m.model_dump_json(), d.name.value, json.dumps(d.reasons, ensure_ascii=False), text))
