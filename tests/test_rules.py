from datetime import date, timedelta

import pytest

from coach.plan.adapt import BlockMetrics, DecisionName, Thresholds, decide
from coach.plan.models import Block, Intensity, Kind, Session, Week, WeekKind
from coach.plan.validate import Limits, validate_block

MON = date(2026, 10, 26)
BASELINE_H = 5.0


def S(d, kind, intensity, minutes, **kw):
    return Session(date=d, kind=kind, intensity=intensity, duration_min=minutes, **kw)


def make_week(start, kind=WeekKind.normal, scale=1.0):
    """Settimana valida: 5 giorni di corsa, 1 duro (mar), forza mer-gio-ven, riposo domenica."""
    d = lambda i: start + timedelta(days=i)  # noqa: E731
    sessions = [
        S(d(0), Kind.easy, Intensity.easy, round(45 * scale)),
        S(d(1), Kind.tempo, Intensity.hard, round(60 * scale), z3plus_min=round(20 * scale)),
        S(d(2), Kind.easy, Intensity.easy, round(45 * scale)),
        S(d(4), Kind.easy, Intensity.easy, round(40 * scale)),
        S(d(5), Kind.long, Intensity.moderate, round(110 * scale)),
    ]
    return Week(start=start, kind=kind, sessions=sessions, strength_days=[d(2), d(3), d(4)])


def make_block(weeks=None):
    weeks = weeks or [
        make_week(MON, WeekKind.deload, scale=0.75),
        make_week(MON + timedelta(days=7)),
    ]
    return Block(phase="test", start_date=MON, weeks=weeks)


def check(block, **kw):
    return validate_block(block, Limits(), baseline_hours=BASELINE_H, baseline_dplus=0, **kw)


def has(errs, text):
    return any(text in e for e in errs)


def test_valid_block_has_no_violations():
    assert check(make_block()) == []


def test_start_must_be_monday():
    b = make_block()
    b.start_date = MON + timedelta(days=1)
    assert has(check(b), "non è un lunedì")


def test_session_outside_week():
    b = make_block()
    b.weeks[0].sessions[0].date = MON + timedelta(days=9)
    assert has(check(b), "fuori dalla settimana")


def test_two_sessions_same_day():
    b = make_block()
    b.weeks[0].sessions.append(S(MON, Kind.easy, Intensity.easy, 20))
    assert has(check(b), "2 sessioni il")


def test_too_many_run_days():
    b = make_block()
    b.weeks[1].sessions.append(S(MON + timedelta(days=13), Kind.easy, Intensity.easy, 30))
    assert has(check(b), "giorni di corsa")


def test_no_rest_day():
    b = make_block()
    w = b.weeks[1]
    w.strength_days = [w.start + timedelta(days=i) for i in (2, 3, 6)]  # ven. libero ma dom. forza
    w.sessions[3].date = w.start + timedelta(days=3)                    # corsa giovedì
    w.sessions[4].date = w.start + timedelta(days=5)
    w.sessions.append(S(w.start + timedelta(days=4), Kind.easy, Intensity.easy, 20))
    w.sessions.append(S(w.start + timedelta(days=6), Kind.easy, Intensity.easy, 20))
    assert has(check(b), "riposo totale")


def test_consecutive_hard_sessions():
    b = make_block()
    b.weeks[1].sessions[2].intensity = Intensity.hard  # mercoledì duro dopo martedì duro
    errs = check(b)
    assert has(errs, "dure consecutive")


def test_too_many_hard_sessions():
    b = make_block()
    w = b.weeks[1]
    w.sessions[3].intensity = Intensity.hard  # venerdì
    w.sessions[0].intensity = Intensity.hard  # lunedì (e quindi lun+mar consecutive)
    assert has(check(b), "sessioni dure (max 2)")


def test_strength_on_hard_day_and_day_before():
    b = make_block()
    w = b.weeks[1]
    w.strength_days = [w.start + timedelta(days=i) for i in (0, 1, 3)]
    errs = check(b)
    assert has(errs, "giorno prima di una corsa dura")  # lunedì
    assert has(errs, "giorno di corsa dura")            # martedì


def test_strength_count():
    b = make_block()
    b.weeks[1].strength_days = b.weeks[1].strength_days[:2]
    assert has(check(b), "giorni di forza")


