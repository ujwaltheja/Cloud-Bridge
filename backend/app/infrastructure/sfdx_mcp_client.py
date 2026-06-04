"""
SFDX MCP Client

Embeds the Salesforce DX MCP Server (@salesforce/mcp) directly inside Cloud Bridge.
Manages the MCP server subprocess lifecycle, bridges DB-stored auth tokens into
SFDX's auth store, and exposes async Python methods for each MCP tool call.

Architecture:
  1. SFDXAuthBridge  - writes a temp SFDX auth URL file, runs 'sf org login sfdx-url'
                       so the MCP server can resolve the org by alias
  2. SFDXMCPProcess  - starts 'npx @salesforce/mcp@latest' as a child process,
                       communicates via JSON-RPC 2.0 over stdin/stdout
  3. SFDXMCPClient   - high-level async API: retrieve_metadata(), deploy_metadata(),
                       run_apex_tests(), list_orgs(), call_tool()
"""

import asyncio
import contextlib
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from collections.abc import AsyncGenerator
from typing import Any

logger = logging.getLogger("cloudbridge.sfdx_mcp")


# ---------------------------------------------------------------------------
# Auth bridge: inject a Salesforce org into the local SFDX auth store
# ---------------------------------------------------------------------------

async def _register_org_with_sfdx(
    access_token: str,
    instance_url: str,
    alias: str,
) -> str:
    """
    Authorize the org alias in the local Salesforce CLI using the official
    access-token login method (recommended for tokens from OAuth/JWT flows).

    Uses SF_ACCESS_TOKEN env var + `sf org login access-token --instance-url ...`
    per Salesforce CLI docs. This avoids fragile sfdx-url force:// hacks
    that can hang or timeout (especially on Windows or with access-token-only).

    See: https://developer.salesforce.com/docs/atlas.en-us.sfdx_dev.meta/sfdx_dev/sfdx_dev_auth_existing_access_token.htm
    """
    sf_exe = shutil.which("sf") or shutil.which("sfdx")
    if not sf_exe:
        # Common Windows install location as last resort
        win_sf = r"C:\Program Files\sf\bin\sf.CMD"
        if sys.platform == "win32" and os.path.exists(win_sf):
            sf_exe = win_sf
        else:
            raise RuntimeError(
                "Salesforce CLI ('sf' or 'sfdx') not found on PATH. "
                "Install it with: npm install -g @salesforce/cli  or from https://developer.salesforce.com/tools/sfdxcli"
            )

    # Ensure instance_url has protocol
    inst_url = instance_url if instance_url.startswith(("http://", "https://")) else f"https://{instance_url}"

    try:
        # On Windows, .cmd must run through cmd /c
        if sys.platform == "win32":
            cmd = ["cmd", "/c", sf_exe, "org", "login", "access-token",
                   "--instance-url", inst_url, "--alias", alias, "--no-prompt", "--json"]
        else:
            cmd = [sf_exe, "org", "login", "access-token",
                   "--instance-url", inst_url, "--alias", alias, "--no-prompt", "--json"]

        env = os.environ.copy()
        env["SF_ACCESS_TOKEN"] = access_token

        def run_subprocess():
            proc = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=120,  # longer; first-run sf can be slow to initialize
                check=False,
                env=env,
            )
            return proc.stdout, proc.stderr, proc.returncode

        stdout, stderr, returncode = await asyncio.to_thread(run_subprocess)

        out = stdout.decode(errors="replace")
        err = stderr.decode(errors="replace")
        if returncode != 0:
            logger.warning("sf org login access-token failed (alias=%s, rc=%s): %s | %s", alias, returncode, err[:500], out[:300])
            # Non-fatal: token may already be usable or subsequent commands may succeed
        else:
            logger.info("sf org login access-token succeeded for alias=%s", alias)
            # Optional: log brief success info from json if present
            try:
                j = json.loads(out)
                if j.get("result", {}).get("orgId"):
                    logger.debug("Authorized orgId: %s", j["result"]["orgId"])
            except Exception:
                pass
    except Exception as exc:  # includes TimeoutError, subprocess errors
        logger.warning("sf org login access-token for alias=%s failed/ timed out: %s — continuing (CLI commands may still work if previously authorized)", alias, exc)

    return alias


# ---------------------------------------------------------------------------
# MCP JSON-RPC 2.0 subprocess session
# ---------------------------------------------------------------------------

