"""Database orchestration for user-scoped recommendations and daily plans."""
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.entities import AvailabilityBlock, DailyPlan, PlanItem, Task, TaskDependency
from app.services.planner import (Interval, WorkHours, generate_daily_schedule,
                                  local_day_interval, work_intervals, PlannerError)
from app.services.priority import PriorityWeights, TaskRecord, score_tasks


class PlanningError(ValueError):
    pass


def _tasks(db: Session, owner_id: UUID):
    tasks = db.query(Task).filter(Task.owner_id == owner_id).all()
    ids = [task.id for task in tasks]
    dependencies = {}
    if ids:
        for task_id, dep_id in db.query(TaskDependency.task_id, TaskDependency.depends_on_id).filter(TaskDependency.task_id.in_(ids)).all():
            dependencies.setdefault(task_id, []).append(str(dep_id))
    records = [TaskRecord(str(t.id), t.title, t.status, t.priority, t.importance, t.estimated_minutes,
                          t.deadline, tuple(dependencies.get(t.id, ())), t.scheduled_start, t.scheduled_end) for t in tasks]
    return tasks, records


def _weights(settings):
    return PriorityWeights(settings.priority_weight_deadline, settings.priority_weight_importance,
                           settings.priority_weight_priority, settings.priority_weight_time_fit,
                           settings.priority_weight_downstream)


def recommendations(db: Session, owner_id: UUID, available_minutes=None):
    _, tasks = _tasks(db, owner_id)
    ranked, blocked = score_tasks(tasks, available_minutes=available_minutes, weights=_weights(get_settings()))
    return ranked, blocked


def list_availability(db: Session, owner_id: UUID):
    return db.query(AvailabilityBlock).filter(AvailabilityBlock.owner_id == owner_id).order_by(AvailabilityBlock.kind, AvailabilityBlock.weekday, AvailabilityBlock.starts_at).all()


def add_availability(db: Session, owner_id: UUID, payload):
    if payload.kind == 'WORKING_HOURS':
        rows = db.query(AvailabilityBlock).filter_by(owner_id=owner_id, kind='WORKING_HOURS', weekday=payload.weekday).all()
        for row in rows:
            if payload.local_start < row.local_end and row.local_start < payload.local_end:
                raise PlanningError('Working hour windows cannot overlap')
    else:
        conflict = db.query(AvailabilityBlock).filter(AvailabilityBlock.owner_id == owner_id,
            AvailabilityBlock.kind == 'COMMITMENT', AvailabilityBlock.starts_at < payload.ends_at,
            AvailabilityBlock.ends_at > payload.starts_at).first()
        task_conflict = db.query(Task).filter(Task.owner_id == owner_id, Task.status != 'DONE',
            Task.scheduled_start < payload.ends_at, Task.scheduled_end > payload.starts_at).first()
        if conflict or task_conflict:
            raise PlanningError('This commitment overlaps another commitment or scheduled task')
    row = AvailabilityBlock(owner_id=owner_id, **payload.dict())
    db.add(row); db.commit(); db.refresh(row)
    return row


def generate_plan(db: Session, owner, payload):
    day_start, day_end = local_day_interval(payload.plan_date, owner.timezone)
    hours_rows = db.query(AvailabilityBlock).filter_by(owner_id=owner.id, kind='WORKING_HOURS', weekday=payload.plan_date.weekday()).all()
    hours = work_intervals(payload.plan_date, owner.timezone, [WorkHours(r.weekday, r.local_start, r.local_end) for r in hours_rows])
    commitments = db.query(AvailabilityBlock).filter(AvailabilityBlock.owner_id == owner.id,
        AvailabilityBlock.kind == 'COMMITMENT', AvailabilityBlock.starts_at < day_end,
        AvailabilityBlock.ends_at > day_start).all()
    blocks = [Interval(r.starts_at, r.ends_at, r.title or 'Commitment', 'COMMITMENT') for r in commitments]
    tasks, records = _tasks(db, owner.id)
    for t in tasks:
        if t.status != 'DONE' and t.scheduled_start and t.scheduled_start < day_end and t.scheduled_end > day_start:
            blocks.append(Interval(t.scheduled_start, t.scheduled_end, t.title, 'TASK', str(t.id), 'Existing scheduled task'))
    result = generate_daily_schedule(records, hours, blocks, payload.plan_date, payload.available_minutes,
        payload.break_minutes, payload.break_every_minutes, now=datetime.now(timezone.utc), weights=_weights(get_settings()))
    plan = db.query(DailyPlan).filter_by(owner_id=owner.id, plan_date=payload.plan_date).first()
    if plan and plan.status == 'APPROVED':
        raise PlanningError('An approved plan already exists for this date')
    if not plan:
        plan = DailyPlan(owner_id=owner.id, plan_date=payload.plan_date, timezone=owner.timezone)
        db.add(plan); db.flush()
    else:
        db.query(PlanItem).filter_by(plan_id=plan.id).delete(synchronize_session=False)
    plan.timezone, plan.available_minutes = owner.timezone, payload.available_minutes
    plan.break_minutes, plan.break_every_minutes = payload.break_minutes, payload.break_every_minutes
    plan.generated_at = datetime.utcnow()
    for item in result.items:
        db.add(PlanItem(plan_id=plan.id, task_id=UUID(item.task_id) if item.task_id else None,
            item_type=item.item_type, title=item.title, starts_at=item.starts_at, ends_at=item.ends_at,
            reason=item.reason, position=item.position))
    db.commit(); db.refresh(plan)
    return get_plan(db, owner.id, plan.id)


