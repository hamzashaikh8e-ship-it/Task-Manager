from datetime import date, datetime, time, timedelta, timezone
from typing import Dict, List, Optional, Set
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from sqlalchemy import case, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import current_session, current_user
from app.core.database import get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.models.entities import AuthSession, AvailabilityBlock, Category, FocusSession, Notification, Reminder, Task, TaskDependency, User
from app.schemas.auth import LoginIn, RegisterIn, TokenOut, UserOut
from app.schemas.task import CategoryIn, CategoryOut, TaskInput, TaskOut
from app.schemas.planner import (AvailabilityIn, AvailabilityOut, DailyPlanOut, PlanGenerateIn,
                                 PlanItemEditIn, PreferencesIn, RecommendationOut)
from app.services import planning, focus as focus_service, reminders as reminder_service, gamification, analytics as analytics_service
from app.schemas.focus import FocusSessionOut, FocusStartIn, FocusSummaryOut, NotificationOut, ReminderOut
from app.schemas.analytics import AnalyticsOut
from app.schemas.gamification import GamificationProfileOut

router = APIRouter()


@router.post("/auth/register", response_model=TokenOut, status_code=201)
def register(payload: RegisterIn, db: Session = Depends(get_db)):
    email = payload.email.lower()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    user = User(email=email, full_name=payload.full_name.strip(), password_hash=hash_password(payload.password))
    db.add(user)
    db.flush()
    token = create_access_token(db, user.id)
    db.commit()
    db.refresh(user)
    return {"access_token": token, "user": user}


@router.post("/auth/login", response_model=TokenOut)
def login(payload: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email.lower()).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    token = create_access_token(db, user.id)
    db.commit()
    return {"access_token": token, "user": user}


@router.post("/auth/logout", status_code=204)
def logout(session: AuthSession = Depends(current_session), db: Session = Depends(get_db)):
    session.revoked_at = datetime.utcnow()
    db.commit()
    return Response(status_code=204)


