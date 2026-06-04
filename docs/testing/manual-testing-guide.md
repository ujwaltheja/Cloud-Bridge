# Cloud Bridge - Manual Testing Guide

> **Purpose**: This document contains step-by-step manual testing instructions for the Cloud Bridge project.
> It is meant to be updated **cumulatively** (concatenated) as new features are developed.

---

## How to Maintain This Document

**Rule**: After completing any significant development work (new PR, major feature, or module), **append** new testing steps to this file.

- Do **not** delete or overwrite previous sections.
- Add a new section at the bottom with the format:
  - `## Testing Steps - [Feature/Module Name] (PR X)`
- Keep steps clear, numbered, and realistic for manual execution.
- Include expected results and pass/fail criteria.

This ensures we always have a growing, living record of how to manually verify the system.

---

## Current Project Status

**Phase**: Prototype / Foundation (PR 1 completed)

**What is currently testable**:
- Basic backend API health
- API documentation (Swagger)
- Example background task triggering
- Frontend loading
- SQLite database setup
- Optional Celery worker execution

---

## Testing Steps - Foundation / Prototype (PR 1)

### Prerequisites

Before starting manual testing, ensure the following are running:

1. Backend is running:
   ```powershell
   cd backend
   python -m uvicorn app.main:app --reload --port 8000
   ```

2. Frontend is running:
   ```powershell
   cd frontend
   npm run dev
   ```

3. Database migration has been applied at least once:
   ```powershell
   cd backend
   alembic upgrade head
   ```

---

### 1. Backend Health Endpoints

**Test the core health checks:**

| Endpoint | URL | Method | Expected Result |
|----------|-----|--------|-----------------|
| Liveness | `http://localhost:8000/api/v1/health` | GET | `200 OK` + JSON with `status: healthy` |
| Readiness | `http://localhost:8000/api/v1/ready` | GET | `200 OK` + JSON with `status: ready` |
| Root Health | `http://localhost:8000/health` | GET | `200 OK` + `{"status": "ok"}` |

**How to test**:
- Open each URL in a browser, or use curl/Postman.
- Verify JSON response and status code.

**Pass Criteria**: All endpoints return 200 with valid JSON.

---

### 2. API Documentation (Swagger UI)

1. Open: `http://localhost:8000/api/v1/docs`
2. Verify Swagger UI loads without errors.
3. Expand sections and try executing endpoints directly from the UI.

**Pass Criteria**:
- UI loads cleanly.
- Endpoints can be executed from the browser.

---

### 3. Trigger Example Background Task

This tests the task queuing system.

**Steps**:

1. Go to Swagger UI: `http://localhost:8000/api/v1/docs`
2. Locate `POST /api/v1/tasks/example`
3. Click **Try it out**
4. Use this request body:
   ```json
   {
     "name": "Manual Test"
   }
   ```
5. Click **Execute**

**Expected Response**:
```json
{
  "task_id": "some-uuid",
  "status": "enqueued",
  "message": "..."
}
```

**Optional (with Celery worker running)**:
- Start worker in third terminal:
  ```powershell
  cd backend
  celery -A app.infrastructure.celery_app worker --loglevel=INFO
  ```
- After triggering the task, check worker logs for:
  - `celery.task.started`
  - `example.hello_world.executing`

**Pass Criteria**: Task is accepted by the API (even if worker is not running).

---

### 4. Frontend Application

1. Open: `http://localhost:5173`
2. Verify the page loads with the title "Cloud Bridge".
3. Check that the status cards are visible (mentioning Async, API Versioning, Celery, etc.).
4. Observe the Backend Health section.

**Pass Criteria**:
- Page loads without console errors.
- UI is readable and shows expected information.

---

### 5. Database Verification (SQLite)

1. In the project root, confirm the file `cloudbridge.db` exists.
2. (Optional) Inspect tables using DB Browser for SQLite or this command:

```powershell
cd backend
python -c "
import sqlite3
conn = sqlite3.connect('../cloudbridge.db')
cursor = conn.cursor()
cursor.execute(\"SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;\")
for row in cursor.fetchall():
    print(row[0])
conn.close()
"
```

**Expected Tables**:
- `alembic_version`
- `task_executions`
- `users`

**Pass Criteria**: File exists and contains the expected tables.

---

### 6. End-to-End Smoke Test (Recommended Order)

Run these in sequence:

