from datetime import date

from coach.plan.adapt import BlockMetrics, DecisionName, decide
from coach.plan.match import Match
from coach.plan.models import Block, Intensity, Kind, Session, Week
from coach.plan import review as R


def _block():
    s = Session(date=date(2026, 10, 27), kind=Kind.easy, intensity=Intensity.easy, duration_min=45)
    return Block(phase="x", start_date=date(2026, 10, 26), weeks=[Week(start=date(2026, 10, 26), sessions=[s])]), s


def test_metrics_from_feedback(monkeypatch):
    block, s = _block()
    monkeypatch.setattr(R, "feedback_in", lambda a, b: [
        {"activity_id": 1, "date": "2026-10-27", "rpe": 8, "feel": "pesante", "pain": "polpaccio"}])
    monkeypatch.setattr(R, "health_changes", lambda a, b: (-9.0, 6.0))
    m, extra = R.build_metrics(block, [Match("x", s, None, 1.0, True, False)], date(2026, 10, 29))
    assert m.pain_reports == 1 and m.rpe_above_expected
    assert decide(m).name == DecisionName.deload   # HRV -9% + FC +6 = 2 segnali
    assert "polpaccio" in extra["dolori"][0]


def test_narrative_handles_missing_health():
    m = BlockMetrics(compliance=0.9, key_hit_pct=1.0)
    text = R.narrative(m, decide(m), {"sessioni_valutate": 20, "feedback": 0, "dolori": []})
    assert "PROGRESS" in text and "n.d." in text
