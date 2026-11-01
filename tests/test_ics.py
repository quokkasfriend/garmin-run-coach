from datetime import date, datetime, timezone

from coach.plan.ics import block_to_ics
from tests.test_calendar import reference_block


def test_ics_structure_and_folding():
    ics = block_to_ics(reference_block(), datetime(2026, 10, 28, tzinfo=timezone.utc))
    assert ics.startswith("BEGIN:VCALENDAR\r\n") and ics.endswith("END:VCALENDAR\r\n")
    assert ics.count("BEGIN:VEVENT") == ics.count("END:VEVENT") > 20
    assert all(len(l.encode()) <= 75 for l in ics.split("\r\n"))
    uids = [l for l in ics.split("\r\n") if l.startswith("UID:")]
    assert len(uids) == len(set(uids))
    assert "DTSTART;VALUE=DATE:20261129" in ics   # maratona
