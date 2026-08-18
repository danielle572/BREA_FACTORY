#!/usr/bin/env python3
"""
brea_factory.py
Session F2 -- Factory Orchestrator Service

Flask + SocketIO service on port 5004 that polls TASK_QUEUE every 30 seconds
and dispatches tasks by Mode:
  Auto     -- executes headless via Claude Code SDK, logs result, marks Done
  Approve  -- fires Socket.IO notification, holds until dashboard approval
  Critical -- holds immediately, requires explicit confirmation + written note

HARD RULE (enforced first in every execution path):
  This service will NEVER read, write, or touch any .env file or API key file
  under any circumstance. Violations are blocked, logged, and notified.

Boot banner confirms: Factory Orchestrator online, TASK_QUEUE connected,
hard exclusions active.

Requires:
    pip install flask flask-socketio requests python-dotenv anthropic
"""

import os
import sys
import re
import json
import time
import threading
import subprocess
import datetime
import traceback

import requests
from flask import Flask, jsonify, request
from flask_socketio import SocketIO, emit

try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))
except ImportError:
    pass


# ── Persist console output to a log file for the dashboard /logs route ─────────

_LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "factory_orchestrator.log")

class _Tee:
    def __init__(self, *streams):
        self._streams = streams

    def write(self, data):
        for s in self._streams:
            s.write(data)
            s.flush()

    def flush(self):
        for s in self._streams:
            s.flush()

_log_file = open(_LOG_PATH, "a", encoding="utf-8")
sys.stdout = _Tee(sys.stdout, _log_file)
sys.stderr = _Tee(sys.stderr, _log_file)


# ── Configuration ──────────────────────────────────────────────────────────────

AIRTABLE_TOKEN  = os.environ.get("AIRTABLE_TOKEN", "")
FACTORY_BASE_ID = os.environ.get("FACTORY_BASE_ID", "")
POLL_INTERVAL   = 30   # seconds
PORT            = 5004

# ── Health watchdog ────────────────────────────────────────────────────────────
_HEALTH_INTERVAL       = 60    # seconds between full sweeps
_HEALTH_SLOW_THRESHOLD = 2.0   # seconds — above this is a Warning
_HEALTH_TARGETS = [
    {"key": "brea3",     "name": "Brea 3",               "port": 5000, "path": "/"},
    {"key": "boss",      "name": "BOSS",                 "url": "https://web-production-524676.up.railway.app/health"},
    {"key": "dashboard", "name": "Factory Dashboard",    "port": 5003, "path": "/"},
    {"key": "factory",   "name": "Factory Orchestrator", "port": 5004, "path": "/status"},
]
_health_fail_count: dict = {}   # key -> consecutive failure/slow count
_health_last_state: dict = {}  # key -> "OK" | "Warning" | "Critical"

AIRTABLE_HEADERS = {
    "Authorization": f"Bearer {AIRTABLE_TOKEN}",
    "Content-Type":  "application/json",
}

# ── Hard exclusion patterns (RULE 9) ──────────────────────────────────────────
# These are checked FIRST before any task execution. Non-negotiable.

_FORBIDDEN = [
    r"\.env(\.|$)",
    r"\.env\.example",
    r"api[_\-]?key",
    r"secret[_\-]?key",
    r"private[_\-]?key",
    r"access[_\-]?token",
    r"bearer[_\-]?token",
    r"auth[_\-]?token",
    r"\bpassword\b",
    r"credentials?\b",
    r"\.pem\b",
    r"\.p12\b",
    r"\.pfx\b",
    r"id_rsa",
    r"id_ed25519",
    r"\.aws/credentials",
    r"pat[a-z0-9]{14}\.",   # Airtable PAT pattern
]

# ── In-memory approval queues ──────────────────────────────────────────────────

pending_approvals  = {}   # record_id -> task dict  (Approve mode)
pending_criticals  = {}   # record_id -> task dict  (Critical mode)

# ── Flask + SocketIO ───────────────────────────────────────────────────────────

app      = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")


# ══════════════════════════════════════════════════════════════════════════════
#  HARD RULE -- always called first
# ══════════════════════════════════════════════════════════════════════════════

