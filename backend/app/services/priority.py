"""Deterministic task ranking. Scores are normalized to 0–100 and are not predictions."""
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class PriorityWeights:
    deadline: float = 0.30
    importance: float = 0.25
    priority: float = 0.20
    time_fit: float = 0.15
    downstream: float = 0.10

    def normalized(self) -> Dict[str, float]:
        raw = {"deadline": self.deadline, "importance": self.importance, "priority": self.priority,
               "time_fit": self.time_fit, "downstream": self.downstream}
        if any(value < 0 for value in raw.values()) or sum(raw.values()) <= 0:
            raise ValueError("Priority weights must be non-negative with a positive total")
        total = sum(raw.values())
        return {key: value / total for key, value in raw.items()}


@dataclass(frozen=True)
class TaskRecord:
    id: str
    title: str
    status: str
    priority: str
    importance: int
    estimated_minutes: Optional[int]
    deadline: Optional[datetime]
    dependency_ids: Tuple[str, ...] = ()
    scheduled_start: Optional[datetime] = None
    scheduled_end: Optional[datetime] = None


@dataclass(frozen=True)
class Recommendation:
    task: TaskRecord
    score: float
    explanation: Tuple[str, ...]


@dataclass(frozen=True)
class BlockedTask:
    task: TaskRecord
    reason: str


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _deadline_score(task: TaskRecord, now: datetime) -> Tuple[float, str]:
    if task.deadline is None:
        return 35.0, "No deadline; urgency is neutral."
    hours = (_as_utc(task.deadline) - _as_utc(now)).total_seconds() / 3600
    if hours < 0:
        days_overdue = max(1, int((-hours + 23) // 24))
        return 100.0, "Overdue by {} day{}; deadline urgency is high.".format(days_overdue, "s" if days_overdue != 1 else "")
    if hours <= 24:
        return 90.0, "Due within 24 hours."
    days = hours / 24
    if days <= 3:
        return 80.0, "Due within 3 days."
    if days <= 7:
        return 65.0, "Due within a week."
    if days <= 14:
        return 50.0, "Due within two weeks."
    if days <= 30:
        return 35.0, "Due within a month."
    return 20.0, "Deadline is more than 30 days away."


def _time_fit_score(task: TaskRecord, available_minutes: Optional[int]) -> Tuple[float, str]:
    if task.estimated_minutes is None:
        return 55.0, "No duration estimate; time fit uses a neutral score."
    if available_minutes is None:
        return 60.0, "Available time was not specified; time fit uses a neutral score."
    if task.estimated_minutes <= available_minutes:
        score = 100.0 if available_minutes == 0 else max(70.0, 100.0 - 30.0 * task.estimated_minutes / available_minutes)
        return score, "Estimated {} min fits in the available {} min.".format(task.estimated_minutes, available_minutes)
    score = 100.0 * available_minutes / task.estimated_minutes
    return score, "Estimated {} min exceeds the available {} min.".format(task.estimated_minutes, available_minutes)


def score_tasks(tasks: Sequence[TaskRecord], now: Optional[datetime] = None,
                available_minutes: Optional[int] = None, weights: PriorityWeights = PriorityWeights()
                ) -> Tuple[List[Recommendation], List[BlockedTask]]:
    """Return actionable ranked tasks and a separate blocked list.

    Completed tasks are omitted. Incomplete prerequisites prevent a recommendation;
    direct incomplete dependents contribute downstream impact to their prerequisite.
    """
    now = now or datetime.now(timezone.utc)
    normalized_weights = weights.normalized()
    by_id = {str(task.id): task for task in tasks}
    dependents: Dict[str, int] = {task_id: 0 for task_id in by_id}
    for task in tasks:
        if task.status != "DONE":
            for prerequisite in task.dependency_ids:
                if prerequisite in dependents:
                    dependents[prerequisite] += 1

    recommendations: List[Recommendation] = []
    blocked: List[BlockedTask] = []
    priority_scores = {"LOW": 25.0, "MEDIUM": 50.0, "HIGH": 75.0, "URGENT": 100.0}
    for task in tasks:
        if task.status == "DONE":
            continue
        names = []
        for dependency in task.dependency_ids:
            prerequisite = by_id.get(dependency)
            if prerequisite is None:
                names.append("missing prerequisite")
            elif prerequisite.status != "DONE":
                names.append(prerequisite.title)
        if names:
            blocked.append(BlockedTask(task, "Blocked by unfinished prerequisite{}: {}".format(
                "s" if len(names) != 1 else "", ", ".join(names))))
            continue
        deadline_score, deadline_reason = _deadline_score(task, now)
        importance_score = max(0.0, min(100.0, (task.importance - 1) * 25.0))
        priority_score = priority_scores.get(task.priority.upper(), 50.0)
        fit_score, fit_reason = _time_fit_score(task, available_minutes)
        downstream_score = min(100.0, dependents.get(str(task.id), 0) * 25.0)
        score = (deadline_score * normalized_weights["deadline"] +
                 importance_score * normalized_weights["importance"] +
                 priority_score * normalized_weights["priority"] +
                 fit_score * normalized_weights["time_fit"] +
                 downstream_score * normalized_weights["downstream"])
        explanation = [deadline_reason, "User priority is {}.".format(task.priority.lower()),
                       "Importance is {}/5.".format(task.importance), fit_reason]
        count = dependents.get(str(task.id), 0)
        if count:
            explanation.append("Unblocks {} incomplete task{}.".format(count, "s" if count != 1 else ""))
        recommendations.append(Recommendation(task, round(score, 2), tuple(explanation)))
    recommendations.sort(key=lambda item: (-item.score, item.task.deadline is None,
                                             _as_utc(item.task.deadline) if item.task.deadline else datetime.max.replace(tzinfo=timezone.utc),
                                             str(item.task.id)))
    blocked.sort(key=lambda item: (item.task.title.casefold(), str(item.task.id)))
    return recommendations, blocked
