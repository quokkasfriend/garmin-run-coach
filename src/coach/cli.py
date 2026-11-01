import typer

app = typer.Typer(no_args_is_help=True, help="Running coach locale.")


@app.command()
def probe() -> None:
    """Salva il JSON grezzo di ogni endpoint Garmin in data/probe/."""
    from coach.garmin.probe import run_probe

    run_probe(typer.echo)


@app.command()
def sync(
    days: int = typer.Option(365, help="Finestra massima di storico."),
    fit: bool = typer.Option(True, help="Scarica i FIT delle corse."),
) -> None:
    """Sincronizza Garmin -> SQLite (incrementale)."""
    from coach.garmin.sync import sync_all

    sync_all(days=days, fit=fit, on_step=typer.echo)


@app.command()
def weeks(last: int = typer.Option(12, help="Quante settimane mostrare.")) -> None:
    """Ore, km, D+ e quota Z3+ per settimana (solo corsa) dai dati sincronizzati."""
    from coach.metrics.weekly import weekly_summary

    df = weekly_summary()
    if df.empty:
        raise typer.Exit("Nessuna attività: esegui prima `coach sync`.")
    df = df.tail(last).copy()
    df.index.name = "lunedì"
    df["runs"] = df["runs"].astype(int)
    typer.echo(df.round({"hours": 2, "km": 1, "dplus": 0, "strength_h": 1, "long_run_km": 1}).to_string())


@app.command("plan-block")
def plan_block(
    attempts: int = typer.Option(3, help="Tentativi massimi prima di arrendersi."),
    dry_run: bool = typer.Option(False, help="Stampa il prompt e non chiama Claude."),
) -> None:
    """Genera il blocco da config.yaml + methodology.yaml con `claude -p` e lo valida."""
    from coach.agent.planner import build_context, generate_block, save_block
    from coach.agent.prompts import build_user_prompt

    if dry_run:
        typer.echo(build_user_prompt(build_context()[0]))
        raise typer.Exit()
    block, _ = generate_block(max_attempts=attempts, on_step=typer.echo)
    block_id, md = save_block(block)
    typer.echo(f"Blocco valido (id {block_id}) -> {md}")


@app.command()
def log(
    rpe: int = typer.Option(None, help="Sforzo percepito 1-10."),
    feel: str = typer.Option(None, help="ottimo | buono | ok | pesante | pessimo."),
    pain: str = typer.Option(None, help="Dolore o fastidio (testo libero, es. 'polpaccio dx')."),
    day: str = typer.Option(None, "--date", help="YYYY-MM-DD (default: oggi)."),
    activity: int = typer.Option(None, help="activity_id Garmin (default: ultima corsa del giorno)."),
    list_: bool = typer.Option(False, "--list", help="Mostra gli ultimi feedback invece di registrarne uno."),
) -> None:
    """Registra RPE, sensazioni e dolore di una sessione (alimenta la revisione del blocco)."""
    from datetime import date as _date

    from coach.db import connect
    from coach.feedback import add_feedback, list_feedback

    with connect() as conn:
        if list_:
            for f in list_feedback(conn):
                typer.echo(f"{f['date']}  RPE {f['rpe'] or '-':>2}  {f['feel'] or '-':8} "
                           f"{f['km']:>5} km {f['min']:>3}'  {f['pain'] or ''}")
            raise typer.Exit()
        try:
            d = _date.fromisoformat(day) if day else _date.today()
            fid, act = add_feedback(conn, d, rpe, feel, pain, activity)
        except ValueError as e:
            raise typer.BadParameter(str(e))
    typer.echo(f"Feedback {fid} salvato per il {d}" + (f" (attività {act})" if act else
               " (nessuna corsa trovata quel giorno: legato solo alla data, prova `coach sync`)"))