class SFDXMCPProcess:
    """
    Manages a single 'npx @salesforce/mcp@latest' child process.
    Communicates over stdin/stdout using the MCP JSON-RPC 2.0 protocol.
    """

    def __init__(self, org_alias: str, toolsets: str = "orgs,metadata,data,testing,users"):
        self.org_alias = org_alias
        self.toolsets = toolsets
        self._proc: asyncio.subprocess.Process | None = None
        self._req_id = 0
        self._initialized = False
        self._stderr_task: asyncio.Task | None = None

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, *_):
        await self.stop()

    async def start(self):
        """Spawn the MCP server process."""
        # Windows asyncio subprocess with pipes is not supported
        if sys.platform == "win32":
            raise NotImplementedError(
                "SFDX MCP integration is not supported on Windows due to asyncio limitations. "
                "The system will automatically fall back to SOQL-based metadata retrieval."
            )
        
        logger.info("Starting SFDX MCP server for org alias: %s", self.org_alias)

        cmd = ["npx", "-y", "@salesforce/mcp@latest",
               "--orgs", self.org_alias,
               "--toolsets", self.toolsets,
               "--no-telemetry", "--allow-non-ga-tools"]

        self._proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        # Drain stderr in the background to prevent buffer-full deadlock on Windows
        self._stderr_task = asyncio.create_task(self._drain_stderr())

        await self._initialize()

    async def _drain_stderr(self):
        """Background task: read and log stderr so the pipe never fills up."""
        try:
            while self._proc and self._proc.returncode is None:
                line = await self._proc.stderr.readline()
                if not line:
                    break
                text = line.decode(errors="replace").rstrip()
                if text:
                    logger.debug("MCP stderr: %s", text)
        except Exception:
            pass

    async def stop(self):
        """Terminate the MCP server process."""
        if self._stderr_task:
            self._stderr_task.cancel()
            self._stderr_task = None
        if self._proc and self._proc.returncode is None:
            try:
                self._proc.stdin.close()
                await asyncio.wait_for(self._proc.wait(), timeout=5)
            except Exception:
                self._proc.kill()
        self._proc = None
        self._initialized = False

    def _next_id(self) -> int:
        self._req_id += 1
        return self._req_id

    async def _send(self, message: dict) -> None:
        """Write a JSON-RPC message to the process stdin."""
        payload = json.dumps(message) + "\n"
        self._proc.stdin.write(payload.encode())
        await self._proc.stdin.drain()

    async def _recv(self, timeout: float = 60.0) -> dict:
        """Read one JSON-RPC message from stdout. Skips non-JSON garbage."""
        while True:
            line = await asyncio.wait_for(
                self._proc.stdout.readline(), timeout=timeout
            )
            if not line:
                raise EOFError("MCP server closed stdout unexpectedly")
            try:
                line_str = line.decode('utf-8').strip()
                if not line_str:
                    continue
                return json.loads(line_str)
            except json.JSONDecodeError:
                logger.debug("Skipped non-JSON line from MCP stdout: %s", line_str)
                continue

    async def _initialize(self):
        """Perform the MCP protocol handshake."""
        req_id = self._next_id()
        await self._send({
            "jsonrpc": "2.0",
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "cloudbridge", "version": "1.0.0"},
            },
            "id": req_id,
        })
        resp = await self._recv(timeout=120)
        logger.debug("MCP initialize response: %s", resp)

        # Send initialized notification
        await self._send({
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {},
        })
        self._initialized = True
        logger.info("SFDX MCP server initialized")

    async def call_tool(self, tool_name: str, arguments: dict[str, Any], timeout: float = 120.0) -> Any:
        """
        Call an MCP tool and return its result content.
        Raises RuntimeError on error responses.
        """
        if not self._initialized:
            raise RuntimeError("MCP process not initialized — call start() first")

        req_id = self._next_id()
        await self._send({
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments,
            },
            "id": req_id,
        })

        # Collect responses, skipping any notifications (no "id" field)
        while True:
            resp = await self._recv(timeout=timeout)
            if resp.get("id") == req_id:
                break
            # It's a notification — log and continue waiting
            logger.debug("MCP notification: %s", resp.get("method"))

        if "error" in resp:
            raise RuntimeError(f"MCP tool '{tool_name}' error: {resp['error']}")

        result = resp.get("result", {})
        # MCP returns content as a list of {type, text} blocks
        content = result.get("content", [])
        if content:
            texts = [c.get("text", "") for c in content if c.get("type") == "text"]
            combined = "\n".join(texts)
            # Try to parse as JSON; return raw string if not parseable
            try:
                return json.loads(combined)
            except (json.JSONDecodeError, ValueError):
                return combined
        return result

    async def list_tools(self) -> list:
        """List all available MCP tools."""
        req_id = self._next_id()
        await self._send({"jsonrpc": "2.0", "method": "tools/list", "id": req_id})
        while True:
            resp = await self._recv(timeout=30)
            if resp.get("id") == req_id:
                break
        return resp.get("result", {}).get("tools", [])


# ---------------------------------------------------------------------------
# SFDX project helpers
# ---------------------------------------------------------------------------

def _get_default_project_dir() -> str:
    """Return the SFDX project directory (env var SFDX_PROJECT_DIR or OS temp)."""
    env_dir = os.environ.get("SFDX_PROJECT_DIR")
    if env_dir:
        return env_dir
    return os.path.join(tempfile.gettempdir(), "cloudbridge-sfdx")


def _ensure_sfdx_project(project_dir: str) -> None:
    """
    Create a minimal SFDX project scaffold in *project_dir* if one does not
    already exist.  Every MCP tool requires a ``directory`` param that points
    to a folder containing a valid ``sfdx-project.json``.
    """
    os.makedirs(project_dir, exist_ok=True)
    sfdx_json = os.path.join(project_dir, "sfdx-project.json")
    if not os.path.exists(sfdx_json):
        config = {
            "packageDirectories": [{"path": "force-app", "default": True}],
            "name": "cloudbridge",
            "namespace": "",
            "sourceApiVersion": "62.0",
        }
        with open(sfdx_json, "w", encoding="utf-8") as fh:
            json.dump(config, fh, indent=2)
        os.makedirs(
            os.path.join(project_dir, "force-app", "main", "default"),
            exist_ok=True,
        )
        logger.info("Created SFDX project scaffold at %s", project_dir)


# Special token sent by the UI only in "Complete Backup" mode.
# Backend treats an *exact* match as "generate full manifest via sf project generate manifest --from-org"
# (the Salesforce-recommended way for a true complete org backup). Using an exact non-XML token
# (instead of a substring check against a fake XML) ensures a user-supplied custom package.xml
# can never accidentally trigger the complete/full backup path.
COMPLETE_ORG_BACKUP_SENTINEL = "__CLOUD_BRIDGE_COMPLETE_ORG_BACKUP__"


def _run_sf_generate_manifest(
    sf_exe: str, alias: str, output_dir: str, project_dir: str
) -> dict[str, Any]:
    """
    Synchronous helper: run `sf project generate manifest --from-org <alias> --output-dir <dir>`.
    Returns dict with stdout, stderr, returncode.
    This is the Salesforce-recommended way to get a complete package.xml for full org backup
    (it enumerates actual members for types that don't support *, includes folders for reports etc.).
    """
    if sys.platform == "win32":
        cmd = [
            "cmd", "/c", sf_exe, "project", "generate", "manifest",
            "--from-org", alias,
            "--output-dir", output_dir,
            "--json",
        ]
    else:
        cmd = [
            sf_exe, "project", "generate", "manifest",
            "--from-org", alias,
            "--output-dir", output_dir,
            "--json",
        ]

    env = os.environ.copy()
    # For very large orgs, users can tune: export SF_LIST_METADATA_BATCH_SIZE=3
    # env.setdefault("SF_LIST_METADATA_BATCH_SIZE", "5")

    logger.info("Running manifest generation: %s (cwd=%s)", " ".join(cmd), project_dir)

    proc = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=600,  # 10 min generous for describe/listMetadata on large orgs
        check=False,
        cwd=project_dir,
        env=env,
    )
    return {
        "stdout": proc.stdout.decode(errors="replace"),
        "stderr": proc.stderr.decode(errors="replace"),
        "returncode": proc.returncode,
    }