def test_long_run_share():
    b = make_block()
    b.weeks[1].sessions[4].duration_min = 200
    assert has(check(b), "lungo =")


def test_z3_share():
    b = make_block()
    b.weeks[1].sessions[1].z3plus_min = 40
    errs = validate_block(b, Limits(z3plus_max_pct=0.10), baseline_hours=BASELINE_H, baseline_dplus=0)
    assert has(errs, "Z3+")


def test_z3_cannot_exceed_session_duration():
    with pytest.raises(ValueError):
        S(MON, Kind.easy, Intensity.easy, 30, z3plus_min=40)


def test_hours_ramp():
    b = make_block()
    for s in b.weeks[1].sessions:
        s.duration_min = round(s.duration_min * 1.3)
        s.z3plus_min = round(s.z3plus_min * 1.3)
    assert has(check(b), "ramp oltre")


def test_dplus_ramp():
    b = make_block()
    b.weeks[1].sessions[4].dplus_m = 800
    assert has(check(b), "D+")


def test_deload_required():
    b = make_block([make_week(MON), make_week(MON + timedelta(days=7))])
    assert has(check(b), "nessuna settimana di scarico")


def test_deload_must_be_lighter():
    b = make_block([make_week(MON, WeekKind.deload, scale=0.95), make_week(MON + timedelta(days=7))])
    assert has(check(b), "scarico a")


def test_weeks_must_be_consecutive():
    b = make_block([make_week(MON, WeekKind.deload, 0.75), make_week(MON + timedelta(days=14))])
    assert has(check(b), "non segue la precedente")


# --- regole di adattamento -------------------------------------------------

def metrics(**kw):
    base = dict(compliance=0.95, key_hit_pct=0.9)
    return BlockMetrics(**{**base, **kw})


def test_progress():
    d = decide(metrics())
    assert d.name == DecisionName.progress and d.volume_change == pytest.approx(0.08)


def test_deload_on_two_pain_reports():
    assert decide(metrics(pain_reports=2)).name == DecisionName.deload


def test_deload_on_two_recovery_signals():
    d = decide(metrics(hrv_change_pct=-8, rhr_change_bpm=6))
    assert d.name == DecisionName.deload and d.volume_change == pytest.approx(-0.30)
    assert len(d.reasons) == 2


def test_one_signal_is_consolidate():
    d = decide(metrics(hrv_change_pct=-8))
    assert d.name == DecisionName.consolidate and d.volume_change == 0


def test_single_pain_is_consolidate():
    assert decide(metrics(pain_reports=1)).name == DecisionName.consolidate


def test_low_compliance_is_repeat():
    d = decide(metrics(compliance=0.65))
    assert d.name == DecisionName.repeat and d.volume_change == pytest.approx(-0.10)


def test_sick_days_is_repeat():
    assert decide(metrics(sick_days=5)).name == DecisionName.repeat


def test_medium_compliance_is_consolidate():
    assert decide(metrics(compliance=0.80)).name == DecisionName.consolidate


def test_key_hit_is_consolidate():
    assert decide(metrics(key_hit_pct=0.5)).name == DecisionName.consolidate


def test_deload_beats_repeat():
    assert decide(metrics(compliance=0.5, pain_reports=2)).name == DecisionName.deload


def test_custom_thresholds():
    t = Thresholds(volume_progress=0.05)
    assert decide(metrics(), t).volume_change == pytest.approx(0.05)


def test_taper_volume_cap():
    b = make_block([make_week(MON, WeekKind.taper, scale=0.9), make_week(MON + timedelta(days=7), WeekKind.taper, scale=0.9)])
    lim = Limits(taper_ratios=[0.5, 0.3])
    errs = validate_block(b, lim, baseline_hours=BASELINE_H, baseline_dplus=0)
    assert has(errs, "taper") and sum("taper" in e and "massimo" in e for e in errs) == 2


def test_final_week_strength_count():
    b = make_block()
    lim = Limits(strength_final_week=1)
    errs = validate_block(b, lim, baseline_hours=BASELINE_H, baseline_dplus=0)
    assert has(errs, "settimana 2") and has(errs, "richiesti 1")