def get_plan(db: Session, owner_id: UUID, plan_id: UUID):
    plan = db.query(DailyPlan).filter_by(id=plan_id, owner_id=owner_id).first()
    if not plan: return None
    plan.items = db.query(PlanItem).filter_by(plan_id=plan.id).order_by(PlanItem.position).all()
    return plan


def get_plan_by_date(db: Session, owner_id: UUID, day):
    plan = db.query(DailyPlan).filter_by(owner_id=owner_id, plan_date=day).first()
    return get_plan(db, owner_id, plan.id) if plan else None


def _validate_plan_intervals(db: Session, owner_id: UUID, plan, scheduled):
    day_start, day_end = local_day_interval(plan.plan_date, plan.timezone)
    commitments = db.query(AvailabilityBlock).filter(AvailabilityBlock.owner_id == owner_id,
        AvailabilityBlock.kind == 'COMMITMENT', AvailabilityBlock.starts_at < day_end,
        AvailabilityBlock.ends_at > day_start).all()
    included_task_ids = {str(item.task_id) for item in scheduled if item.task_id}
    external_tasks = db.query(Task).filter(Task.owner_id == owner_id, Task.status != 'DONE',
        Task.scheduled_start < day_end, Task.scheduled_end > day_start).all()
    for item in scheduled:
        for commitment in commitments:
            if item.starts_at < commitment.ends_at and commitment.starts_at < item.ends_at:
                raise PlanningError('A fixed commitment now overlaps {}'.format(item.title))
        for existing in external_tasks:
            if str(existing.id) not in included_task_ids and item.starts_at < existing.scheduled_end and existing.scheduled_start < item.ends_at:
                raise PlanningError('An existing calendar task now overlaps {}'.format(item.title))


def edit_item(db: Session, owner_id: UUID, plan_id: UUID, item_id: UUID, payload):
    plan = get_plan(db, owner_id, plan_id)
    if not plan: return None
    if plan.status != 'DRAFT': raise PlanningError('Approved plans cannot be edited')
    item = next((i for i in plan.items if i.id == item_id), None)
    if not item or item.item_type != 'TASK': raise PlanningError('Only scheduled task items can be edited')
    for other in plan.items:
        if other.id != item.id and other.starts_at and payload.starts_at < other.ends_at and other.starts_at < payload.ends_at:
            raise PlanningError('This edit overlaps another plan item')
    task = db.query(Task).filter_by(id=item.task_id, owner_id=owner_id).first()
    if not task: raise PlanningError('Task no longer exists')
    hours_rows = db.query(AvailabilityBlock).filter_by(owner_id=owner_id, kind='WORKING_HOURS', weekday=plan.plan_date.weekday()).all()
    windows = work_intervals(plan.plan_date, plan.timezone, [WorkHours(r.weekday, r.local_start, r.local_end) for r in hours_rows])
    if not any(window.starts_at <= payload.starts_at and payload.ends_at <= window.ends_at for window in windows):
        raise PlanningError('Edited task must fit inside a configured working-hours window')
    proposed_items = [SimpleNamespace(task_id=other.task_id, title=other.title,
                        starts_at=payload.starts_at if other.id == item.id else other.starts_at,
                        ends_at=payload.ends_at if other.id == item.id else other.ends_at)
                      for other in plan.items if other.item_type == 'TASK' and other.starts_at]
    _validate_plan_intervals(db, owner_id, plan, proposed_items)
    item.starts_at, item.ends_at = payload.starts_at, payload.ends_at
    db.commit()
    return get_plan(db, owner_id, plan_id)


def approve_plan(db: Session, owner_id: UUID, plan_id: UUID):
    plan = get_plan(db, owner_id, plan_id)
    if not plan: return None
    if plan.status == 'APPROVED': return plan
    scheduled = [i for i in plan.items if i.item_type == 'TASK' and i.task_id and i.starts_at]
    _validate_plan_intervals(db, owner_id, plan, scheduled)
    tasks, records = _tasks(db, owner_id)
    from app.services.planner import detect_dependency_cycles
    detect_dependency_cycles(records)
    by_id = {str(task.id): task for task in tasks}
    scheduled_by_id = {str(item.task_id): item for item in scheduled}
    for item in scheduled:
        task = by_id.get(str(item.task_id))
        if task is None: raise PlanningError('Task no longer exists')
        dependencies = [row[0] for row in db.query(TaskDependency.depends_on_id).filter(TaskDependency.task_id == task.id).all()]
        for dep_id in dependencies:
            prerequisite = by_id.get(str(dep_id))
            if prerequisite and prerequisite.status != 'DONE':
                dep_item = scheduled_by_id.get(str(dep_id))
                if dep_item is None or dep_item.ends_at > item.starts_at:
                    raise PlanningError('A prerequisite is not scheduled before {}'.format(task.title))
    for index, item in enumerate(sorted(scheduled, key=lambda x: x.starts_at)):
        if index and item.starts_at < sorted(scheduled, key=lambda x: x.starts_at)[index-1].ends_at:
            raise PlanningError('Plan contains overlapping tasks')
        task = db.query(Task).filter_by(id=item.task_id, owner_id=owner_id).first()
        if not task: raise PlanningError('Task no longer exists')
        task.scheduled_start, task.scheduled_end = item.starts_at, item.ends_at
    plan.status, plan.approved_at = 'APPROVED', datetime.utcnow()
    db.commit()
    return get_plan(db, owner_id, plan_id)
