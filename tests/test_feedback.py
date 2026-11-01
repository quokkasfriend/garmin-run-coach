import json
import sqlite3
from datetime import date

import pytest

from coach.db import SCHEMA
from coach.feedback import add_feedback, list_feedback


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    for aid, start, typ in [(1, "2026-10-27 07:00:00", "running"), (2, "2026-10-27 18:00:00", "running"),
                            (3, "2026-10-27 12:00:00", "strength_training")]:
        c.execute("INSERT INTO activity_raw (activity_id, start_local, type_key, json) VALUES (?,?,?,?)",
                  (aid, start, typ, json.dumps({"distance": 8000, "duration": 2700})))
    return c


def test_links_latest_run_of_day(conn):
    _, act = add_feedback(conn, date(2026, 10, 27), 5, "buono", None)
    assert act == 2


def test_no_run_keeps_date_only(conn):
    _, act = add_feedback(conn, date(2026, 10, 28), None, None, "polpaccio")
    assert act is None


def test_explicit_activity_and_list(conn):
    add_feedback(conn, date(2026, 10, 27), 6, "ok", "ginocchio", activity_id=1)
    [f] = list_feedback(conn)
    assert (f["activity_id"], f["rpe"], f["pain"], f["km"], f["min"]) == (1, 6, "ginocchio", 8.0, 45)


@pytest.mark.parametrize("kw", [dict(rpe=11), dict(rpe=0), dict(rpe=5, feel="boh"), dict()])
def test_rejects_bad_input(conn, kw):
    with pytest.raises(ValueError):
        add_feedback(conn, date(2026, 10, 27), kw.get("rpe"), kw.get("feel"), None)


def test_unknown_activity(conn):
    with pytest.raises(ValueError):
        add_feedback(conn, date(2026, 10, 27), 5, None, None, activity_id=99)
