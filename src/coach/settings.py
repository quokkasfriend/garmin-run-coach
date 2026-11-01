"""Percorsi, variabili d'ambiente e config.yaml."""

import os
from pathlib import Path

import truststore
import yaml
from dotenv import load_dotenv

# Usa il portachiavi di sistema (CA aziendali incluse) invece del bundle certifi.
truststore.inject_into_ssl()

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "coach.db"
FIT_DIR = DATA_DIR / "fit"
PROBE_DIR = DATA_DIR / "probe"
BLOCKS_DIR = DATA_DIR / "blocks"
TOKEN_CACHE = DATA_DIR / "garmin-token.json"
CONFIG_PATH = Path(os.environ.get("COACH_CONFIG") or ROOT / "config.yaml")
METHODOLOGY_PATH = ROOT / "methodology.yaml"

load_dotenv(ROOT / ".env")


def garmin_api_key() -> str:
    key = os.environ.get("GARMIN_PERSONAL_API_KEY", "").strip()
    if not key:
        raise SystemExit("GARMIN_PERSONAL_API_KEY mancante: copia .env.example in .env e compilalo.")
    return key


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        raise SystemExit(f"{CONFIG_PATH.name} non trovato: copia config.example.yaml in config.yaml.")
    return yaml.safe_load(CONFIG_PATH.read_text()) or {}


def ensure_dirs() -> None:
    for d in (DATA_DIR, FIT_DIR, PROBE_DIR, BLOCKS_DIR):
        d.mkdir(parents=True, exist_ok=True)
