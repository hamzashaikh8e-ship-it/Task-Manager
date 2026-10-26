# TaskFlow AI

TaskFlow AI is a React + TypeScript productivity application backed by FastAPI and SQLAlchemy. It includes authenticated task management, Kanban, calendar, explainable prioritization, daily planning, reminders, in-app notifications, Focus Room, analytics, and gamification. AI goal breakdown, subtasks, and voice-to-task are intentionally not included.

## Requirements

- Python 3.10 or newer (backend dependencies are pinned)
- Node.js 18 or newer and pnpm
- SQLite for local use; PostgreSQL for production

## Local setup (Windows PowerShell)

From the repository root:

```powershell
Copy-Item .env.example .env
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements-dev.txt
pnpm --dir frontend install --frozen-lockfile
```

Set `SECRET_KEY` in `.env` to a unique random value before using the app beyond local testing. Generate a value locally with:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Copy the generated value directly into your local `.env`; never commit `.env` or paste the secret into support messages.

Apply database migrations and start FastAPI in one terminal:

```powershell
Set-Location backend
$env:PYTHONPATH = (Get-Location).Path
python -m alembic upgrade head
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Start Vite in another terminal from the repository root:

```powershell
pnpm --dir frontend dev
```

Open [http://localhost:5173](http://localhost:5173). In development, Vite proxies `/api` to `http://127.0.0.1:8000`. FastAPI docs are at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs); `/health` is liveness and `/ready` checks database connectivity.

SQLite defaults to `backend/taskflow.db` when commands run with `backend` as the working directory. The `.env.example` SQLite URL is relative to the process working directory. Use `sqlite:///./taskflow.db` from the `backend` directory.

## Environment variables

| Variable | Purpose |
|---|---|
| `APP_ENV` | `development`, `test`, or `production`; production checks reject unsafe settings. |
| `DATABASE_URL` | SQLAlchemy URL. SQLite locally; PostgreSQL with `postgresql+psycopg://...` in production. |
| `SECRET_KEY` | Server-only JWT signing key. Use a unique random value of at least 32 characters in production. |
| `ACCESS_TOKEN_MINUTES` | Bearer token lifetime (1–1440 minutes). |
| `CORS_ORIGINS` | Comma-separated browser origins; production requires explicit HTTPS origins. |
| `ALLOWED_HOSTS` | Comma-separated HTTP Host allowlist; set production API hostnames. |
| `LOG_LEVEL` | Server logging level; do not enable SQL parameter logging in production. |
| `VITE_API_URL` | Public API base URL at frontend build time. Defaults to same-origin `/api/v1`; use a full HTTPS API URL if frontend and API are separate origins. This is public configuration, never a secret. |
| `VITE_DEV_API_TARGET` | Optional local Vite proxy target; defaults to `http://127.0.0.1:8000`. |
| `PRIORITY_WEIGHT_*` | Rule-based planner scoring weights. |
| `XP_*` | Gamification reward configuration. |

The API has no AI provider credentials or AI feature configuration. Do not add server secrets to variables beginning with `VITE_`.

## Database migrations and data safety

Migrations are managed by Alembic. Do not delete `backend/taskflow.db` to apply changes. Back up the database file before upgrades:

```powershell
Copy-Item backend\taskflow.db "$env:TEMP\taskflow-backup-$(Get-Date -Format yyyyMMdd-HHmmss).db"
Set-Location backend
$env:PYTHONPATH = (Get-Location).Path
python -m alembic current
python -m alembic upgrade head
```

Migration `0010_auth_sessions` adds a session table only. Existing accounts, tasks, focus sessions, and gamification history are retained. Access tokens issued before this migration do not have a server session record; users must sign in again once after upgrading. Logout now revokes the active token server-side.

## Tests and production build

Backend tests (run from `backend`):

```powershell
$env:PYTHONPATH = (Get-Location).Path
python -m pytest app/tests -q
```

Frontend tests and production build (run from repository root):

```powershell
pnpm --dir frontend test
pnpm --dir frontend build
```

The build runs the TypeScript project checks (`tsc -b`) before Vite. No lint script is currently configured.

## Production deployment guide

This repository prepares the application for deployment; it does not deploy automatically. Choose a host that supports a Python ASGI service, PostgreSQL, and static frontend hosting.

1. **Provision PostgreSQL and HTTPS domains.** Keep database credentials in the backend host's secret manager. Do not use the demo credentials from `docker-compose.yml` outside local development.
2. **Configure backend variables** in the host dashboard: `APP_ENV=production`, a unique `SECRET_KEY`, PostgreSQL `DATABASE_URL`, `ACCESS_TOKEN_MINUTES`, `CORS_ORIGINS=https://your-frontend-domain`, and `ALLOWED_HOSTS=your-api-domain`. Production startup fails if the secret, PostgreSQL URL, HTTPS CORS origins, or public host allowlist is missing or unsafe.
3. **Build and start the API.** From `backend`, install `requirements.txt`, then run `python -m alembic upgrade head` as a release/pre-deploy step and start with `python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT`. Use one API worker while reminders are scheduled by the in-process reminder loop; multiple workers would each run a poller. For horizontal scaling, move reminder polling to a single dedicated scheduler before increasing API workers.
4. **Build the frontend** with `VITE_API_URL=https://your-api-domain/api/v1` if frontend and API use separate origins, then run `pnpm --dir frontend build` and publish `frontend/dist` to a static host. Alternatively, serve the frontend and reverse-proxy `/api` to the API on one origin, leaving `VITE_API_URL=/api/v1`.
5. **Set CORS to the exact frontend origin** and set `ALLOWED_HOSTS` to the API hostname. Verify the API `/health` and `/ready` endpoints, login, task persistence, and reminder delivery after deployment. FastAPI interactive docs are disabled when `APP_ENV=production`.
6. **Back up PostgreSQL** and rehearse migrations against a staging copy before production releases. Apply Alembic migrations as a separate release step; do not run schema auto-creation in production.

The current bearer token is stored in browser `localStorage`, so use HTTPS and deploy a strong Content Security Policy. The application does not currently implement API-level rate limiting; configure rate limits at the API gateway/edge, especially for registration and login. Account deletion is not exposed as an in-app workflow. Email delivery and browser push are not configured; reminders are in-app notifications delivered by the backend's scheduler.

## Reminder scheduling

The FastAPI process polls for due reminders every 15 seconds. This needs no Redis or other external service for a single-instance deployment. Keep one API process running for scheduled delivery. Delivery records are deduplicated in the database. Use a dedicated single scheduler/worker before running multiple API instances.

## Troubleshooting

- **Browser cannot reach API:** ensure FastAPI is listening on port 8000 and the Vite proxy target is correct. For a separate production API, rebuild with the public `VITE_API_URL`.
- **401 after upgrade:** sign in again; old tokens predate server-side session revocation.
- **Migration error:** inspect `python -m alembic current` and database URL configuration; make a backup before attempting a repair. Never drop/recreate the database to resolve a migration problem.
- **Reminder did not appear:** verify the task has a future deadline and reminders enabled, the backend is running, and `/ready` succeeds.
