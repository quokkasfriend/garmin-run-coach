"""plan-block: contesto deterministico -> Claude (`claude -p`) -> validatore -> rigenera se viola."""

import json
import subprocess
from collections.abc import Callable
from datetime import date, timedelta

from pydantic import ValidationError

from coach.agent.prompts import SYSTEM, build_user_prompt
from coach.db import connect
from coach.metrics.weekly import weekly_summary
from coach.plan.methodology import check_provenance, limits_from_methodology, load_methodology
from coach.plan.models import Block
from coach.plan.render import render_markdown
from coach.plan.validate import Limits, fixed_events_from_config, validate_block
from coach.settings import BLOCKS_DIR, ensure_dirs, load_config

MAX_ATTEMPTS = 3
CLAUDE_TIMEOUT_S = 600

Llm = Callable[[str], str]


def claude_cli(prompt: str) -> str:
    """Chiama Claude Code in modalità non interattiva (abbonamento, nessuna API key), senza tool."""
    proc = subprocess.run(
        ["claude", "-p", "--tools", "", "--no-session-persistence", "--output-format", "json",
         "--append-system-prompt", SYSTEM],
        input=prompt, capture_output=True, text=True, timeout=CLAUDE_TIMEOUT_S,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"claude -p fallito ({proc.returncode}): {proc.stderr.strip()[:500]}")
    out = json.loads(proc.stdout)
    if out.get("is_error"):
        raise RuntimeError(f"claude -p errore: {out.get('result')}")
    return out["result"]


def parse_block(text: str) -> Block:
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("nessun oggetto JSON nella risposta")
    return Block.model_validate_json(text[start : end + 1])


def _recent(today: date) -> tuple[dict, float | None, float | None]:
    monday = today - timedelta(days=today.weekday())
    df = weekly_summary()
    weeks = df[df.index < monday].tail(6) if not df.empty else df
    baseline_h = float(weeks.iloc[-1]["hours"]) if len(weeks) else None
    baseline_d = float(weeks.iloc[-1]["dplus"]) if len(weeks) else None
    rows = [
        {"lunedì": str(i), "corse": int(r.runs), "ore": round(r.hours, 2), "km": round(r.km, 1),
         "dplus_m": round(r.dplus), "z3plus_pct": None if r.z3plus_pct != r.z3plus_pct else r.z3plus_pct,
         "lungo_km": round(r.long_run_km, 1) if r.long_run_km == r.long_run_km else None}
        for i, r in weeks.iterrows()
    ]
    with connect() as conn:
        daily = [json.loads(r["json"]) for r in conn.execute(
            "SELECT json FROM health_raw WHERE kind='daily' ORDER BY date DESC LIMIT 7")]
        hrv = [json.loads(r["json"]) for r in conn.execute(
            "SELECT json FROM health_raw WHERE kind='hrv' ORDER BY date DESC LIMIT 7")]
    rhr = [d["heartRate"]["restingValue"] for d in daily if (d.get("heartRate") or {}).get("restingValue")]
    hrv_avg = [h["lastNightAvg"] for h in hrv if h.get("lastNightAvg")]
    recent = {
        "ultime_settimane_complete": rows,
        "fc_riposo_media_7g": round(sum(rhr) / len(rhr), 1) if rhr else None,
        "hrv_notte_media_7g": round(sum(hrv_avg) / len(hrv_avg), 1) if hrv_avg else None,
        "riferimento_mezza": "1:31:00 (≈4:19/km)",
    }
    return recent, baseline_h, baseline_d


