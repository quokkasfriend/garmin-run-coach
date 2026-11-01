"""Carica methodology.yaml e ne verifica la provenienza (ogni valore ha una fonte)."""

import yaml

from coach.plan.adapt import Thresholds
from coach.plan.validate import Limits, config_limit_overrides
from coach.settings import METHODOLOGY_PATH


def load_methodology(path=METHODOLOGY_PATH) -> dict:
    if not path.exists():
        raise SystemExit("methodology.yaml non trovato.")
    return yaml.safe_load(path.read_text()) or {}


def check_provenance(node, path: str = "") -> list[str]:
    """Ogni dict con chiave `value` deve avere `sources` non vuote oppure `project_default: true`."""
    errs: list[str] = []
    if isinstance(node, dict):
        if "value" in node and not (node.get("sources") or node.get("source") or node.get("project_default")):
            errs.append(f"{path or '<root>'}: valore senza fonte")
        for k, v in node.items():
            errs += check_provenance(v, f"{path}.{k}" if path else k)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            errs += check_provenance(v, f"{path}[{i}]")
    return errs


def _values(section: dict, fields) -> dict:
    return {k: v["value"] for k, v in section.items() if k in fields and isinstance(v, dict) and "value" in v}


def limits_from_methodology(m: dict, cfg: dict | None = None) -> Limits:
    """Soglie dai libri, poi sovrascritte da config.yaml (giorni, riposo, forza)."""
    values = _values(m.get("limits", {}), Limits.model_fields)
    values.update(config_limit_overrides(cfg or {}))
    return Limits(**values)


def thresholds_from_methodology(m: dict) -> Thresholds:
    return Thresholds(**_values(m.get("adaptation", {}), Thresholds.model_fields))
