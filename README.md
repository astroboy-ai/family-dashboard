# FamilyOS

FamilyOS is a self-hosted family knowledge and coordination system. Its core idea is simple: capture information once as a **Note**, then make it easy for family members and approved tools to find and use it. The longer-term plan includes family calendars, chores, meals, learning, a private vault, transit widgets, and the Archify knowledge graph.

This repository is being built in stages. The current code is an early backend foundation, not a finished dashboard: it includes the container stack, database models and initial migration, health/readiness endpoints, login/session foundations, and the first media upload flow. **There is no web frontend or first-run onboarding UI yet.**

## What You Need

For the containerized app:

- Docker Desktop (Windows or macOS) or Docker Engine (Linux), with Docker Compose v2 available.
- Git, to clone or update the repository.
- Internet access on first start so Docker can download the service images.

For backend tests outside Docker:

- `uv` and Python 3.12. The project pins the backend to Python 3.12; `uv` can install it for your user.
- Docker Engine is additionally required for tests that use Testcontainers and start PostgreSQL. Unit tests that do not need external services can run without Docker.

Node.js is not needed for the current backend or Python Playwright setup. It will be needed when the Next.js frontends are added.

## Quick Setup (Windows)

Open PowerShell in the `family-dashboard` directory.

1. **Start Docker Desktop** and wait until it reports that the engine is running. Check the tools:

   ```powershell
   docker --version
   docker compose version
   ```

2. **Create your local environment file.** It is ignored by Git and should stay on your machine:

   ```powershell
   Copy-Item .env.example .env
   ```

3. **Replace the required development secrets** in `.env`. Generate random 32-byte hexadecimal values locally with PowerShell:

   ```powershell
   $bytes = New-Object byte[] 32
   $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
   $rng.GetBytes($bytes)
   [Convert]::ToHexString($bytes).ToLowerInvariant()
   $rng.Dispose()
   ```

   Run that snippet separately for `POSTGRES_PASSWORD`, `MINIO_ROOT_PASSWORD`, and `JWT_SECRET`. Paste each value directly into `.env`; do not put real values in source files, Issues, chat, or commits. `MINIO_ROOT_USER=familyos` is a local development username and can be changed if desired.

4. **Start the services:**

   ```powershell
   docker compose up --build -d
   docker compose ps
   ```

   The first start downloads images, creates persistent data volumes, runs the initial database migration, creates the private MinIO media bucket, and starts the API.

5. **Check service health.** If GNU Make is installed, run:

   ```powershell
   make health
   ```

   Otherwise, run the checks directly:

   ```powershell
   docker compose exec -T postgres pg_isready -U familyos -d familyos
   docker compose exec -T redis redis-cli ping
   docker compose run --rm --no-deps minio-init
   docker compose exec -T backend python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2)"
   ```

   The API also has `/readyz`, which checks its database, Redis, and storage dependencies. The backend port is intentionally not published to the host in this compose file, so these checks run inside the Docker network. MinIO's S3 API is published on `localhost:9000` for browser-direct uploads; its admin console is not published.

## Environment Settings

Values in `.env.example` fall into three groups. Compose currently requires these values to be set even when a development default would otherwise be possible:

| Variable | Required now? | Purpose |
|---|---|---|
| `POSTGRES_PASSWORD` | **Yes** | Password for the local PostgreSQL service and backend database URL. Use a unique random value. |
| `MINIO_ROOT_USER` | **Yes** | Local MinIO administrator username. The example uses `familyos`. |
| `MINIO_ROOT_PASSWORD` | **Yes** | Local MinIO administrator password. Use a unique random value. |
| `S3_PUBLIC_ENDPOINT` | **Yes** | URL the browser uses for presigned media uploads. For local development, use `http://localhost:9000`. It must be reachable from the browser. |
| `JWT_SECRET` | **Yes** | Signs login access tokens. Set a random value of at least 32 bytes; never reuse a production secret in development. |
| `MINIO_API_PORT` | No | Host port for the MinIO S3 API; defaults to `9000`. Change it if that port is already occupied, and update `S3_PUBLIC_ENDPOINT` to match. |
| `MINIO_API_CORS_ALLOW_ORIGIN` | No | Comma-separated browser origins allowed to upload to MinIO. Defaults to the three planned local frontend origins. |
| `ENVIRONMENT` | No | Application environment; defaults to `development`. |
| `LOG_LEVEL` | No | Structured application log level; defaults to `INFO`. |