def _skeleton(cfg: dict, limits: Limits, baseline_h: float | None, today: date) -> list[dict]:
    """Per ogni settimana: tipo, forza richiesta, tetto ore (deload/normal/taper/recovery)."""
    blk = cfg["block"]
    start = blk["start_date"]
    n = blk["weeks"]
    out = []
    for i in range(1, n + 1):
        wp = blk["weeks_plan"][i]
        kind = wp["week_kind"]
        cap = None
        if baseline_h:
            if kind == "deload":
                cap = baseline_h * limits.deload_max_ratio
            elif kind == "normal":
                cap = baseline_h * (1 + limits.ramp_hours_max_pct)
                if limits.normal_max_hours:
                    cap = min(cap, limits.normal_max_hours)
            elif kind == "recovery" and limits.recovery_ratios:
                k = sum(1 for j in range(1, i) if blk["weeks_plan"][j]["week_kind"] == "recovery")
                cap = baseline_h * limits.recovery_ratios[min(k, len(limits.recovery_ratios) - 1)]
            elif kind == "taper":
                k = sum(1 for j in range(1, i) if blk["weeks_plan"][j]["week_kind"] == "taper")
                cap = baseline_h * limits.taper_ratios[min(k, len(limits.taper_ratios) - 1)] if limits.taper_ratios else None
        out.append({
            "settimana": i,
            "lunedì": str(start + timedelta(days=7 * (i - 1))),
            "kind": kind,
            "nota": wp.get("note", ""),
            "forza_richiesta": limits.recovery_strength if kind == "recovery" and limits.recovery_strength is not None
            else limits.strength_final_week if i == n and limits.strength_final_week is not None
            else limits.strength_per_week,
            "tetto_ore_pianificate": round(cap, 2) if cap else None,
        })
    return out


def build_context(today: date | None = None, cfg: dict | None = None, reference: tuple[float, float] | None = None,
                  decision: dict | None = None) -> tuple[dict, Limits, list, float | None, float | None]:
    """`reference` = (ore, D+) di riferimento al posto dell'ultima settimana completa; `decision` = fine blocco."""
    today = today or date.today()
    cfg, meth = cfg or load_config(), load_methodology()
    errs = check_provenance(meth)
    if not meth.get("sources") or errs:
        raise SystemExit("methodology.yaml senza fonti:\n" + "\n".join(errs))
    limits = limits_from_methodology(meth, cfg)
    if decision:
        limits.normal_max_hours = round(reference[0] * (1 + decision["variazione_volume"]), 2)
    events = fixed_events_from_config(cfg)
    recent, base_h, base_d = _recent(today)
    if reference:
        base_h, base_d = reference
    ctx = {
        "today": str(today),
        "config": {k: v for k, v in cfg.items() if k != "fixed_events"},
        "methodology": meth,
        "recent": recent,
        "limits": limits.model_dump(),
        "skeleton": _skeleton(cfg, limits, base_h, today),
        "fixed_events": [e.model_dump(mode="json") for e in events],
    }
    if decision:
        ctx["decision"] = decision
    return ctx, limits, events, base_h, base_d


def generate_block(llm: Llm = claude_cli, today: date | None = None, max_attempts: int = MAX_ATTEMPTS,
                   on_step: Callable[[str], None] = print, context: tuple | None = None) -> tuple[Block, list[str]]:
    ctx, limits, events, base_h, base_d = context or build_context(today)
    violations: list[str] | None = None
    for attempt in range(1, max_attempts + 1):
        on_step(f"tentativo {attempt}/{max_attempts}: chiamo Claude…")
        try:
            block = parse_block(llm(build_user_prompt(ctx, violations)))
        except (ValueError, ValidationError) as e:
            violations = [f"risposta non valida: {str(e)[:400]}"]
            on_step(f"  JSON non valido: {violations[0]}")
            continue
        violations = validate_block(block, limits, events, base_h, base_d, ctx["config"].get("pinned_days"))
        if not violations:
            return block, []
        on_step(f"  {len(violations)} violazioni:")
        for v in violations:
            on_step(f"   - {v}")
    raise SystemExit(f"Blocco non valido dopo {max_attempts} tentativi: allenta un vincolo.\n"
                     + "\n".join(violations or []))


def save_block(block: Block, directory=BLOCKS_DIR) -> tuple[int, str]:
    ensure_dirs()
    stem = f"block-{block.start_date}"
    (directory / f"{stem}.json").write_text(block.model_dump_json(indent=2))
    (directory / f"{stem}.md").write_text(render_markdown(block))
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO block (phase, start_date, weeks, json) VALUES (?, ?, ?, ?)",
            (block.phase, str(block.start_date), len(block.weeks), block.model_dump_json()),
        )
        return cur.lastrowid, str(directory / f"{stem}.md")
