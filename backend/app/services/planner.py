"""Pure daily scheduling routines. All interval values passed here are UTC datetimes."""
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

import pytz
from pytz.exceptions import AmbiguousTimeError, NonExistentTimeError

from app.services.priority import PriorityWeights, TaskRecord, score_tasks

DEFAULT_TASK_MINUTES = 30


class PlannerError(ValueError):
    pass


class DependencyCycleError(PlannerError):
    def __init__(self, cycle: Sequence[str]):
        self.cycle = list(cycle)
        super().__init__("Task dependencies contain a cycle: {}".format(" -> ".join(self.cycle)))


class ScheduleConflictError(PlannerError):
    pass


@dataclass(frozen=True)
class WorkHours:
    weekday: int
    local_start: str
    local_end: str


@dataclass(frozen=True)
class Interval:
    starts_at: datetime
    ends_at: datetime
    title: str
    item_type: str
    task_id: Optional[str] = None
    reason: Optional[str] = None


@dataclass(frozen=True)
class DraftItem:
    item_type: str
    title: str
    task_id: Optional[str]
    starts_at: Optional[datetime]
    ends_at: Optional[datetime]
    reason: Optional[str]
    position: int


@dataclass(frozen=True)
class PlannerResult:
    items: Tuple[DraftItem, ...]
    unscheduled: Tuple[DraftItem, ...]


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc).replace(tzinfo=None)
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def local_day_interval(day: date, timezone_name: str) -> Tuple[datetime, datetime]:
    """Return naive-UTC bounds for the user's local day, including DST transitions."""
    zone = pytz.timezone(timezone_name)
    try:
        local_start = zone.localize(datetime.combine(day, time.min), is_dst=None)
        local_end = zone.localize(datetime.combine(day + timedelta(days=1), time.min), is_dst=None)
    except (AmbiguousTimeError, NonExistentTimeError) as exc:
        raise PlannerError("The selected local day has an ambiguous timezone boundary") from exc
    return _utc(local_start), _utc(local_end)


def work_intervals(day: date, timezone_name: str, hours: Sequence[WorkHours]) -> List[Interval]:
    zone = pytz.timezone(timezone_name)
    result = []
    for block in hours:
        if block.weekday != day.weekday():
            continue
        try:
            start = datetime.strptime(block.local_start, "%H:%M").time()
            end = datetime.strptime(block.local_end, "%H:%M").time()
            if end <= start:
                raise PlannerError("Working hours must end later on the same day")
            local_start = zone.localize(datetime.combine(day, start), is_dst=None)
            local_end = zone.localize(datetime.combine(day, end), is_dst=None)
        except (ValueError, AmbiguousTimeError, NonExistentTimeError) as exc:
            raise PlannerError("Working hours contain an invalid local time for {}".format(day.isoformat())) from exc
        result.append(Interval(_utc(local_start), _utc(local_end), "Working hours", "WORK"))
    result.sort(key=lambda item: item.starts_at)
    for left, right in zip(result, result[1:]):
        if right.starts_at < left.ends_at:
            raise ScheduleConflictError("Configured working hour windows overlap")
    return result


def detect_dependency_cycles(tasks: Sequence[TaskRecord]) -> None:
    by_id = {str(task.id): task for task in tasks}
    state: Dict[str, int] = {}
    stack: List[str] = []

    def visit(task_id: str) -> None:
        state[task_id] = 1
        stack.append(task_id)
        for dependency in by_id[task_id].dependency_ids:
            if dependency not in by_id:
                continue
            if state.get(dependency) == 1:
                start = stack.index(dependency)
                raise DependencyCycleError(stack[start:] + [dependency])
            if state.get(dependency, 0) == 0:
                visit(dependency)
        stack.pop()
        state[task_id] = 2

    for task_id in by_id:
        if state.get(task_id, 0) == 0:
            visit(task_id)


def _ensure_non_overlapping(blocks: Sequence[Interval]) -> None:
    sorted_blocks = sorted(blocks, key=lambda item: (item.starts_at, item.ends_at))
    for left, right in zip(sorted_blocks, sorted_blocks[1:]):
        if right.starts_at < left.ends_at:
            raise ScheduleConflictError("Fixed commitments overlap: {} and {}".format(left.title, right.title))


