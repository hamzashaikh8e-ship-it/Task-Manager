from datetime import date
from typing import Dict, List
from pydantic import BaseModel

class DailyMetric(BaseModel):
    date: date
    completed: int
    focus_seconds: int
    focus_sessions: int

class WeeklyMetric(BaseModel):
    week_start: date
    completed: int
    focus_seconds: int

class AnalyticsOut(BaseModel):
    start_date: date
    end_date: date
    timezone: str
    total_tasks: int
    completed_tasks: int
    incomplete_tasks: int
    overdue_tasks: int
    completion_rate: float
    status_breakdown: Dict[str, int]
    priority_breakdown: Dict[str, int]
    daily_trend: List[DailyMetric]
    weekly_trend: List[WeeklyMetric]
    range_completed_tasks: int
    range_focus_seconds: int
    range_focus_sessions: int
    today_date: date
