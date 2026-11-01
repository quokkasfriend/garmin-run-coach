"""Salva in data/probe/ il JSON grezzo di ogni endpoint, per verificare i campi in fields.py."""

import json
import zipfile
from datetime import date, timedelta
from io import BytesIO

from coach.garmin.client import call, garmin_client
from coach.settings import PROBE_DIR, ensure_dirs


def run_probe(on_step=print) -> None:
    ensure_dirs()
    today = date.today()
    week_ago = today - timedelta(days=14)

    def save(name: str, payload) -> None:
        (PROBE_DIR / f"{name}.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False))
        on_step(f"ok  {name}")

    with garmin_client() as c:
        activities = call(c.search_activities, limit=20)
        save("activities", activities)
        runs = [a for a in activities if "run" in a["activityType"]["typeKey"]]
        if runs:
            aid = runs[0]["activityId"]
            save("activity_detail", call(c.get_activity, aid))
            save("activity_workouts", call(c.get_activity_workouts, aid))
            blob = call(c.download_activity, aid)
            with zipfile.ZipFile(BytesIO(blob)) as z:
                save("activity_download_listing", [i.filename for i in z.infolist()])

        save("profile", call(c.get_user_profile_settings))
        save("heart_rate_zones", call(c.get_heart_rate_zones))
        save("hrv_summaries", call(c.get_daily_hrv_summaries, week_ago, today))
        save("sleep_summaries", call(c.get_daily_sleep_summaries, week_ago, today))
        save("daily_summaries", call(c.get_daily_summaries, week_ago, today))
        save("body_battery", call(c.get_daily_body_battery, today, today))
        save("stress", call(c.get_daily_stress, today, today))
        save("heart_rate", call(c.get_daily_heart_rate, today))
        save("fitness_age", call(c.get_fitness_age, today))
