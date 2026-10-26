from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, Field, root_validator, validator


class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)

    @validator("name")
    def trim_name(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Category name cannot be empty")
        return value


class CategoryOut(BaseModel):
    id: UUID
    name: str

    class Config:
        orm_mode = True


class TaskInput(BaseModel):
    class Config:
        extra = "forbid"

    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=10000)
    status: str = "TODO"
    priority: str = "MEDIUM"
    importance: int = Field(default=3, ge=1, le=5)
    category: Optional[str] = Field(default=None, max_length=80)
    estimated_minutes: Optional[int] = Field(default=None, ge=1, le=10080)
    deadline: Optional[datetime] = None
    scheduled_start: Optional[datetime] = None
    scheduled_end: Optional[datetime] = None
    dependency_ids: List[UUID] = Field(default_factory=list)
    reminder_enabled: bool = False
    reminder_lead_minutes: int = Field(default=30, ge=0, le=10080)

    @validator("title")
    def trim_title(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Task title cannot be empty")
        return value

    @validator("category")
    def trim_category(cls, value):
        if value is None:
            return None
        value = value.strip()
        return value or None

    @validator("deadline", "scheduled_start", "scheduled_end")
    def store_datetimes_as_utc_naive(cls, value):
        if value is not None and value.tzinfo is not None:
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        return value

    @root_validator
    def validate_schedule_range(cls, values):
        start, end = values.get("scheduled_start"), values.get("scheduled_end")
        if (start is None) != (end is None):
            raise ValueError("Scheduled start and end must be supplied together")
        if start is not None and end <= start:
            raise ValueError("Scheduled end must be after scheduled start")
        return values

    @validator("dependency_ids")
    def unique_dependencies(cls, value):
        if len(value) != len(set(value)):
            raise ValueError("Dependencies must not contain duplicates")
        return value

    @validator("status")
    def valid_status(cls, value):
        value = value.upper()
        if value not in ("TODO", "IN_PROGRESS", "DONE"):
            raise ValueError("Status must be TODO, IN_PROGRESS, or DONE")
        return value

    @validator("priority")
    def valid_priority(cls, value):
        value = value.upper()
        if value not in ("LOW", "MEDIUM", "HIGH", "URGENT"):
            raise ValueError("Priority must be LOW, MEDIUM, HIGH, or URGENT")
        return value


class TaskOut(TaskInput):
    id: UUID
    owner_id: UUID
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime]

    class Config:
        orm_mode = True