1. Visit Frontend → Confirm it loads.
2. Visit API Docs → Confirm Swagger is working.
3. Call `/api/v1/health` → Should succeed.
4. Trigger example task via Swagger.
5. (Optional) Start Celery worker and verify task execution in logs.
6. Check `cloudbridge.db` file exists.

---

## Notes for Future Updates

When adding new features (e.g., Salesforce Org Connection, Metadata Retrieval, Deployment, etc.), append new sections below using this format:

```markdown
## Testing Steps - [Feature Name] (PR X)

### Prerequisites
...

### Test Cases
1. ...
```

---

**Last Updated**: 2026-06-01 (Org Management + Start of Metadata Retrieval)

---

## Update Log (Cumulative)

- **2026-06-01**: Initial manual testing steps for PR 1 Foundation / Prototype added.
- **2026-06-01**: Started "Salesforce Org Management" slice (first major end-to-end feature). New tables, models, schemas, service, and API endpoints created. Testing steps will be appended once this slice reaches 100% testable state.

---

## Testing Steps - Salesforce Org Management (Current Slice)

### Prerequisites
- Backend + Frontend running locally (`uvicorn` + `npm run dev`)
- A Salesforce Sandbox + Connected App configured with:
  - OAuth scopes: `api` + `refresh_token`
  - For JWT: Certificate uploaded + "Use Digital Signature" enabled

### 1. Add Organization via JWT (Fully Working)

1. Open `http://localhost:5173`
2. Click **+ Add Org**
3. Choose **JWT (Server-to-Server)**
4. Fill:
   - Name
   - Org Type → `sandbox`
   - Client ID (Consumer Key)
   - Username
   - Paste the full private key (PEM)
5. Click **Add Organization**

**Expected**: The org appears in the list with `success` status (it automatically fetches the access token).

### 2. Test Connection

Click **Test Connection** on any org row.

**Expected**: Alert shows success or a clear error from Salesforce.

### 3. Delete Org

Click the **Delete** button on an org.

### 4. Web OAuth Flow (End-to-End)

1. In the Add Org form, switch to **Web OAuth**
2. Enter Name, Org Type, and Client ID
3. Click **Start OAuth Login**
4. You will be redirected to Salesforce login
5. After logging in and approving, you should be redirected back and the org should show as connected.

---

**Status**: This slice is now in a **testable end-to-end state** (JWT fully working + OAuth flow complete from frontend to backend).

**Last Updated in Guide**: 2026-06-01

---

## Testing Steps - Metadata Retrieval (New Slice - In Progress)

### Prerequisites
- At least one Salesforce org connected via the Orgs page (from previous slice)
- Backend and frontend running

### 1. Trigger a Metadata Retrieval from an Org

1. Go to the **Retrievals** page (or use the Orgs page if integrated).
2. Select a connected org.
3. Use the default or custom `package.xml`.
4. Click **Start Retrieval**.

**Expected**:
- A new job appears in the list with status `running` → `success`.
- An `artifact_key` is generated (e.g. `retrievals/{job_id}/result.json`).

### 2. View Retrieval Results

