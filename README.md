# FamilyOS

FamilyOS is a self-hosted family knowledge and coordination system. This repository contains an early usable slice, not the complete blueprint: backend foundations, a Next.js dashboard, first-run household setup, email/PIN authentication, notes and blocks, basic keyword search, a freehand whiteboard, persisted tag proposals, an initial Archify graph projection, and a Transit ETA proxy.

Calendar, transit presets/widgets, complete hybrid/faceted search, full tag governance, the full Archify feature set, Hermes chat, wall/kid apps, and PWA/offline support remain unfinished.

## What You Need
For the main frontend, Node.js and npm are required. The current UI lives in `frontend-main/`; run it separately from the backend with `npm install` and `npm run dev`.

For the containerized app:

- Docker Desktop (Windows or macOS) or Docker Engine (Linux), with Docker Compose v2 available.
- Git, to clone or update the repository.
- Internet access on first start so Docker can download the service images.

For backend tests outside Docker:

- `uv` and Python 3.12. The project pins the backend to Python 3.12; `uv` can install it for your user.
- Docker Engine is additionally required for tests that use Testcontainers and start PostgreSQL. Unit tests that do not need external services can run without Docker.

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

   Run that snippet separately for `POSTGRES_PASSWORD`, `S3_SECRET_KEY`, and `JWT_SECRET`. Paste each value directly into `.env`; do not put real values in source files, Issues, chat, or commits. `S3_ACCESS_KEY=familyos` is a local development access key and can be changed if desired.

4. **Start the services:**

   ```powershell
   docker compose up --build -d
   docker compose ps
   ```

   The first start downloads images, creates persistent data volumes, runs the initial database migration, creates the authenticated SeaweedFS S3 bucket, and starts the API.
   If you have data in an older MinIO volume, SeaweedFS cannot read that on-disk format directly. Copy existing objects through the S3 API before switching; the old `miniodata` volume is not mounted or deleted by this configuration.

5. **Check service health.** If GNU Make is installed, run:

   ```powershell
   make health
   ```

   Otherwise, run the checks directly:

   ```powershell
   docker compose exec -T postgres pg_isready -U familyos -d familyos
   docker compose exec -T redis redis-cli ping
   docker compose exec -T backend python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/readyz', timeout=5)"
   docker compose exec -T backend python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2)"
   ```

   `/readyz` checks the database, Redis, and S3 bucket using the configured credentials. The backend port is intentionally not published to the host in this compose file, so these checks run inside the Docker network. SeaweedFS's S3 API is published on `localhost:8333` for browser-direct uploads; its admin interfaces are not published.

## Environment Settings

Values in `.env.example` fall into three groups. Compose currently requires these values to be set even when a development default would otherwise be possible:

| Variable | Required now? | Purpose |
|---|---|---|
| `POSTGRES_PASSWORD` | **Yes** | Password for the local PostgreSQL service and backend database URL. Use a unique random value. |
| `S3_ACCESS_KEY` | **Yes** | S3 access key used by the backend and SeaweedFS. The example uses `familyos`. |
| `S3_SECRET_KEY` | **Yes** | S3 secret key used by the backend and SeaweedFS. Use a unique random value. |
| `S3_BUCKET` | No | Bucket created by SeaweedFS at startup; defaults to `familyos-media`. |
| `S3_PUBLIC_ENDPOINT` | **Yes** | URL the browser uses for presigned media uploads. For local development, use `http://localhost:8333`. It must be reachable from the browser. |
| `JWT_SECRET` | **Yes** | Signs login access tokens. Set a random value of at least 32 bytes; never reuse a production secret in development. |
| `S3_API_PORT` | No | Host port for the S3 API; defaults to `8333`. Change it if that port is already occupied, and update `S3_PUBLIC_ENDPOINT` to match. |
| `S3_CORS_ALLOWED_ORIGINS` | No | Comma-separated browser origins allowed for S3 uploads. Defaults to the three planned local frontend origins. |
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

## Run the Frontend

From PowerShell at the repository root:

```powershell
Push-Location frontend-main
npm install
npm run dev
Pop-Location
```

The app runs at `http://localhost:3000`. API-backed pages also require the backend and its database services to be running.

## Common Commands

| Command | What it does |
|---|---|
| `docker compose up --build -d` | Build and start the local services. |
| `docker compose ps` | Show service state and health. |
| `docker compose logs -f backend` | Follow backend logs. Press `Ctrl+C` to stop following. |
| `docker compose down` | Stop and remove containers; keep database, Redis, and media volumes. |
| `make health` | Check Postgres, Redis, S3 bucket readiness, and API readiness. |
| `uv run pytest` (from `backend/`) | Run backend tests. |

**Keep your data:** `docker compose down` preserves named volumes. `docker compose down -v` deletes the database, Redis data, and media files; only use it when you intentionally want a complete local reset.

## Current API Surface

The backend is private to the Compose network in the current setup. Implemented routes include:

- `GET /healthz` and `GET /readyz` for health and dependency readiness.
- `GET /api/auth/members`, `GET /api/auth/setup-status`, `POST /api/auth/setup`, `POST /api/auth/login`, `POST /api/auth/pin-login`, `POST /api/auth/pin`, `GET /api/auth/me`, and `POST /api/auth/logout` for setup and access-cookie auth.
- `POST /api/media/presign` and `POST /api/media/{asset_id}/complete` for authenticated media upload setup and completion.
- Note CRUD, block/tag routes, `GET /api/search`, `GET /api/graph`, and authenticated `GET /api/transit/eta` for the current notes/search/graph/ETA slices.
- `/api/tags/proposals` routes for parent review of persisted tag proposals.
- `/internal/agent/tools` routes for the service-token-protected read-only tool registry.

The documented APIs are an incomplete subset of the blueprint. Device pairing, refresh-token rotation, calendar, transit presets/widgets, full hybrid/faceted search, Hermes runtime, and several other domain APIs remain in development. Do not expose the backend directly to an untrusted network.

## Troubleshooting

- **A port is already in use:** change `S3_API_PORT` and make `S3_PUBLIC_ENDPOINT` use the same port, then restart with `docker compose up -d`.
- **A service is unhealthy:** inspect it with `docker compose ps` and `docker compose logs -f <service>`.
- **The backend cannot connect to Postgres or Redis:** wait for the database and Redis health checks, then inspect `docker compose logs backend`.
- **Browser upload cannot reach S3 storage:** confirm `S3_PUBLIC_ENDPOINT` is reachable from the browser and that its origin is included in `S3_CORS_ALLOWED_ORIGINS`.
- **Testcontainers cannot start:** install/start Docker Engine. Skipping that service-backed test is expected when Docker is unavailable; report it as skipped rather than treating it as a passing integration test.

## Project Layout

```text
backend/           FastAPI app, SQLAlchemy models, Alembic migrations, tests
frontend-main/     Next.js dashboard and app routes
[00]System-Blueprint.md
[01]Add-on 1 — Archify Gallery-Complete Design.md
[02]Add-on 2--- HK Transit Widget (Bus+MTR).md
[03]Add-on 3 -- Universal Search & Filter.md
docker-compose.yml  Local backend, PostgreSQL, Redis, and SeaweedFS S3 services
.env.example        Safe-to-commit environment template
Makefile            Local Compose shortcuts and health check
```

The blueprint is the implementation source of truth. Work proceeds in its build order; later product features should not be assumed available just because they appear in the roadmap.