The template also contains `SERVICE_TOKEN`, `MASTER_KEY`, household settings, AI-provider settings, Google Calendar settings, and Home Assistant settings. They are placeholders for planned features and are **not required by the current Compose/backend implementation**. Do not add real integration credentials until the corresponding feature is implemented.

## Run Backend Tests

From PowerShell at the repository root:

```powershell
Push-Location backend
uv sync --group test
uv run pytest
Pop-Location
```

`uv sync` creates an ignored `backend/.venv` and installs the pinned test tools from `backend/uv.lock`. Unit tests run without Docker. Integration tests that start PostgreSQL with Testcontainers require Docker Engine to be installed and running. Python Playwright is included for future browser tests; the current repository does not yet contain frontend end-to-end tests.

## Common Commands

| Command | What it does |
|---|---|
| `docker compose up --build -d` | Build and start the local services. |
| `docker compose ps` | Show service state and health. |
| `docker compose logs -f backend` | Follow backend logs. Press `Ctrl+C` to stop following. |
| `docker compose down` | Stop and remove containers; keep database, Redis, and media volumes. |
| `make health` | Check Postgres, Redis, MinIO bucket setup, and API liveness. |
| `uv run pytest` (from `backend/`) | Run backend tests. |

**Keep your data:** `docker compose down` preserves named volumes. `docker compose down -v` deletes the database, Redis data, and media files; only use it when you intentionally want a complete local reset.

## Current API Surface

The backend is private to the Compose network in the current setup. Implemented routes include:

- `GET /healthz` and `GET /readyz` for health and dependency readiness.
- `POST /api/auth/login`, `GET /api/auth/me`, and `POST /api/auth/logout` for the current access-cookie flow.
- `POST /api/media/presign` and `POST /api/media/{asset_id}/complete` for authenticated media upload setup and completion.

There is not yet a browser-accessible API proxy or frontend, nor a first-run account creation screen. Account provisioning and later API access flows are still under development; the login endpoint expects a user that has already been created in the database. Do not expose the backend directly to an untrusted network.

## Troubleshooting

- **A port is already in use:** change `MINIO_API_PORT` and make `S3_PUBLIC_ENDPOINT` use the same port, then restart with `docker compose up -d`.
- **A service is unhealthy:** inspect it with `docker compose ps` and `docker compose logs -f <service>`.
- **The backend cannot connect to Postgres or Redis:** wait for the database and Redis health checks, then inspect `docker compose logs backend`.
- **Browser upload cannot reach MinIO:** confirm `S3_PUBLIC_ENDPOINT` is reachable from the browser and that the browser origin is included in `MINIO_API_CORS_ALLOW_ORIGIN`.
- **Testcontainers cannot start:** install/start Docker Engine. Skipping that service-backed test is expected when Docker is unavailable; report it as skipped rather than treating it as a passing integration test.

## Project Layout

```text
backend/           FastAPI app, SQLAlchemy models, Alembic migration, tests
[00]System-Blueprint.md
[01]Add-on 1 — Archify Gallery-Complete Design.md
[02]Add-on 2--- HK Transit Widget (Bus+MTR).md
[03]Add-on 3 -- Universal Search & Filter.md
docker-compose.yml  Local backend, PostgreSQL, Redis, and MinIO services
.env.example        Safe-to-commit environment template
Makefile            Local Compose shortcuts and health check
```

The blueprint is the implementation source of truth. Work proceeds in its build order; later product features should not be assumed available just because they appear in the roadmap.
