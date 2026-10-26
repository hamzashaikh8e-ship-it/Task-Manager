from datetime import datetime, timedelta
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
import pytz
from app.models.entities import Notification, Reminder, Task, User

def sync_task_reminder(db: Session, task: Task) -> None:
    reminder=db.query(Reminder).filter_by(task_id=task.id, owner_id=task.owner_id).first()
    enabled=bool(task.reminder_enabled and task.deadline and task.status != "DONE")
    if not enabled:
        if reminder:
            reminder.status="CANCELLED"
            reminder.updated_at=datetime.utcnow()
        return
    due_at=task.deadline-timedelta(minutes=task.reminder_lead_minutes or 0)
    if reminder is None:
        reminder=Reminder(owner_id=task.owner_id,task_id=task.id,due_at=due_at,status="PENDING")
        db.add(reminder)
    elif reminder.due_at != due_at or reminder.status in ("CANCELLED", "SENT"):
        reminder.due_at=due_at
        reminder.status="PENDING"
        reminder.delivered_at=None
    reminder.updated_at=datetime.utcnow()

def deliver_due_reminders(db: Session, now: datetime = None) -> int:
    now=now or datetime.utcnow()
    pending=db.query(Reminder).filter(Reminder.status=="PENDING",Reminder.due_at<=now).all()
    sent=0
    for reminder in pending:
        task=db.query(Task).filter_by(id=reminder.task_id,owner_id=reminder.owner_id).first()
        if not task or task.status=="DONE" or not task.reminder_enabled or not task.deadline:
            reminder.status="CANCELLED"
            continue
        key="reminder:{}:{}".format(reminder.id,reminder.due_at.isoformat())
        owner=db.query(User).filter_by(id=reminder.owner_id).first()
        try:
            user_tz=pytz.timezone(owner.timezone if owner else "UTC")
        except pytz.UnknownTimeZoneError:
            user_tz=pytz.UTC
        deadline_utc=pytz.UTC.localize(task.deadline) if task.deadline.tzinfo is None else task.deadline.astimezone(pytz.UTC)
        local_deadline=deadline_utc.astimezone(user_tz)
        display_deadline=local_deadline.strftime("%b %d, %Y %H:%M %Z")
        notification=Notification(owner_id=reminder.owner_id,task_id=task.id,reminder_id=reminder.id,
            dedupe_key=key,title="Task deadline reminder",message="{} is due {}.".format(task.title,display_deadline))
        db.add(notification)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            reminder=db.query(Reminder).filter_by(id=reminder.id).first()
            if reminder: reminder.status="SENT"; reminder.delivered_at=now
            continue
        reminder.status="SENT"
        reminder.delivered_at=now
        sent+=1
    db.commit()
    return sent