def _write_manifest_xml(metadata_types: list, project_dir: str) -> str:
    """
    Write (or overwrite) ``manifest/package.xml`` inside *project_dir* for the
    given metadata types.  Returns the absolute path to the manifest file.

    Each entry in *metadata_types* can be:
    - ``"TypeName"``           → retrieves all members (wildcard ``*``)
    - ``"TypeName:MemberName"`` → retrieves a specific member
    """
    types_map: dict[str, list] = {}
    for entry in metadata_types:
        if ":" in entry:
            type_name, member = entry.split(":", 1)
        else:
            type_name, member = entry, "*"
        types_map.setdefault(type_name, []).append(member)

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<Package xmlns="http://soap.sforce.com/2006/04/metadata">',
    ]
    for type_name in sorted(types_map):
        lines.append("    <types>")
        for member in sorted(types_map[type_name]):
            lines.append(f"        <members>{member}</members>")
        lines.append(f"        <name>{type_name}</name>")
        lines.append("    </types>")
    lines.append("    <version>62.0</version>")
    lines.append("</Package>")

    manifest_dir = os.path.join(project_dir, "manifest")
    os.makedirs(manifest_dir, exist_ok=True)
    manifest_path = os.path.join(manifest_dir, "package.xml")
    with open(manifest_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    logger.debug("Wrote manifest to %s (%d types)", manifest_path, len(types_map))
    return manifest_path


async def retrieve_metadata_direct(
    access_token: str,
    instance_url: str,
    alias: str,
    package_xml: str | None = None,
    project_dir: str | None = None,
    wait_minutes: int = 15,
) -> dict[str, Any]:
    """
    Perform a real SFDX metadata retrieve using the Salesforce CLI directly
    (sf project retrieve start --manifest). This is the robust, cross-platform
    (including Windows) path that does NOT depend on the @salesforce/mcp server
    or its asyncio subprocess limitations.

    Follows official steps:
      1. Ensure a valid sfdx-project.json scaffold exists.
      2. Authorize alias via sf org login access-token (using provided token).
      3. Write the caller's package.xml (supports complete backup or any custom
         manifest the user supplies via UI or API).
         If the exact magic token COMPLETE_ORG_BACKUP_SENTINEL is passed (only from
         "Complete Backup" UI), we first run `sf project generate manifest --from-org`
         (Salesforce docs recommended method) to produce a real full-org manifest.
      4. Run `sf project retrieve start --manifest ... --target-org <alias> --json --wait N`
      5. Capture result + archive the retrieved source tree as a zip artifact.

    Returns a dict with keys: success, result (CLI json), files (list), project_dir, etc.
    The caller is responsible for zipping/storing the on-disk result for downloads.
    """
    proj = project_dir or _get_default_project_dir()
    _ensure_sfdx_project(proj)

    # 1+2. Auth (will fall back to existing if token login is slow/non-fatal)
    await _register_org_with_sfdx(access_token, instance_url, alias)

    # 3. Write the provided package.xml (or a minimal default)
    #    Special case: if COMPLETE sentinel, use Salesforce CLI's `sf project generate manifest --from-org`
    #    (the documented way to get a *complete* org backup manifest, not a hand-maintained subset).
    manifest_dir = os.path.join(proj, "manifest")
    os.makedirs(manifest_dir, exist_ok=True)
    manifest_path = os.path.join(manifest_dir, "package.xml")

    # Locate sf early (needed for both generate and retrieve)
    sf_exe = shutil.which("sf") or shutil.which("sfdx")
    if not sf_exe:
        win_sf = r"C:\Program Files\sf\bin\sf.CMD"
        if sys.platform == "win32" and os.path.exists(win_sf):
            sf_exe = win_sf
        else:
            raise RuntimeError("Salesforce CLI not found. Install @salesforce/cli.")

    effective_package_xml = package_xml or ""
    if (package_xml or "").strip() == COMPLETE_ORG_BACKUP_SENTINEL:
        logger.info("Complete org backup sentinel token detected — generating full manifest with sf project generate manifest --from-org %s", alias)
        gen = await asyncio.to_thread(
            _run_sf_generate_manifest, sf_exe, alias, manifest_dir, proj
        )
        if gen["returncode"] != 0:
            err_preview = (gen["stderr"] or gen["stdout"] or "unknown error")[:800]
            logger.error("sf project generate manifest failed (rc=%s): %s", gen["returncode"], err_preview)
            return {
                "success": False,
                "error": f"Complete manifest generation failed: {err_preview}",
                "project_dir": proj,
                "manifest": manifest_path,
                "stdout": gen["stdout"][:2000],
                "stderr": gen["stderr"][:2000],
                "returncode": gen["returncode"],
            }
        # sf wrote the real full manifest to manifest/package.xml
        if os.path.exists(manifest_path):
            try:
                with open(manifest_path, "r", encoding="utf-8") as fh:
                    effective_package_xml = fh.read()
                logger.info(
                    "Generated complete manifest (%d bytes, ~%d <types> entries)",
                    len(effective_package_xml),
                    effective_package_xml.count("<types>"),
                )
            except Exception as read_err:
                logger.warning("Generated manifest written but could not re-read it: %s", read_err)
                effective_package_xml = ""
        else:
            logger.warning("Generate claimed success but %s not found; will fall back to minimal.", manifest_path)

    if effective_package_xml and effective_package_xml.strip():
        with open(manifest_path, "w", encoding="utf-8") as fh:
            fh.write(effective_package_xml)
        logger.info("Wrote package.xml to %s (%d bytes)", manifest_path, len(effective_package_xml))
    else:
        # Minimal safe default (Apex only) if none provided
        default = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<Package xmlns="http://soap.sforce.com/2006/04/metadata">\n'
            '  <version>62.0</version>\n'
            '  <types><members>*</members><name>ApexClass</name></types>\n'
            '</Package>'
        )
        with open(manifest_path, "w", encoding="utf-8") as fh:
            fh.write(default)
        logger.warning("No package_xml supplied — wrote minimal default to %s", manifest_path)

    # 4. Run the retrieve (official command per Salesforce docs)
    if sys.platform == "win32":
        cmd = [
            "cmd", "/c", sf_exe, "project", "retrieve", "start",
            "--manifest", manifest_path,
            "--target-org", alias,
            "--json",
            "--wait", str(wait_minutes),
        ]
    else:
        cmd = [
            sf_exe, "project", "retrieve", "start",
            "--manifest", manifest_path,
            "--target-org", alias,
            "--json",
            "--wait", str(wait_minutes),
        ]

    logger.info("Running direct retrieve: %s (cwd=%s, wait=%smin)", " ".join(cmd), proj, wait_minutes)

    def run_retrieve_cmd():
        env = os.environ.copy()
        # Provide the token directly for the retrieve command. The login step is still
        # performed to ensure the alias is registered in the local sf auth store, but
        # setting SF_ACCESS_TOKEN makes the operation more robust on cases where the
        # login access-token partially fails (e.g. AuthCodeUsernameRetrievalError seen
        # in some orgs/tokens) but the token is still valid for Metadata API ops.
        env["SF_ACCESS_TOKEN"] = access_token
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=max(180, wait_minutes * 70),  # generous; retrieves can be slow
            check=False,
            cwd=proj,
            env=env,
        )
        return proc.stdout, proc.stderr, proc.returncode

    try:
        stdout, stderr, rc = await asyncio.to_thread(run_retrieve_cmd)
    except Exception as e:
        logger.exception("Direct retrieve subprocess failed")
        return {"success": False, "error": str(e), "project_dir": proj, "manifest": manifest_path}

    out = stdout.decode(errors="replace")
    err = stderr.decode(errors="replace")

    cli_result: Any
    try:
        cli_result = json.loads(out) if out.strip() else {"raw_stdout": out}
    except Exception:
        cli_result = {"raw_stdout": out, "stderr": err[:2000], "returncode": rc}

    success = rc == 0

    # 5. Walk the retrieved files (source is now on disk in force-app/...)
    files: list[dict[str, Any]] = []
    force_app_root = os.path.join(proj, "force-app")
    if os.path.isdir(force_app_root):
        for root, _dirs, filenames in os.walk(force_app_root):
            for fn in filenames:
                fp = os.path.join(root, fn)
                try:
                    rel = os.path.relpath(fp, proj).replace("\\", "/")
                    sz = os.path.getsize(fp)
                    files.append({"name": rel, "size": sz})
                except Exception:
                    pass

    logger.info("Direct retrieve completed: success=%s, files=%d, rc=%s", success, len(files), rc)
    if err:
        logger.debug("sf retrieve stderr (first 800): %s", err[:800])

    return {
        "success": success,
        "result": cli_result,
        "files": files,
        "files_count": len(files),
        "project_dir": proj,
        "manifest": manifest_path,
        "stdout": out[:2000] if not success else "",
        "stderr": err[:2000] if err else "",
        "returncode": rc,
    }


