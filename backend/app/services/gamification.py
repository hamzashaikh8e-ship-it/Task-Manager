from datetime import date, datetime, time, timedelta, timezone
from typing import Dict, List, Optional
import pytz
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.models.entities import Achievement, FocusSession, PointEvent, Task, User, UserAchievement, UserStats

ACHIEVEMENTS = (
    ("first_task", "First finish", "Complete your first task.", "tasks", 1),
    ("ten_tasks", "Ten done", "Complete ten different tasks.", "tasks", 10),
    ("first_focus", "First focus", "Complete a qualifying focus session.", "focus", 1),
    ("seven_day_streak", "A week of progress", "Build a seven-day activity streak.", "streak", 7),
    ("five_focus_hours", "Deep work", "Complete five hours of focus sessions.", "focus_seconds", 18000),
)


def _ensure_stats(db: Session, owner_id) -> UserStats:
    stats = db.query(UserStats).filter_by(owner_id=owner_id).first()
    if stats is None:
        try:
            with db.begin_nested():
                stats = UserStats(owner_id=owner_id)
                db.add(stats)
                db.flush()
        except IntegrityError:
            stats = db.query(UserStats).filter_by(owner_id=owner_id).first()
    return stats


def _activity_days(db: Session, owner_id, timezone_name: str, now: datetime) -> List[date]:
    zone = pytz.timezone(timezone_name)
    local_today = pytz.UTC.localize(now).astimezone(zone).date()
    stamps = [row[0] for row in db.query(PointEvent.created_at).filter(
        PointEvent.owner_id == owner_id,
        PointEvent.source_type.in_(("TASK_COMPLETION", "FOCUS_COMPLETION")),
        PointEvent.created_at <= now,
    ).all()]
    # Count eligible activity predating this ledger too, while the point ledger
    # preserves activity for tasks that are later deleted or reopened.
    stamps.extend(row[0] for row in db.query(Task.completed_at).filter(
        Task.owner_id == owner_id, Task.status == "DONE", Task.completed_at.isnot(None), Task.completed_at <= now).all())
    minimum = get_settings().xp_focus_min_seconds
    stamps.extend(row[0] for row in db.query(FocusSession.ended_at).filter(
        FocusSession.owner_id == owner_id, FocusSession.kind == "FOCUS", FocusSession.status == "COMPLETED",
        FocusSession.elapsed_seconds >= minimum, FocusSession.ended_at.isnot(None), FocusSession.ended_at <= now).all())
    days = set()
    for stamp in stamps:
        utc_stamp = pytz.UTC.localize(stamp) if stamp.tzinfo is None else stamp.astimezone(pytz.UTC)
        local_day = utc_stamp.astimezone(zone).date()
        if local_day <= local_today:
            days.add(local_day)
    return sorted(days)


def _streak_values(days: List[date], today: date):
    if not days:
        return 0, 0, None
    longest = current_run = 0
    previous = None
    for day in days:
        current_run = current_run + 1 if previous and day == previous + timedelta(days=1) else 1
        longest = max(longest, current_run)
        previous = day
    day_set = set(days)
    cursor = today if today in day_set else today - timedelta(days=1) if today - timedelta(days=1) in day_set else None
    current = 0
    while cursor is not None and cursor in day_set:
        current += 1
        cursor -= timedelta(days=1)
    return current, longest, days[-1]


def _unlock(db: Session, owner_id, achievement: Achievement, now: datetime) -> None:
    if db.query(UserAchievement.id).filter_by(owner_id=owner_id, achievement_id=achievement.id).first():
        return
    try:
        with db.begin_nested():
            db.add(UserAchievement(owner_id=owner_id, achievement_id=achievement.id, unlocked_at=now))
            db.flush()
    except IntegrityError:
        # A concurrent profile/reward refresh already unlocked this achievement.
        return