def _subtract_interval(slot: Tuple[datetime, datetime], block: Interval) -> List[Tuple[datetime, datetime]]:
    start, end = slot
    if block.ends_at <= start or block.starts_at >= end:
        return [slot]
    result = []
    if start < block.starts_at:
        result.append((start, block.starts_at))
    if block.ends_at < end:
        result.append((block.ends_at, end))
    return result


def _free_slots(hours: Sequence[Interval], blocked: Sequence[Interval], now: datetime) -> List[Tuple[datetime, datetime]]:
    slots: List[Tuple[datetime, datetime]] = []
    for work in hours:
        start = max(work.starts_at, now)
        if start < work.ends_at:
            slots.append((start, work.ends_at))
    for block in sorted(blocked, key=lambda item: item.starts_at):
        slots = [piece for slot in slots for piece in _subtract_interval(slot, block)]
    return sorted(slots)


def _take_slot(slots: List[Tuple[datetime, datetime]], duration: int,
               earliest: datetime) -> Optional[Tuple[datetime, datetime]]:
    length = timedelta(minutes=duration)
    for index, (start, end) in enumerate(slots):
        start = max(start, earliest)
        if start + length <= end:
            finish = start + length
            replacement = []
            if slots[index][0] < start:
                replacement.append((slots[index][0], start))
            if finish < end:
                replacement.append((finish, end))
            slots[index:index + 1] = replacement
            return start, finish
    return None


