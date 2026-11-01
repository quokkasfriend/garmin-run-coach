"""Validatore deterministico: ritorna l'elenco delle violazioni (vuoto = blocco valido)."""

from collections import Counter
from datetime import date, timedelta

from pydantic import BaseModel

from coach.plan.models import Block, FixedEvent, Intensity, Week, WeekKind


class Limits(BaseModel):
    """Soglie del validatore. I default sono provvisori: vanno sostituiti da methodology.yaml."""

    max_run_days: int = 5
    rest_days: int = 1                   # giorni senza corsa né forza
    max_hard_per_week: int = 2           # gare incluse
    long_run_max_pct: float = 0.40       # lungo / minuti della settimana
    z3plus_max_pct: float = 0.30         # solo sessioni non fisse
    ramp_hours_max_pct: float = 0.10
    ramp_dplus_max_pct: float = 0.20
    ramp_dplus_floor_m: int = 150        # sotto questo incremento assoluto il ramp D+ non vale
    deload_max_ratio: float = 0.80       # ore deload / ore di riferimento
    strength_per_week: int = 3
    strength_final_week: int | None = None  # forza nell'ultima settimana del blocco (gara)
    taper_ratios: list[float] = []          # volume non fisso delle settimane taper / picco
    recovery_ratios: list[float] = []       # tetto ore delle settimane recovery / ore di riferimento
    recovery_strength: int | None = None    # forza nelle settimane recovery
    normal_max_hours: float | None = None   # tetto assoluto per le settimane normal (decisione di fine blocco)


def fixed_events_from_config(cfg: dict) -> list[FixedEvent]:
    return [FixedEvent(**e) for e in cfg.get("fixed_events", [])]


def config_limit_overrides(cfg: dict) -> dict:
    av, st = cfg.get("availability", {}), cfg.get("strength", {})
    overrides = {
        "max_run_days": av.get("run_days_per_week"),
        "rest_days": av.get("rest_days_per_week"),
        "strength_per_week": st.get("sessions_per_week"),
        "strength_final_week": st.get("final_week_sessions"),
    }
    return {k: v for k, v in overrides.items() if v is not None}


def limits_from_config(cfg: dict) -> Limits:
    return Limits(**config_limit_overrides(cfg))


def validate_block(
    block: Block,
    limits: Limits,
    fixed_events: list[FixedEvent] | None = None,
    baseline_hours: float | None = None,
    baseline_dplus: float | None = None,
    pinned: list[dict] | None = None,
) -> list[str]:
    fixed_events = fixed_events or []
    errs: list[str] = []
    events_per_day = Counter(e.date for e in fixed_events)

    if block.start_date.weekday() != 0:
        errs.append(f"start_date {block.start_date} non è un lunedì")

    all_sessions = [s for w in block.weeks for s in w.sessions]
    hard_dates = sorted({s.date for s in all_sessions if s.is_hard})

    for i, w in enumerate(block.weeks):
        errs += _check_week_shape(i, w, block, limits, events_per_day)
        errs += _check_week_rules(i, w, limits, hard_dates, last=i == len(block.weeks) - 1)

    errs += _check_consecutive_hard(hard_dates)
    errs += _check_fixed_events(block, fixed_events)
    errs += _check_load(block, limits, baseline_hours, baseline_dplus)
    errs += _check_taper(block, limits, baseline_hours)
    errs += _check_recovery(block, limits, baseline_hours)
    errs += _check_pinned(block, pinned or [])

    if not any(w.kind in (WeekKind.deload, WeekKind.taper, WeekKind.recovery) for w in block.weeks):
        errs.append("nessuna settimana di scarico (deload/taper) nel blocco")
    return errs


def _label(i: int, w: Week) -> str:
    return f"settimana {i + 1} ({w.start})"


