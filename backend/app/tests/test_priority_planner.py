from datetime import date, datetime, timedelta, timezone
import unittest

from app.services.planner import (DependencyCycleError, Interval, ScheduleConflictError,
                                  WorkHours, generate_daily_schedule, work_intervals)
from app.services.priority import TaskRecord, score_tasks


class PriorityPlannerTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 5, 1, 8, tzinfo=timezone.utc)

    def test_priority_overdue_missing_and_completed(self):
        tasks = [
            TaskRecord('late', 'Overdue', 'TODO', 'LOW', 1, 30, self.now - timedelta(days=1)),
            TaskRecord('none', 'No date or estimate', 'TODO', 'LOW', 1, None, None),
            TaskRecord('done', 'Finished', 'DONE', 'URGENT', 5, 5, self.now),
        ]
        ranked, blocked = score_tasks(tasks, self.now)
        self.assertEqual(len(ranked), 2)
        self.assertEqual(ranked[0].task.id, 'late')
        self.assertTrue(any('Overdue' in reason for reason in ranked[0].explanation))
        self.assertTrue(any('No duration estimate' in reason for reason in ranked[1].explanation))
        self.assertEqual(blocked, [])

    def test_blocked_task_excluded_and_prerequisite_impact(self):
        prerequisite = TaskRecord('p', 'Prerequisite', 'TODO', 'LOW', 2, 20, None)
        blocked = TaskRecord('b', 'Blocked', 'TODO', 'URGENT', 5, 20, None, ('p',))
        ranked, blocked_list = score_tasks([prerequisite, blocked], self.now)
        self.assertEqual([item.task.id for item in ranked], ['p'])
        self.assertEqual(blocked_list[0].task.id, 'b')
        self.assertIn('Unblocks 1 incomplete task', ranked[0].explanation[-1])

    def test_schedule_respects_commitment_breaks_and_dependency(self):
        day = date(2026, 5, 4)
        hours = work_intervals(day, 'UTC', [WorkHours(day.weekday(), '09:00', '13:00')])
        commitment = Interval(datetime(2026,5,4,10),datetime(2026,5,4,10,30),'Meeting','COMMITMENT')
        tasks = [TaskRecord('a','First','TODO','HIGH',4,50,None),
                 TaskRecord('b','Second','TODO','MEDIUM',3,30,None,('a',))]
        result = generate_daily_schedule(tasks,hours,[commitment],day,break_minutes=10,break_every_minutes=50,
            now=datetime(2026,5,4,8,tzinfo=timezone.utc))
        timed = [item for item in result.items if item.starts_at]
        self.assertTrue(any(item.item_type=='BREAK' for item in timed))
        self.assertTrue(any(item.title=='Meeting' for item in timed))
        slots={item.task_id:item for item in timed if item.item_type=='TASK'}
        self.assertLessEqual(slots['a'].ends_at, slots['b'].starts_at)
        for left,right in zip(sorted(timed,key=lambda x:x.starts_at),sorted(timed,key=lambda x:x.starts_at)[1:]):
            self.assertLessEqual(left.ends_at,right.starts_at)

    def test_cycle_and_overlapping_commitments_rejected(self):
        day=date(2026,5,4)
        hours=work_intervals(day,'UTC',[WorkHours(day.weekday(),'09:00','17:00')])
        with self.assertRaises(DependencyCycleError):
            generate_daily_schedule([TaskRecord('a','A','TODO','LOW',2,30,None,('b',)),TaskRecord('b','B','TODO','LOW',2,30,None,('a',))],hours,[],day,now=datetime(2026,5,4,8,tzinfo=timezone.utc))
        overlap=[Interval(datetime(2026,5,4,10),datetime(2026,5,4,11),'A','COMMITMENT'),Interval(datetime(2026,5,4,10,30),datetime(2026,5,4,11,30),'B','COMMITMENT')]
        with self.assertRaises(ScheduleConflictError):
            generate_daily_schedule([],hours,overlap,day,now=datetime(2026,5,4,8,tzinfo=timezone.utc))

    def test_insufficient_time_reports_unscheduled_reason(self):
        day=date(2026,5,4)
        hours=work_intervals(day,'UTC',[WorkHours(day.weekday(),'09:00','10:00')])
        result=generate_daily_schedule([TaskRecord('a','Too long','TODO','HIGH',4,90,None)],hours,[],day,
            now=datetime(2026,5,4,8,tzinfo=timezone.utc))
        self.assertEqual(result.unscheduled[0].title,'Too long')
        self.assertIn('uninterrupted minutes',result.unscheduled[0].reason)

    def test_weekly_hours_use_monday_zero_for_monday_and_tuesday(self):
        monday = date(2026, 10, 26)
        tuesday = date(2026, 10, 27)
        monday_hours = WorkHours(0, '09:00', '12:00')
        tuesday_hours = WorkHours(1, '13:00', '17:00')
        self.assertEqual(monday.weekday(), 0)
        self.assertEqual(tuesday.weekday(), 1)
        self.assertEqual(len(work_intervals(monday, 'UTC', [monday_hours, tuesday_hours])), 1)
        self.assertEqual(work_intervals(monday, 'UTC', [monday_hours, tuesday_hours])[0].starts_at,
                         datetime(2026, 10, 26, 9))
        self.assertEqual(len(work_intervals(tuesday, 'UTC', [monday_hours, tuesday_hours])), 1)
        self.assertEqual(work_intervals(tuesday, 'UTC', [monday_hours, tuesday_hours])[0].starts_at,
                         datetime(2026, 10, 27, 13))


if __name__=='__main__': unittest.main()