# ---------------------------------------------------------------------------
# Direct (non-MCP) helpers for package.xml builder: list types + list members
# These power the UI "package create" / custom manifest builder.
# Follow same pattern as retrieve: ensure project + sf auth bridge + direct sf cmd --json
# ---------------------------------------------------------------------------


async def list_metadata_types_direct(
    access_token: str,
    instance_url: str,
    alias: str,
    project_dir: str | None = None,
) -> list[dict[str, Any]]:
    """
    List all metadata types enabled in the org using
    `sf org list metadata-types --target-org <alias> --json`.

    Note: the CLI returns {status, result: {metadataObjects: [...] } } (not a flat result array).

    Returns a list of type info dicts (e.g. {"xmlName": "ApexClass", "directoryName": "classes", "inFolder": false, ...}).
    Used to populate the "select component type" dropdown in the package builder.
    On auth/permission failure (very common: the org user needs "Modify Metadata Through Metadata API Functions"),
    returns a list containing one {"error": "...", "xmlName": "__ERROR__"} entry so callers can surface the real reason.
    """
    proj = project_dir or _get_default_project_dir()
    _ensure_sfdx_project(proj)
    await _register_org_with_sfdx(access_token, instance_url, alias)

    sf_exe = shutil.which("sf") or shutil.which("sfdx")
    if not sf_exe:
        win_sf = r"C:\Program Files\sf\bin\sf.CMD"
        if sys.platform == "win32" and os.path.exists(win_sf):
            sf_exe = win_sf
        else:
            raise RuntimeError("Salesforce CLI not found. Install @salesforce/cli.")

    if sys.platform == "win32":
        cmd = ["cmd", "/c", sf_exe, "org", "list", "metadata-types",
               "--target-org", alias, "--json"]
    else:
        cmd = [sf_exe, "org", "list", "metadata-types",
               "--target-org", alias, "--json"]

    logger.info("Running list metadata-types: %s (cwd=%s)", " ".join(cmd), proj)

    def run_list_types():
        env = os.environ.copy()
        env["SF_ACCESS_TOKEN"] = access_token  # provide directly in case alias auth from login step is incomplete
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=120,
            check=False,
            cwd=proj,
            env=env,
        )
        return proc.stdout, proc.stderr, proc.returncode

    stdout, stderr, rc = await asyncio.to_thread(run_list_types)
    out = stdout.decode(errors="replace")
    err = stderr.decode(errors="replace")

    if rc != 0:
        logger.warning("list metadata-types rc=%s: %s", rc, err[:500])
        # Try to parse any partial json result anyway
    try:
        data = json.loads(out) if out.strip() else {}
    except Exception:
        data = {"raw": out, "stderr": err}

    # The sf org list metadata-types --json returns:
    # { "status": 0, "result": { "metadataObjects": [ {xmlName, directoryName, inFolder, ...}, ... ] } }
    # Not a flat list under "result" (unlike the members list command).
    res = data.get("result") if isinstance(data, dict) else None
    if isinstance(res, dict):
        objs = res.get("metadataObjects") or res.get("metadata_objects") or []
        if isinstance(objs, list):
            cleaned = [o for o in objs if isinstance(o, dict)]
            # Sort by xmlName for nice dropdown
            return sorted(cleaned, key=lambda t: (t.get("xmlName") or ""))
    if isinstance(res, list):
        # Some versions or aliases might return flat list
        return sorted([o for o in res if isinstance(o, dict)], key=lambda t: (t.get("xmlName") or ""))

    # double-wrapped edge case
    if isinstance(data, dict) and isinstance(data.get("result"), dict) and "result" in data.get("result", {}):
        inner = data["result"]["result"]
        if isinstance(inner, dict):
            objs = inner.get("metadataObjects") or []
            if isinstance(objs, list):
                return sorted([o for o in objs if isinstance(o, dict)], key=lambda t: (t.get("xmlName") or ""))

    # Detect structured error from CLI (auth failures, permission issues like missing "Modify Metadata Through Metadata API Functions", etc.)
    if isinstance(data, dict):
        if data.get("name") or data.get("message") or data.get("error"):
            msg = data.get("message") or data.get("error") or str(data.get("name", "CLI Error"))
            if data.get("actions"):
                try:
                    msg += " | " + " ".join(str(a) for a in data.get("actions") or [])
                except Exception:
                    pass
            logger.warning("list metadata-types CLI error surfaced: %s", msg[:300])
            return [{"error": msg, "xmlName": "__ERROR__", "details": data}]

    # stderr sometimes contains the json error payload
    if err:
        try:
            err_data = json.loads(err)
            if isinstance(err_data, dict) and (err_data.get("message") or err_data.get("name")):
                msg = err_data.get("message") or err_data.get("error") or str(err_data.get("name"))
                return [{"error": msg, "xmlName": "__ERROR__", "details": err_data}]
        except Exception:
            pass

    if rc != 0:
        snippet = ((err or "") + " " + (out or ""))[:400].strip() or "no output"
        return [{"error": f"sf org list metadata-types failed (rc={rc}): {snippet}", "xmlName": "__ERROR__"}]

    return []