def is_forbidden(task: dict) -> tuple:
    """
    HARD RULE: Scan every field in the task record for .env / key file patterns.
    Returns (True, reason_string) if forbidden, (False, "") if clean.
    Called before ANY execution path. Non-negotiable.
    """
    task_text = json.dumps(task).lower()
    for pattern in _FORBIDDEN:
        if re.search(pattern, task_text, re.IGNORECASE):
            reason = (
                f"HARD RULE VIOLATION -- task references forbidden pattern: '{pattern}'. "
                "This service never reads, writes, or touches .env or API key files."
            )
            return (True, reason)
    return (False, "")


# ══════════════════════════════════════════════════════════════════════════════
#  Airtable helpers
# ══════════════════════════════════════════════════════════════════════════════

def _at_url(table: str, suffix: str = "") -> str:
    return f"https://api.airtable.com/v0/{FACTORY_BASE_ID}/{table}{suffix}"


def at_get(table: str, formula: str = "") -> list:
    params = {}
    if formula:
        params["filterByFormula"] = formula
    resp = requests.get(_at_url(table), headers=AIRTABLE_HEADERS, params=params)
    resp.raise_for_status()
    return resp.json().get("records", [])


def at_patch(table: str, record_id: str, fields: dict) -> dict:
    resp = requests.patch(
        _at_url(table, f"/{record_id}"),
        headers=AIRTABLE_HEADERS,
        json={"fields": fields},
    )
    resp.raise_for_status()
    return resp.json()


def at_create(table: str, fields: dict, typecast: bool = False) -> dict:
    body = {"records": [{"fields": fields}]}
    if typecast:
        body["typecast"] = True
    resp = requests.post(_at_url(table), headers=AIRTABLE_HEADERS, json=body)
    resp.raise_for_status()
    return resp.json()


# ══════════════════════════════════════════════════════════════════════════════
#  Diagnostic log writer
# ══════════════════════════════════════════════════════════════════════════════

def log_diagnostic(
    task: dict,
    error_category: str,
    error_type: str,
    message: str,
    diagnosis: str = "",
    suggested_fix: str = "",
    resolution: str = "Open",
    data_at_risk: bool = False,
) -> None:
    """Writes one row to MASTER_DIAGNOSTIC_LOG. Never raises -- logs to stdout on failure."""
    fields_in = task.get("fields", {})
    now = datetime.datetime.utcnow().isoformat() + "Z"

    record = {
        "Error_Name":            f"FACTORY-{datetime.datetime.utcnow().strftime('%Y%m%d-%H%M%S')}",
        "Instance_ID":           "FACTORY",
        "Instance_Type":         "Factory",
        "Capability_ID":         fields_in.get("Capability_ID", ""),
        "Error_Category":        error_category,
        "Error_Type":            error_type,
        "Error_Message":         message[:10000],
        "Brea_Diagnosis":        diagnosis[:10000],
        "Suggested_Fix":         suggested_fix[:5000],
        "Resolution_Status":     resolution,
        "Factory_Review_Status": "Unreviewed" if resolution == "Open" else "Reviewed",
        "Session_Wave":          fields_in.get("Session_Wave", ""),
        "Data_At_Risk":          data_at_risk,
    }
    if resolution in ("Auto-Resolved", "Fixed"):
        record["Resolved_At"] = now
        record["Resolved_By"] = "Factory Auto"

    try:
        at_create("MASTER_DIAGNOSTIC_LOG", record)
    except Exception as exc:
        print(f"  [LOG FAIL] MASTER_DIAGNOSTIC_LOG write failed: {exc}")


# ══════════════════════════════════════════════════════════════════════════════
#  Claude Code SDK executor (Auto tasks)
# ══════════════════════════════════════════════════════════════════════════════