@router.get("/users/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user


@router.put("/users/preferences", response_model=UserOut)
def update_preferences(payload: PreferencesIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    user.timezone = payload.timezone
    db.commit()
    db.refresh(user)
    return user


@router.get("/planner/recommendations", response_model=List[RecommendationOut])
def get_recommendations(available_minutes: Optional[int] = Query(None, ge=0, le=1440),
                        db: Session = Depends(get_db), user: User = Depends(current_user)):
    ranked, _blocked = planning.recommendations(db, user.id, available_minutes)
    return [{"task_id": item.task.id, "title": item.task.title, "score": item.score,
             "priority": item.task.priority, "deadline": item.task.deadline,
             "estimated_minutes": item.task.estimated_minutes, "explanation": list(item.explanation)} for item in ranked]


@router.get("/planner/availability", response_model=List[AvailabilityOut])
def get_availability(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return planning.list_availability(db, user.id)


@router.post("/planner/availability", response_model=AvailabilityOut, status_code=201)
def create_availability(payload: AvailabilityIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    try:
        return planning.add_availability(db, user.id, payload)
    except planning.PlanningError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.delete("/planner/availability/{availability_id}", status_code=204)
def delete_availability(availability_id: UUID, db: Session = Depends(get_db), user: User = Depends(current_user)):
    row = db.query(AvailabilityBlock).filter_by(id=availability_id, owner_id=user.id).first()
    if not row: raise HTTPException(status_code=404, detail="Availability block not found")
    db.delete(row); db.commit()
    return Response(status_code=204)


@router.post("/planner/plans/generate", response_model=DailyPlanOut)
def generate_daily_plan(payload: PlanGenerateIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    try:
        return planning.generate_plan(db, user, payload)
    except planning.PlanningError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except planning.PlannerError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/planner/plans", response_model=Optional[DailyPlanOut])
def get_daily_plan(plan_date: date = Query(...), db: Session = Depends(get_db), user: User = Depends(current_user)):
    return planning.get_plan_by_date(db, user.id, plan_date)


@router.get("/planner/plans/{plan_id}", response_model=DailyPlanOut)
def get_daily_plan_by_id(plan_id: UUID, db: Session = Depends(get_db), user: User = Depends(current_user)):
    result = planning.get_plan(db, user.id, plan_id)
    if result is None: raise HTTPException(status_code=404, detail="Daily plan not found")
    return result


@router.put("/planner/plans/{plan_id}/items/{item_id}", response_model=DailyPlanOut)
def edit_daily_plan_item(plan_id: UUID, item_id: UUID, payload: PlanItemEditIn,
                         db: Session = Depends(get_db), user: User = Depends(current_user)):
    try:
        result = planning.edit_item(db, user.id, plan_id, item_id, payload)
    except planning.PlanningError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    if result is None: raise HTTPException(status_code=404, detail="Daily plan not found")
    return result


@router.post("/planner/plans/{plan_id}/approve", response_model=DailyPlanOut)
def approve_daily_plan(plan_id: UUID, db: Session = Depends(get_db), user: User = Depends(current_user)):
    try:
        result = planning.approve_plan(db, user.id, plan_id)
    except planning.PlanningError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    if result is None: raise HTTPException(status_code=404, detail="Daily plan not found")
    return result


def _task_output(task: Task, dependency_ids: Optional[List[UUID]] = None) -> TaskOut:
    result = TaskOut.from_orm(task)
    return result.copy(update={"dependency_ids": dependency_ids or []})


def _idempotent_task_response(db: Session, existing: Task, payload: TaskInput) -> TaskOut:
    scalar_fields = ("title", "description", "status", "priority", "importance", "estimated_minutes",
                     "deadline", "scheduled_start", "scheduled_end", "reminder_enabled", "reminder_lead_minutes")
    same = all(getattr(existing, field) == getattr(payload, field) for field in scalar_fields)
    old_category = (existing.category or "").casefold()
    new_category = (payload.category or "").casefold()
    dependencies = [row[0] for row in db.query(TaskDependency.depends_on_id).filter(TaskDependency.task_id == existing.id).all()]
    if not same or old_category != new_category or set(dependencies) != set(payload.dependency_ids):
        raise HTTPException(status_code=409, detail="This Idempotency-Key was already used with different task details")
    return _task_output(existing, dependencies)


def _dependency_ids(db: Session, tasks: List[Task]) -> Dict[UUID, List[UUID]]:
    if not tasks:
        return {}
    task_ids = [task.id for task in tasks]
    rows = db.query(TaskDependency.task_id, TaskDependency.depends_on_id).filter(TaskDependency.task_id.in_(task_ids)).all()
    output = {task_id: [] for task_id in task_ids}
    for task_id, depends_on_id in rows:
        output[task_id].append(depends_on_id)
    return output


def _task_or_404(db: Session, task_id: UUID, user_id: UUID) -> Task:
    task = db.query(Task).filter(Task.id == task_id, Task.owner_id == user_id).first()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


def _category_name(db: Session, owner_id: UUID, name: Optional[str]) -> Optional[str]:
    if name is None:
        return None
    existing = db.query(Category).filter(Category.owner_id == owner_id, func.lower(Category.name) == name.lower()).first()
    if existing:
        return existing.name
    category = Category(owner_id=owner_id, name=name)
    db.add(category)
    db.flush()
    return category.name


def _validate_dependencies(db: Session, owner_id: UUID, task_id: Optional[UUID], dependency_ids: List[UUID]) -> None:
    if task_id in dependency_ids:
        raise HTTPException(status_code=422, detail="A task cannot depend on itself")
    if not dependency_ids:
        return
    found = db.query(Task.id).filter(Task.owner_id == owner_id, Task.id.in_(dependency_ids)).all()
    if {row[0] for row in found} != set(dependency_ids):
        raise HTTPException(status_code=422, detail="Dependencies must belong to this account")
    if task_id is None:
        return
    for dependency_id in dependency_ids:
        pending = [dependency_id]
        visited: Set[UUID] = set()
        while pending:
            current_id = pending.pop()
            if current_id == task_id:
                raise HTTPException(status_code=409, detail="Task dependencies cannot contain cycles")
            if current_id in visited:
                continue
            visited.add(current_id)
            pending.extend(row[0] for row in db.query(TaskDependency.depends_on_id).filter(TaskDependency.task_id == current_id).all())


def _replace_dependencies(db: Session, task_id: UUID, dependency_ids: List[UUID]) -> None:
    db.query(TaskDependency).filter(TaskDependency.task_id == task_id).delete(synchronize_session=False)
    db.add_all([TaskDependency(task_id=task_id, depends_on_id=dependency_id) for dependency_id in dependency_ids])


def _validate_schedule_conflict(db: Session, owner_id: UUID, payload: TaskInput, task_id: Optional[UUID] = None) -> None:
    if payload.status == "DONE" or payload.scheduled_start is None:
        return
    conflict = db.query(Task.id).filter(
        Task.owner_id == owner_id,
        Task.status != "DONE",
        Task.scheduled_start.isnot(None),
        Task.scheduled_start < payload.scheduled_end,
        Task.scheduled_end > payload.scheduled_start,
        Task.id != task_id if task_id is not None else Task.id.isnot(None),
    ).first()
    if conflict:
        raise HTTPException(status_code=409, detail="This time overlaps another scheduled task")


@router.get("/categories", response_model=List[CategoryOut])
def list_categories(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return db.query(Category).filter(Category.owner_id == user.id).order_by(func.lower(Category.name)).all()


@router.post("/categories", response_model=CategoryOut, status_code=201)
def create_category(payload: CategoryIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    existing = db.query(Category).filter(Category.owner_id == user.id, func.lower(Category.name) == payload.name.lower()).first()
    if existing:
        return existing
    category = Category(owner_id=user.id, name=payload.name)
    db.add(category)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.query(Category).filter(Category.owner_id == user.id, func.lower(Category.name) == payload.name.lower()).first()
        if existing:
            return existing
        raise
    db.refresh(category)
    return category


@router.delete("/categories/{category_id}", status_code=204)
def delete_category(category_id: UUID, db: Session = Depends(get_db), user: User = Depends(current_user)):
    category = db.query(Category).filter(Category.id == category_id, Category.owner_id == user.id).first()
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found")
    db.query(Task).filter(Task.owner_id == user.id, Task.category == category.name).update({Task.category: None}, synchronize_session=False)
    db.delete(category)
    db.commit()
    return Response(status_code=204)


@router.get("/tasks", response_model=List[TaskOut])
def list_tasks(q: str = Query(default="", max_length=200), status: Optional[str] = None,
               priority: Optional[str] = None, category: Optional[str] = None,
               deadline_from: Optional[date] = None, deadline_to: Optional[date] = None,
               sort_by: str = Query("created", pattern="^(created|updated|deadline|priority|title)$"),
               sort_order: str = Query("desc", pattern="^(asc|desc)$"),
               offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
               db: Session = Depends(get_db), user: User = Depends(current_user)):
    query = db.query(Task).filter(Task.owner_id == user.id)
    if q.strip():
        search = "%{}%".format(q.strip())
        query = query.filter(or_(Task.title.ilike(search), Task.description.ilike(search)))
    if status:
        if status.upper() not in ("TODO", "IN_PROGRESS", "DONE"):
            raise HTTPException(status_code=422, detail="Invalid task status filter")
        query = query.filter(Task.status == status.upper())
    if priority:
        if priority.upper() not in ("LOW", "MEDIUM", "HIGH", "URGENT"):
            raise HTTPException(status_code=422, detail="Invalid priority filter")
        query = query.filter(Task.priority == priority.upper())
    if category:
        query = query.filter(func.lower(Task.category) == category.lower())
    if deadline_from:
        query = query.filter(Task.deadline >= datetime.combine(deadline_from, time.min))
    if deadline_to:
        query = query.filter(Task.deadline < datetime.combine(deadline_to + timedelta(days=1), time.min))
    columns = {"created": Task.created_at, "updated": Task.updated_at, "deadline": Task.deadline, "title": func.lower(Task.title)}
    if sort_by == "priority":
        sort_column = case((Task.priority == "URGENT", 0), (Task.priority == "HIGH", 1), (Task.priority == "MEDIUM", 2), else_=3)
    else:
        sort_column = columns[sort_by]
    sort_column = sort_column.asc() if sort_order == "asc" else sort_column.desc()
    tasks = query.order_by(sort_column, Task.created_at.desc()).offset(offset).limit(limit).all()
    dependency_map = _dependency_ids(db, tasks)
    return [_task_output(task, dependency_map.get(task.id, [])) for task in tasks]


@router.get("/calendar/events", response_model=List[TaskOut])
def calendar_events(start: datetime, end: datetime, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if start.tzinfo is None or end.tzinfo is None:
        raise HTTPException(status_code=422, detail="Calendar range must include a timezone offset")
    start = start.astimezone(timezone.utc).replace(tzinfo=None)
    end = end.astimezone(timezone.utc).replace(tzinfo=None)
    if end <= start or end - start > timedelta(days=368):
        raise HTTPException(status_code=422, detail="Calendar range must be valid and no longer than 367 days")
    range_start, range_end = start, end
    tasks = db.query(Task).filter(
        Task.owner_id == user.id,
        or_(
            (Task.deadline >= range_start) & (Task.deadline < range_end),
            (Task.scheduled_start < range_end) & (Task.scheduled_end > range_start),
        ),
    ).order_by(Task.scheduled_start.asc(), Task.deadline.asc(), Task.title.asc()).all()
    dependency_map = _dependency_ids(db, tasks)
    return [_task_output(task, dependency_map.get(task.id, [])) for task in tasks]


@router.post("/tasks", response_model=TaskOut, status_code=201)
def create_task(payload: TaskInput, idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key", min_length=16, max_length=128), db: Session = Depends(get_db), user: User = Depends(current_user)):
    if idempotency_key is not None:
        try:
            idempotency_key = str(UUID(idempotency_key))
        except ValueError:
            raise HTTPException(status_code=422, detail="Idempotency-Key must be a UUID")
        existing = db.query(Task).filter_by(owner_id=user.id, idempotency_key=idempotency_key).first()
        if existing is not None:
            return _idempotent_task_response(db, existing, payload)
    values = payload.dict(exclude={"dependency_ids"})
    values["category"] = _category_name(db, user.id, values.get("category"))
    _validate_dependencies(db, user.id, None, payload.dependency_ids)
    _validate_schedule_conflict(db, user.id, payload)
    task = Task(**values, owner_id=user.id, idempotency_key=idempotency_key)
    if task.status == "DONE":
        task.completed_at = datetime.utcnow()
    db.add(task)
    db.flush()
    _replace_dependencies(db, task.id, payload.dependency_ids)
    reminder_service.sync_task_reminder(db, task)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        # Concurrent retries can race between the first lookup and insert.
        # Return the winner's row rather than creating a second task.
        if idempotency_key is not None:
            existing = db.query(Task).filter_by(owner_id=user.id, idempotency_key=idempotency_key).first()
            if existing is not None:
                return _idempotent_task_response(db, existing, payload)
        raise
    db.refresh(task)
    return _task_output(task, payload.dependency_ids)


@router.get("/tasks/{task_id}", response_model=TaskOut)
def get_task(task_id: UUID, db: Session = Depends(get_db), user: User = Depends(current_user)):
    task = _task_or_404(db, task_id, user.id)
    dependencies = [row[0] for row in db.query(TaskDependency.depends_on_id).filter(TaskDependency.task_id == task.id).all()]
    return _task_output(task, dependencies)


@router.put("/tasks/{task_id}", response_model=TaskOut)
def update_task(task_id: UUID, payload: TaskInput, db: Session = Depends(get_db), user: User = Depends(current_user)):
    task = _task_or_404(db, task_id, user.id)
    was_completed = task.status == "DONE"
    values = payload.dict(exclude={"dependency_ids"})
    values["category"] = _category_name(db, user.id, values.get("category"))
    _validate_dependencies(db, user.id, task.id, payload.dependency_ids)
    _validate_schedule_conflict(db, user.id, payload, task.id)
    for key, value in values.items():
        setattr(task, key, value)
    if task.status == "DONE":
        task.completed_at = task.completed_at or datetime.utcnow()
    else:
        task.completed_at = None
    _replace_dependencies(db, task.id, payload.dependency_ids)
    reminder_service.sync_task_reminder(db, task)
    if not was_completed and task.status == "DONE":
        gamification.award_task_completion(db, user.id, task.id)
    db.commit()
    db.refresh(task)
    return _task_output(task, payload.dependency_ids)


@router.post("/tasks/{task_id}/duplicate", response_model=TaskOut, status_code=201)
def duplicate_task(task_id: UUID, db: Session = Depends(get_db), user: User = Depends(current_user)):
    source = _task_or_404(db, task_id, user.id)
    task = Task(owner_id=user.id, title=source.title + " (copy)", description=source.description,
                priority=source.priority, importance=source.importance, category=source.category,
                estimated_minutes=source.estimated_minutes, deadline=source.deadline)
    db.add(task)
    db.commit()
    db.refresh(task)
    return _task_output(task)


@router.get("/reminders", response_model=List[ReminderOut])
def list_reminders(db: Session = Depends(get_db), user: User = Depends(current_user)):
    rows=(db.query(Reminder,Task).join(Task,Task.id==Reminder.task_id).filter(
        Reminder.owner_id==user.id, Task.owner_id==user.id, Task.status!="DONE", Task.deadline.isnot(None)
    ).order_by(Task.deadline.asc()).limit(100).all())
    return [{"id":r.id,"task_id":t.id,"task_title":t.title,"deadline":t.deadline,"due_at":r.due_at,
             "status":r.status,"delivered_at":r.delivered_at,"timezone":user.timezone} for r,t in rows]


@router.get("/notifications", response_model=List[NotificationOut])
def list_notifications(limit:int=Query(30,ge=1,le=100),db:Session=Depends(get_db),user:User=Depends(current_user)):
    return db.query(Notification).filter_by(owner_id=user.id).order_by(Notification.created_at.desc()).limit(limit).all()


@router.get("/notifications/unread-count")
def unread_notifications(db:Session=Depends(get_db),user:User=Depends(current_user)):
    return {"count":db.query(Notification).filter_by(owner_id=user.id,read_at=None).count()}


@router.post("/notifications/read-all",response_model=List[NotificationOut])
def read_all_notifications(db:Session=Depends(get_db),user:User=Depends(current_user)):
    db.query(Notification).filter_by(owner_id=user.id,read_at=None).update({Notification.read_at:datetime.utcnow()},synchronize_session=False)
    db.commit()
    return db.query(Notification).filter_by(owner_id=user.id).order_by(Notification.created_at.desc()).limit(100).all()


@router.post("/notifications/{notification_id}/read",response_model=NotificationOut)
def read_notification(notification_id:UUID,db:Session=Depends(get_db),user:User=Depends(current_user)):
    item=db.query(Notification).filter_by(id=notification_id,owner_id=user.id).first()
    if not item: raise HTTPException(status_code=404,detail="Notification not found")
    if item.read_at is None: item.read_at=datetime.utcnow();db.commit();db.refresh(item)
    return item


@router.get("/focus/summary",response_model=FocusSummaryOut)
def focus_summary(db:Session=Depends(get_db),user:User=Depends(current_user)):
    return focus_service.summary(db,user.id,user.timezone)


@router.post("/focus/sessions",response_model=FocusSessionOut,status_code=201)
def start_focus_session(payload:FocusStartIn,db:Session=Depends(get_db),user:User=Depends(current_user)):
    try: return focus_service.start(db,user.id,payload)
    except focus_service.FocusError as exc: raise HTTPException(status_code=409,detail=str(exc))


@router.post("/focus/sessions/{session_id}/{action}",response_model=FocusSessionOut)
def update_focus_session(session_id:UUID,action:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    if action not in ("pause","resume","finish","reset"): raise HTTPException(status_code=404,detail="Focus session action not found")
    try: result=focus_service.transition(db,user.id,session_id,action)
    except focus_service.FocusError as exc: raise HTTPException(status_code=409,detail=str(exc))
    if result is None: raise HTTPException(status_code=404,detail="Focus session not found")
    return result


@router.delete("/tasks/{task_id}", status_code=204)
def delete_task(task_id: UUID, db: Session = Depends(get_db), user: User = Depends(current_user)):
    task = _task_or_404(db, task_id, user.id)
    db.delete(task)
    db.commit()
    return Response(status_code=204)


@router.get("/analytics/overview", response_model=AnalyticsOut)
def analytics_overview(start_date: Optional[date] = None, end_date: Optional[date] = None,
                      db: Session = Depends(get_db), user: User = Depends(current_user)):
    import pytz
    local_today = datetime.utcnow().replace(tzinfo=timezone.utc).astimezone(pytz.timezone(user.timezone)).date()
    start = start_date or local_today - timedelta(days=29)
    end = end_date or local_today
    if start > end:
        raise HTTPException(status_code=422, detail="Start date must be on or before end date")
    if (end - start).days > 365:
        raise HTTPException(status_code=422, detail="Date range cannot exceed 366 days")
    return analytics_service.overview(db, user.id, user.timezone, start, end)


@router.get("/gamification/profile", response_model=GamificationProfileOut)
def gamification_profile(db: Session = Depends(get_db), user: User = Depends(current_user)):
    result = gamification.refresh_profile(db, user.id)
    db.commit()
    return result
