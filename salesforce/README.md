# Cloud Bridge Salesforce App (LWC)

This folder contains a Salesforce DX project that adds a Lightning Web Component for:

- Generating package.xml metadata manifests directly inside Salesforce
- Triggering Cloud Bridge retrieval jobs without org connection screens
- Polling job status and exposing download links for SFDX and JSON artifacts

## What You Get

- LWC `cloudBridgeRetrieval`:
   - Metadata row builder (`type + members`) to generate valid package.xml
   - Deployment requester field for audit context
   - Direct retrieval trigger (background mode)
   - Live polling until success or failure
   - One-click download links for SFDX ZIP and JSON ZIP
- Apex API bridge:
   - `CloudBridgeApiService` for robust backend callouts
   - `CloudBridgeRetrievalController` for LWC-friendly methods
- Security/deploy artifacts:
   - Permission set `CloudBridgeUser`
   - Remote site setting `CloudBridgeBackend`
   - Custom labels for runtime config

## Quick Start

1. Create or choose a Salesforce DX org.
2. Configure custom labels:
   - CloudBridge_Base_Url
   - CloudBridge_Default_Org_Id (optional fallback)
   - CloudBridge_Api_Key (optional)
3. Confirm the backend host in Remote Site Settings (`CloudBridgeBackend`) or switch to a Named Credential value in `CloudBridge_Base_Url`.
4. Deploy:

```bash
sf project deploy start --source-dir force-app --target-org <your-org-alias>
```

5. Assign permission set:

```bash
sf org assign permset --name CloudBridgeUser --target-org <your-org-alias>
```

6. Add the `cloudBridgeRetrieval` component to an App page in Lightning App Builder.

## Runtime Flow

1. Open the LWC in Salesforce.
2. Add one or more metadata rows and generate package.xml.
3. Fill Deployment Requester (optional but recommended).
4. Click Trigger Retrieval.
5. LWC calls backend `/api/v1/retrievals?use_background=true`.
6. LWC polls `/api/v1/retrievals/{job_id}`.
7. On success, LWC opens `/api/v1/retrievals/{job_id}/download?format=sfdx` or `format=json`.

## Notes

- The LWC does not handle org connection management. It directly works with retrieval jobs.
- `org_id` can be typed in the UI or read from `CloudBridge_Default_Org_Id` label.
- Deployment Requester is sent to backend as retrieval `description` (for traceability).
- If backend requires custom auth, set `CloudBridge_Api_Key` and update backend to validate header `x-api-key`.