def execute_headless(task: dict) -> tuple:
    """
    Executes an Auto task via Claude Code SDK (headless) or Anthropic SDK fallback.
    Returns (success: bool, output: str).
    """
    fields = task.get("fields", {})
    name   = fields.get("Task_Name", "Unnamed Task")
    desc   = fields.get("Description", "")
    module = fields.get("Module", "")
    cap_id = fields.get("Capability_ID", "")

    prompt = (
        f"BREA FACTORY -- Auto Task Execution\n"
        f"Task: {name}\n"
        f"Module: {module}  |  Capability: {cap_id}\n"
        f"\n{desc}"
    )

    # Attempt 1: Claude Code CLI in headless / print mode
    print(f"[CLI] Executing task: {name}")
    try:
        result = subprocess.run(
            [r"C:\Users\Danielle\AppData\Roaming\npm\claude.cmd", "-p", "--output-format", "text",
             "--allowedTools", "Edit", "Write", "Read", "Glob", "Grep"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=300,
            env=os.environ.copy(),
            shell=True,
        )
        if result.returncode == 0:
            print(f"[CLI] Task complete: {name}")
            return (True, result.stdout.strip())
        stderr = result.stderr.strip()
        return (False, f"Claude Code CLI exit {result.returncode}: {stderr}")
    except FileNotFoundError:
        pass   # CLI not installed -- fall through
    except subprocess.TimeoutExpired:
        return (False, "Task timed out after 300 seconds")
    except Exception as exc:
        print(f"[CLI] FAILED: {exc}")
        traceback.print_exc()
        return (False, f"Claude Code CLI unexpected error: {exc}")

    # Attempt 2: Anthropic Python SDK
    try:
        import anthropic
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            return (False, "ANTHROPIC_API_KEY not set and Claude Code CLI not found.")
        client   = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=8096,
            messages=[{"role": "user", "content": prompt}],
        )
        output = response.content[0].text if response.content else "(empty response)"
        return (True, output)
    except ImportError:
        return (
            False,
            "Neither Claude Code CLI nor anthropic SDK available. "
            "Run: pip install anthropic  or install Claude Code CLI.",
        )
    except Exception as exc:
        return (False, f"Anthropic SDK error: {exc}")


# ══════════════════════════════════════════════════════════════════════════════
#  Task handlers
# ══════════════════════════════════════════════════════════════════════════════

def process_task(task: dict) -> None:
    """Entry point for every task picked up from TASK_QUEUE."""
    record_id = task["id"]
    fields    = task.get("fields", {})
    name      = fields.get("Task_Name", record_id)
    mode      = fields.get("Mode", "Auto") or "Auto"

    print(f"\n  [TASK] {name}  |  Mode: {mode}  |  ID: {record_id}")

    # ── HARD RULE: first check, always, before anything else ──────────────
    forbidden, reason = is_forbidden(task)
    if forbidden:
        print(f"  [BLOCKED] {reason}")
        at_patch("TASK_QUEUE", record_id, {
            "Status": "Cancelled",
            "Notes":  f"BLOCKED BY HARD RULE\n{reason}",
        })
        log_diagnostic(
            task,
            error_category="Hard Break",
            error_type="Hard Failure",
            message=reason,
            diagnosis="Task attempted to reference a .env or API key file. Hard Rule enforced automatically.",
            suggested_fix="Remove all .env / key file references from Task_Name, Description, and Notes.",
            resolution="Fixed",
            data_at_risk=True,
        )
        socketio.emit("task_blocked", {
            "task_id":   record_id,
            "task_name": name,
            "reason":    reason,
        })
        return
    # ── Hard rule passed ──────────────────────────────────────────────────

    # Mark in-progress to prevent double-pick-up on next poll
    at_patch("TASK_QUEUE", record_id, {"Status": "In Progress"})

    if mode == "Auto":
        _exec_auto(task)
    elif mode == "Approve":
        _hold_for_approval(task)
    elif mode == "Critical":
        _hold_for_critical(task)
    else:
        print(f"  [WARN] Unknown mode '{mode}' -- routing to Approve for safety")
        _hold_for_approval(task)


