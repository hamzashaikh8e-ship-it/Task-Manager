from datetime import datetime
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, Field, validator
import pytz

class FocusStartIn(BaseModel):
    kind: str = "FOCUS"
    planned_minutes: int = Field(default=25, ge=1, le=240)
    task_id: Optional[UUID] = None
    @validator("kind")
    def valid_kind(cls, value):
        value=value.upper()
        if value not in ("FOCUS", "BREAK"):
            raise ValueError("Session kind must be FOCUS or BREAK")
        return value

class FocusSessionOut(BaseModel):
    id: UUID
    task_id: Optional[UUID]
    kind: str
    status: str
    planned_minutes: int
    elapsed_seconds: int
    started_at: datetime
    paused_at: Optional[datetime]
    ended_at: Optional[datetime]
    task_title: Optional[str] = None
    remaining_seconds: int = 0
    class Config: orm_mode=True

class FocusSummaryOut(BaseModel):
    today_seconds: int
    week_seconds: int
    history: List[FocusSessionOut]
    active_session: Optional[FocusSessionOut]

class ReminderOut(BaseModel):
    id: UUID
    task_id: UUID
    task_title: str
    deadline: datetime
    due_at: datetime
    status: str
    delivered_at: Optional[datetime]
    timezone: str

class NotificationOut(BaseModel):
    id: UUID
    task_id: Optional[UUID]
    title: str
    message: str
    created_at: datetime
    read_at: Optional[datetime]
    class Config: orm_mode=True