def _check_week_shape(i: int, w: Week, block: Block, limits: Limits,
                      events_per_day: Counter) -> list[str]:
    errs, lab = [], _label(i, w)
    if w.start != block.start_date + timedelta(days=7 * i):
        errs.append(f"{lab}: la settimana non segue la precedente (atteso {block.start_date + timedelta(days=7 * i)})")
    if w.start.weekday() != 0:
        errs.append(f"{lab}: non inizia di lunedì")

    week_days = set(w.days)
    for s in w.sessions:
        if s.date not in week_days:
            errs.append(f"{lab}: sessione {s.kind} del {s.date} fuori dalla settimana")
    for d in w.strength_days:
        if d not in week_days:
            errs.append(f"{lab}: forza del {d} fuori dalla settimana")

    per_day = Counter(s.date for s in w.sessions)
    for d, n in per_day.items():
        fixed_n = events_per_day.get(d, 0)
        if fixed_n and any(not s.fixed for s in w.sessions if s.date == d):
            errs.append(f"{lab}: {d} è un giorno gara, nessuna sessione aggiuntiva")
        if n > max(1, fixed_n):
            errs.append(f"{lab}: {n} sessioni il {d} (max {max(1, fixed_n)})")

    if len(per_day) > limits.max_run_days:
        errs.append(f"{lab}: {len(per_day)} giorni di corsa (max {limits.max_run_days})")
    return errs


def _check_week_rules(i: int, w: Week, limits: Limits, hard_dates: list[date],
                      last: bool = False) -> list[str]:
    errs, lab = [], _label(i, w)
    used = {s.date for s in w.sessions} | set(w.strength_days)
    free = [d for d in w.days if d not in used]
    if len(free) < limits.rest_days:
        errs.append(f"{lab}: {len(free)} giorni di riposo totale (minimo {limits.rest_days})")

    required = limits.strength_final_week if last and limits.strength_final_week is not None else limits.strength_per_week
    if w.kind == WeekKind.recovery and limits.recovery_strength is not None:
        required = limits.recovery_strength
    if len(set(w.strength_days)) != len(w.strength_days) or len(w.strength_days) != required:
        errs.append(f"{lab}: {len(w.strength_days)} giorni di forza (richiesti {required})")
    hard = set(hard_dates)
    for d in w.strength_days:
        if d in hard:
            errs.append(f"{lab}: forza il {d}, giorno di corsa dura")
        elif d + timedelta(days=1) in hard:
            errs.append(f"{lab}: forza il {d}, giorno prima di una corsa dura")

    n_hard = sum(s.is_hard for s in w.sessions)
    if n_hard > limits.max_hard_per_week:
        errs.append(f"{lab}: {n_hard} sessioni dure (max {limits.max_hard_per_week})")

    planned = [s for s in w.sessions if not s.fixed]
    planned_min = sum(s.duration_min for s in planned)
    has_fixed = any(s.fixed for s in w.sessions)
    if planned_min and not has_fixed:
        longest = max((s.duration_min for s in planned if s.kind.value == "long"), default=0)
        if longest / w.minutes > limits.long_run_max_pct:
            errs.append(f"{lab}: lungo = {longest / w.minutes:.0%} della settimana (max {limits.long_run_max_pct:.0%})")
    if planned_min:
        z3 = sum(s.z3plus_min for s in planned) / planned_min
        if z3 > limits.z3plus_max_pct:
            errs.append(f"{lab}: Z3+ {z3:.0%} (max {limits.z3plus_max_pct:.0%})")
    return errs


def _check_consecutive_hard(hard_dates: list[date]) -> list[str]:
    return [
        f"sessioni dure consecutive: {a} e {b}"
        for a, b in zip(hard_dates, hard_dates[1:])
        if (b - a).days == 1
    ]


def _check_fixed_events(block: Block, events: list[FixedEvent]) -> list[str]:
    errs = []
    fixed = Counter(
        (s.date, s.intensity) for w in block.weeks for s in w.sessions if s.fixed
    )
    expected = Counter((e.date, e.intensity) for e in events)
    for key, n in expected.items():
        if fixed.get(key, 0) != n:
            errs.append(f"evento fisso mancante o diverso: {key[0]} {key[1].value} (atteso {n}, trovato {fixed.get(key, 0)})")
    for key in fixed.keys() - expected.keys():
        errs.append(f"sessione fixed senza evento in config: {key[0]} {key[1].value}")
    return errs


