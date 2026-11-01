"""Blocco successivo: 2 settimane di recupero fisso, poi settimane normal limitate dalla decisione di fine blocco."""

from datetime import date, timedelta

from coach.metrics.weekly import weekly_summary
from coach.plan.adapt import Decision
from coach.plan.models import Block, WeekKind

RECOVERY_WEEKS = 2
DEFAULT_WEEKS = 4


def reference_volume(block: Block) -> tuple[float, float]:
    """(ore, D+) di riferimento: settimana normal più carica realmente eseguita nel blocco concluso."""
    df = weekly_summary()
    normal = [w.start for w in block.weeks if w.kind == WeekKind.normal]
    rows = df[df.index.isin(normal)] if not df.empty else df
    if rows.empty:
        raise SystemExit("Nessuna settimana normal eseguita nel blocco: impossibile fissare il volume di riferimento.")
    best = rows.loc[rows["hours"].idxmax()]
    return float(best["hours"]), float(best["dplus"])


def next_config(cfg: dict, prev: Block, weeks: int = DEFAULT_WEEKS) -> dict:
    """Config del blocco 2: parte il lunedì dopo la fine del blocco 1; i primi RECOVERY_WEEKS sono recovery."""
    start = prev.weeks[-1].start + timedelta(days=7)
    new = dict(cfg)
    new["block"] = {
        "start_date": start, "weeks": weeks, "phase": "post_marathon_recovery_build",
        "weeks_plan": {i: {"week_kind": "recovery" if i <= RECOVERY_WEEKS else "normal",
                           "note": "recupero fisso post-maratona" if i <= RECOVERY_WEEKS else "ripresa"}
                       for i in range(1, weeks + 1)},
    }
    new["fixed_events"] = [e for e in cfg.get("fixed_events", []) if e["date"] >= start]
    new["goal"] = {"race_name": None, "note": "nessun obiettivo deciso dopo la maratona: base aerobica"}
    return new


def decision_ctx(d: Decision, reference: tuple[float, float]) -> dict:
    return {"decisione": d.name.value, "variazione_volume": d.volume_change, "motivi": d.reasons,
            "ore_riferimento": round(reference[0], 2),
            "tetto_ore_settimane_normal": round(reference[0] * (1 + d.volume_change), 2)}
