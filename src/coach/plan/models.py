"""Schema del blocco di allenamento (output del planner, input del validatore)."""

from datetime import date, timedelta
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class Intensity(StrEnum):
    easy = "easy"
    moderate = "moderate"
    hard = "hard"
    race = "race"


class Kind(StrEnum):
    easy = "easy"
    recovery = "recovery"
    long = "long"
    tempo = "tempo"
    intervals = "intervals"
    marathon_pace = "marathon_pace"
    race = "race"


class WeekKind(StrEnum):
    normal = "normal"
    deload = "deload"
    race_week = "race_week"
    taper = "taper"
    recovery = "recovery"      # recupero fisso dopo la gara


class FixedEvent(BaseModel):
    """Evento deciso dall'atleta (gara): il planner lo inserisce così com'è."""

    date: date
    name: str
    intensity: Intensity
    kind: Kind = Kind.race
    duration_min: int | None = None


class Session(BaseModel):
    date: date
    kind: Kind
    intensity: Intensity
    duration_min: int = Field(gt=0)
    distance_km: float | None = None
    dplus_m: int = 0
    z3plus_min: int = Field(default=0, ge=0)  # minuti previsti in Z3 o sopra
    fixed: bool = False                        # True = corrisponde a un FixedEvent
    target: str = ""                           # passo/FC/RPE obiettivo
    description: str = ""

    @model_validator(mode="after")
    def _z3_within_duration(self):
        if self.z3plus_min > self.duration_min:
            raise ValueError("z3plus_min supera duration_min")
        return self

    @property
    def is_hard(self) -> bool:
        return self.intensity in (Intensity.hard, Intensity.race)


class Week(BaseModel):
    start: date                                # lunedì
    kind: WeekKind = WeekKind.normal
    sessions: list[Session]
    strength_days: list[date] = Field(default_factory=list)

    @property
    def days(self) -> list[date]:
        return [self.start + timedelta(days=i) for i in range(7)]

    @property
    def minutes(self) -> int:
        return sum(s.duration_min for s in self.sessions)

    @property
    def hours(self) -> float:
        return self.minutes / 60

    @property
    def dplus(self) -> int:
        return sum(s.dplus_m for s in self.sessions)


class Block(BaseModel):
    phase: str
    start_date: date
    weeks: list[Week]
    rationale: str = ""