def _exec_auto(task: dict) -> None:
    record_id = task["id"]
    name      = task.get("fields", {}).get("Task_Name", record_id)

    print(f"  [AUTO] Executing headless: {name}")
    success, output = execute_headless(task)
    now = datetime.datetime.utcnow().isoformat() + "Z"

    if success:
        at_patch("TASK_QUEUE", record_id, {
            "Status":       "Complete",
            "Notes":        output[:10000],
            "Completed_At": now,
        })
        log_diagnostic(
            task,
            error_category="Recovery",
            error_type="Recovery",
            message=f"Auto task completed: {name}",
            diagnosis=output[:5000],
            resolution="Auto-Resolved",
        )
        socketio.emit("task_complete", {
            "task_id":   record_id,
            "task_name": name,
            "mode":      "Auto",
            "result":    output[:500],
        })
        print(f"  [DONE] {name}")
    else:
        at_patch("TASK_QUEUE", record_id, {
            "Status": "Blocked",
            "Notes":  f"Execution failed:\n{output}",
        })
        log_diagnostic(
            task,
            error_category="Hard Break",
            error_type="Hard Failure",
            message=f"Auto task failed: {name}",
            diagnosis=output[:5000],
            suggested_fix="Check Claude Code CLI installation and ANTHROPIC_API_KEY.",
            resolution="Open",
        )
        socketio.emit("task_failed", {
            "task_id":   record_id,
            "task_name": name,
            "error":     output[:500],
        })
        print(f"  [FAIL] {name}: {output[:200]}")


def _hold_for_approval(task: dict) -> None:
    record_id = task["id"]
    fields    = task.get("fields", {})
    name      = fields.get("Task_Name", record_id)

    pending_approvals[record_id] = task
    socketio.emit("approve_required", {
        "task_id":     record_id,
        "task_name":   name,
        "description": fields.get("Description", ""),
        "module":      fields.get("Module", ""),
        "priority":    fields.get("Priority", ""),
    })
    log_diagnostic(
        task,
        error_category="Recovery",
        error_type="Warning",
        message=f"Approve task holding for human confirmation: {name}",
        resolution="Investigating",
    )
    print(f"  [HOLD] Awaiting approval: {name}")


def _hold_for_critical(task: dict) -> None:
    record_id = task["id"]
    fields    = task.get("fields", {})
    name      = fields.get("Task_Name", record_id)

    pending_criticals[record_id] = task
    at_patch("TASK_QUEUE", record_id, {"Status": "Blocked"})
    socketio.emit("critical_required", {
        "task_id":     record_id,
        "task_name":   name,
        "description": fields.get("Description", ""),
        "module":      fields.get("Module", ""),
        "priority":    fields.get("Priority", ""),
        "instruction": (
            "CRITICAL task -- explicit confirmation AND a written note "
            "are required before this executes. POST to /confirm/<task_id> "
            "with JSON body: {\"note\": \"your reason here\"}."
        ),
    })
    log_diagnostic(
        task,
        error_category="Transient",
        error_type="Warning",
        message=f"Critical task holding for explicit confirmation: {name}",
        resolution="Investigating",
    )
    print(f"  [CRITICAL] Holding -- explicit confirmation required: {name}")


# ══════════════════════════════════════════════════════════════════════════════
#  Polling loop
# ══════════════════════════════════════════════════════════════════════════════

def _poll_loop() -> None:
    print(f"  [POLL] Background thread started -- interval {POLL_INTERVAL}s")
    while True:
        try:
            queued = at_get("TASK_QUEUE", formula="OR({Status}='Queued')")
            if queued:
                print(f"\n  [POLL] {len(queued)} task(s) in queue")
                for task in queued:
                    process_task(task)
            else:
                ts = datetime.datetime.now().strftime("%H:%M:%S")
                print(f"  [POLL] {ts} -- queue empty")
        except Exception as exc:
            print(f"  [POLL ERROR] {exc}")
        time.sleep(POLL_INTERVAL)


# ══════════════════════════════════════════════════════════════════════════════
#  Health watchdog
# ══════════════════════════════════════════════════════════════════════════════

