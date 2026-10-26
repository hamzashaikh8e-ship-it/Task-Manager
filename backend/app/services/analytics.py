from datetime import date, datetime, time, timedelta
import pytz
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.models.entities import FocusSession, PointEvent, Task


def overview(db: Session, owner_id, timezone_name: str, start: date, end: date):
    zone = pytz.timezone(timezone_name)
    today = datetime.now(pytz.UTC).astimezone(zone).date()
    now_utc = datetime.utcnow()
    status_rows = db.query(Task.status, func.count(Task.id)).filter_by(owner_id=owner_id).group_by(Task.status).all()
    status = {key: 0 for key in ("TODO", "IN_PROGRESS", "DONE")}
    status.update({key: int(count) for key, count in status_rows})
    priority_rows = db.query(Task.priority, func.count(Task.id)).filter_by(owner_id=owner_id).group_by(Task.priority).all()
    priority = {key: 0 for key in ("LOW", "MEDIUM", "HIGH", "URGENT")}
    priority.update({key: int(count) for key, count in priority_rows})
    total = sum(status.values())
    completed = status.get("DONE", 0)
    incomplete = total - completed
    overdue = int(db.query(func.count(Task.id)).filter(Task.owner_id == owner_id, Task.status != "DONE",
        Task.deadline.isnot(None), Task.deadline < now_utc).scalar() or 0)
    daily = {start + timedelta(days=i): {"completed": 0, "focus_seconds": 0, "focus_sessions": 0}
             for i in range((end - start).days + 1)}
    local_start = zone.localize(datetime.combine(start, time.min)).astimezone(pytz.UTC).replace(tzinfo=None)
    local_end = zone.localize(datetime.combine(end + timedelta(days=1), time.min)).astimezone(pytz.UTC).replace(tzinfo=None)
    completion_events = db.query(PointEvent.source_id, PointEvent.created_at).filter(
        PointEvent.owner_id == owner_id, PointEvent.source_type == "TASK_COMPLETION",
        PointEvent.created_at >= local_start, PointEvent.created_at < local_end, PointEvent.created_at <= now_utc).all()
    event_task_ids = {row[0] for row in db.query(PointEvent.source_id).filter_by(
        owner_id=owner_id, source_type="TASK_COMPLETION").all()}
    completion_stamps = [stamp for _task_id, stamp in completion_events]
    # Legacy tasks and tasks created already complete have no XP ledger row.
    completion_stamps.extend(row[1] for row in db.query(Task.id, Task.completed_at).filter(
        Task.owner_id == owner_id, Task.status == "DONE", Task.completed_at >= local_start,
        Task.completed_at < local_end, Task.completed_at <= now_utc).all()
        if str(row[0]) not in event_task_ids)
    for stamp in completion_stamps:
        if stamp:
            local_day = pytz.UTC.localize(stamp).astimezone(zone).date()
            if local_day in daily:
                daily[local_day]["completed"] += 1
    sessions = db.query(FocusSession).filter(FocusSession.owner_id == owner_id, FocusSession.kind == "FOCUS",
        FocusSession.status == "COMPLETED", FocusSession.ended_at >= local_start, FocusSession.ended_at < local_end,
        FocusSession.ended_at <= now_utc).all()
    for session in sessions:
        if session.ended_at:
            local_day = pytz.UTC.localize(session.ended_at).astimezone(zone).date()
            if local_day in daily:
                daily[local_day]["focus_seconds"] += session.elapsed_seconds or 0
                daily[local_day]["focus_sessions"] += 1
    days = [{"date": day.isoformat(), **daily[day]} for day in daily]
    focus_total = sum(item["focus_seconds"] for item in daily.values())
    completion_trend = sum(item["completed"] for item in daily.values())
    weekly = {}
    for day, values in daily.items():
        monday = day - timedelta(days=day.weekday())
        bucket = weekly.setdefault(monday, {"completed": 0, "focus_seconds": 0})
        bucket["completed"] += values["completed"]
        bucket["focus_seconds"] += values["focus_seconds"]
    return {"start_date": start, "end_date": end, "timezone": timezone_name,
        "total_tasks": total, "completed_tasks": completed, "incomplete_tasks": incomplete,
        "overdue_tasks": overdue, "completion_rate": round((completed / total * 100) if total else 0, 1),
        "status_breakdown": status, "priority_breakdown": priority, "daily_trend": days,
        "weekly_trend": [{"week_start": week.isoformat(), **values} for week, values in sorted(weekly.items())],
        "range_completed_tasks": completion_trend, "range_focus_seconds": focus_total,
        "range_focus_sessions": sum(item["focus_sessions"] for item in daily.values()),
        "today_date": today}
