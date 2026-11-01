"""Aggregati settimanali (lun-dom) dalle attività in SQLite. Nessun LLM, solo pandas."""

import json

import pandas as pd

from coach.db import connect
from coach.metrics import fields as F


def load_activities() -> pd.DataFrame:
    with connect() as conn:
        rows = conn.execute("SELECT json FROM activity_raw").fetchall()
    recs = []
    for r in rows:
        a = json.loads(r["json"])
        zones = [a.get(k) or 0.0 for k in F.A_HR_ZONE_S]
        recs.append({
            "activity_id": a[F.A_ID],
            "start": pd.Timestamp(a[F.A_START_LOCAL]),
            "type": a[F.A_TYPE[0]][F.A_TYPE[1]],
            "km": (a.get(F.A_DISTANCE_M) or 0.0) / 1000,
            "hours": (a.get(F.A_DURATION_S) or 0.0) / 3600,
            "dplus": a.get(F.A_ELEV_GAIN_M) or 0.0,
            "z12_s": zones[0] + zones[1],
            "z3plus_s": sum(zones[2:]),
        })
    df = pd.DataFrame(recs)
    if df.empty:
        return df
    df["is_run"] = df["type"].isin(F.RUN_TYPES)
    df["week"] = df["start"].dt.to_period("W-SUN").dt.start_time.dt.date  # lunedì
    return df


def weekly_summary(df: pd.DataFrame | None = None) -> pd.DataFrame:
    df = load_activities() if df is None else df
    if df.empty:
        return df
    runs = df[df["is_run"]]
    out = runs.groupby("week").agg(
        runs=("activity_id", "count"),
        hours=("hours", "sum"),
        km=("km", "sum"),
        dplus=("dplus", "sum"),
        z12_s=("z12_s", "sum"),
        z3plus_s=("z3plus_s", "sum"),
    )
    zone_total = out["z12_s"] + out["z3plus_s"]
    out["z3plus_pct"] = (out["z3plus_s"] / zone_total.where(zone_total > 0) * 100).round(0)
    out["long_run_km"] = runs.groupby("week")["km"].max()
    out["strength_h"] = df[df["type"] == "strength_training"].groupby("week")["hours"].sum()
    out = out.drop(columns=["z12_s", "z3plus_s"]).fillna({"strength_h": 0.0})
    # settimane senza corsa incluse
    full = pd.date_range(out.index.min(), out.index.max(), freq="7D").date
    return out.reindex(full).fillna({"runs": 0, "hours": 0.0, "km": 0.0, "dplus": 0.0, "strength_h": 0.0})
