import pytest

from coach.plan.adapt import Thresholds
from coach.plan.methodology import (
    check_provenance,
    limits_from_methodology,
    load_methodology,
    thresholds_from_methodology,
)
from coach.settings import load_config


def test_every_value_has_a_source():
    assert check_provenance(load_methodology()) == []


def test_missing_source_is_detected():
    assert check_provenance({"limits": {"x": {"value": 1}}})
    assert not check_provenance({"limits": {"x": {"value": 1, "project_default": True}}})


def test_limits_come_from_methodology_and_config():
    limits = limits_from_methodology(load_methodology(), load_config())
    assert limits.ramp_hours_max_pct == pytest.approx(0.10)
    assert limits.long_run_max_pct == pytest.approx(0.40)
    assert limits.strength_per_week == 3 and limits.max_run_days == 5


def test_thresholds_load():
    t = thresholds_from_methodology(load_methodology())
    assert t.volume_deload == pytest.approx(-0.30)
    assert t.rhr_rise_bpm == 5 and isinstance(t, Thresholds)


def test_reference_block_valid_with_methodology_limits():
    from coach.plan.validate import fixed_events_from_config, validate_block
    from tests.test_calendar import reference_block

    cfg = load_config()
    errs = validate_block(
        reference_block(), limits_from_methodology(load_methodology(), cfg),
        fixed_events_from_config(cfg), baseline_hours=7.27, baseline_dplus=422,
    )
    assert errs == []
