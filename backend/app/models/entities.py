import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, Column, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.types import TypeDecorator, CHAR
import uuid as uuid_module

from app.core.database import Base


class GUID(TypeDecorator):
    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if not isinstance(value, uuid_module.UUID):
            value = uuid_module.UUID(str(value))
        return value if dialect.name == "postgresql" else str(value)

    def process_result_value(self, value, dialect):
        return value if value is None or isinstance(value, uuid_module.UUID) else uuid_module.UUID(value)


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    id = Column(GUID(), primary_key=True)
    user_id = Column(GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False, index=True)
    revoked_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class User(Base):
    __tablename__ = "users"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    email = Column(String(320), nullable=False, unique=True, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(120), nullable=False)
    timezone = Column(String(64), nullable=False, default="UTC")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (UniqueConstraint("owner_id", "name", name="uq_category_owner_name"),)
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    owner_id = Column(GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(80), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (UniqueConstraint("owner_id", "idempotency_key", name="uq_task_owner_idempotency_key"),)
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    owner_id = Column(GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False, default="")
    status = Column(String(20), nullable=False, default="TODO", index=True)
    priority = Column(String(20), nullable=False, default="MEDIUM")
    importance = Column(Integer, nullable=False, default=3)
    category = Column(String(80), nullable=True)
    estimated_minutes = Column(Integer, nullable=True)
    deadline = Column(DateTime, nullable=True, index=True)
    scheduled_start = Column(DateTime, nullable=True, index=True)
    scheduled_end = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    idempotency_key = Column(String(128), nullable=True)
    reminder_enabled = Column(Boolean, nullable=False, default=False)
    reminder_lead_minutes = Column(Integer, nullable=False, default=30)


class TaskDependency(Base):
    __tablename__ = "task_dependencies"
    __table_args__ = (
        CheckConstraint("task_id <> depends_on_id", name="ck_task_dependency_not_self"),
    )
    task_id = Column(GUID(), ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True)
    depends_on_id = Column(GUID(), ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class AvailabilityBlock(Base):
    __tablename__ = "availability_blocks"
    __table_args__ = (
        CheckConstraint("kind IN ('WORKING_HOURS', 'COMMITMENT')", name="ck_availability_kind"),
        CheckConstraint("(kind = 'WORKING_HOURS' AND weekday IS NOT NULL AND local_start IS NOT NULL AND local_end IS NOT NULL AND starts_at IS NULL AND ends_at IS NULL) OR (kind = 'COMMITMENT' AND weekday IS NULL AND local_start IS NULL AND local_end IS NULL AND starts_at IS NOT NULL AND ends_at IS NOT NULL)", name="ck_availability_shape"),
    )
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    owner_id = Column(GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    kind = Column(String(24), nullable=False, index=True)
    weekday = Column(Integer, nullable=True)
    local_start = Column(String(5), nullable=True)
    local_end = Column(String(5), nullable=True)
    starts_at = Column(DateTime, nullable=True, index=True)
    ends_at = Column(DateTime, nullable=True)
    title = Column(String(160), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class DailyPlan(Base):
    __tablename__ = "daily_plans"
    __table_args__ = (
        UniqueConstraint("owner_id", "plan_date", name="uq_daily_plan_owner_date"),
        CheckConstraint("status IN ('DRAFT', 'APPROVED')", name="ck_daily_plan_status"),
        CheckConstraint("break_minutes >= 0 AND break_every_minutes >= 0", name="ck_daily_plan_breaks"),
    )
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    owner_id = Column(GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    plan_date = Column(Date, nullable=False, index=True)
    timezone = Column(String(64), nullable=False)
    status = Column(String(16), nullable=False, default="DRAFT")
    available_minutes = Column(Integer, nullable=True)
    break_minutes = Column(Integer, nullable=False, default=10)
    break_every_minutes = Column(Integer, nullable=False, default=50)
    generated_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    approved_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class PlanItem(Base):
    __tablename__ = "plan_items"
    __table_args__ = (
        CheckConstraint("item_type IN ('TASK', 'BREAK', 'COMMITMENT', 'UNSCHEDULED')", name="ck_plan_item_type"),
        CheckConstraint("(starts_at IS NULL AND ends_at IS NULL) OR (starts_at IS NOT NULL AND ends_at IS NOT NULL AND starts_at < ends_at)", name="ck_plan_item_interval"),
    )
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    plan_id = Column(GUID(), ForeignKey("daily_plans.id", ondelete="CASCADE"), nullable=False, index=True)
    task_id = Column(GUID(), ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True)
    item_type = Column(String(20), nullable=False, index=True)
    title = Column(String(200), nullable=False)
    starts_at = Column(DateTime, nullable=True, index=True)
    ends_at = Column(DateTime, nullable=True)
    reason = Column(String(500), nullable=True)
    position = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class Reminder(Base):
    __tablename__ = "reminders"
    __table_args__ = (UniqueConstraint("task_id", name="uq_reminder_task"),)
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    owner_id = Column(GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    task_id = Column(GUID(), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    due_at = Column(DateTime, nullable=False, index=True)
    status = Column(String(16), nullable=False, default="PENDING", index=True)
    delivered_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (UniqueConstraint("owner_id", "dedupe_key", name="uq_notification_owner_dedupe"),)
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    owner_id = Column(GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    task_id = Column(GUID(), ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True)
    reminder_id = Column(GUID(), ForeignKey("reminders.id", ondelete="SET NULL"), nullable=True, index=True)
    dedupe_key = Column(String(200), nullable=False)
    title = Column(String(200), nullable=False)
    message = Column(String(500), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    read_at = Column(DateTime, nullable=True, index=True)


class FocusSession(Base):
    __tablename__ = "focus_sessions"
    __table_args__ = (
        CheckConstraint("kind IN ('FOCUS', 'BREAK')", name="ck_focus_session_kind"),
        CheckConstraint("status IN ('ACTIVE', 'PAUSED', 'COMPLETED', 'CANCELLED')", name="ck_focus_session_status"),
        CheckConstraint("planned_minutes BETWEEN 1 AND 240", name="ck_focus_planned_minutes"),
        CheckConstraint("elapsed_seconds >= 0", name="ck_focus_elapsed_seconds"),
    )
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    owner_id = Column(GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    task_id = Column(GUID(), ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True)
    kind = Column(String(10), nullable=False, default="FOCUS")
    status = Column(String(16), nullable=False, default="ACTIVE", index=True)
    planned_minutes = Column(Integer, nullable=False)
    elapsed_seconds = Column(Integer, nullable=False, default=0)
    started_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    paused_at = Column(DateTime, nullable=True)
    ended_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)


class UserStats(Base):
    __tablename__ = "user_stats"
    __table_args__ = (UniqueConstraint("owner_id", name="uq_user_stats_owner"),)
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    owner_id = Column(GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    total_xp = Column(Integer, nullable=False, default=0)
    current_streak = Column(Integer, nullable=False, default=0)
    longest_streak = Column(Integer, nullable=False, default=0)
    last_activity_date = Column(Date, nullable=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class Achievement(Base):
    __tablename__ = "achievements"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    slug = Column(String(64), nullable=False, unique=True, index=True)
    title = Column(String(120), nullable=False)
    description = Column(String(300), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class UserAchievement(Base):
    __tablename__ = "user_achievements"
    __table_args__ = (UniqueConstraint("owner_id", "achievement_id", name="uq_user_achievement"),)
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    owner_id = Column(GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    achievement_id = Column(GUID(), ForeignKey("achievements.id", ondelete="CASCADE"), nullable=False, index=True)
    unlocked_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class PointEvent(Base):
    __tablename__ = "point_events"
    __table_args__ = (UniqueConstraint("owner_id", "event_key", name="uq_point_event_owner_key"),)
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    owner_id = Column(GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    event_key = Column(String(160), nullable=False)
    source_type = Column(String(32), nullable=False, index=True)
    source_id = Column(String(64), nullable=False)
    points = Column(Integer, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
