from datetime import date, datetime
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel

class AchievementProgress(BaseModel):
    id: UUID
    slug: str
    title: str
    description: str
    progress: int
    target: int
    unlocked_at: Optional[datetime]

class PointEventOut(BaseModel):
    id: UUID
    source_type: str
    source_id: str
    points: int
    created_at: datetime

class GamificationProfileOut(BaseModel):
    total_xp: int
    level: int
    xp_in_level: int
    xp_to_next_level: int
    current_streak: int
    longest_streak: int
    last_activity_date: Optional[date]
    achievements: List[AchievementProgress]
    point_events: List[PointEventOut]
