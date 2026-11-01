import os
from pathlib import Path

# I test usano sempre la config di esempio, mai quella personale.
os.environ["COACH_CONFIG"] = str(Path(__file__).resolve().parents[1] / "config.example.yaml")