async def list_metadata_members_direct(
    access_token: str,
    instance_url: str,
    alias: str,
    metadata_type: str,
    folder: str | None = None,
    project_dir: str | None = None,
) -> list[dict[str, Any]]:
    """
    List concrete members/components of a metadata type using
    `sf org list metadata --metadata-type <Type> --target-org <alias> [--folder <f>] --json`.

    Returns list of {"fullName": "...", "type": "...", "manageableState": "...", ...}
    For types in folders (Report, Dashboard, EmailTemplate, Document) supply the folder name.
    Use this to populate the checkbox list so user can pick specific components to put in package.xml.
    """
    if not metadata_type:
        return []

    proj = project_dir or _get_default_project_dir()
    _ensure_sfdx_project(proj)
    await _register_org_with_sfdx(access_token, instance_url, alias)

    sf_exe = shutil.which("sf") or shutil.which("sfdx")
    if not sf_exe:
        win_sf = r"C:\Program Files\sf\bin\sf.CMD"
        if sys.platform == "win32" and os.path.exists(win_sf):
            sf_exe = win_sf
        else:
            raise RuntimeError("Salesforce CLI not found. Install @salesforce/cli.")

    if sys.platform == "win32":
        cmd = ["cmd", "/c", sf_exe, "org", "list", "metadata",
               "--metadata-type", metadata_type,
               "--target-org", alias,
               "--json"]
    else:
        cmd = [sf_exe, "org", "list", "metadata",
               "--metadata-type", metadata_type,
               "--target-org", alias,
               "--json"]

    if folder:
        # Insert --folder before the json for both styles
        # For list: append flag
        if sys.platform == "win32":
            cmd = ["cmd", "/c", sf_exe, "org", "list", "metadata",
                   "--metadata-type", metadata_type,
                   "--folder", folder,
                   "--target-org", alias, "--json"]
        else:
            cmd = [sf_exe, "org", "list", "metadata",
                   "--metadata-type", metadata_type,
                   "--folder", folder,
                   "--target-org", alias, "--json"]

    logger.info("Running list metadata members: %s (cwd=%s, type=%s, folder=%s)", " ".join(cmd), proj, metadata_type, folder)

    def run_list_members():
        env = os.environ.copy()
        env["SF_ACCESS_TOKEN"] = access_token  # provide directly in case alias auth from login step is incomplete
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=180,  # listing can be slow for big types like CustomObject or Report
            check=False,
            cwd=proj,
            env=env,
        )
        return proc.stdout, proc.stderr, proc.returncode

    stdout, stderr, rc = await asyncio.to_thread(run_list_members)
    out = stdout.decode(errors="replace")
    err = stderr.decode(errors="replace")

    if rc != 0:
        logger.warning("list metadata members rc=%s for %s: %s", rc, metadata_type, err[:600])

    try:
        data = json.loads(out) if out.strip() else {}
    except Exception:
        data = {"raw_stdout": out[:1000], "stderr": err[:500]}

    result = data.get("result") if isinstance(data, dict) else None
    if isinstance(result, list):
        # Dedup + sort by fullName
        seen = set()
        clean = []
        for item in result:
            fn = item.get("fullName") or item.get("name")
            if fn and fn not in seen:
                seen.add(fn)
                clean.append(item)
        return sorted(clean, key=lambda x: (x.get("fullName") or ""))

    # Detect structured error from CLI (permissions, auth, "no authorization information", insufficient access for metadata list, etc.)
    if isinstance(data, dict):
        if data.get("name") or data.get("message") or data.get("error"):
            msg = data.get("message") or data.get("error") or str(data.get("name", "CLI Error"))
            if data.get("actions"):
                try:
                    msg += " | " + " ".join(str(a) for a in data.get("actions") or [])
                except Exception:
                    pass
            logger.warning("list metadata members CLI error for %s: %s", metadata_type, msg[:300])
            return [{"error": msg, "fullName": "__ERROR__", "details": data}]

    if err:
        try:
            err_data = json.loads(err)
            if isinstance(err_data, dict) and (err_data.get("message") or err_data.get("name")):
                msg = err_data.get("message") or err_data.get("error") or str(err_data.get("name"))
                return [{"error": msg, "fullName": "__ERROR__", "details": err_data}]
        except Exception:
            pass

    if rc != 0:
        snippet = ((err or "") + " " + (out or ""))[:400].strip() or "no output"
        return [{"error": f"sf org list metadata failed (rc={rc}) for {metadata_type}: {snippet}", "fullName": "__ERROR__"}]

    return result if isinstance(result, list) else []


