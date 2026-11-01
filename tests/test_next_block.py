from datetime import date, timedelta

from coach.plan.adapt import Decision, DecisionName
from coach.plan.models import Block, Intensity, Kind, Session, Week, WeekKind
from coach.plan.next_block import decision_ctx, next_config
from coach.plan.validate import Limits, validate_block
from coach.settings import load_config

START = date(2026, 11, 30)


def _w(i, kind, mins_by_day, strength, intensity=Intensity.easy, z3=0):
    start = START + timedelta(days=7 * i)
    sessions = [Session(date=start + timedelta(days=d), kind=Kind.easy, intensity=intensity, duration_min=m,
                        z3plus_min=z3) for d, m in mins_by_day]
    return Week(start=start, kind=kind, sessions=sessions, strength_days=[start + timedelta(days=d) for d in strength])


def _block(rec1=(0, 30), rec_extra_z3=0):
    w1 = _w(0, WeekKind.recovery, [(1, 30), (3, 30), (5, 30), (6, rec1[1])][:3], [0], z3=rec_extra_z3)
    w2 = _w(1, WeekKind.recovery, [(1, 60), (2, 60), (4, 60), (6, 60)], [3])
    w3 = _w(2, WeekKind.normal, [(1, 80), (2, 80), (4, 80), (5, 80), (6, 100)], [0, 3, 5])
    w3.sessions[-1].kind = Kind.long
    return Block(phase="x", start_date=START, weeks=[w1, w2, w3])


LIM = Limits(recovery_ratios=[0.3, 0.6], recovery_strength=1, normal_max_hours=7.3)


def test_valid_recovery_then_build():
    # riferimento 6.5 h: recupero 1 = 1.5 h <= 1.95; recupero 2 = 4 h > 3.9 -> viola
    errs = validate_block(_block(), LIM, [], 6.5, 100)
    assert any("recupero a 4.0 h" in e for e in errs) and not any("settimana 1" in e for e in errs)


def test_recovery_rejects_z3():
    errs = validate_block(_block(rec_extra_z3=5), LIM, [], 6.5, 100)
    assert any("solo corse facili" in e for e in errs)


def test_normal_cap_from_decision():
    errs = validate_block(_block(), Limits(normal_max_hours=6.0, recovery_strength=1), [], 6.5, 100)
    assert any("dalla decisione di fine blocco" in e for e in errs)


def test_next_config_dates_and_kinds():
    prev = Block(phase="x", start_date=date(2026, 10, 26),
                 weeks=[Week(start=date(2026, 10, 26) + timedelta(days=7 * i), sessions=[]) for i in range(5)])
    cfg = next_config(load_config(), prev, 4)
    assert cfg["block"]["start_date"] == START
    assert [cfg["block"]["weeks_plan"][i]["week_kind"] for i in range(1, 5)] == ["recovery"] * 2 + ["normal"] * 2
    assert cfg["fixed_events"] == []   # la maratona è del 29/11, prima del nuovo blocco


def test_decision_ctx_cap():
    d = Decision(name=DecisionName.consolidate, volume_change=0.0, reasons=["x"])
    assert decision_ctx(d, (6.5, 0))["tetto_ore_settimane_normal"] == 6.5
