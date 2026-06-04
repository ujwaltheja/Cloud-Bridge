# Cloud Bridge

**Salesforce DevOps Deployment Platform** (prototype stage)

> **Important**: This is currently in **prototype mode**.  
> We have simplified the setup so you can run everything locally **without Docker**.

**Current Status**: PR 1 Foundation + Prototype Local Run Support

## Goals

- Enable safe, auditable, repeatable metadata deployments across Salesforce orgs
- Provide first-class comparison, validation, deployment orchestration, Git integration, and pipelines
- Deliver an excellent developer and release manager experience with strong observability and security

## Current State

This is currently a **working prototype**.

What exists:
- Clean Architecture foundation
- Async FastAPI with versioned API (`/api/v1/`)
- Support for both SQLite (prototype) and PostgreSQL
- Celery + structured worker observability
- Pluggable ArtifactStore (Local + MinIO/S3 ready)
- Modern React frontend
- Basic quality tooling and tests

**No real Salesforce integration or core DevOps features yet.** We are still in the foundation + prototype phase.

You can run the current code easily with just Python + Node (no Docker).

## Running Locally (Simple Prototype - No Docker)

This is the recommended way while this is in prototype stage.

### Prerequisites
- **Python 3.12 or 3.13** (strongly recommended — 3.14 currently has compatibility issues with several packages)
- Node.js 20+
- Git

### One-Time Setup

**Important:** This project works best on **Python 3.12 or 3.13**.

You are currently getting build errors because you are using **Python 3.14**, which is not yet supported by several dependencies (`asyncpg`, `pydantic-core`, etc.).

#### Recommended Steps

1. Install **Python 3.12** or **3.13** (strongly advised for now).
2. Then run:

```powershell
# 1. Environment file
copy .env.example .env

# 2. Generate Fernet key and paste it into .env
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# 3. Install backend dependencies (prototype-friendly version)
cd backend
pip install -r requirements-prototype.txt

# 4. Install frontend dependencies
cd ../frontend
npm install

# 5. Back to root
cd ..
```

> After you are on a supported Python version, you can switch to the full `requirements.txt` later.

### Workaround if you are on Python 3.14

If you get build errors for `pydantic-core` (the most common one on 3.14), try this before installing:

```powershell
# Run this in the same terminal, then install
$env:PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1

cd backend
pip install -r requirements-prototype.txt
```

This is a temporary hack. The proper solution is still to use Python 3.12 or 3.13.

### Run the Project (Two Terminals)

**Terminal 1 – Backend**
```powershell
cd backend

# First time only
alembic upgrade head

# Start API
python -m uvicorn app.main:app --reload --port 8000
```

**Terminal 2 – Frontend**
```powershell
cd frontend
npm run dev
```

### Access

- **UI**: http://localhost:5173
- **API Docs**: http://localhost:8000/api/v1/docs

---

## Manual Testing

All manual testing steps are maintained in a single living document:

**→ [docs/testing/manual-testing-guide.md](docs/testing/manual-testing-guide.md)**

### Maintenance Rule (Important)

This document follows a **"concat" / cumulative** style:

- After you finish developing any new feature or complete a PR, **append** the new testing steps at the bottom of the file.
- Do **not** delete or replace old sections.
- Use clear headings like: `## Testing Steps - [Feature Name] (PR X)`

This ensures we always have a complete, growing history of how to manually verify the entire system.

### Optional: Celery Worker (Third Terminal)

```powershell
cd backend
celery -A app.infrastructure.celery_app worker --loglevel=INFO
```

---

## Full Docker Version (Optional)

If you want the complete stack (Postgres + Redis + MinIO):

```powershell
docker compose up --build
```

For daily prototype development, the simple local method above is much faster and lighter.

## Project Structure

```
backend/
├── app/
│   ├── core/                    # Configuration, logging, DI, security
│   ├── domain/                  # Pure business entities (minimal in early PRs)
│   ├── application/modules/     # Feature modules (orgs, deployments, etc.)
│   ├── infrastructure/          # Adapters (db, artifact, celery, etc.)
│   └── api/v1/                  # Versioned API routers
├── alembic/
├── tests/
└── ...

frontend/
└── src/                         # React + TypeScript application

docker-compose.yml
```

## Technology Decisions (PR 1)

- **Async-first**: FastAPI routes and database access are async by default.
- **API Versioning**: All endpoints live under `/api/v1/`.
- **Artifact Storage**: Pluggable `ArtifactStore` with local filesystem (default) and S3/MinIO.
- **Worker Observability**: Structured JSON logging + `task_executions` table + Celery hooks from day one.
- **Quality**: Ruff + type checking + pytest + frontend linting enforced.

## Next Steps (After PR 1)

See the project plan and design document for the approved sequence (PR 2 = Auth + RBAC + Fernet encryption, PR 3 = Real Salesforce org connections + first Celery retrieve task, etc.).

## Contributing

This project follows strict production-grade standards from the first commit:
- No TODO/FIXME comments in merged code
- High test coverage on all new logic
- Clear module boundaries
- Excellent observability and error handling

---

**Built with care for Salesforce release teams who deserve better tooling.**
