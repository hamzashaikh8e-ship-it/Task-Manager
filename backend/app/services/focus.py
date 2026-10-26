from datetime import datetime, timedelta, time
from typing import Optional
import pytz
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.models.entities import FocusSession, Task
from app.schemas.focus import FocusSessionOut
from app.services.gamification import award_focus_completion

class FocusError(ValueError): pass

def elapsed(session: FocusSession, now: datetime) -> int:
    value=session.elapsed_seconds or 0
    if session.status=="ACTIVE": value+=max(0,int((now-session.started_at).total_seconds()))
    return value

def output(db: Session, session: FocusSession, now: Optional[datetime]=None):
    now=now or datetime.utcnow()
    task=db.query(Task).filter_by(id=session.task_id,owner_id=session.owner_id).first() if session.task_id else None
    seconds=elapsed(session,now)
    return FocusSessionOut(id=session.id,task_id=session.task_id,kind=session.kind,status=session.status,
        planned_minutes=session.planned_minutes,elapsed_seconds=seconds,started_at=session.started_at,
        paused_at=session.paused_at,ended_at=session.ended_at,task_title=task.title if task else None,
        remaining_seconds=max(0,session.planned_minutes*60-seconds))

def start(db:Session, owner_id, data, now=None):
    now=now or datetime.utcnow()
    if db.query(FocusSession).filter(FocusSession.owner_id==owner_id,FocusSession.status.in_(["ACTIVE","PAUSED"])).first():
        raise FocusError("Finish or reset your current session before starting another.")
    if data.task_id and not db.query(Task).filter_by(id=data.task_id,owner_id=owner_id).first():
        raise FocusError("The selected task was not found in your account.")
    session=FocusSession(owner_id=owner_id,task_id=data.task_id,kind=data.kind,planned_minutes=data.planned_minutes,
        status="ACTIVE",started_at=now,elapsed_seconds=0)
    db.add(session);db.commit();db.refresh(session)
    return output(db,session,now)

def transition(db:Session, owner_id, session_id, action, now=None):
    now=now or datetime.utcnow()
    session=db.query(FocusSession).filter_by(id=session_id,owner_id=owner_id).first()
    if not session: return None
    if action=="pause":
        if session.status=="PAUSED": return output(db,session,now)
        if session.status!="ACTIVE": raise FocusError("Only an active session can be paused.")
        session.elapsed_seconds=elapsed(session,now);session.status="PAUSED";session.paused_at=now
    elif action=="resume":
        if session.status=="ACTIVE": return output(db,session,now)
        if session.status!="PAUSED": raise FocusError("Only a paused session can be resumed.")
        session.status="ACTIVE";session.started_at=now;session.paused_at=None
    elif action=="finish":
        if session.status=="COMPLETED": return output(db,session,now)
        if session.status not in ("ACTIVE","PAUSED"): raise FocusError("This session is no longer active.")
        session.elapsed_seconds=elapsed(session,now);session.status="COMPLETED";session.ended_at=now;session.paused_at=None
        award_focus_completion(db, session, now)
    elif action=="reset":
        if session.status in ("ACTIVE","PAUSED"):
            session.status="CANCELLED";session.ended_at=now;session.paused_at=None
        return output(db,session,now)
    db.commit();db.refresh(session)
    return output(db,session,now)

def summary(db:Session, owner_id, timezone_name="UTC", now=None):
    now=now or datetime.utcnow();zone=pytz.timezone(timezone_name)
    local_now=pytz.UTC.localize(now).astimezone(zone)
    local_today=local_now.date();monday=local_today-timedelta(days=local_today.weekday())
    day_start=zone.localize(datetime.combine(local_today,time.min)).astimezone(pytz.UTC).replace(tzinfo=None)
    week_start=zone.localize(datetime.combine(monday,time.min)).astimezone(pytz.UTC).replace(tzinfo=None)
    base=db.query(FocusSession).filter_by(owner_id=owner_id,kind="FOCUS",status="COMPLETED")
    sessions=base.order_by(FocusSession.ended_at.desc()).limit(50).all()
    today=int(db.query(func.coalesce(func.sum(FocusSession.elapsed_seconds),0)).filter(
        FocusSession.owner_id==owner_id,FocusSession.kind=="FOCUS",FocusSession.status=="COMPLETED",
        FocusSession.ended_at>=day_start).scalar() or 0)
    week=int(db.query(func.coalesce(func.sum(FocusSession.elapsed_seconds),0)).filter(
        FocusSession.owner_id==owner_id,FocusSession.kind=="FOCUS",FocusSession.status=="COMPLETED",
        FocusSession.ended_at>=week_start).scalar() or 0)
    active=db.query(FocusSession).filter(FocusSession.owner_id==owner_id,FocusSession.status.in_(["ACTIVE","PAUSED"])).first()
    return {"today_seconds":today,"week_seconds":week,"history":[output(db,x,now) for x in sessions],"active_session":output(db,active,now) if active else None}
