"""Pure point-in-time selector for user-supplied macro releases; no revised backfill."""
from datetime import date, datetime, timezone

from pydantic import BaseModel, FiniteFloat, field_validator, model_validator


class Observation(BaseModel):
    series: str
    period: date
    value: FiniteFloat
    released_at: datetime
    collected_at: datetime
    source: str
    unit: str

    @field_validator('released_at', 'collected_at')
    @classmethod
    def timezone_required(cls, stamp):
        if stamp.tzinfo is None:
            raise ValueError('timezone required')
        return stamp.astimezone(timezone.utc)

    @model_validator(mode='after')
    def chronology(self):
        if self.collected_at < self.released_at:
            raise ValueError('collection precedes release')
        return self


def available_vintages(observations, as_of):
    if as_of.tzinfo is None:
        raise ValueError('timezone required')
    selected = {}
    for item in sorted(observations, key=lambda o: (o.released_at, o.collected_at)):
        if max(item.released_at, item.collected_at) <= as_of:
            selected[item.series, item.period] = item
    return list(selected.values())
