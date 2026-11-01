"""Decisione di fine blocco: regole deterministiche, nessun LLM."""

from enum import StrEnum

from pydantic import BaseModel


class Thresholds(BaseModel):
    """Default dal piano v2; da sostituire con methodology.yaml -> adaptation."""

    pain_reports_deload: int = 2
    negative_signals_deload: int = 2
    hrv_drop_pct: float = 7.0
    rhr_rise_bpm: float = 5.0
    compliance_repeat: float = 0.70
    sick_days_repeat: int = 5
    compliance_consolidate: float = 0.85
    key_hit_consolidate: float = 0.70
    volume_deload: float = -0.30
    volume_repeat: float = -0.10
    volume_consolidate: float = 0.0
    volume_progress: float = 0.08


class BlockMetrics(BaseModel):
    pain_reports: int = 0
    hrv_change_pct: float | None = None     # variazione vs baseline; negativa = calo
    rhr_change_bpm: float | None = None     # positiva = FC a riposo salita
    rpe_above_expected: bool = False
    compliance: float                       # 0-1, sessioni fatte / pianificate
    key_hit_pct: float                      # 0-1, sessioni chiave centrate
    sick_days: int = 0


class DecisionName(StrEnum):
    deload = "deload"
    repeat = "repeat"
    consolidate = "consolidate"
    progress = "progress"


class Decision(BaseModel):
    name: DecisionName
    volume_change: float                    # +0.08 = +8% sul volume del blocco precedente
    reasons: list[str]


def recovery_signals(m: BlockMetrics, t: Thresholds) -> list[str]:
    out = []
    if m.hrv_change_pct is not None and m.hrv_change_pct <= -t.hrv_drop_pct:
        out.append(f"HRV {m.hrv_change_pct:+.1f}% (soglia -{t.hrv_drop_pct:g}%)")
    if m.rhr_change_bpm is not None and m.rhr_change_bpm >= t.rhr_rise_bpm:
        out.append(f"FC a riposo {m.rhr_change_bpm:+.0f} bpm (soglia +{t.rhr_rise_bpm:g})")
    if m.rpe_above_expected:
        out.append("RPE sopra le attese")
    return out


def decide(m: BlockMetrics, t: Thresholds | None = None) -> Decision:
    """Ordine di priorità: deload > repeat > consolidate > progress.

    Una singola segnalazione di dolore conta come un segnale negativo (consolidate):
    la tabella del piano non la prevede, scelta conservativa.
    """
    t = t or Thresholds()
    signals = recovery_signals(m, t)
    negatives = len(signals) + (1 if m.pain_reports == 1 else 0)

    if m.pain_reports >= t.pain_reports_deload or len(signals) >= t.negative_signals_deload:
        reasons = []
        if m.pain_reports >= t.pain_reports_deload:
            reasons.append(f"{m.pain_reports} segnalazioni di dolore")
        if len(signals) >= t.negative_signals_deload:
            reasons += signals
        return Decision(name=DecisionName.deload, volume_change=t.volume_deload, reasons=reasons)

    if m.compliance < t.compliance_repeat or m.sick_days >= t.sick_days_repeat:
        reasons = []
        if m.compliance < t.compliance_repeat:
            reasons.append(f"compliance {m.compliance:.0%} < {t.compliance_repeat:.0%}")
        if m.sick_days >= t.sick_days_repeat:
            reasons.append(f"{m.sick_days} giorni di malattia")
        return Decision(name=DecisionName.repeat, volume_change=t.volume_repeat, reasons=reasons)

    reasons = []
    if m.compliance < t.compliance_consolidate:
        reasons.append(f"compliance {m.compliance:.0%} < {t.compliance_consolidate:.0%}")
    if m.key_hit_pct < t.key_hit_consolidate:
        reasons.append(f"sessioni chiave centrate {m.key_hit_pct:.0%} < {t.key_hit_consolidate:.0%}")
    if negatives >= 1:
        reasons += signals or [f"{m.pain_reports} segnalazione di dolore"]
    if reasons:
        return Decision(name=DecisionName.consolidate, volume_change=t.volume_consolidate, reasons=reasons)

    return Decision(
        name=DecisionName.progress,
        volume_change=t.volume_progress,
        reasons=[f"compliance {m.compliance:.0%}, chiave centrate {m.key_hit_pct:.0%}, nessun segnale negativo"],
    )