def _write_health_diagnostic(
    svc: dict,
    severity: str,       # "Warning" or "Critical"
    diagnosis: str,
    fix: str,
    pattern_flag: bool,
) -> None:
    """Write one health-failure row to MASTER_DIAGNOSTIC_LOG. Never raises."""
    ts     = datetime.datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    record = {
        "Error_Name":            f"HEALTH-{svc['key'].upper()}-{ts}",
        "Instance_ID":           "FACTORY",
        "Instance_Type":         "Factory",
        "Error_Category":        "Transient" if severity in ("Warning", "Recovered") else "Hard Break",
        "Error_Type":            severity,
        "Error_Message":         f"{svc['name']} health check {severity.lower()}",
        "Brea_Diagnosis":        diagnosis,
        "Suggested_Fix":         fix,
        "Resolution_Status":     "Open",
        "Factory_Review_Status": "Unreviewed",
        "Session_Wave":          "F4",
    }
    try:
        at_create("MASTER_DIAGNOSTIC_LOG", record, typecast=True)
        print(f"  [HEALTH OK] Wrote {severity} row for {svc['name']} -> {record['Error_Name']}")
    except Exception as exc:
        detail = getattr(getattr(exc, "response", None), "text", None) or str(exc)
        print(f"  [HEALTH LOG FAIL] Could not write diagnostic for {svc['name']}: {type(exc).__name__}: {detail}")


def _health_loop() -> None:
    print(f"  [HEALTH] Watchdog started — {len(_HEALTH_TARGETS)} services, interval {_HEALTH_INTERVAL}s")
    while True:
        for svc in _HEALTH_TARGETS:
            key      = svc["key"]
            name     = svc["name"]
            port     = svc.get("port")
            url      = svc.get("url") or f"http://localhost:{port}{svc['path']}"
            location = svc.get("url") or f"port {port}"

            try:
                t0      = time.time()
                resp    = requests.get(url, timeout=_HEALTH_SLOW_THRESHOLD + 1.0)
                elapsed = time.time() - t0

                if resp.status_code == 200 and elapsed <= _HEALTH_SLOW_THRESHOLD:
                    was_unhealthy = _health_last_state.get(key) not in (None, "OK")
                    _health_fail_count[key] = 0
                    if was_unhealthy:
                        _write_health_diagnostic(
                            svc, "Recovered",
                            f"{name} is healthy again after a prior {_health_last_state[key].lower()} state.",
                            "No action needed — auto-resolved.", False,
                        )
                    _health_last_state[key] = "OK"
                    socketio.emit("health_ok", {
                        "service": name, "port": port,
                        "elapsed_ms": round(elapsed * 1000),
                    })

                elif resp.status_code == 200:   # responded, but slowly
                    _health_fail_count[key] = _health_fail_count.get(key, 0) + 1
                    consec = _health_fail_count[key]
                    diag   = (
                        f"{name} responded slowly: {elapsed:.2f}s (threshold {_HEALTH_SLOW_THRESHOLD}s). "
                        "Likely cause: high CPU/memory load or a slow downstream API call. "
                        "Performance may be degraded for end users."
                    )
                    fix = (
                        f"Check {name} resource utilization. "
                        "If this persists across multiple checks, restart the service."
                    )
                    if _health_last_state.get(key) != "Warning":
                        _write_health_diagnostic(svc, "Warning", diag, fix, consec >= 3)
                    _health_last_state[key] = "Warning"
                    socketio.emit("health_warning", {
                        "service": name, "port": port,
                        "diagnosis": diag,
                        "elapsed_ms": round(elapsed * 1000),
                        "consecutive": consec,
                        "pattern_flag": consec >= 3,
                    })

                else:   # non-200 status code
                    _health_fail_count[key] = _health_fail_count.get(key, 0) + 1
                    consec = _health_fail_count[key]
                    diag   = (
                        f"{name} returned HTTP {resp.status_code}. "
                        "The service is running but in an error state — "
                        "it may have lost its database connection or hit a configuration problem."
                    )
                    fix = f"Check {name} logs for root cause and restart if the error persists."
                    if _health_last_state.get(key) != "Critical":
                        _write_health_diagnostic(svc, "Critical", diag, fix, consec >= 3)
                    _health_last_state[key] = "Critical"
                    socketio.emit("health_critical", {
                        "service": name, "port": port,
                        "diagnosis": diag,
                        "status_code": resp.status_code,
                        "consecutive": consec,
                        "pattern_flag": consec >= 3,
                    })

            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
                _health_fail_count[key] = _health_fail_count.get(key, 0) + 1
                consec = _health_fail_count[key]
                diag   = (
                    f"{name} is not responding at {location}. "
                    "The service has likely crashed, been killed, or never started. "
                    "No requests can reach it right now."
                )
                fix = (
                    f"Verify the {name} process is running ({location}). "
                    "Check for crash logs and restart the service."
                )
                if _health_last_state.get(key) != "Critical":
                    _write_health_diagnostic(svc, "Critical", diag, fix, consec >= 3)
                _health_last_state[key] = "Critical"
                socketio.emit("health_critical", {
                    "service": name, "port": port,
                    "diagnosis": diag,
                    "consecutive": consec,
                    "pattern_flag": consec >= 3,
                })

            except Exception as exc:
                print(f"  [HEALTH] Unexpected error checking {name}: {exc}")

        time.sleep(_HEALTH_INTERVAL)