# ---------------------------------------------------------------------------
# Direct deploy (validation + full deploy + test runs) — bypasses MCP limitations
# Uses official sf CLI per Salesforce docs + Workbench-equivalent behavior (checkOnly + testLevel)
# ---------------------------------------------------------------------------

async def deploy_metadata_direct(
    access_token: str,
    instance_url: str,
    alias: str,
    source_dir: str | None = None,
    manifest_path: str | None = None,
    project_dir: str | None = None,
    check_only: bool = False,
    test_level: str | None = None,
    tests: list[str] | None = None,
    wait_minutes: int = 30,
) -> dict[str, Any]:
    """
    Deploy (or validate-only) metadata using the Salesforce CLI directly
    (sf project deploy start / sf project deploy validate).

    This is the robust path (same as retrieve_metadata_direct) that gives us
    full control over validation and Apex test execution — the @salesforce/mcp
    deploy_metadata tool currently lacks proper check-only + test level support.

    Validation modes (chosen automatically based on check_only + test_level):
      - check_only + test_level != NoTestRun  → "sf project deploy validate"
        (produces job ID for later "sf project deploy quick"; does not allow NoTestRun)
      - check_only + NoTestRun                → "sf project deploy start --dry-run"
        (lighter validation, sandbox-friendly per sf help; supports NoTestRun)
      - otherwise                             → "sf project deploy start"

    Key flags (observed on sf 2.133+ / plugin-deploy-retrieve):
      --dry-run on start, or the "validate" subcommand : validation (dry run, no commit)
      --test-level NoTestRun | RunLocalTests | RunSpecifiedTests | RunAllTestsInOrg | RunRelevantTests
      --tests TestClass1,TestClass2                    : when RunSpecifiedTests

    Returns parsed CLI JSON (contains "id" = Salesforce AsyncResult / Deploy ID
    usable for status polling or quick-deploy) + success flag + logs.
    """
    proj = project_dir or _get_default_project_dir()
    _ensure_sfdx_project(proj)
    await _register_org_with_sfdx(access_token, instance_url, alias)

    if not source_dir and not manifest_path:
        logger.warning("deploy_metadata_direct called with neither source_dir nor manifest_path (project_dir=%s). The sf command may use source tracking or fail.", proj)

    sf_exe = shutil.which("sf") or shutil.which("sfdx")
    if not sf_exe:
        win_sf = r"C:\Program Files\sf\bin\sf.CMD"
        if sys.platform == "win32" and os.path.exists(win_sf):
            sf_exe = win_sf
        else:
            raise RuntimeError("Salesforce CLI not found. Install @salesforce/cli.")

    # Choose subcommand + validation mode based on the actual installed sf CLI (observed v2.133+):
    # - sf project deploy validate : dedicated validation. Produces a job ID you can later
    #   "sf project deploy quick". Does NOT support NoTestRun (CLI help + docs explicitly
    #   say use start --dry-run on sandboxes if you need NoTestRun). Good for prod + quick-deploy.
    # - sf project deploy start --dry-run : the modern equivalent of the old --check-only.
    #   Supports NoTestRun. Recommended by sf help for sandbox validation.
    # We NEVER emit --check-only (that flag no longer exists on start in this CLI version;
    # passing it produces exactly the "Nonexistent flag: --check-only" error seen in logs).
    if check_only:
        wants_no_test_run = (test_level == "NoTestRun")
        if wants_no_test_run:
            # validate subcommand does not allow NoTestRun; must use start + --dry-run
            base_sub = ["project", "deploy", "start"]
            use_dry_run = True
        else:
            # Prefer the validate subcommand when we can (proper job ID for quick deploy)
            base_sub = ["project", "deploy", "validate"]
            use_dry_run = False
    else:
        base_sub = ["project", "deploy", "start"]
        use_dry_run = False

    if sys.platform == "win32":
        cmd = ["cmd", "/c", sf_exe] + base_sub
    else:
        cmd = [sf_exe] + base_sub

    if source_dir:
        cmd += ["--source-dir", source_dir]
    if manifest_path:
        cmd += ["--manifest", manifest_path]

    cmd += ["--target-org", alias, "--json", "--wait", str(wait_minutes)]

    if use_dry_run:
        cmd += ["--dry-run"]
    # Intentionally no --check-only branch anymore.

    if test_level:
        cmd += ["--test-level", test_level]
    if tests:
        # CLI accepts comma-separated list for --tests
        cmd += ["--tests", ",".join(tests)]

    logger.info("Running direct deploy: %s (cwd=%s, check_only=%s, test_level=%s, dry_run=%s)", " ".join(cmd), proj, check_only, test_level, use_dry_run)

    def run_deploy_cmd():
        env = os.environ.copy()
        env["SF_ACCESS_TOKEN"] = access_token
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=max(300, wait_minutes * 70),
            check=False,
            cwd=proj,
            env=env,
        )
        return proc.stdout, proc.stderr, proc.returncode

    try:
        stdout, stderr, rc = await asyncio.to_thread(run_deploy_cmd)
    except Exception as e:
        logger.exception("Direct deploy subprocess failed")
        return {"success": False, "error": str(e), "project_dir": proj, "returncode": -1}

    out = stdout.decode(errors="replace")
    err = stderr.decode(errors="replace")

    try:
        cli_result = json.loads(out) if out.strip() else {}
    except Exception:
        cli_result = {"raw_stdout": out, "stderr": err[:2000], "returncode": rc}

    success = rc == 0

    deploy_id = None
    status = None
    if isinstance(cli_result, dict):
        res = cli_result.get("result") if "result" in cli_result else cli_result
        if isinstance(res, dict):
            deploy_id = res.get("id") or res.get("deployId") or (res.get("details") or {}).get("id")
            status = res.get("status") or res.get("state")

    logger.info("Direct deploy completed: success=%s, id=%s, status=%s, rc=%s", success, deploy_id, status, rc)
    if err:
        logger.debug("deploy stderr (first 600): %s", err[:600])

    return {
        "success": success,
        "result": cli_result,
        "salesforce_deployment_id": deploy_id,
        "status": status,
        "project_dir": proj,
        "stdout": (out[:2500] if not success else out[:800]),
        "stderr": (err[:2500] if err else ""),
        "returncode": rc,
    }


