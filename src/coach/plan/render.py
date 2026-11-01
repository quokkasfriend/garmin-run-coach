"""Blocco -> tabella .md da trascrivere sull'orologio (l'API Garmin è solo in lettura)."""

from coach.plan.models import Block

DAYS = ["lun", "mar", "mer", "gio", "ven", "sab", "dom"]


def render_markdown(block: Block) -> str:
    out = [f"# Blocco {block.phase} dal {block.start_date}", "", block.rationale, ""]
    for i, w in enumerate(block.weeks, 1):
        z3 = sum(s.z3plus_min for s in w.sessions)
        out += [
            f"## Settimana {i} — {w.kind.value} (dal {w.start})",
            f"Corsa: {w.hours:.1f} h · D+ {w.dplus} m · Z3+ pianificata {z3} min",
            "",
            "| Giorno | Sessione | Min | Target | Descrizione |",
            "|---|---|---|---|---|",
        ]
        strength = set(w.strength_days)
        for d in w.days:
            sessions = sorted((s for s in w.sessions if s.date == d), key=lambda s: -s.duration_min)
            label = f"{DAYS[d.weekday()]} {d:%d/%m}"
            if not sessions:
                out.append(f"| {label} | {'forza' if d in strength else 'riposo'} | | | |")
                continue
            for s in sessions:
                extra = " + forza" if d in strength else ""
                tag = " 🏁" if s.fixed else ""
                out.append(f"| {label} | {s.kind.value} ({s.intensity.value}){tag}{extra} | {s.duration_min} "
                           f"| {s.target} | {s.description} |")
                extra = ""
        out.append("")
    return "\n".join(out)