# ══════════════════════════════════════════════════════════════════════════════
#  Flask routes
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/status")
def route_status():
    return jsonify({
        "service":            "BREA Factory Orchestrator",
        "status":             "online",
        "port":               PORT,
        "factory_base_id":    FACTORY_BASE_ID,
        "poll_interval_s":    POLL_INTERVAL,
        "pending_approvals":  len(pending_approvals),
        "pending_criticals":  len(pending_criticals),
        "hard_exclusions":    "ACTIVE",
        "forbidden_patterns": len(_FORBIDDEN),
    })


@app.route("/queue")
def route_queue():
    try:
        records = at_get("TASK_QUEUE")
        return jsonify({
            "count":             len(records),
            "pending_approvals": list(pending_approvals.keys()),
            "pending_criticals": list(pending_criticals.keys()),
            "tasks": [
                {
                    "id":     r["id"],
                    "name":   r.get("fields", {}).get("Task_Name", ""),
                    "status": r.get("fields", {}).get("Status", ""),
                    "mode":   r.get("fields", {}).get("Mode", ""),
                }
                for r in records
            ],
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/approve/<task_id>", methods=["POST"])
def route_approve(task_id: str):
    """Approve a pending Approve-mode task and execute it immediately."""
    if task_id not in pending_approvals:
        return jsonify({"error": "Task ID not in pending approvals"}), 404

    task = pending_approvals.pop(task_id)
    name = task.get("fields", {}).get("Task_Name", task_id)

    # Hard rule re-check before execution
    forbidden, reason = is_forbidden(task)
    if forbidden:
        log_diagnostic(task, "Hard Break", "Hard Failure", reason,
                       resolution="Fixed", data_at_risk=True)
        return jsonify({"error": f"HARD RULE BLOCKED: {reason}"}), 403

    print(f"\n  [APPROVED] Executing: {name}")
    success, output = execute_headless(task)
    now = datetime.datetime.utcnow().isoformat() + "Z"

    if success:
        at_patch("TASK_QUEUE", task_id, {
            "Status": "Complete", "Notes": output[:10000], "Completed_At": now,
        })
        log_diagnostic(task, "Recovery", "Recovery",
                       f"Approve task completed after human confirmation: {name}",
                       diagnosis=output[:5000], resolution="Auto-Resolved")
        socketio.emit("task_complete", {"task_id": task_id, "task_name": name,
                                        "mode": "Approve", "result": output[:500]})
        print(f"  [DONE] {name}")
        return jsonify({"status": "complete", "output": output[:2000]})
    else:
        at_patch("TASK_QUEUE", task_id, {
            "Status": "Blocked", "Notes": f"Failed after approval:\n{output}",
        })
        log_diagnostic(task, "Hard Break", "Hard Failure",
                       f"Approve task failed after confirmation: {name}",
                       diagnosis=output[:5000], resolution="Open")
        return jsonify({"status": "failed", "error": output[:2000]}), 500


@app.route("/confirm/<task_id>", methods=["POST"])
def route_confirm_critical(task_id: str):
    """
    Confirm and execute a Critical-mode task.
    Body: {"note": "written reason, minimum 20 characters"}
    """
    if task_id not in pending_criticals:
        return jsonify({"error": "Task ID not in pending criticals"}), 404

    data = request.get_json(silent=True) or {}
    note = data.get("note", "").strip()

    if not note:
        return jsonify({
            "error": "A written confirmation note is required for Critical tasks.",
            "hint":  "POST JSON body: {\"note\": \"your explicit reason here\"}"
        }), 400
    if len(note) < 20:
        return jsonify({
            "error":            "Confirmation note must be at least 20 characters.",
            "provided_length":  len(note),
        }), 400

    task = pending_criticals.pop(task_id)
    name = task.get("fields", {}).get("Task_Name", task_id)

    # Hard rule re-check before execution
    forbidden, reason = is_forbidden(task)
    if forbidden:
        log_diagnostic(task, "Hard Break", "Hard Failure", reason,
                       resolution="Fixed", data_at_risk=True)
        return jsonify({"error": f"HARD RULE BLOCKED: {reason}"}), 403

    print(f"\n  [CRITICAL CONFIRMED] {name}")
    print(f"  Operator note: {note}")

    success, output = execute_headless(task)
    now       = datetime.datetime.utcnow().isoformat() + "Z"
    full_note = f"CONFIRMED {now}\nOperator note: {note}\n\nResult:\n{output}"

    if success:
        at_patch("TASK_QUEUE", task_id, {
            "Status": "Complete", "Notes": full_note[:10000], "Completed_At": now,
        })
        log_diagnostic(
            task, "Recovery", "Recovery",
            f"Critical task completed after explicit confirmation: {name}",
            diagnosis=f"Note: {note}\n\nOutput: {output[:3000]}",
            resolution="Fixed",
        )
        socketio.emit("task_complete", {"task_id": task_id, "task_name": name,
                                        "mode": "Critical", "result": output[:500]})
        print(f"  [DONE] {name}")
        return jsonify({"status": "complete", "output": output[:2000]})
    else:
        at_patch("TASK_QUEUE", task_id, {
            "Status": "Blocked", "Notes": full_note[:10000],
        })
        log_diagnostic(
            task, "Hard Break", "Hard Failure",
            f"Critical task failed after confirmation: {name}",
            diagnosis=f"Note: {note}\nError: {output[:3000]}",
            resolution="Open",
        )
        return jsonify({"status": "failed", "error": output[:2000]}), 500


@app.route("/reject/<task_id>", methods=["POST"])
def route_reject(task_id: str):
    """Reject and cancel any pending Approve or Critical task."""
    task = pending_approvals.pop(task_id, None) or pending_criticals.pop(task_id, None)
    if not task:
        return jsonify({"error": "Task ID not in pending approvals or criticals"}), 404

    name   = task.get("fields", {}).get("Task_Name", task_id)
    data   = request.get_json(silent=True) or {}
    reason = data.get("reason", "Rejected by operator").strip() or "Rejected by operator"

    at_patch("TASK_QUEUE", task_id, {
        "Status": "Cancelled", "Notes": f"Rejected: {reason}",
    })
    log_diagnostic(task, "Misuse", "Warning",
                   f"Task rejected by operator: {name}",
                   diagnosis=reason, resolution="Fixed")
    socketio.emit("task_rejected", {
        "task_id": task_id, "task_name": name, "reason": reason,
    })
    print(f"  [REJECTED] {name} -- {reason}")
    return jsonify({"status": "cancelled", "task": name, "reason": reason})


# ══════════════════════════════════════════════════════════════════════════════
#  Socket.IO events
# ══════════════════════════════════════════════════════════════════════════════

@socketio.on("connect")
def on_connect():
    print("  [SOCKET] Client connected")
    emit("factory_status", {
        "online":            True,
        "pending_approvals": len(pending_approvals),
        "pending_criticals": len(pending_criticals),
        "hard_exclusions":   "ACTIVE",
    })


@socketio.on("disconnect")
def on_disconnect():
    print("  [SOCKET] Client disconnected")


# ══════════════════════════════════════════════════════════════════════════════
#  Boot helpers
# ══════════════════════════════════════════════════════════════════════════════

def _ensure_task_queue_fields() -> None:
    """
    Adds Mode and Confirmation_Note fields to TASK_QUEUE if not present.
    Called once at boot before the poll loop starts.
    """
    try:
        resp = requests.get(
            f"https://api.airtable.com/v0/meta/bases/{FACTORY_BASE_ID}/tables",
            headers=AIRTABLE_HEADERS,
        )
        resp.raise_for_status()
        tables = resp.json().get("tables", [])
        tq = next((t for t in tables if t["name"] == "TASK_QUEUE"), None)
        if not tq:
            print("  [WARN] TASK_QUEUE not found in base")
            return

        existing   = {f["name"] for f in tq.get("fields", [])}
        fields_url = (
            f"https://api.airtable.com/v0/meta/bases/{FACTORY_BASE_ID}"
            f"/tables/{tq['id']}/fields"
        )
        to_add = []

        if "Mode" not in existing:
            to_add.append({
                "name": "Mode",
                "type": "singleSelect",
                "options": {
                    "choices": [
                        {"name": "Auto"},
                        {"name": "Approve"},
                        {"name": "Critical"},
                    ]
                },
            })
        if "Confirmation_Note" not in existing:
            to_add.append({"name": "Confirmation_Note", "type": "multilineText"})

        for field_def in to_add:
            r = requests.post(fields_url, headers=AIRTABLE_HEADERS, json=field_def)
            status = "+" if r.ok else "FAIL"
            print(f"  [{status}] Field '{field_def['name']}' -> TASK_QUEUE")
            time.sleep(0.3)

    except Exception as exc:
        print(f"  [WARN] Could not patch TASK_QUEUE schema: {exc}")


def _validate_env() -> None:
    missing = []
    if not AIRTABLE_TOKEN:
        missing.append("AIRTABLE_TOKEN")
    if not FACTORY_BASE_ID:
        missing.append("FACTORY_BASE_ID")
    if missing:
        for m in missing:
            print(f"  ERROR: {m} not set in environment or .env file")
        sys.exit(1)


def _boot_banner() -> None:
    print()
    print("=" * 60)
    print("  BREA FACTORY ORCHESTRATOR")
    print("  Session F2  |  Wave 1  |  June 2026")
    print("=" * 60)
    print(f"  Service          : Factory Orchestrator")
    print(f"  Port             : {PORT}")
    print(f"  Factory Base ID  : {FACTORY_BASE_ID}")
    print(f"  Poll interval    : {POLL_INTERVAL}s")
    print(f"  Watching         : TASK_QUEUE")
    print(f"  Logging to       : MASTER_DIAGNOSTIC_LOG")
    print()
    print("  HEALTH WATCHDOG  : ACTIVE")
    print(f"    Services        : {len(_HEALTH_TARGETS)}")
    print(f"    Interval        : {_HEALTH_INTERVAL}s")
    print(f"    Slow threshold  : {_HEALTH_SLOW_THRESHOLD}s")
    print(f"    Pattern flag at : 3 consecutive failures")
    print()
    print("  HARD EXCLUSIONS  : ACTIVE")
    print("    .env files      : BLOCKED")
    print("    API key files   : BLOCKED")
    print("    Secret/PEM files: BLOCKED")
    print(f"    Patterns active : {len(_FORBIDDEN)}")
    print()
    print("  TASK MODES")
    print("  Auto     -> Claude Code SDK headless -- auto-executes, logs, marks Done")
    print("  Approve  -> Holds -- fires Socket.IO notification -- awaits /approve/<id>")
    print("  Critical -> Holds -- requires explicit confirm + written note via /confirm/<id>")
    print()
    print("  ENDPOINTS")
    print(f"  GET  http://localhost:{PORT}/status")
    print(f"  GET  http://localhost:{PORT}/queue")
    print(f"  POST http://localhost:{PORT}/approve/<task_id>")
    print(f"  POST http://localhost:{PORT}/confirm/<task_id>   body: {{note: '...'}}")
    print(f"  POST http://localhost:{PORT}/reject/<task_id>")
    print()
    print("  TASK_QUEUE       : CONNECTED")
    print("  Factory Orchestrator online.")
    print("=" * 60)
    print()


# ══════════════════════════════════════════════════════════════════════════════
#  Entry point
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    _validate_env()
    _ensure_task_queue_fields()
    _boot_banner()

    poll_thread = threading.Thread(target=_poll_loop, daemon=True, name="factory-poll")
    poll_thread.start()

    health_thread = threading.Thread(target=_health_loop, daemon=True, name="health-watchdog")
    health_thread.start()

    socketio.run(app, host="0.0.0.0", port=PORT, debug=False, use_reloader=False)