# Quick-deploy helper (after a successful validation)
async def quick_deploy_direct(
    access_token: str,
    instance_url: str,
    alias: str,
    job_id: str,
    project_dir: str | None = None,
    wait_minutes: int = 10,
) -> dict[str, Any]:
    """Run `sf project deploy quick --job-id <id>` to perform the actual deploy after a prior validate."""
    proj = project_dir or _get_default_project_dir()
    _ensure_sfdx_project(proj)
    await _register_org_with_sfdx(access_token, instance_url, alias)

    sf_exe = shutil.which("sf") or shutil.which("sfdx")
    if not sf_exe:
        win_sf = r"C:\Program Files\sf\bin\sf.CMD"
        if sys.platform == "win32" and os.path.exists(win_sf):
            sf_exe = win_sf
        else:
            raise RuntimeError("Salesforce CLI not found.")

    if sys.platform == "win32":
        cmd = ["cmd", "/c", sf_exe, "project", "deploy", "quick",
               "--job-id", job_id, "--target-org", alias, "--json", "--wait", str(wait_minutes)]
    else:
        cmd = [sf_exe, "project", "deploy", "quick",
               "--job-id", job_id, "--target-org", alias, "--json", "--wait", str(wait_minutes)]

    def run_quick():
        env = os.environ.copy()
        env["SF_ACCESS_TOKEN"] = access_token
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=120, check=False, cwd=proj, env=env)
        return proc.stdout, proc.stderr, proc.returncode

    stdout, stderr, rc = await asyncio.to_thread(run_quick)
    out = stdout.decode(errors="replace")
    err = stderr.decode(errors="replace")
    try:
        cli_result = json.loads(out) if out.strip() else {}
    except Exception:
        cli_result = {"raw": out}
    success = rc == 0
    new_id = None
    if isinstance(cli_result, dict):
        r = cli_result.get("result") or cli_result
        if isinstance(r, dict):
            new_id = r.get("id")
    return {
        "success": success,
        "result": cli_result,
        "salesforce_deployment_id": new_id,
        "stdout": out[:1000],
        "stderr": err[:1000],
        "returncode": rc,
    }


# ---------------------------------------------------------------------------
# High-level async client
# ---------------------------------------------------------------------------

