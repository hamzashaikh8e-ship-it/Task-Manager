from datetime import date, datetime, timezone
from typing import List, Literal, Optional
from uuid import UUID

import pytz
from pydantic import BaseModel, Field, root_validator, validator


class PreferencesIn(BaseModel):
    timezone: str = Field(min_length=1, max_length=64)

    @validator("timezone")
    def valid_timezone(cls, value):
        try:
            pytz.timezone(value)
        except pytz.UnknownTimeZoneError:
            raise ValueError("Choose a valid IANA timezone")
        return value


class AvailabilityIn(BaseModel):
    kind: Literal["WORKING_HOURS", "COMMITMENT"]
    weekday: Optional[int] = Field(default=None, ge=0, le=6, description="Python weekday index: Monday=0 through Sunday=6")
    local_start: Optional[str] = None
    local_end: Optional[str] = None
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    title: Optional[str] = Field(default=None, max_length=160)

    @validator("local_start", "local_end")
    def valid_local_time(cls, value):
        if value is None:
            return value
        try:
            datetime.strptime(value, "%H:%M")
        except ValueError:
            raise ValueError("Time must use 24-hour HH:MM format")
        return value

    @validator("starts_at", "ends_at")
    def normalize_instant(cls, value):
        if value is not None:
            if value.tzinfo is None:
                raise ValueError("Timestamps must include a timezone")
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        return value

    @root_validator
    def validate_shape(cls, values):
        kind = values.get("kind")
        if kind == "WORKING_HOURS":
            if values.get("weekday") is None or not values.get("local_start") or not values.get("local_end"):
                raise ValueError("Working hours require a weekday and start/end local times")
            if values["local_end"] <= values["local_start"]:
                raise ValueError("Working hours must end later on the same day")
            if values.get("starts_at") or values.get("ends_at"):
                raise ValueError("Working hours use local times, not fixed timestamps")
        elif kind == "COMMITMENT":
            if values.get("weekday") is not None or values.get("local_start") or values.get("local_end"):
                raise ValueError("Fixed commitments use dated timestamps")
            if values.get("starts_at") is None or values.get("ends_at") is None:
                raise ValueError("Commitments require start and end timestamps")
            if values["ends_at"] <= values["starts_at"]:
                raise ValueError("Commitment end must be after its start")
            if not (values.get("title") or "").strip():
                raise ValueError("Commitments need a title")
            values["title"] = values["title"].strip()
        return values


class AvailabilityOut(BaseModel):
    id: UUID
    owner_id: UUID
    kind: str
    weekday: Optional[int]
    local_start: Optional[str]
    local_end: Optional[str]
    starts_at: Optional[datetime]
    ends_at: Optional[datetime]
    title: Optional[str]

    class Config:
        orm_mode = True


class PlanGenerateIn(BaseModel):
    plan_date: date
    available_minutes: Optional[int] = Field(default=None, ge=1, le=1440)
    break_minutes: int = Field(default=10, ge=0, le=60)
    break_every_minutes: int = Field(default=50, ge=15, le=240)


class PlanItemEditIn(BaseModel):
    starts_at: datetime
    ends_at: datetime

    @validator("starts_at", "ends_at")
    def normalize_instant(cls, value):
        if value.tzinfo is None:
            raise ValueError("Schedule timestamps must include a timezone")
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    @root_validator
    def validate_range(cls, values):
        start, end = values.get("starts_at"), values.get("ends_at")
        if start and end and end <= start:
            raise ValueError("End time must be after start time")
        return values


class PlanItemOut(BaseModel):
    id: UUID
    task_id: Optional[UUID]
    item_type: str
    title: str
    starts_at: Optional[datetime]
    ends_at: Optional[datetime]
    reason: Optional[str]
    position: int

    class Config:
        orm_mode = True


class DailyPlanOut(BaseModel):
    id: UUID
    plan_date: date
    timezone: str
    status: str
    available_minutes: Optional[int]
    break_minutes: int
    break_every_minutes: int
    generated_at: datetime
    approved_at: Optional[datetime]
    items: List[PlanItemOut] = Field(default_factory=list)

    class Config:
        orm_mode = True


class RecommendationOut(BaseModel):
    task_id: UUID
    title: str
    score: float
    priority: str
    deadline: Optional[datetime]
    estimated_minutes: Optional[int]
    explanation: List[str]
