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

## Deploying to Vercel

This repository is configured as **two Vercel projects** connected to the same GitHub repository: a static Vite frontend rooted at `frontend` and a FastAPI Python Function rooted at `backend`. Vercel's Python runtime supports FastAPI, but it is currently in beta. Vercel Functions are request-driven; do not rely on the local in-process reminder polling loop there.

### 1. Provision PostgreSQL

Create a hosted PostgreSQL database (for example, through a Vercel Marketplace provider or another managed PostgreSQL host). Copy its connection URL into the API project's server-side `DATABASE_URL` environment variable using the installed psycopg driver, in this form: `postgresql+psycopg://USER:PASSWORD@HOST:5432/DBNAME?sslmode=require`. Do not use the SQLite file on Vercel; function filesystems are not the persistent database.

First create **both** Vercel projects from this repository and note their canonical `.vercel.app` domains. The frontend project uses root `frontend`; the API project uses root `backend`. Configure the API's CORS origin with the frontend domain and the frontend API URL with the API domain before the final deployments.

### 2. Deploy the backend project

In Vercel, import `hamzashaikh8e-ship-it/Task-Manager` as a new project and set **Root Directory** to `backend`. Vercel should detect FastAPI and read `backend/requirements.txt`; the Python version file pins 3.12. Set these environment variables for Production (and Preview separately only if you intend to use previews):

- `APP_ENV=production`
- `DATABASE_URL` to the managed PostgreSQL URL
- `SECRET_KEY` to a unique random secret of at least 32 characters
- `ACCESS_TOKEN_MINUTES=60`
- `CORS_ORIGINS=https://<your-frontend-project>.vercel.app`
- `ALLOWED_HOSTS=<your-api-project>.vercel.app`
- `REMINDER_CRON_SECRET` to a unique random secret of at least 32 characters
- `RUN_REMINDER_SCHEDULER=false`

Production startup validates these settings and turns off FastAPI docs. Once the API project has a domain, use its exact hostname for `ALLOWED_HOSTS`; use the frontend's exact origin for `CORS_ORIGINS`. Keep all of these values in Vercel's server-side Environment Variables settings.

### 3. Apply database migrations

On Vercel, the backend runs the checked-in Alembic migrations during its Python build step, before API functions serve requests. PostgreSQL advisory locking prevents overlapping deployment builds from racing migrations. This uses migrations rather than `create_all` and is safe when repeated; later deploys only apply new revisions. The build uses Neon’s direct `DATABASE_URL_UNPOOLED` when available. For other hosting providers, apply Alembic as a separate release step using a trusted terminal and the server-side environment values. Rehearse upgrades on a staging database first and take a database backup.

```powershell
$env:PYTHONPATH = (Get-Location).Path
python -m pip install -r requirements.txt
python -m alembic upgrade head
```

Never commit a pulled environment file or paste its values into chat. Rehearse upgrades on a staging database first and take a database backup.

### 4. Deploy the frontend project

Import the same GitHub repository a second time. Set **Root Directory** to `frontend`; the included `frontend/vercel.json` configures `pnpm install --frozen-lockfile`, `pnpm build`, the `dist` output, and a same-origin `/api/v1` rewrite to the backend project. The rewrite destination is the public API URL in that file. If you use a different API hostname, update the rewrite target and push the change. The browser uses the frontend origin, which must exactly match the API `CORS_ORIGINS` value.

### 5. Schedule reminders outside the API request

The API automatically skips its long-running reminder loop when running on Vercel. Configure a trusted external scheduler to request `GET https://<your-api-project>.vercel.app/api/v1/internal/reminders/deliver` every 1–5 minutes with header `Authorization: Bearer <REMINDER_CRON_SECRET>`. The endpoint rejects missing or incorrect secrets, and reminder delivery is idempotent. Do not place this secret in frontend settings. Vercel Hobby Cron supports only daily schedules, which is too infrequent for deadline reminders; use a scheduler that supports the desired interval or a plan/service that does.

### 6. Verify the deployment

Check `https://<your-api-project>.vercel.app/ready`, then register a test account, sign in, create and complete a task, refresh, and verify analytics and task state. Add a near-future reminder and confirm it appears after the next scheduler run. Do not point the production frontend at SQLite or commit production credentials.

For Vercel's current Python runtime and FastAPI entrypoint behavior, see [Vercel Python Functions](https://vercel.com/docs/functions/runtimes/python) and [Deploy a FastAPI app on Vercel](https://vercel.com/docs/frameworks/backend/fastapi). For its scheduled job limits, see [Vercel Cron Jobs](https://vercel.com/docs/cron-jobs/manage-cron-jobs).

## Troubleshooting

- **Browser cannot reach API:** ensure FastAPI is listening on port 8000 and the Vite proxy target is correct. For a separate production API, rebuild with the public `VITE_API_URL`.
- **401 after upgrade:** sign in again; old tokens predate server-side session revocation.
- **Migration error:** inspect `python -m alembic current` and database URL configuration; make a backup before attempting a repair. Never drop/recreate the database to resolve a migration problem.
- **Reminder did not appear:** verify the task has a future deadline and reminders enabled, the backend is running, and `/ready` succeeds.
