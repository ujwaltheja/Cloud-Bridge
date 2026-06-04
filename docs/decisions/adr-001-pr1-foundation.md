# ADR-001: PR 1 Foundation Decisions

**Date**: 2026-06-01  
**Status**: Accepted  
**PR**: 1

## Context

We needed to establish a production-grade, long-term maintainable foundation for Cloud Bridge before implementing any Salesforce-specific or domain logic. The following five priorities were explicitly called out by the product owner before any code was written:

1. Async architecture
2. API versioning
3. Artifact storage (MinIO)
4. Module boundaries
5. Worker observability

## Decisions

### 1. Async Architecture
- Use async FastAPI routes and async SQLAlchemy 2.0 (asyncpg) from day one.
- Celery tasks remain primarily synchronous (pragmatic for sf CLI and heavy external I/O).
- All ports are designed to support async implementations.

### 2. API Versioning
- All routes live under `/api/v1/` from the first commit.
- OpenAPI docs are served under the versioned path.
- No unversioned production routes are allowed.

### 3. Artifact Storage (MinIO)
- Introduced an `ArtifactStore` port with two implementations:
  - `LocalFilesystemArtifactStore` (default for dev speed)
  - `S3ArtifactStore` (works with MinIO and real S3)
- MinIO is included in `docker-compose.yml` from PR 1.
- The abstraction allows future transparent migration to object storage.

### 4. Module Boundaries
- Hybrid structure: Clean Architecture layers + explicit feature modules under `application/modules/` and `infrastructure/adapters/`.
- Strict `__init__.py` exports and import discipline enforced from the beginning.

### 5. Worker Observability
- Structured logging with `structlog` + correlation IDs.
- `task_executions` table created in the first migration.
- Celery signals (`prerun`, `postrun`, `success`, `failure`) write both logs and DB records.

## Consequences

**Positive**
- The system is positioned for high concurrency on the API side.
- Worker behavior is observable even without full OpenTelemetry.
- Artifact storage can evolve without touching business logic.
- Future developers inherit strong conventions instead of a ball of mud.

**Negative / Trade-offs**
- Slightly more complex bootstrap than a "hello world" FastAPI app.
- Async SQLAlchemy requires discipline with session management.
- Celery observability adds one extra table early.

## Alternatives Considered

- Using sync SQLAlchemy + `run_in_executor` → Rejected (we want native async).
- Starting with only local filesystem for artifacts → Rejected after user explicitly asked to elevate MinIO.
- Deferring worker observability until later PRs → Rejected due to explicit priority.

## References

- Design document 208c7127 (Key Decisions + PR Plan)
- Living plan.md in session directory
