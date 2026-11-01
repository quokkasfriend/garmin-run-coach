"""Prompt per il planner. Claude scrive il blocco; i numeri e le decisioni arrivano già calcolati."""

import json

import yaml

SYSTEM = (
    "Sei un allenatore di corsa su strada. Costruisci blocchi di allenamento rispettando le regole "
    "della metodologia fornita e i vincoli numerici. Non fai calcoli di metriche e non cambi i dati "
    "dell'atleta. Rispondi SOLO con un oggetto JSON valido, senza testo prima o dopo e senza code fence."
)

EXAMPLE = {
    "phase": "marathon_specific_taper",
    "start_date": "YYYY-MM-DD",
    "rationale": "perché questa struttura, citando le fonti (koop/uphill/powell) e i dati recenti",
    "weeks": [
        {
            "start": "YYYY-MM-DD (lunedì)",
            "kind": "normal | deload | race_week | taper | recovery",
            "strength_days": ["YYYY-MM-DD"],
            "sessions": [
                {
                    "date": "YYYY-MM-DD",
                    "kind": "easy | recovery | long | tempo | intervals | marathon_pace | race",
                    "intensity": "easy | moderate | hard | race",
                    "duration_min": 45,
                    "distance_km": None,
                    "dplus_m": 0,
                    "z3plus_min": 0,
                    "fixed": False,
                    "target": "RPE / passo / FC obiettivo",
                    "description": "cosa fare, in italiano",
                }
            ],
        }
    ],
}


def build_user_prompt(ctx: dict, violations: list[str] | None = None) -> str:
    parts = [
        "# Atleta e obiettivo (config.yaml)",
        yaml.safe_dump(ctx["config"], allow_unicode=True, sort_keys=False),
        "# Dati recenti (da Garmin, già calcolati)",
        json.dumps(ctx["recent"], ensure_ascii=False, indent=1, default=str),
        "# Metodologia (fonti: koop, uphill, powell)",
        yaml.safe_dump(ctx["methodology"], allow_unicode=True, sort_keys=False),
        "# Vincoli del validatore (violarli fa rigenerare il blocco)",
        json.dumps(ctx["limits"], ensure_ascii=False, indent=1),
        "# Scheletro del blocco (settimane già decise; oggi è " + ctx["today"] + ")",
        json.dumps(ctx["skeleton"], ensure_ascii=False, indent=1),
        *(["# Decisione di fine blocco precedente (deterministica, non modificarla)",
           json.dumps(ctx["decision"], ensure_ascii=False, indent=1)] if ctx.get("decision") else []),
        "# Eventi fissi: inseriscili ESATTAMENTE così, con fixed=true, nessuna altra sessione in quei giorni",
        json.dumps(ctx["fixed_events"], ensure_ascii=False, indent=1, default=str),
        "# Formato di output (JSON)",
        json.dumps(EXAMPLE, ensure_ascii=False, indent=1),
        REGOLE,
    ]
    if violations:
        parts += [
            "# ATTENZIONE: il tuo blocco precedente viola questi vincoli. Correggi e restituisci il blocco COMPLETO.",
            "\n".join(f"- {v}" for v in violations),
        ]
    return "\n\n".join(parts)


REGOLE = """# Regole di scrittura
- Nessuna sessione né forza nei giorni già passati (prima di oggi).
- Le date devono stare dentro la settimana lun-dom indicata nello scheletro.
- Un solo allenamento al giorno, salvo gli eventi fissi. Al massimo i giorni di corsa indicati.
- strength_days: scegli i giorni nel rispetto dei vincoli (mai in un giorno di corsa dura/gara né il giorno prima; almeno un giorno senza né corsa né forza).
- Rispetta i tetti di ore indicati nello scheletro (sono prudenti: restaci sotto).
- z3plus_min = minuti previsti in Z3 o sopra (zone Garmin), mai maggiori della durata.
- Settimane recovery: solo corse facili (intensity easy), z3plus_min 0, nessun lungo oltre i 60 minuti, forza come indicato.
- Se non c'è nessun evento fisso né gara obiettivo, non inventarne: costruisci base aerobica e rispetta i tetti.
- pinned_days (config): sono giorni già decisi dall'atleta. Riproducili ESATTAMENTE (stesso tipo e stessa durata; lista vuota = nessuna corsa). Sceglici la forza compatibile. Se la descrizione di un giorno fissato era diversa (es. allunghi) lasciala come nel blocco precedente. Tieni conto di notes.
- Il campo rationale spiega le scelte e cita le fonti; segnala dove usi default di progetto o lacune (gaps).
- Descrizioni e target in italiano, concreti (RPE o passo). L'obiettivo maratona è goal.target_time (passo ≈ 4:37/km): per le sedute a passo maratona usa quel passo con RPE. La soglia NON è nota con precisione: usa RPE e riferimenti dalla mezza in 1:31."""
