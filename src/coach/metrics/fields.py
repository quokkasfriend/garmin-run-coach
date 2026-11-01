"""Unico punto in cui compaiono i nomi dei campi Garmin (verificati sul probe del 2026-10-26)."""

# Tipi di attività
RUN_TYPES = {"running", "trail_running", "treadmill_running", "ultra_run"}
TRAIL_TYPES = {"trail_running", "ultra_run"}
FIT_TYPES = RUN_TYPES | {"hiking"}  # attività di cui scarichiamo il FIT

# Attività (activitylist search)
A_ID = "activityId"
A_START_LOCAL = "startTimeLocal"          # "YYYY-MM-DD HH:MM:SS"
A_TYPE = ("activityType", "typeKey")
A_DISTANCE_M = "distance"
A_DURATION_S = "duration"                 # tempo in movimento/timer
A_ELEV_GAIN_M = "elevationGain"
A_AVG_HR = "averageHR"
A_MAX_HR = "maxHR"
A_HR_ZONE_S = [f"hrTimeInZone_{i}" for i in range(1, 6)]
A_TRAINING_EFFECT = "aerobicTrainingEffect"
A_BODY_BATTERY_DIFF = "differenceBodyBattery"

# Salute (per giorno, chiave = calendarDate / date)
HRV_LAST_NIGHT_AVG = "lastNightAvg"
HRV_WEEKLY_AVG = "weeklyAvg"
HRV_STATUS = "status"
DAILY_RESTING_HR = ("heartRate", "restingValue")
SLEEP_SECONDS = "sleepTimeSeconds"
