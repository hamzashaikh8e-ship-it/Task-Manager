import asyncio
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from sqlalchemy import text

from app.api.routes import router
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.services.reminders import deliver_due_reminders

settings = get_settings()
logging.basicConfig(level=getattr(logging, settings.log_level), format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)
_reminder_task = None

async def _reminder_loop():
    while True:
        db=SessionLocal()
        try:
            deliver_due_reminders(db)
        except Exception:
            db.rollback()
            logger.exception("Reminder delivery cycle failed")
        finally:
            db.close()
        await asyncio.sleep(15)
production = settings.app_env == "production"
app = FastAPI(title=settings.app_name, version="0.1.0", description="TaskFlow AI task management API",
              docs_url=None if production else "/docs", redoc_url=None if production else "/redoc",
              openapi_url=None if production else "/openapi.json", debug=False)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_host_list)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list,
                   allow_credentials=True, allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
                   allow_headers=["Authorization", "Content-Type", "Idempotency-Key"])
app.include_router(router, prefix=settings.api_prefix)

@app.on_event("startup")
async def start_reminder_worker():
    global _reminder_task
    # Vercel Functions are request-scoped/serverless; a background loop cannot be relied on.
    if not settings.run_reminder_scheduler or os.environ.get("VERCEL") == "1":
        logger.info("In-process reminder polling is disabled for this deployment")
        return
    _reminder_task=asyncio.create_task(_reminder_loop())

@app.on_event("shutdown")
async def stop_reminder_worker():
    global _reminder_task
    if _reminder_task:
        _reminder_task.cancel()
        try: await _reminder_task
        except asyncio.CancelledError: pass
        _reminder_task=None


@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/ready")
def ready():
    """Readiness check verifies the configured database can answer a query."""
    from app.core.database import engine
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return {"status": "ready"}