class SFDXMCPClient:
    """
    High-level async client for SFDX MCP operations within Cloud Bridge.

    Usage (as async context manager):
        async with SFDXMCPClient(access_token, instance_url, org_alias,
                                  project_dir="/path/to/sfdx-project") as client:
            result = await client.retrieve_metadata(["ApexClass", "CustomObject"])
            deploy_result = await client.deploy_metadata(["force-app/main/default"])

    The client handles:
    - Ensuring a minimal SFDX project scaffold exists at *project_dir*
    - Registering the org with the local SFDX auth store
    - Starting / stopping the MCP subprocess
    - Translating high-level calls into correctly-shaped MCP tool invocations

    Parameter rules (enforced by the real @salesforce/mcp Zod schemas):
    - ``usernameOrAlias`` — org username or registered alias (auto-set from org_alias)
    - ``directory``       — absolute path of the SFDX project (auto-set from project_dir)
    """

    def __init__(
        self,
        access_token: str,
        instance_url: str,
        org_alias: str | None = None,
        toolsets: str = "orgs,metadata,data,testing,users",
        project_dir: str | None = None,
    ):
        self.access_token = access_token
        self.instance_url = instance_url
        self.org_alias = org_alias or f"cloudbridge-{uuid.uuid4().hex[:8]}"
        self.toolsets = toolsets
        self.project_dir = project_dir or _get_default_project_dir()
        self._mcp: SFDXMCPProcess | None = None

    async def __aenter__(self):
        # 1. Ensure SFDX project scaffold exists at project_dir
        _ensure_sfdx_project(self.project_dir)
        # 2. Register org with SFDX auth store
        await _register_org_with_sfdx(self.access_token, self.instance_url, self.org_alias)
        # 3. Start MCP server
        self._mcp = SFDXMCPProcess(self.org_alias, self.toolsets)
        await self._mcp.start()
        return self

    async def __aexit__(self, *_):
        if self._mcp:
            await self._mcp.stop()

    # ------------------------------------------------------------------
    # Generic tool call passthrough
    # ------------------------------------------------------------------

    async def call_tool(self, tool_name: str, arguments: dict[str, Any], timeout: float = 120.0) -> Any:
        """
        Call any SFDX MCP tool by name.  The caller is responsible for
        providing the correct argument names as defined by the tool's Zod
        schema (``usernameOrAlias``, ``directory``, etc.).
        """
        return await self._mcp.call_tool(tool_name, arguments, timeout=timeout)

    async def list_tools(self) -> list:
        """Return the list of all available MCP tools."""
        return await self._mcp.list_tools()

    # ------------------------------------------------------------------
    # Metadata tools
    # ------------------------------------------------------------------

    async def retrieve_metadata(
        self,
        metadata_types: list | None = None,
        source_dirs: list | None = None,
        manifest_path: str | None = None,
        ignore_conflicts: bool = False,
    ) -> Any:
        """
        Retrieve metadata from the org via the ``retrieve_metadata`` MCP tool.

        Priority (first match wins):
        1. *manifest_path*  — path to an existing ``package.xml``.
        2. *metadata_types* — list like ``["ApexClass", "Flow:MyFlow"]``; a
                              ``manifest/package.xml`` is auto-generated.
        3. *source_dirs*    — list of local source paths (``sourceDir``).
        4. (nothing)        — source-tracking-based retrieve (org must support it).

        Note: the real tool has no ``metadata`` or ``targetdir`` parameters.
        """
        args: dict[str, Any] = {
            "usernameOrAlias": self.org_alias,
            "directory": self.project_dir,
        }
        if metadata_types and not manifest_path:
            manifest_path = _write_manifest_xml(metadata_types, self.project_dir)
        if manifest_path:
            args["manifest"] = manifest_path
        elif source_dirs:
            args["sourceDir"] = source_dirs
        if ignore_conflicts:
            args["ignoreConflicts"] = True
        return await self._mcp.call_tool("retrieve_metadata", args, timeout=180)

    async def deploy_metadata(
        self,
        source_dirs: list | None = None,
        manifest_path: str | None = None,
        apex_test_level: str | None = None,
        apex_tests: list | None = None,
        ignore_conflicts: bool = False,
    ) -> Any:
        """
        Deploy metadata to the org via the ``deploy_metadata`` MCP tool.

        *apex_test_level* values: ``"NoTestRun"``, ``"RunLocalTests"``,
        ``"RunAllTestsInOrg"``.  Pass *apex_tests* (list of class names) to run
        specific tests alongside the deployment.

        Note: the real tool has no ``checkonly``, ``sourcedir`` (lowercase), or
        ``testlevel`` parameters.  Use ``apexTestLevel`` and ``sourceDir`` (list).
        """
        args: dict[str, Any] = {
            "usernameOrAlias": self.org_alias,
            "directory": self.project_dir,
        }
        if source_dirs:
            args["sourceDir"] = source_dirs
        if manifest_path:
            args["manifest"] = manifest_path
        if apex_test_level:
            args["apexTestLevel"] = apex_test_level
        if apex_tests:
            args["apexTests"] = apex_tests
        if ignore_conflicts:
            args["ignoreConflicts"] = True
        return await self._mcp.call_tool("deploy_metadata", args, timeout=300)

    async def run_apex_tests(
        self,
        class_names: list | None = None,
        method_names: list | None = None,
        test_level: str = "RunLocalTests",
        code_coverage: bool = False,
        verbose: bool = False,
        async_run: bool = False,
    ) -> Any:
        """
        Run Apex tests via the ``run_apex_test`` MCP tool.

        *test_level* values: ``"RunLocalTests"`` (default),
        ``"RunAllTestsInOrg"``, ``"RunSpecifiedTests"`` (auto-set when
        *class_names* or *method_names* are provided).

        Note: the real tool uses ``testLevel`` (camelCase) and ``classNames``
        as a string array — NOT ``testlevel`` or a comma-joined ``classnames``.
        """
        if (class_names or method_names) and test_level not in (
            "RunSpecifiedTests",
        ):
            test_level = "RunSpecifiedTests"
        args: dict[str, Any] = {
            "usernameOrAlias": self.org_alias,
            "directory": self.project_dir,
            "testLevel": test_level,
            "codeCoverage": code_coverage,
            "verbose": verbose,
            "async": async_run,
        }
        if class_names:
            args["classNames"] = class_names
        if method_names:
            args["methodNames"] = method_names
        return await self._mcp.call_tool("run_apex_test", args, timeout=300)

    async def list_orgs(self) -> Any:
        """List all locally authorized orgs (``list_all_orgs`` tool)."""
        return await self._mcp.call_tool(
            "list_all_orgs",
            {"directory": self.project_dir},
        )

    async def get_org_info(self) -> Any:
        """Resolve the current org username/alias (``get_username`` tool)."""
        return await self._mcp.call_tool(
            "get_username",
            {"directory": self.project_dir},
        )


# ---------------------------------------------------------------------------
# Streaming async generator for live progress reporting
# ---------------------------------------------------------------------------

async def run_mcp_tool_streaming(
    access_token: str,
    instance_url: str,
    org_alias: str,
    tool_name: str,
    arguments: dict[str, Any],
    toolsets: str = "orgs,metadata,data,testing,users",
    timeout: float = 120.0,
    project_dir: str | None = None,
) -> AsyncGenerator[dict[str, Any], None]:
    """
    Async generator that yields structured progress events, then the final result.

    Each yielded dict has at minimum:
        phase (str)  - one of: init, auth, auth_ok, auth_warn, mcp_start,
                       mcp_ready, tool_call, done, error
        msg   (str)  - human-readable message
        result (any) - only on 'done' phase

    ``usernameOrAlias`` and ``directory`` are injected into *arguments* if not
    already present, so callers only need to supply tool-specific params.

    Intended for Server-Sent Events streaming endpoints.
    """
    _project_dir = project_dir or _get_default_project_dir()
    _ensure_sfdx_project(_project_dir)

    yield {"phase": "auth", "msg": "Registering org credentials with Salesforce CLI..."}
    try:
        await _register_org_with_sfdx(access_token, instance_url, org_alias)
        yield {"phase": "auth_ok", "msg": f"Org alias '{org_alias}' registered"}
    except Exception as exc:
        yield {"phase": "auth_warn", "msg": f"Auth note: {exc} — continuing"}

    # Inject standard MCP params; user-supplied values take priority
    merged_args: dict[str, Any] = {
        "usernameOrAlias": org_alias,
        "directory": _project_dir,
        **arguments,
    }

    yield {"phase": "mcp_start", "msg": "Starting @salesforce/mcp server..."}
    proc = SFDXMCPProcess(org_alias, toolsets)
    try:
        await proc.start()
        yield {"phase": "mcp_ready", "msg": "MCP server initialised and ready"}
        yield {"phase": "tool_call", "msg": f"Calling MCP tool: {tool_name}"}
        try:
            result = await proc.call_tool(tool_name, merged_args, timeout=timeout)
            yield {"phase": "done", "msg": "Tool completed successfully", "result": result}
        except Exception as exc:
            yield {"phase": "error", "msg": str(exc)}
    except Exception as exc:
        yield {"phase": "error", "msg": f"MCP server error: {exc}"}
    finally:
        await proc.stop()