def _check_load(block: Block, limits: Limits, baseline_hours: float | None,
                baseline_dplus: float | None) -> list[str]:
    errs = []
    last_normal_h, last_normal_d = baseline_hours, baseline_dplus
    prev_h, prev_d = baseline_hours, baseline_dplus
    for i, w in enumerate(block.weeks):
        lab = _label(i, w)
        ref_h = max(x for x in (prev_h, last_normal_h) if x is not None) if (prev_h or last_normal_h) else None
        ref_d = max(x for x in (prev_d, last_normal_d) if x is not None) if (prev_d is not None or last_normal_d is not None) else None

        if w.kind == WeekKind.normal:
            if ref_h and w.hours > ref_h * (1 + limits.ramp_hours_max_pct) + 1e-9:
                errs.append(f"{lab}: {w.hours:.1f} h, ramp oltre +{limits.ramp_hours_max_pct:.0%} su {ref_h:.1f} h")
            if ref_d is not None:
                cap = max(ref_d * (1 + limits.ramp_dplus_max_pct), ref_d + limits.ramp_dplus_floor_m)
                if w.dplus > cap:
                    errs.append(f"{lab}: D+ {w.dplus} m oltre il limite {cap:.0f} m")
            if limits.normal_max_hours and w.hours > limits.normal_max_hours + 1e-9:
                errs.append(f"{lab}: {w.hours:.1f} h, massimo {limits.normal_max_hours:.1f} h dalla decisione di fine blocco")
            last_normal_h, last_normal_d = w.hours, w.dplus
        elif w.kind == WeekKind.deload and ref_h and w.hours > ref_h * limits.deload_max_ratio + 1e-9:
            errs.append(f"{lab}: scarico a {w.hours:.1f} h, massimo {ref_h * limits.deload_max_ratio:.1f} h")
        prev_h, prev_d = w.hours, w.dplus
    return errs


def _check_taper(block: Block, limits: Limits, baseline_hours: float | None) -> list[str]:
    """Volume non fisso (gare escluse) delle settimane taper <= ratio * picco (max fra baseline e settimane normali)."""
    if not limits.taper_ratios:
        return []
    errs, peak, k = [], baseline_hours or 0.0, 0
    for i, w in enumerate(block.weeks):
        if w.kind == WeekKind.normal:
            peak = max(peak, w.hours)
        elif w.kind == WeekKind.taper:
            ratio = limits.taper_ratios[min(k, len(limits.taper_ratios) - 1)]
            k += 1
            planned = sum(s.duration_min for s in w.sessions if not s.fixed)
            if peak and planned > ratio * peak * 60 + 1e-9:
                errs.append(f"{_label(i, w)}: taper {planned / 60:.1f} h pianificate, massimo {ratio * peak:.1f} h ({ratio:.0%} di {peak:.1f} h)")
    return errs


def _check_recovery(block: Block, limits: Limits, reference_hours: float | None) -> list[str]:
    """Recupero fisso: solo corse facili, niente Z3+, ore <= ratio * riferimento (ratio per settimana, in ordine)."""
    errs, k = [], 0
    for i, w in enumerate(block.weeks):
        if w.kind != WeekKind.recovery:
            continue
        lab = _label(i, w)
        if any(s.intensity != Intensity.easy or s.z3plus_min for s in w.sessions):
            errs.append(f"{lab}: il recupero ammette solo corse facili, senza Z3+")
        if limits.recovery_ratios and reference_hours:
            ratio = limits.recovery_ratios[min(k, len(limits.recovery_ratios) - 1)]
            if w.hours > ratio * reference_hours + 1e-9:
                errs.append(f"{lab}: recupero a {w.hours:.1f} h, massimo {ratio * reference_hours:.1f} h ({ratio:.0%} di {reference_hours:.1f} h)")
        k += 1
    return errs


def _check_pinned(block: Block, pinned: list[dict]) -> list[str]:
    """Giorni decisi dall'atleta (config `pinned_days`): stesse sessioni (tipo e durata), o riposo se la lista è vuota."""
    errs = []
    got: dict[date, list[tuple[str, int]]] = {}
    for w in block.weeks:
        for s in w.sessions:
            got.setdefault(s.date, []).append((s.kind.value, s.duration_min))
    for p in pinned:
        want = sorted((x["kind"], x.get("duration_min")) for x in p["sessions"])
        have = sorted((k, m if any(w[0] == k and w[1] for w in want) else None) for k, m in got.get(p["date"], []))
        if want != have:
            errs.append(f"giorno fissato {p['date']}: atteso {want or 'riposo dalla corsa'}, trovato {have or 'riposo dalla corsa'}")
    return errs