def refresh_profile(db: Session, owner_id, now: Optional[datetime] = None) -> Dict:
    now = now or datetime.utcnow()
    user = db.query(User).filter_by(id=owner_id).first()
    if user is None:
        return {"total_xp": 0, "level": 1, "xp_in_level": 0, "xp_to_next_level": get_settings().xp_level_size,
                "current_streak": 0, "longest_streak": 0, "last_activity_date": None, "achievements": []}
    stats = _ensure_stats(db, owner_id)
    zone = pytz.timezone(user.timezone)
    local_today = pytz.UTC.localize(now).astimezone(zone).date()
    days = _activity_days(db, owner_id, user.timezone, now)
    current, longest, latest = _streak_values(days, local_today)
    stats.total_xp = int(db.query(func.coalesce(func.sum(PointEvent.points), 0)).filter(
        PointEvent.owner_id == owner_id, PointEvent.created_at <= now).scalar() or 0)
    stats.current_streak = current
    stats.longest_streak = longest
    stats.last_activity_date = latest

    completed_task_ids = {row[0] for row in db.query(PointEvent.source_id).filter(
        PointEvent.owner_id == owner_id, PointEvent.source_type == "TASK_COMPLETION", PointEvent.created_at <= now).all()}
    completed_task_ids.update(str(row[0]) for row in db.query(Task.id).filter(
        Task.owner_id == owner_id, Task.status == "DONE", Task.completed_at <= now).all())
    task_count = len(completed_task_ids)
    focus_count = db.query(FocusSession.id).filter(FocusSession.owner_id == owner_id, FocusSession.kind == "FOCUS",
        FocusSession.status == "COMPLETED", FocusSession.elapsed_seconds >= get_settings().xp_focus_min_seconds,
        FocusSession.ended_at <= now).count()
    focus_seconds = int(db.query(func.coalesce(func.sum(FocusSession.elapsed_seconds), 0)).filter(
        FocusSession.owner_id == owner_id, FocusSession.kind == "FOCUS", FocusSession.status == "COMPLETED",
        FocusSession.ended_at <= now).scalar() or 0)
    progress = {"tasks": task_count, "focus": focus_count, "streak": longest, "focus_seconds": focus_seconds}
    unlocked = {row.achievement_id for row in db.query(UserAchievement.achievement_id).filter_by(owner_id=owner_id).all()}
    for slug, title, description, metric, target in ACHIEVEMENTS:
        achievement = db.query(Achievement).filter_by(slug=slug).first()
        if achievement is None:
            try:
                with db.begin_nested():
                    achievement = Achievement(slug=slug, title=title, description=description)
                    db.add(achievement)
                    db.flush()
            except IntegrityError:
                achievement = db.query(Achievement).filter_by(slug=slug).one()
        if progress[metric] >= target and achievement.id not in unlocked:
            _unlock(db, owner_id, achievement, now)
    db.flush()
    unlocked_rows = {row.achievement_id: row.unlocked_at for row in db.query(UserAchievement).filter_by(owner_id=owner_id).all()}
    settings = get_settings()
    level_size = max(1, settings.xp_level_size)
    xp_in_level = stats.total_xp % level_size
    achievements = []
    for slug, title, description, metric, target in ACHIEVEMENTS:
        achievement = db.query(Achievement).filter_by(slug=slug).one()
        value = min(progress[metric], target)
        achievements.append({"id": achievement.id, "slug": slug, "title": title, "description": description,
                             "progress": value, "target": target, "unlocked_at": unlocked_rows.get(achievement.id)})
    point_events = db.query(PointEvent).filter_by(owner_id=owner_id).order_by(PointEvent.created_at.desc()).limit(25).all()
    return {"total_xp": stats.total_xp, "level": stats.total_xp // level_size + 1, "xp_in_level": xp_in_level,
            "xp_to_next_level": level_size - xp_in_level, "current_streak": current, "longest_streak": longest,
            "last_activity_date": latest, "achievements": achievements,
            "point_events": [{"id": event.id, "source_type": event.source_type, "source_id": event.source_id,
                              "points": event.points, "created_at": event.created_at} for event in point_events]}


def _award(db: Session, owner_id, event_key: str, source_type: str, source_id: str, points: int,
           now: Optional[datetime] = None) -> bool:
    now = now or datetime.utcnow()
    if db.query(PointEvent.id).filter_by(owner_id=owner_id, event_key=event_key).first():
        return False
    try:
        with db.begin_nested():
            db.add(PointEvent(owner_id=owner_id, event_key=event_key, source_type=source_type,
                              source_id=str(source_id), points=points, created_at=now))
            db.flush()
    except IntegrityError:
        return False
    _ensure_stats(db, owner_id)
    refresh_profile(db, owner_id, now)
    return True


def award_task_completion(db: Session, owner_id, task_id, now: Optional[datetime] = None) -> bool:
    settings = get_settings()
    return _award(db, owner_id, "task-complete:{}".format(task_id), "TASK_COMPLETION", str(task_id),
                  max(0, settings.xp_task_completion), now)


def award_focus_completion(db: Session, session: FocusSession, now: Optional[datetime] = None) -> bool:
    settings = get_settings()
    if session.kind != "FOCUS" or session.status != "COMPLETED" or session.elapsed_seconds < settings.xp_focus_min_seconds:
        return False
    return _award(db, session.owner_id, "focus-complete:{}".format(session.id), "FOCUS_COMPLETION", str(session.id),
                  max(0, settings.xp_focus_session), now)
