from datetime import date

import pytest

from coach.agent.planner import generate_block, parse_block
from coach.agent.prompts import build_user_prompt
from coach.agent.planner import build_context
from coach.plan.render import render_markdown
from tests.test_calendar import reference_block

TODAY = date(2026, 10, 27)


@pytest.fixture(autouse=True)
def no_pinned_days(monkeypatch):
    """Il blocco di riferimento non conosce i giorni fissati in config.yaml."""
    from coach.settings import load_config

    monkeypatch.setattr("coach.agent.planner.load_config",
                        lambda: {k: v for k, v in load_config().items() if k != "pinned_days"})


def good() -> str:
    return "Ecco il blocco:\n```json\n" + reference_block().model_dump_json() + "\n```"


def bad() -> str:
    b = reference_block()
    b.weeks[3].sessions[0].duration_min = 400  # taper enorme
    return b.model_dump_json()


def run(llm, attempts=3):
    return generate_block(llm, today=TODAY, max_attempts=attempts, on_step=lambda _: None)


def test_parse_block_strips_fences():
    assert parse_block(good()).phase == "marathon_specific_taper"


def test_accepts_valid_block_first_try():
    calls = []
    block, v = run(lambda p: calls.append(p) or good())
    assert v == [] and len(calls) == 1 and len(block.weeks) == 5


def test_regenerates_with_violations_in_prompt():
    prompts, answers = [], iter([bad(), good()])
    run(lambda p: prompts.append(p) or next(answers))
    assert len(prompts) == 2
    assert "ATTENZIONE" not in prompts[0] and "taper" in prompts[1] and "ATTENZIONE" in prompts[1]


def test_invalid_json_triggers_retry():
    answers = iter(["non json", good()])
    block, _ = run(lambda p: next(answers))
    assert block.weeks


def test_gives_up_after_max_attempts():
    with pytest.raises(SystemExit):
        run(lambda p: bad(), attempts=2)


def test_prompt_contains_constraints_and_fixed_events():
    ctx = build_context(TODAY)[0]
    p = build_user_prompt(ctx)
    assert "City Marathon" in p and "tetto_ore_pianificate" in p and "koop" in p


def test_markdown_render():
    md = render_markdown(reference_block())
    assert "Settimana 5" in md and "City Marathon" in md