- Check the list of retrieval jobs.
- Verify that the artifact was saved (can be inspected via local filesystem or MinIO console at http://localhost:9001).

### 3. Error Cases to Test

- Try retrieving from an org with no valid access token.
- Use invalid package.xml syntax.

---

**Next**: Full detailed testing steps appended below.

---

## Testing Steps - Metadata Retrieval (Complete Slice)

### Prerequisites
- At least one Salesforce org successfully connected (via Org Management slice)
- Backend and frontend running locally
- (Optional) Celery worker running for background jobs

### 1. Trigger a Metadata Retrieval

**From Retrievals Page:**
1. Go to **Retrievals** page.
2. Select a connected org.
3. (Optional) Customize the `package.xml`.
4. Click **Start Retrieval**.

**From Orgs Page (quick action):**
1. On the Orgs list, click **Retrieve Metadata** on any org.
2. This should redirect or open the retrieval flow.

**Expected Results:**
- A new job appears with status `queued` or `running`.
- After a few seconds it should move to `success`.
- An `artifact_key` should be visible (e.g. `retrievals/xxx/result.json`).

### 2. View Retrieval Results

1. Click **View Artifact** on a successful job.
2. For prototype, it shows the storage location.
3. In a full implementation, this would allow downloading the actual package.

### 3. Test Error Scenarios

- Try retrieving from an org that has no valid access token.
- Submit invalid package.xml.
- Check that proper error messages are shown.

### 4. Background vs Synchronous

- Test with `use_background=true` (if exposed) — should queue to Celery.
- Test synchronous mode (default in prototype) — runs immediately.

---

**Slice Status**: Metadata Retrieval is now a **complete, testable end-to-end feature** (with artifact viewing + background support).

**Last Updated in Guide**: 2026-06-01

---

## Testing Steps - Comparison Engine (Current Slice)

### What is Implemented
- Create comparison between two retrieval jobs
- Basic diff calculation (added/removed Apex classes)
- Results stored in ArtifactStore
- Basic UI to trigger and view comparison

### Manual Testing

1. Complete at least two successful retrievals (from previous slice).
2. Go to **Comparisons** page.
3. Paste the two Retrieval IDs as Source and Target.
4. Click **Run Comparison**.
5. Verify the summary shows added/removed counts.
6. Use the "Compare" button from the Retrievals page to quickly start a comparison.

---

**Next slices** (Deployment + AI) will be added here once developed.

---

## Deployment Engine (New Slice - Started)

Basic model, migration, service, API, and a simple Deployments frontend page have been created.

This slice allows recording deployments linked to retrievals or comparisons.

Full detailed testing steps will be appended as the slice matures.

### Current Manual Testing for Deployment

1. Go to the **Deployments** page.
2. Select an org and optionally a successful retrieval.
3. Choose a deployment type and create the record.
4. Use the status advancement buttons (Start Validating → Deploy → Mark Success) to simulate a deployment lifecycle.
5. Verify the history list updates with correct colors and status.

**From other pages (Integration test):**
- From the **Retrievals** page, click **Deploy** on a successful job → it should help pre-fill the deployment form.

**Note**: (Older note) Real execution (validation/deploy/test runs via direct sf CLI) has now been implemented — see the later "Real Deployments / Validation + Apex Test Runs" section for current testing steps.

---

**Comparison and Deployment slices have received another aggressive push and are now at a significantly more complete and usable state.**

### Comparison Engine - Closer to 100%
- Much stronger UI with summary cards + clean added/removed lists.
- "View Full Diff Artifact" functionality improved.
- Direct "Compare" buttons from Retrievals page.
- Dropdown selection of successful retrievals for easy comparisons.
- Better overall polish.

### Deployment Engine - Further Accelerated
- Status advancement buttons for realistic workflow.
- Direct "Deploy" buttons from Retrievals page.
- Improved form and history with better status colors.
- Better integration across slices.

---

## Latest Aggressive Development (Comparison + Deployment)

### Comparison Engine - Major Steps Toward 100%
- Significantly improved UI: Summary cards + clean added/removed lists.
- "View Full Diff Artifact" functionality enhanced (attempts to load real content).
- Direct "Compare" buttons added from the Retrievals page.
- Dropdown selection of successful retrievals for much easier comparisons.
- Better overall polish and integration.

### Deployment Engine - Accelerated Further
- Status advancement buttons added for realistic demo workflow.
- Direct "Deploy" buttons from the Retrievals page (strong cross-slice integration).
- Improved Deployments page with better form, history, and status presentation.
- Backend support for status updates strengthened.
- Ability to link deployments to retrievals (and soon comparisons).

Both slices have been brought up aggressively in parallel. They are now much closer to the quality and completeness of the earlier slices (Org Management and Metadata Retrieval).

Full detailed testing steps for both will continue to be appended as they reach true 100% completion.

---

## Latest Aggressive Development Push (Comparison + Deployment)

### Comparison Engine - Final Stretch Toward 100%
- Major UI improvements: Beautiful summary cards + clean lists of added/removed items.
- "View Full Diff Artifact" now attempts to load and display real stored content.
- Direct "Compare" buttons from the Retrievals page for seamless workflow.
- Dropdown selection of successful retrievals (much better UX).

### Deployment Engine - Significantly Accelerated
- Status simulation buttons added (Pending → Validating → Deploying → Success).
- "Deploy this Retrieval" buttons added directly from the Retrievals page.
- Improved Deployments page with better form, history, and status colors.
- Backend support for status updates strengthened.

Both slices have received substantial development in this push to bring them closer to the quality level of the earlier slices (Org Management & Metadata Retrieval).

Full detailed testing steps for Comparison and Deployment will be appended as they reach true completion.

### Current Status

- Comparison Engine has improved diff visualization (added/removed lists with counts).
- "Compare" button available directly from Retrievals page.
- Deployment Engine has basic creation + history UI.

---

**Update Log (Cumulative)**

- **2026-06-01**: Comparison Engine significantly improved (better UI diff display, artifact viewing, cross-page integration from Retrievals).
- **2026-06-01**: Deployment Engine foundation + basic UI created.
- **2026-06-01**: Aggressive development across Comparison + Deployment + polish on previous slices.
- Basic model and API structure created.
- Can create a comparison between two retrieval IDs.
- Simple diff on ApexClass names is implemented.

### Manual Testing (Early)
1. Take two successful Retrieval IDs from the previous slice.
2. POST to `/api/v1/comparisons` with both IDs.
3. Check the returned diff summary (added/removed counts).

Full detailed testing steps will be appended once this slice reaches a more complete state.

---

## Update Log (Cumulative)

- **2026-06-01**: Initial manual testing steps for PR 1 Foundation / Prototype added.
- **2026-06-01**: Org Management slice completed + testing steps added.
- **2026-06-01**: Metadata Retrieval slice completed + testing steps added.
- **2026-06-01**: Comparison Engine slice started (model + basic API + frontend page).

---

## Testing Steps - Real Deployments / Validation + Apex Test Runs (Direct sf CLI)

**Implementation**: Deployments now execute for real using direct Salesforce CLI calls (`sf project deploy validate` or `sf project deploy start --dry-run` + `--test-level` + `--tests`). Modern sf CLI (2.133+) uses --dry-run (or the validate subcommand) instead of the old --check-only flag.

This matches:
- Salesforce CLI official reference (project deploy start/validate/quick)
- Metadata API `deploy(..., DeployOptions{checkOnly, testLevel, runTests})` (what Workbench uses)
- Full support for NoTestRun / RunLocalTests / RunSpecifiedTests / RunAllTestsInOrg

MCP path is still available for agentic/generic tool use; core deployment engine and agent/deploy with check_only now prefer the direct path for validation fidelity.

### Prerequisites
- Backend + Frontend running
- At least one connected Salesforce org (sandbox recommended for testing)
- Salesforce CLI (`sf`) installed on the machine running the backend (npm i -g @salesforce/cli)
- (Optional) A prior successful metadata retrieval (so Deployments can auto-unpack source.zip artifact)

### 1. Trigger a Validate-Only (check-only) Deployment
1. Go to **Deployments** page.
2. Select org + (recommended) a successful Retrieval.
3. Deployment type: "Validate Only (check-only)"
4. Check "Check Only / Validate" (or it derives from type).
5. Choose test level e.g. **RunLocalTests** (or RunAllTestsInOrg).
6. (If RunSpecifiedTests) enter comma-separated test class names.
7. Click **Start Validation / Deploy + Tests**

**Expected**:
- New deployment row appears with status progressing: pending → validating/running → success (or failed with error).
- `salesforce_deployment_id` populated with the AsyncResult/Deploy job ID from Salesforce.
- In logs: `sf project deploy validate ... --test-level RunLocalTests` (or `start --dry-run` when NoTestRun is selected).
- No actual metadata changes committed to the target org.

### 2. Full Deploy with Tests
Same steps but choose "Full Deploy", uncheck pure check-only if desired, pick test level.

Uses `sf project deploy start --test-level ...` (real deploy, no dry-run/validate).

### 3. Quick Deploy (after validation)
- After a successful validate (which produces a job ID), create a new Deployment record of type **Quick Deploy**.
- If the record carries the prior `salesforce_deployment_id`, the backend will automatically use `sf project deploy quick --job-id <id>`.
- (Current UI may require creating the record with the ID already known / via API for full quick flow.)

### 4. From Retrievals Page Integration
- Successful retrievals should offer "Deploy" actions that pre-populate the Deployments form (or call the API directly with retrieval_id + options).
- The direct deploy will attempt to unpack the retrieval's `source.zip` artifact into a temp project dir and deploy from it.

### 5. Error / Edge Cases to Verify
- Invalid test classes for RunSpecifiedTests → clear error surfaced.
- NoTestRun on a validate (routes to `start --dry-run --test-level NoTestRun`; the validate subcommand does not allow NoTestRun).
- Deploying from org without proper "Modify Metadata Through Metadata API Functions" perm → auth/perm error from CLI.
- Long running: status moves to success/failed after CLI completes (wait ~10-30min for big deploys/tests).

**Status**: Real end-to-end validation, deployment, and test run execution is now wired (no more pure simulation for new records).

**Last Updated**: (current)

---

**Note for future**: Add polling / SSE for live deploy status, "Cancel", "Quick Deploy" selector UI, and report download (sf project deploy report).
