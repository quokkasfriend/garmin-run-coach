from datetime import date

from coach.plan.match import Run, match_block, summarize
from coach.plan.models import Block, Intensity, Kind, Session, Week, WeekKind


def _block():
    s = [
        Session(date=date(2026, 10, 27), kind=Kind.easy, intensity=Intensity.easy, duration_min=45),
        Session(date=date(2026, 10, 29), kind=Kind.marathon_pace, intensity=Intensity.hard, duration_min=90,
                z3plus_min=45),
        Session(date=date(2026, 10, 30), kind=Kind.easy, intensity=Intensity.easy, duration_min=40),
        Session(date=date(2026, 11, 1), kind=Kind.long, intensity=Intensity.easy, duration_min=70),
    ]
    return Block(phase="x", start_date=date(2026, 10, 26),
                 weeks=[Week(start=date(2026, 10, 26), kind=WeekKind.normal, sessions=s)])


def test_only_past_sessions_and_unmatched_is_zero():
    ms = match_block(_block(), [Run(1, date(2026, 10, 27), 45, 2)], today=date(2026, 10, 31))
    assert [m.session.date.day for m in ms] == [27, 29, 30]
    assert ms[0].target_hit and ms[0].compliance == 1.0
    assert ms[1].run is None and ms[1].compliance == 0 and not ms[1].target_hit


def test_easy_run_too_hard_misses_target():
    ms = match_block(_block(), [Run(1, date(2026, 10, 27), 45, 20)], today=date(2026, 10, 28))
    assert not ms[0].target_hit


def test_hard_needs_z3_and_summary():
    runs = [Run(1, date(2026, 10, 27), 44, 1), Run(2, date(2026, 10, 29), 88, 30),
            Run(3, date(2026, 10, 30), 20, 0)]
    ms = match_block(_block(), runs, today=date(2026, 11, 1))
    assert [m.target_hit for m in ms] == [True, True, False]
    comp, key = summarize(ms)
    assert round(comp, 2) == round((44 / 45 + 88 / 90 + 0.5) / 3, 2)
    assert key == 1.0   # solo la seduta dura è chiave tra le passate
