"""Blocco -> file .ics (eventi di un giorno intero) da importare in Google Calendar."""

from datetime import date, datetime, timedelta, timezone

from coach.plan.models import Block, Kind

KIND_IT = {
    Kind.easy: "Corsa facile", Kind.recovery: "Recupero", Kind.long: "Lungo", Kind.tempo: "Tempo",
    Kind.intervals: "Fartlek/ripetute", Kind.marathon_pace: "Passo maratona", Kind.race: "Gara",
}


def _esc(text: str) -> str:
    return text.replace("\\", "\\\\").replace(";", "\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line: str) -> str:
    """RFC 5545: righe di al massimo 75 byte, continuazione con CRLF + spazio (senza spezzare i caratteri UTF-8)."""
    out, cur, size = [], "", 0
    for ch in line:
        n = len(ch.encode())
        if size + n > (75 if not out else 74):
            out.append(cur)
            cur, size = "", 0
        cur += ch
        size += n
    out.append(cur)
    return "\r\n ".join(out)


def _event(uid: str, day: date, title: str, description: str, stamp: str) -> list[str]:
    return ["BEGIN:VEVENT", f"UID:{uid}@training-planner", f"DTSTAMP:{stamp}",
            f"DTSTART;VALUE=DATE:{day:%Y%m%d}", f"DTEND;VALUE=DATE:{day + timedelta(days=1):%Y%m%d}",
            f"SUMMARY:{_esc(title)}", f"DESCRIPTION:{_esc(description)}", "TRANSP:TRANSPARENT", "END:VEVENT"]


def block_to_ics(block: Block, now: datetime | None = None) -> str:
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//training-planner//coach//IT",
             "CALSCALE:GREGORIAN", "X-WR-CALNAME:Allenamento"]
    for wi, w in enumerate(block.weeks, 1):
        for i, s in enumerate(sorted(w.sessions, key=lambda s: (s.date, -s.duration_min))):
            title = f"{'🏁 ' if s.fixed else '🏃 '}{KIND_IT[s.kind]} {s.duration_min}'"
            if s.date in w.strength_days:
                title += " + forza"
            desc = [f"Settimana {wi} ({w.kind.value}) · {s.duration_min} min · {s.intensity.value}"]
            if s.target:
                desc.append(f"Target: {s.target}")
            if s.description:
                desc.append(s.description)
            if s.date in w.strength_days:
                desc.append("Forza: sessione in palestra, dopo la corsa.")
            lines += _event(f"{s.date}-run-{i}", s.date, title, "\n".join(desc), stamp)
        sessions_days = {s.date for s in w.sessions}
        for d in w.strength_days:
            if d not in sessions_days:
                lines += _event(f"{d}-strength", d, "🏋️ Forza",
                                f"Settimana {wi} ({w.kind.value}) · giorno senza corsa.", stamp)
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(l) for l in lines) + "\r\n"