@app.command("match")
def match_cmd(block_id: int = typer.Option(None, "--block-id", help="Default: ultimo blocco.")) -> None:
    """Abbina le sessioni del blocco alle corse Garmin (solo giorni passati) e salva la compliance."""
    from datetime import date as _date

    from coach.plan.match import load_block, load_runs, match_block, save_matches, summarize

    bid, block = load_block(block_id)
    matches = match_block(block, load_runs(), _date.today())
    if not matches:
        raise typer.Exit("Nessuna sessione passata da valutare.")
    save_matches(bid, matches)
    for m in matches:
        got = f"{m.run.minutes:>4.0f}' (Z3+ {m.run.z3plus_min:.0f}')" if m.run else "   non fatta"
        flag = "ok " if m.target_hit else "NO "
        key = "*" if m.is_key else " "
        typer.echo(f"{m.session.date}  {m.session.kind.value:13}{key} piano {m.session.duration_min:>3}'  "
                   f"fatto {got}  {flag}")
    comp, key = summarize(matches)
    typer.echo(f"\nCompliance {comp:.0%} · sessioni chiave (*) centrate {key:.0%} · blocco {bid}")


@app.command("review-block")
def review_block(block_id: int = typer.Option(None, "--block-id", help="Default: ultimo blocco.")) -> None:
    """Fine blocco: abbina le sessioni, calcola le metriche e applica le regole di adattamento."""
    from datetime import date as _date
    from datetime import timedelta as _td

    from coach.plan.match import load_block, load_runs, match_block, save_matches
    from coach.plan.review import narrative, review, save_review

    today = _date.today()
    bid, block = load_block(block_id)
    matches = match_block(block, load_runs(), today)
    if not matches:
        raise typer.Exit("Nessuna sessione passata da valutare.")
    save_matches(bid, matches)
    m, decision, extra = review(block, matches, today)
    text = narrative(m, decision, extra)
    save_review(bid, m, decision, text)
    typer.echo(text)
    if extra["fino_al"] < str(block.weeks[-1].start + _td(days=6)):
        typer.echo(f"\nATTENZIONE: blocco non concluso, valutato solo fino al {extra['fino_al']}.")


@app.command("plan-next")
def plan_next(
    weeks: int = typer.Option(4, help="Settimane del nuovo blocco (le prime 2 sono recupero fisso)."),
    attempts: int = typer.Option(3, help="Tentativi massimi."),
    dry_run: bool = typer.Option(False, help="Stampa il prompt e non chiama Claude."),
    force: bool = typer.Option(False, help="Genera anche se il blocco precedente non è concluso."),
) -> None:
    """Blocco 2: revisione del blocco concluso -> decisione -> recupero fisso + ripresa, validato."""
    from datetime import date as _date
    from datetime import timedelta as _td

    from coach.agent.planner import build_context, generate_block, save_block
    from coach.agent.prompts import build_user_prompt
    from coach.plan.match import load_block, load_runs, match_block, save_matches
    from coach.plan.next_block import decision_ctx, next_config, reference_volume
    from coach.plan.review import narrative, review, save_review
    from coach.settings import load_config

    today = _date.today()
    bid, prev = load_block()
    end = prev.weeks[-1].start + _td(days=6)
    if today <= end and not force:
        raise typer.Exit(f"Il blocco {bid} finisce il {end}: rilancia dopo, o usa --force.")
    matches = match_block(prev, load_runs(), today)
    save_matches(bid, matches)
    m, decision, extra = review(prev, matches, today)
    text = narrative(m, decision, extra)
    save_review(bid, m, decision, text)
    typer.echo(text + "\n")
    ref = reference_volume(prev)
    ctx = build_context(today, next_config(load_config(), prev, weeks), ref, decision_ctx(decision, ref))
    if dry_run:
        typer.echo(build_user_prompt(ctx[0]))
        raise typer.Exit()
    block, _ = generate_block(max_attempts=attempts, on_step=typer.echo, context=ctx)
    block_id, md = save_block(block)
    typer.echo(f"Blocco 2 valido (id {block_id}) -> {md}")


@app.command("export-ics")
def export_ics(
    block_id: int = typer.Option(None, "--block-id", help="Default: ultimo blocco."),
    out: str = typer.Option(None, help="File di output (default: data/blocks/block-<data>.ics)."),
) -> None:
    """Esporta il blocco in .ics (eventi di un giorno intero) per Google Calendar."""
    from pathlib import Path

    from coach.plan.ics import block_to_ics
    from coach.plan.match import load_block
    from coach.settings import BLOCKS_DIR

    _, block = load_block(block_id)
    path = Path(out) if out else BLOCKS_DIR / f"block-{block.start_date}.ics"
    path.write_text(block_to_ics(block), newline="")
    typer.echo(f"{path}")


if __name__ == "__main__":
    app()
