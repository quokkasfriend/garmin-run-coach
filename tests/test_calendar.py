"""Il calendario reale (config.yaml) ammette almeno un blocco valido? Se no, i vincoli sono incompatibili."""

from datetime import date

from coach.plan.models import Block, Intensity, Kind, Session, Week, WeekKind
from coach.plan.validate import fixed_events_from_config, limits_from_config, validate_block
from coach.settings import load_config

E, M, H = Intensity.easy, Intensity.moderate, Intensity.hard


def s(day, kind, inten, minutes, **kw):
    return Session(date=day, kind=kind, intensity=inten, duration_min=minutes, **kw)


def d(m, day):
    return date(2026, m, day)


def reference_block() -> Block:
    w1 = Week(start=d(10, 26), kind=WeekKind.deload, strength_days=[d(10, 27), d(10, 28), d(10, 30)], sessions=[
        s(d(10, 27), Kind.easy, E, 50), s(d(10, 28), Kind.easy, E, 45), s(d(10, 30), Kind.easy, E, 40),
        s(d(10, 31), Kind.easy, E, 45), s(d(11, 1), Kind.long, M, 90),
    ])
    w2 = Week(start=d(11, 2), kind=WeekKind.race_week, strength_days=[d(11, 2), d(11, 3), d(11, 5)], sessions=[
        s(d(11, 2), Kind.easy, E, 45), s(d(11, 3), Kind.easy, E, 45), s(d(11, 5), Kind.easy, E, 40),
        s(d(11, 7), Kind.race, Intensity.hard, 95, fixed=True, description="City Half 21k"),
        s(d(11, 7), Kind.easy, E, 30, fixed=True, description="City 5k"),
        s(d(11, 8), Kind.easy, E, 55, fixed=True, description="City 10k #1"),
        s(d(11, 8), Kind.easy, E, 55, fixed=True, description="City 10k #2"),
    ])
    w3 = Week(start=d(11, 9), kind=WeekKind.normal, strength_days=[d(11, 9), d(11, 10), d(11, 13)], sessions=[
        s(d(11, 10), Kind.easy, E, 60), s(d(11, 11), Kind.easy, E, 50),
        s(d(11, 12), Kind.marathon_pace, H, 90, z3plus_min=40),
        s(d(11, 13), Kind.easy, E, 50), s(d(11, 15), Kind.long, M, 150),
    ])
    w4 = Week(start=d(11, 16), kind=WeekKind.taper, strength_days=[d(11, 16), d(11, 19), d(11, 20)], sessions=[
        s(d(11, 17), Kind.easy, E, 50), s(d(11, 18), Kind.marathon_pace, H, 60, z3plus_min=25),
        s(d(11, 19), Kind.easy, E, 45), s(d(11, 20), Kind.easy, E, 40), s(d(11, 22), Kind.long, M, 90),
    ])
    w5 = Week(start=d(11, 23), kind=WeekKind.taper, strength_days=[d(11, 23)], sessions=[
        s(d(11, 23), Kind.easy, E, 35), s(d(11, 24), Kind.easy, E, 35), s(d(11, 26), Kind.easy, E, 30),
        s(d(11, 28), Kind.easy, E, 20),
        s(d(11, 29), Kind.race, Intensity.race, 210, fixed=True, description="City Marathon"),
    ])
    return Block(phase="marathon_specific_taper", start_date=d(10, 26), weeks=[w1, w2, w3, w4, w5])


def test_reference_block_satisfies_real_config():
    cfg = load_config()
    errs = validate_block(
        reference_block(),
        limits_from_config(cfg),
        fixed_events_from_config(cfg),
        baseline_hours=7.27,
        baseline_dplus=422,
    )
    assert errs == []