def generate_daily_schedule(tasks: Sequence[TaskRecord], work_hours: Sequence[Interval],
                            fixed_blocks: Sequence[Interval], plan_date: date,
                            available_minutes: Optional[int] = None, break_minutes: int = 10,
                            break_every_minutes: int = 50, now: Optional[datetime] = None,
                            weights: PriorityWeights = PriorityWeights(),
                            default_task_minutes: int = DEFAULT_TASK_MINUTES) -> PlannerResult:
    """Build an explainable draft, honoring hard intervals and dependencies.

    Missing estimates reserve ``default_task_minutes``. A task's slot is not split;
    configured breaks are inserted between tasks once accumulated focus reaches the
    configured interval. Already scheduled tasks and fixed commitments stay put.
    """
    if not work_hours:
        raise PlannerError("No working hours are configured for {}".format(plan_date.strftime("%A")))
    if available_minutes is not None and available_minutes <= 0:
        raise PlannerError("Available work time must be greater than zero")
    if break_minutes < 0 or break_every_minutes <= 0 or default_task_minutes <= 0:
        raise PlannerError("Break and default-duration settings are invalid")
    now = _utc(now or datetime.now(timezone.utc))
    detect_dependency_cycles(tasks)
    task_by_id = {str(task.id): task for task in tasks}
    _ensure_non_overlapping(fixed_blocks)
    for left, right in zip(sorted(work_hours, key=lambda item: item.starts_at),
                           sorted(work_hours, key=lambda item: item.starts_at)[1:]):
        if right.starts_at < left.ends_at:
            raise ScheduleConflictError("Configured working hour windows overlap")

    day_start = min(item.starts_at for item in work_hours)
    day_end = max(item.ends_at for item in work_hours)
    day_blocks = [block for block in fixed_blocks if block.starts_at < day_end and block.ends_at > day_start]
    _ensure_non_overlapping(day_blocks)
    slots = _free_slots(work_hours, day_blocks, now)
    scheduled_today = {block.task_id: block for block in fixed_blocks
                       if block.item_type == "TASK" and block.task_id is not None}
    items: List[DraftItem] = []
    unscheduled: List[DraftItem] = []
    for block in fixed_blocks:
        if block.item_type == "COMMITMENT" or block.task_id in scheduled_today:
            items.append(DraftItem(block.item_type, block.title, block.task_id,
                                   block.starts_at, block.ends_at, block.reason, 0))

    pending: Dict[str, TaskRecord] = {}
    for task in tasks:
        task_id = str(task.id)
        if task.status == "DONE" or task_id in scheduled_today:
            continue
        if task.scheduled_start is not None:
            unscheduled.append(DraftItem("UNSCHEDULED", task.title, task_id, None, None,
                                         "Already scheduled on another date; its existing block was left unchanged.", 0))
        else:
            pending[task_id] = task

    completed = {str(task.id) for task in tasks if task.status == "DONE"}
    placed: Dict[str, datetime] = {task_id: block.ends_at for task_id, block in scheduled_today.items()}
    work_used = 0
    focus_since_break = 0
    break_failed = False

    while pending and not break_failed:
        ready = []
        for task_id, task in pending.items():
            if all(dep in completed or dep in placed for dep in task.dependency_ids):
                ready.append(task)
        if not ready:
            break
        completed_or_placed = completed | set(placed)
        scoring_records = [TaskRecord(id=str(task.id), title=task.title,
                                      status="DONE" if str(task.id) in completed_or_placed else task.status,
                                      priority=task.priority, importance=task.importance,
                                      estimated_minutes=task.estimated_minutes, deadline=task.deadline,
                                      dependency_ids=task.dependency_ids) for task in tasks]
        remaining = None if available_minutes is None else max(0, available_minutes - work_used)
        recommendations, _ = score_tasks(scoring_records, now=now, available_minutes=remaining, weights=weights)
        ready_ids = {str(task.id) for task in ready}
        selected_recommendation = next(item for item in recommendations if str(item.task.id) in ready_ids)
        selected = next(task for task in ready if str(task.id) == str(selected_recommendation.task.id))
        task_id = str(selected.id)
        duration = selected.estimated_minutes or default_task_minutes
        if remaining is not None and duration > remaining:
            unscheduled.append(DraftItem("UNSCHEDULED", selected.title, task_id, None, None,
                                         "Needs {} work minutes but only {} configured minutes remain.".format(duration, remaining), 0))
            pending.pop(task_id)
            continue
        dependency_end = max([placed[dep] for dep in selected.dependency_ids if dep in placed] or [now])
        slot = _take_slot(slots, duration, dependency_end)
        if slot is None:
            longest = max([int((end - start).total_seconds() // 60) for start, end in slots] or [0])
            reason = "Needs {} uninterrupted minutes; the longest remaining slot is {} minutes.".format(duration, longest)
            if selected.estimated_minutes is None:
                reason += " No estimate was set, so the planner tried its {} minute default.".format(default_task_minutes)
            unscheduled.append(DraftItem("UNSCHEDULED", selected.title, task_id, None, None, reason, 0))
            pending.pop(task_id)
            continue
        start, end = slot
        rationale = "Priority score {:.1f}/100; {} minutes reserved{}".format(
            selected_recommendation.score, duration,
            " ({}-minute default; estimate missing)".format(default_task_minutes) if selected.estimated_minutes is None else "")
        items.append(DraftItem("TASK", selected.title, task_id, start, end, rationale, 0))
        placed[task_id] = end
        pending.pop(task_id)
        work_used += duration
        focus_since_break += duration
        if break_minutes and focus_since_break >= break_every_minutes and pending:
            pause = _take_slot(slots, break_minutes, end)
            if pause is None:
                break_failed = True
            else:
                pause_start, pause_end = pause
                items.append(DraftItem("BREAK", "Break", None, pause_start, pause_end,
                                       "{} minute break after {} minutes of focus work.".format(break_minutes, focus_since_break), 0))
                focus_since_break = 0

    if pending:
        for task_id, task in pending.items():
            missing = [task_by_id[dep].title if dep in task_by_id else "missing prerequisite"
                       for dep in task.dependency_ids if dep not in completed and dep not in placed]
            if missing:
                reason = "Blocked because prerequisite{} {} could not be scheduled first.".format(
                    "s" if len(missing) != 1 else "", ", ".join(missing))
            elif break_failed:
                reason = "The configured break could not fit in the remaining work windows."
            else:
                reason = "No remaining working slot can fit this task."
            unscheduled.append(DraftItem("UNSCHEDULED", task.title, task_id, None, None, reason, 0))

    items.sort(key=lambda item: (item.starts_at or datetime.max, item.ends_at or datetime.max, item.item_type, item.title))
    unscheduled.sort(key=lambda item: (item.title.casefold(), item.task_id or ""))
    items = [DraftItem(item.item_type, item.title, item.task_id, item.starts_at, item.ends_at, item.reason, index)
             for index, item in enumerate(items)]
    unscheduled = [DraftItem(item.item_type, item.title, item.task_id, None, None, item.reason, index)
                   for index, item in enumerate(unscheduled)]
    return PlannerResult(tuple(items + unscheduled), tuple(unscheduled))
