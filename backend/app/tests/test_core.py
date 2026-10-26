import os
import tempfile
import unittest
from datetime import date, timedelta
from unittest.mock import patch

_fd, _db_path = tempfile.mkstemp(suffix=".db")
os.environ["DATABASE_URL"] = "sqlite:///" + _db_path
os.environ["SECRET_KEY"] = "test-secret-key-long-enough-for-tests"
from fastapi.testclient import TestClient
from app.main import app
from app.core.database import Base, engine

Base.metadata.create_all(bind=engine)

class CoreApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_authentication_logout_revokes_token_and_rejects_missing_or_invalid_tokens(self):
        account = self.client.post("/api/v1/auth/register", json={
            "email": "session-security@example.com", "password": "correct-horse-battery", "full_name": "Session User"
        })
        self.assertEqual(account.status_code, 201)
        token = account.json()["access_token"]
        headers = {"Authorization": "Bearer " + token}
        self.assertEqual(self.client.get("/api/v1/users/me").status_code, 401)
        self.assertEqual(self.client.get("/api/v1/users/me", headers={"Authorization": "Bearer invalid"}).status_code, 401)
        self.assertEqual(self.client.get("/api/v1/users/me", headers=headers).status_code, 200)
        self.assertEqual(self.client.post("/api/v1/auth/logout", headers=headers).status_code, 204)
        self.assertEqual(self.client.get("/api/v1/users/me", headers=headers).status_code, 401)
        login = self.client.post("/api/v1/auth/login", json={"email": "session-security@example.com", "password": "correct-horse-battery"})
        self.assertEqual(login.status_code, 200)
        self.assertEqual(self.client.post("/api/v1/auth/login", json={"email": "session-security@example.com", "password": "wrong-password-value"}).status_code, 401)

    def test_registration_task_crud_and_user_isolation(self):
        self.assertNotIn("/api/v1/ai/breakdown", self.client.get("/openapi.json").json()["paths"])
        self.assertEqual(self.client.post("/api/v1/ai/breakdown", json={"goal":"Prepare for exam"}).status_code, 404)
        a = self.client.post("/api/v1/auth/register", json={"email":"a@example.com","password":"correct-horse-battery","full_name":"A User"})
        b = self.client.post("/api/v1/auth/register", json={"email":"b@example.com","password":"correct-horse-battery","full_name":"B User"})
        self.assertEqual(a.status_code, 201)
        ta, tb = a.json()["access_token"], b.json()["access_token"]
        created = self.client.post("/api/v1/tasks", headers={"Authorization":"Bearer "+ta}, json={"title":"Plan the week","priority":"HIGH"})
        self.assertEqual(created.status_code, 201)
        task_id = created.json()["id"]
        self.assertEqual(self.client.get("/api/v1/tasks", headers={"Authorization":"Bearer "+tb}).json(), [])
        self.assertEqual(self.client.get("/api/v1/tasks/"+task_id, headers={"Authorization":"Bearer "+tb}).status_code, 404)
        self.assertEqual(self.client.put("/api/v1/tasks/"+task_id, headers={"Authorization":"Bearer "+ta}, json={"title":"Plan the week","priority":"LOW","status":"DONE"}).json()["status"], "DONE")
        self.assertEqual(self.client.delete("/api/v1/tasks/"+task_id, headers={"Authorization":"Bearer "+ta}).status_code, 204)

    def test_daily_plan_persistence_edit_approval_and_authorization(self):
        a = self.client.post("/api/v1/auth/register", json={"email":"planner-a@example.com","password":"correct-horse-battery","full_name":"Planner A"})
        b = self.client.post("/api/v1/auth/register", json={"email":"planner-b@example.com","password":"correct-horse-battery","full_name":"Planner B"})
        ha = {"Authorization":"Bearer "+a.json()["access_token"]}
        hb = {"Authorization":"Bearer "+b.json()["access_token"]}
        target = date.today() + timedelta(days=7)
        available = self.client.post("/api/v1/planner/availability", headers=ha, json={"kind":"WORKING_HOURS","weekday":target.weekday(),"local_start":"09:00","local_end":"12:00"})
        self.assertEqual(available.status_code, 201, available.text)
        task = self.client.post("/api/v1/tasks", headers=ha, json={"title":"Planner persistence check","estimated_minutes":30,"priority":"HIGH"})
        self.assertEqual(task.status_code, 201, task.text)
        generated = self.client.post("/api/v1/planner/plans/generate", headers=ha, json={"plan_date":target.isoformat(),"break_minutes":0,"break_every_minutes":50})
        self.assertEqual(generated.status_code, 200, generated.text)
        plan = generated.json()
        scheduled = next(item for item in plan["items"] if item["item_type"] == "TASK")
        self.assertEqual(self.client.get("/api/v1/planner/plans?plan_date="+target.isoformat(), headers=ha).json()["id"], plan["id"])
        self.assertEqual(self.client.get("/api/v1/planner/plans/"+plan["id"], headers=hb).status_code, 404)
        edited = self.client.put("/api/v1/planner/plans/{}/items/{}".format(plan["id"], scheduled["id"]), headers=ha,
            json={"starts_at":target.isoformat()+"T11:00:00+00:00","ends_at":target.isoformat()+"T11:30:00+00:00"})
        self.assertEqual(edited.status_code, 200, edited.text)
        approved = self.client.post("/api/v1/planner/plans/"+plan["id"]+"/approve", headers=ha)
        self.assertEqual(approved.status_code, 200, approved.text)
        self.assertEqual(approved.json()["status"], "APPROVED")
        saved_task = self.client.get("/api/v1/tasks/"+task.json()["id"], headers=ha).json()
        self.assertEqual(saved_task["scheduled_start"], target.isoformat()+"T11:00:00")
        self.assertEqual(self.client.post("/api/v1/planner/plans/generate", headers=ha, json={"plan_date":target.isoformat()}).status_code, 409)

    def test_daily_plan_without_matching_hours_returns_actionable_validation_error(self):
        account = self.client.post("/api/v1/auth/register", json={"email":"planner-no-hours@example.com","password":"correct-horse-battery","full_name":"Planner No Hours"})
        headers = {"Authorization":"Bearer "+account.json()["access_token"]}
        target = date.today()
        response = self.client.post("/api/v1/planner/plans/generate", headers=headers,
                                    json={"plan_date":target.isoformat()})
        self.assertEqual(response.status_code, 422)
        self.assertIn("No working hours are configured", response.json()["detail"])

    def test_task_fields_categories_filters_duplicate_and_dependencies(self):
        auth = self.client.post("/api/v1/auth/register", json={"email":"phase2@example.com","password":"correct-horse-battery","full_name":"Phase Two"})
        headers = {"Authorization":"Bearer "+auth.json()["access_token"]}
        category = self.client.post("/api/v1/categories", headers=headers, json={"name":"Research"})
        self.assertEqual(category.status_code, 201)
        self.assertEqual(self.client.get("/api/v1/categories", headers=headers).json()[0]["name"], "Research")
        parent = self.client.post("/api/v1/tasks", headers=headers, json={
            "title":"Write report", "description":"Research data", "category":"Research",
            "estimated_minutes":90, "deadline":"2026-11-02T18:00:00", "priority":"HIGH",
        })
        blocker = self.client.post("/api/v1/tasks", headers=headers, json={"title":"Collect sources"})
        self.assertEqual(parent.status_code, 201)
        self.assertEqual(parent.json()["category"], "Research")
        self.assertEqual(parent.json()["estimated_minutes"], 90)
        task = self.client.post("/api/v1/tasks", headers=headers, json={
            "title":"Draft findings", "dependency_ids":[blocker.json()["id"]],
        })
        self.assertEqual(task.status_code, 201)
        self.assertEqual(task.json()["dependency_ids"], [blocker.json()["id"]])
        filtered = self.client.get("/api/v1/tasks?q=Research&category=Research&sort_by=deadline&sort_order=asc", headers=headers)
        self.assertEqual([item["id"] for item in filtered.json()], [parent.json()["id"]])
        duplicate = self.client.post("/api/v1/tasks/"+parent.json()["id"]+"/duplicate", headers=headers)
        self.assertEqual(duplicate.status_code, 201)
        self.assertEqual(duplicate.json()["title"], "Write report (copy)")
        self.assertEqual(duplicate.json()["category"], "Research")
        self.assertEqual(duplicate.json()["dependency_ids"], [])
        # Dependency cycles remain guarded independently of the removed parent-task feature.
        cycle = {"title":"Collect sources", "dependency_ids":[task.json()["id"]]}
        self.assertEqual(self.client.put("/api/v1/tasks/"+blocker.json()["id"], headers=headers, json=cycle).status_code, 409)
        rejected = self.client.post("/api/v1/tasks", headers=headers, json={"title":"Legacy child", "parent_task_id":parent.json()["id"]})
        self.assertEqual(rejected.status_code, 422)
        other = self.client.post("/api/v1/auth/register", json={"email":"phase2b@example.com","password":"correct-horse-battery","full_name":"Other User"})
        other_headers = {"Authorization":"Bearer "+other.json()["access_token"]}
        self.assertEqual(self.client.get("/api/v1/categories", headers=other_headers).json(), [])
        self.assertEqual(self.client.delete("/api/v1/categories/"+category.json()["id"], headers=headers).status_code, 204)
        self.assertIsNone(self.client.get("/api/v1/tasks/"+parent.json()["id"], headers=headers).json()["category"])

    def test_reminder_delivery_lifecycle_notifications_and_ownership(self):
        from datetime import datetime, timedelta
        from app.core.database import SessionLocal
        from app.models.entities import Notification, Reminder
        from app.services.reminders import deliver_due_reminders
        a=self.client.post("/api/v1/auth/register",json={"email":"reminder-a@example.com","password":"correct-horse-battery","full_name":"Reminder A"})
        b=self.client.post("/api/v1/auth/register",json={"email":"reminder-b@example.com","password":"correct-horse-battery","full_name":"Reminder B"})
        ha={"Authorization":"Bearer "+a.json()["access_token"]};hb={"Authorization":"Bearer "+b.json()["access_token"]}
        self.assertEqual(self.client.put("/api/v1/users/preferences",headers=ha,json={"timezone":"Asia/Kolkata"}).status_code,200)
        deadline=(datetime.utcnow()-timedelta(minutes=3)).isoformat()+"Z"
        task=self.client.post("/api/v1/tasks",headers=ha,json={"title":"Reminder task","deadline":deadline,"reminder_enabled":True,"reminder_lead_minutes":0})
        self.assertEqual(task.status_code,201,task.text)
        self.assertEqual(len(self.client.get("/api/v1/reminders",headers=ha).json()),1)
        db=SessionLocal()
        try:
            self.assertEqual(deliver_due_reminders(db),1)
            self.assertEqual(deliver_due_reminders(db),0)
            self.assertEqual(db.query(Notification).filter_by(owner_id=a.json()["user"]["id"]).count(),1)
        finally: db.close()
        notifications=self.client.get("/api/v1/notifications",headers=ha)
        self.assertEqual(notifications.status_code,200);self.assertEqual(len(notifications.json()),1)
        self.assertIn("IST",notifications.json()[0]["message"])
        notification_id=notifications.json()[0]["id"]
        self.assertEqual(self.client.post("/api/v1/notifications/"+notification_id+"/read",headers=hb).status_code,404)
        self.assertEqual(self.client.get("/api/v1/notifications/unread-count",headers=ha).json()["count"],1)
        self.assertEqual(self.client.post("/api/v1/notifications/"+notification_id+"/read",headers=ha).status_code,200)
        self.assertEqual(self.client.get("/api/v1/notifications/unread-count",headers=ha).json()["count"],0)
        updated_deadline=(datetime.utcnow()+timedelta(days=2)).isoformat()+"Z"
        changed=self.client.put("/api/v1/tasks/"+task.json()["id"],headers=ha,json={"title":"Reminder task","deadline":updated_deadline,"reminder_enabled":True,"reminder_lead_minutes":60})
        self.assertEqual(changed.status_code,200,changed.text)
        self.assertEqual(self.client.get("/api/v1/reminders",headers=ha).json()[0]["status"],"PENDING")
        changed_payload={"title":"Reminder task","deadline":updated_deadline,"reminder_enabled":True,"reminder_lead_minutes":60,"status":"DONE"}
        self.assertEqual(self.client.put("/api/v1/tasks/"+task.json()["id"],headers=ha,json=changed_payload).status_code,200)
        self.assertEqual(self.client.get("/api/v1/reminders",headers=ha).json(),[])
        removable=self.client.post("/api/v1/tasks",headers=ha,json={"title":"Delete reminder task","deadline":updated_deadline,"reminder_enabled":True})
        self.assertEqual(removable.status_code,201,removable.text)
        self.assertEqual(len(self.client.get("/api/v1/reminders",headers=ha).json()),1)
        self.assertEqual(self.client.delete("/api/v1/tasks/"+removable.json()["id"],headers=ha).status_code,204)
        db=SessionLocal()
        try:
            self.assertEqual(db.query(Reminder).filter_by(task_id=removable.json()["id"]).count(),0)
        finally: db.close()

    def test_focus_session_transitions_recovery_history_and_ownership(self):
        a=self.client.post("/api/v1/auth/register",json={"email":"focus-a@example.com","password":"correct-horse-battery","full_name":"Focus A"})
        b=self.client.post("/api/v1/auth/register",json={"email":"focus-b@example.com","password":"correct-horse-battery","full_name":"Focus B"})
        ha={"Authorization":"Bearer "+a.json()["access_token"]};hb={"Authorization":"Bearer "+b.json()["access_token"]}
        task=self.client.post("/api/v1/tasks",headers=ha,json={"title":"Focus task"}).json()
        started=self.client.post("/api/v1/focus/sessions",headers=ha,json={"kind":"FOCUS","planned_minutes":2,"task_id":task["id"]})
        self.assertEqual(started.status_code,201,started.text)
        session_id=started.json()["id"]
        self.assertEqual(self.client.get("/api/v1/focus/summary",headers=ha).json()["active_session"]["id"],session_id)
        self.assertEqual(self.client.get("/api/v1/focus/summary",headers=hb).json()["active_session"],None)
        self.assertEqual(self.client.post("/api/v1/focus/sessions/"+session_id+"/pause",headers=hb).status_code,404)
        self.assertEqual(self.client.post("/api/v1/focus/sessions/"+session_id+"/pause",headers=ha).json()["status"],"PAUSED")
        self.assertEqual(self.client.get("/api/v1/focus/summary",headers=ha).json()["active_session"]["status"],"PAUSED")
        self.assertEqual(self.client.post("/api/v1/focus/sessions/"+session_id+"/resume",headers=ha).json()["status"],"ACTIVE")
        self.assertEqual(self.client.post("/api/v1/focus/sessions/"+session_id+"/finish",headers=ha).json()["status"],"COMPLETED")
        self.assertEqual(self.client.post("/api/v1/focus/sessions/"+session_id+"/finish",headers=ha).status_code,200)
        summary=self.client.get("/api/v1/focus/summary",headers=ha).json()
        self.assertEqual(summary["active_session"],None);self.assertEqual(len(summary["history"]),1)
        self.assertGreaterEqual(summary["today_seconds"],0);self.assertGreaterEqual(summary["week_seconds"],summary["today_seconds"])

    def test_gamification_task_xp_idempotency_levels_and_achievement(self):
        from app.core.config import get_settings
        from app.core.database import SessionLocal
        from app.models.entities import PointEvent
        account=self.client.post("/api/v1/auth/register",json={"email":"xp-task@example.com","password":"correct-horse-battery","full_name":"XP Task"})
        headers={"Authorization":"Bearer "+account.json()["access_token"]}
        other=self.client.post("/api/v1/auth/register",json={"email":"xp-task-other@example.com","password":"correct-horse-battery","full_name":"Other XP"})
        other_headers={"Authorization":"Bearer "+other.json()["access_token"]}
        task=self.client.post("/api/v1/tasks",headers=headers,json={"title":"Finish once"}).json()
        task_payload={"title":"Finish once","status":"DONE"}
        self.assertEqual(self.client.put("/api/v1/tasks/"+task["id"],headers=headers,json=task_payload).status_code,200)
        profile=self.client.get("/api/v1/gamification/profile",headers=headers).json()
        self.assertEqual(profile["total_xp"],get_settings().xp_task_completion)
        self.assertEqual(profile["level"],1)
        self.assertEqual(next(x for x in profile["achievements"] if x["slug"]=="first_task")["progress"],1)
        self.assertEqual(self.client.put("/api/v1/tasks/"+task["id"],headers=headers,json=task_payload).status_code,200)
        reopened=dict(task_payload,status="TODO")
        self.client.put("/api/v1/tasks/"+task["id"],headers=headers,json=reopened)
        self.client.put("/api/v1/tasks/"+task["id"],headers=headers,json=task_payload)
        profile=self.client.get("/api/v1/gamification/profile",headers=headers).json()
        self.assertEqual(profile["total_xp"],get_settings().xp_task_completion)
        self.assertEqual(len(profile["point_events"]),1)
        other_profile=self.client.get("/api/v1/gamification/profile",headers=other_headers).json()
        self.assertEqual((other_profile["total_xp"],other_profile["point_events"]),(0,[]))
        db=SessionLocal()
        try: self.assertEqual(db.query(PointEvent).filter_by(owner_id=account.json()["user"]["id"]).count(),1)
        finally: db.close()
        for index in range(9):
            extra=self.client.post("/api/v1/tasks",headers=headers,json={"title":"Milestone task {}".format(index)}).json()
            payload={"title":extra["title"],"status":"DONE"}
            self.assertEqual(self.client.put("/api/v1/tasks/"+extra["id"],headers=headers,json=payload).status_code,200)
        profile=self.client.get("/api/v1/gamification/profile",headers=headers).json()
        self.assertEqual((profile["total_xp"],profile["level"],profile["xp_in_level"]),(100,2,0))
        self.assertIsNotNone(next(x for x in profile["achievements"] if x["slug"]=="ten_tasks")["unlocked_at"])

    def test_gamification_focus_xp_and_consecutive_local_activity_streak(self):
        from datetime import datetime, timedelta
        from app.core.database import SessionLocal
        from app.models.entities import PointEvent, FocusSession
        from app.services.gamification import _streak_values
        import pytz
        today=date.today()
        self.assertEqual(_streak_values([today-timedelta(days=3),today-timedelta(days=2),today],today)[:2],(1,2))
        account=self.client.post("/api/v1/auth/register",json={"email":"xp-focus@example.com","password":"correct-horse-battery","full_name":"XP Focus"})
        headers={"Authorization":"Bearer "+account.json()["access_token"]}
        self.client.put("/api/v1/users/preferences",headers=headers,json={"timezone":"Asia/Kolkata"})
        started=self.client.post("/api/v1/focus/sessions",headers=headers,json={"kind":"FOCUS","planned_minutes":25})
        self.assertEqual(started.status_code,201,started.text)
        db=SessionLocal()
        try:
            session=db.query(FocusSession).filter_by(id=started.json()["id"]).one()
            session.elapsed_seconds=600
            session.started_at=datetime.utcnow()-timedelta(seconds=600)
            db.commit()
        finally: db.close()
        completed=self.client.post("/api/v1/focus/sessions/"+started.json()["id"]+"/finish",headers=headers)
        self.assertEqual(completed.status_code,200,completed.text)
        self.assertEqual(self.client.post("/api/v1/focus/sessions/"+started.json()["id"]+"/finish",headers=headers).status_code,200)
        local_today=datetime.utcnow().replace(tzinfo=pytz.UTC).astimezone(pytz.timezone("Asia/Kolkata")).date()
        db=SessionLocal()
        try:
            for offset in (3,2,-1):
                local_stamp=pytz.timezone("Asia/Kolkata").localize(datetime.combine(local_today-timedelta(days=offset),datetime.min.time())+timedelta(hours=12))
                stamp=local_stamp.astimezone(pytz.UTC).replace(tzinfo=None)
                db.add(PointEvent(owner_id=account.json()["user"]["id"],event_key="history-{}".format(offset),
                    source_type="TASK_COMPLETION",source_id="historical-{}".format(offset),points=0,created_at=stamp))
            db.commit()
        finally: db.close()
        profile=self.client.get("/api/v1/gamification/profile",headers=headers).json()
        self.assertEqual(profile["total_xp"],5)
        self.assertEqual((profile["current_streak"],profile["longest_streak"]),(1,2))
        self.assertIsNotNone(next(x for x in profile["achievements"] if x["slug"]=="first_focus")["unlocked_at"])
        db=SessionLocal()
        try: self.assertEqual(db.query(PointEvent).filter_by(owner_id=account.json()["user"]["id"]).count(),4)
        finally: db.close()

    def test_analytics_real_records_timezone_boundaries_empty_and_ownership(self):
        from datetime import datetime, timedelta
        from app.core.database import SessionLocal
        from app.models.entities import FocusSession
        from pytz import UTC
        account=self.client.post("/api/v1/auth/register",json={"email":"analytics-a@example.com","password":"correct-horse-battery","full_name":"Analytics A"})
        other=self.client.post("/api/v1/auth/register",json={"email":"analytics-b@example.com","password":"correct-horse-battery","full_name":"Analytics B"})
        ha={"Authorization":"Bearer "+account.json()["access_token"]};hb={"Authorization":"Bearer "+other.json()["access_token"]}
        self.client.put("/api/v1/users/preferences",headers=ha,json={"timezone":"Asia/Kolkata"})
        self.assertEqual(self.client.get("/api/v1/analytics/overview",headers=ha).json()["total_tasks"],0)
        self.assertEqual(self.client.get("/api/v1/analytics/overview",headers=hb).json()["total_tasks"],0)
        self.assertEqual(self.client.get("/api/v1/analytics/overview").status_code,401)
        done=self.client.post("/api/v1/tasks",headers=ha,json={"title":"Saved completed task","status":"DONE"})
        overdue=self.client.post("/api/v1/tasks",headers=ha,json={"title":"Overdue task","deadline":(datetime.utcnow()-timedelta(days=2)).isoformat()+"Z"})
        self.assertEqual(done.status_code,201);self.assertEqual(overdue.status_code,201)
        db=SessionLocal()
        try:
            ended=datetime.utcnow()
            db.add(FocusSession(owner_id=account.json()["user"]["id"],kind="FOCUS",status="COMPLETED",planned_minutes=25,
                elapsed_seconds=1200,started_at=ended-timedelta(minutes=20),ended_at=ended,created_at=ended))
            db.commit()
        finally: db.close()
        local_today=self.client.get("/api/v1/users/me",headers=ha).json()["timezone"]
        import pytz
        target=datetime.utcnow().replace(tzinfo=UTC).astimezone(pytz.timezone(local_today)).date().isoformat()
        response=self.client.get("/api/v1/analytics/overview?start_date="+target+"&end_date="+target,headers=ha)
        self.assertEqual(response.status_code,200,response.text)
        result=response.json()
        self.assertEqual((result["total_tasks"],result["completed_tasks"],result["incomplete_tasks"],result["overdue_tasks"]),(2,1,1,1))
        self.assertEqual(result["completion_rate"],50.0)
        self.assertEqual(result["range_completed_tasks"],1)
        self.assertEqual(result["daily_trend"][0]["completed"],1)
        self.assertEqual(result["weekly_trend"][0]["completed"],1)
        self.assertEqual(result["weekly_trend"][0]["week_start"],(date.fromisoformat(target)-timedelta(days=date.fromisoformat(target).weekday())).isoformat())
        self.assertEqual((result["range_focus_seconds"],result["range_focus_sessions"]),(1200,1))
        self.assertEqual(result["timezone"],"Asia/Kolkata")
        empty=self.client.get("/api/v1/analytics/overview?start_date=2020-01-01&end_date=2020-01-02",headers=hb).json()
        self.assertEqual(empty["daily_trend"][0]["completed"],0)
        self.assertEqual(self.client.get("/api/v1/analytics/overview?start_date=2026-02-02&end_date=2026-01-01",headers=ha).status_code,422)

    def test_tasks_require_authentication(self):
        self.assertEqual(self.client.get("/api/v1/tasks").status_code, 401)

    def test_calendar_events_timezone_ranges_and_schedule_conflicts(self):
        account = self.client.post("/api/v1/auth/register", json={
            "email": "calendar@example.com", "password": "correct-horse-battery", "full_name": "Calendar User",
        })
        headers = {"Authorization": "Bearer " + account.json()["access_token"]}
        first = self.client.post("/api/v1/tasks", headers=headers, json={
            "title": "Design review", "deadline": "2026-11-02T18:29:00Z",
            "scheduled_start": "2026-11-02T09:00:00+05:30", "scheduled_end": "2026-11-02T10:00:00+05:30",
        })
        self.assertEqual(first.status_code, 201, first.text)
        self.assertEqual(first.json()["scheduled_start"], "2026-11-02T03:30:00")
        events = self.client.get("/api/v1/calendar/events?start=2026-11-02T00:00:00%2B05:30&end=2026-11-03T00:00:00%2B05:30", headers=headers)
        self.assertEqual(events.status_code, 200, events.text)
        self.assertEqual([event["id"] for event in events.json()], [first.json()["id"]])
        conflict = self.client.post("/api/v1/tasks", headers=headers, json={
            "title": "Conflicting block", "scheduled_start": "2026-11-02T09:30:00+05:30",
            "scheduled_end": "2026-11-02T10:30:00+05:30",
        })
        self.assertEqual(conflict.status_code, 409)
        invalid = self.client.post("/api/v1/tasks", headers=headers, json={
            "title": "Incomplete schedule", "scheduled_start": "2026-11-03T09:00:00Z",
        })
        self.assertEqual(invalid.status_code, 422)
