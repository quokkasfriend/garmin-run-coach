from datetime import date

from coach.plan.models import Block, Intensity, Kind, Session, Week
from coach.plan.validate import _check_pinned

PINNED = [{"date": date(2026, 10, 28), "sessions": [{"kind": "easy", "duration_min": 45}]},
          {"date": date(2026, 10, 30), "sessions": []}]


def _block(sessions):
    return Block(phase="x", start_date=date(2026, 10, 26), weeks=[Week(start=date(2026, 10, 26), sessions=sessions)])


def _s(day, mins):
    return Session(date=date(2026, 10, day), kind=Kind.easy, intensity=Intensity.easy, duration_min=mins)


def test_pinned_ok():
    assert _check_pinned(_block([_s(28, 45), _s(29, 50)]), PINNED) == []


def test_pinned_wrong_duration_and_rest_violated():
    errs = _check_pinned(_block([_s(28, 40), _s(30, 30)]), PINNED)
    assert len(errs) == 2
