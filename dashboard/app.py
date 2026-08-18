#!/usr/bin/env python3
"""
dashboard/app.py  —  Session F3  |  Factory Dashboard
Flask + SocketIO on port 5003. Bridges live events from Factory Orchestrator (5004).
"""
# Factory orchestrator test - shell=True fix verified 2026-06-11

import datetime
import json
import os
import sys
import time
import threading
import traceback
import uuid
import requests
from flask import Flask, jsonify, render_template, request
from flask_socketio import SocketIO, emit
import socketio as sio_module
import base64


def _load_file(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""

_KB_PATH = r"C:\Users\Danielle\Desktop\BREA_FACTORY\BREA_EMPIRE_MASTER_KNOWLEDGE_BASE.md"
_FACTORY_LOG_PATH = r"C:\Users\Danielle\Desktop\BREA_FACTORY\factory_orchestrator.log"
_PROGRESS_PATHS = {
    "BREA BOSS Progress":        r"C:\Users\Danielle\Desktop\BREA_FACTORY\brea_boss_progress.md",
    "Brea 3 Progress (Wave 10)": r"C:\Users\Danielle\Desktop\BREA_FACTORY\brea_progress-10.md",
    "Brea Phone Blueprint":      r"C:\Users\Danielle\Desktop\BREA_FACTORY\BREA_PHONE_blueprint.md",
}


def _read_factory_log(n: int = 100) -> list:
    """Returns the last n lines of the Factory Orchestrator's log file."""
    try:
        with open(_FACTORY_LOG_PATH, "r", encoding="utf-8", errors="replace") as f:
            return [line.rstrip("\n") for line in f.readlines()[-n:]]
    except FileNotFoundError:
        return []

EMPIRE_KB    = _load_file(_KB_PATH)
PROJECT_DOCS = {}
for _doc_name, _doc_path in _PROGRESS_PATHS.items():
    _doc_content = _load_file(_doc_path)
    if _doc_content:
        PROJECT_DOCS[_doc_name] = _doc_content


try:
    import anthropic
except ImportError:
    anthropic = None

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
except ImportError:
    Observer = None
    FileSystemEventHandler = object

try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))
except ImportError:
    pass

AIRTABLE_TOKEN  = os.environ.get("AIRTABLE_TOKEN", "")
FACTORY_BASE_ID = os.environ.get("FACTORY_BASE_ID", "")
PORT            = 5003
FACTORY_PORT    = 5004

DEEPGRAM_API_KEY    = os.environ.get("DEEPGRAM_API_KEY",    "")
ANTHROPIC_API_KEY   = os.environ.get("ANTHROPIC_API_KEY",   "")
ELEVENLABS_API_KEY  = os.environ.get("ELEVENLABS_API_KEY",  "")
# Brea's real voice (hardcoded in brea_sandbox.py, not .env) — was falling back to
# ElevenLabs' stock "Bella" id whenever ELEVENLABS_VOICE_ID wasn't set in .env.
ELEVENLABS_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "x8syuETaTA9JYwAbE2JM")

# Fish Audio — ported from Brea 3's proven speak() (brea_sandbox.py:3602-3631).
# Voice-turn TTS only; typed /respond text stays on the old ElevenLabs path unused.
TTS_PROVIDER      = os.environ.get("TTS_PROVIDER",      "elevenlabs")
FISH_API_KEY      = os.environ.get("FISH_API_KEY",      "")
FISH_REFERENCE_ID = os.environ.get("FISH_REFERENCE_ID", "")
FISH_MODEL        = os.environ.get("FISH_MODEL",        "s2.1-pro-free")

try:
    from fish_audio_sdk import Session as _FishSession, TTSRequest as _FishTTSRequest
    FISH_SDK_AVAILABLE = True
except ImportError:
    _FishSession = None
    _FishTTSRequest = None
    FISH_SDK_AVAILABLE = False

def _build_system_prompt() -> str:
    base = (
        "You are Brea — Danielle's Chief of Staff and the intelligence layer of the Brea Empire. "
        "You have live access to the empire's state: capability registry, task queue, diagnostic "
        "log, and tenant registry. You know what's running, what's broken, and what's next.\n\n"
        "You speak warmly and directly. You match Danielle's energy — sharp when she's sharp, "
        "easy when she's easy. You never say 'certainly' or 'great question'. You don't hedge or "
        "pad. You give her exactly what she needs to move.\n\n"
        "When something is broken or at risk, you surface it clearly without drama. When everything "
        "is running clean, you say so. You never pretend to know something you don't.\n\n"
        "Never use markdown formatting, asterisks, bold, or italic markers in your responses. "
        "Speak in plain conversational sentences only.\n\n"
        "You know every active project, what was last built, what is next, and what is blocked. "
        "When Danielle mentions any project by name you already know its current state. "
        "You never ask Danielle to re-explain context you already have."
    )
    parts = [base]
    if EMPIRE_KB:
        parts.append(
            f"\n\n--- BREA EMPIRE MASTER KNOWLEDGE BASE ---\n{EMPIRE_KB}\n--- END KNOWLEDGE BASE ---"
        )
    for doc_name, doc_content in PROJECT_DOCS.items():
        parts.append(f"\n\n--- {doc_name.upper()} ---\n{doc_content}\n--- END {doc_name.upper()} ---")
    return "".join(parts)

BREA_SYSTEM_PROMPT = _build_system_prompt()

AT_HEADERS = {
    "Authorization": f"Bearer {AIRTABLE_TOKEN}",
    "Content-Type":  "application/json",
}

app      = Flask(__name__, static_folder='static')
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")
_voice_buffers: dict = {}   # socket-sid -> list[bytes]
_voice_mime: dict = {}      # socket-sid -> exact MediaRecorder mimeType reported by the client
_interrupt_flags: dict = {} # socket-sid -> bool, set by voice_interrupt
_interrupt_global = {"set": False}  # interrupt flag for the broadcast /respond flow

SESSION_ID = str(uuid.uuid4())


def at_get(table, formula="", max_records=100, fetch_all=False):
    url    = f"https://api.airtable.com/v0/{FACTORY_BASE_ID}/{table}"
    if not fetch_all:
        params = {"maxRecords": max_records}
        if formula:
            params["filterByFormula"] = formula
        resp = requests.get(url, headers=AT_HEADERS, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json().get("records", [])

    # fetch_all: page through offset cursor until exhausted, capped so a
    # mistakenly-wide formula can never turn into a full-table scan.
    records, offset, PAGE_CAP = [], None, 5000
    while len(records) < PAGE_CAP:
        params = {"pageSize": 100}
        if formula:
            params["filterByFormula"] = formula
        if offset:
            params["offset"] = offset
        resp = requests.get(url, headers=AT_HEADERS, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break
    return records


def at_create(table, fields):
    url  = f"https://api.airtable.com/v0/{FACTORY_BASE_ID}/{table}"
    resp = requests.post(url, headers=AT_HEADERS, json={"records": [{"fields": fields}]}, timeout=10)
    resp.raise_for_status()
    return resp.json()


def _log_conversation(user_message: str, brea_response: str) -> None:
    try:
        at_create("CONVERSATION_LOG", {
            "User_Message":  user_message,
            "Brea_Response": brea_response,
            "Timestamp":     datetime.datetime.utcnow().isoformat() + "Z",
            "Session_ID":    SESSION_ID,
        })
    except Exception as exc:
        print(f"  [CONVERSATION_LOG] Write failed: {exc}")


def _get_empire_context() -> str:
    """Fetches live empire state from Airtable for Brea's system prompt."""
    parts = []
    try:
        caps    = at_get("MASTER_CAPABILITY_REGISTRY", max_records=200)
        active  = sum(1 for r in caps if r.get("fields", {}).get("Status") == "Active")
        pending = sum(1 for r in caps
                      if "Pending" in str(r.get("fields", {}).get("Status", "")))
        parts.append(f"Capabilities: {active} active, {pending} pending build.")
    except Exception:
        pass
    try:
        tasks    = at_get("TASK_QUEUE")
        in_queue = [r for r in tasks
                    if r.get("fields", {}).get("Status") in ("Queued", "In Progress")]
        if in_queue:
            names = [r.get("fields", {}).get("Task_Name", "—") for r in in_queue[:5]]
            parts.append(f"Task queue ({len(in_queue)} active): {', '.join(names)}.")
        else:
            parts.append("Task queue is empty.")
    except Exception:
        pass
    try:
        issues = at_get("MASTER_DIAGNOSTIC_LOG",
                        formula="{Resolution_Status}='Open'", max_records=20)
        if issues:
            msgs = [r.get("fields", {}).get("Error_Message", "—") for r in issues[:5]]
            parts.append(f"Open issues ({len(issues)}): {'; '.join(msgs)}.")
            log_lines = _read_factory_log(30)
            if log_lines:
                parts.append("Recent Factory Orchestrator log:\n" + "\n".join(log_lines))
        else:
            parts.append("No open issues.")
    except Exception:
        pass
    return "\n".join(parts) if parts else "Empire context unavailable at this time."


# ── Page ──────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


# ── Data APIs ─────────────────────────────────────────────────────────────────

@app.route("/api/empire-status")
def empire_status():
    try:
        caps     = at_get("MASTER_CAPABILITY_REGISTRY", fetch_all=True)
        active   = sum(1 for r in caps
                       if r.get("fields", {}).get("Status") == "Active")
        pending  = sum(1 for r in caps
                       if "Pending" in str(r.get("fields", {}).get("Status", "")))
        tasks    = at_get("TASK_QUEUE")
        in_queue = sum(1 for r in tasks
                       if r.get("fields", {}).get("Status") in ("Queued", "In Progress"))
        return jsonify({
            "active_capabilities": active,
            "pending_build":       pending,
            "tasks_in_queue":      in_queue,
            "open_issues":         None,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/tenants")
def tenants():
    try:
        records = at_get("TENANT_REGISTRY")
        return jsonify([
            {
                "id":     r["id"],
                "name":   (r.get("fields", {}).get("Tenant_Name")
                           or r.get("fields", {}).get("Name", "—")),
                "tier":   r.get("fields", {}).get("Tier", "—"),
                "status": r.get("fields", {}).get("Status", "Unknown"),
            }
            for r in records
        ])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/activity")
def activity():
    try:
        records = at_get(
            "MASTER_DIAGNOSTIC_LOG",
            formula="IS_AFTER(CREATED_TIME(), DATEADD(NOW(), -1, 'days'))",
            fetch_all=True,
        )
        records.sort(key=lambda r: r.get("createdTime", ""), reverse=True)
        return jsonify([
            {
                "id":         r["id"],
                "name":       r.get("fields", {}).get("Error_Name", "—"),
                "category":   r.get("fields", {}).get("Error_Category", "—"),
                "type":       r.get("fields", {}).get("Error_Type", "—"),
                "message":    (r.get("fields", {}).get("Error_Message", "") or "")[:200],
                "instance":   r.get("fields", {}).get("Instance_ID", "—"),
                "resolution": r.get("fields", {}).get("Resolution_Status", "Open"),
                "created":    r.get("createdTime", ""),
            }
            for r in records[:20]
        ])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/logs")
def logs():
    """Returns the last 100 lines of the Factory Orchestrator's terminal output."""
    return jsonify({"lines": _read_factory_log(100)})


@app.route("/api/tasks")
def tasks():
    try:
        records = at_get("TASK_QUEUE", formula="OR({Status}='Queued', {Status}='In Progress')")
        records.sort(key=lambda r: r.get("createdTime", ""), reverse=True)
        return jsonify([
            {
                "id":          r["id"],
                "name":        r.get("fields", {}).get("Task_Name", "—"),
                "mode":        r.get("fields", {}).get("Mode", "Auto"),
                "status":      r.get("fields", {}).get("Status", "—"),
                "description": (r.get("fields", {}).get("Description", "") or "")[:200],
                "module":      r.get("fields", {}).get("Module", ""),
                "priority":    r.get("fields", {}).get("Priority", ""),
                "created":     r.get("createdTime", ""),
            }
            for r in records
        ])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/conversation-history")
def conversation_history():
    try:
        url    = f"https://api.airtable.com/v0/{FACTORY_BASE_ID}/CONVERSATION_LOG"
        params = {
            "maxRecords": 20,
            "sort[0][field]": "Timestamp",
            "sort[0][direction]": "desc",
        }
        resp = requests.get(url, headers=AT_HEADERS, params=params, timeout=10)
        resp.raise_for_status()
        records = resp.json().get("records", [])
        return jsonify([
            {
                "user":      r.get("fields", {}).get("User_Message", ""),
                "brea":      r.get("fields", {}).get("Brea_Response", ""),
                "timestamp": r.get("fields", {}).get("Timestamp", ""),
            }
            for r in records
        ])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/setup-conversation-log")
def setup_conversation_log():
    try:
        url     = f"https://api.airtable.com/v0/meta/bases/{FACTORY_BASE_ID}/tables"
        payload = {
            "name": "CONVERSATION_LOG",
            "fields": [
                {"name": "Session_ID",    "type": "singleLineText"},
                {"name": "User_Message",  "type": "multilineText"},
                {"name": "Brea_Response", "type": "multilineText"},
                {"name": "Timestamp",     "type": "singleLineText"},
            ],
        }
        resp = requests.post(url, headers=AT_HEADERS, json=payload, timeout=10)
        resp.raise_for_status()
        return jsonify({"status": "created", "table": resp.json()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


_SPEC_SYSTEM = (
    "You are Brea — Danielle's Chief of Staff and architect for the Brea Empire. "
    "You already know the full empire architecture, every active project, what has been built, "
    "and what is pending. Danielle is describing a feature she wants built.\n\n"
    "Your job is a three-phase conversation:\n\n"
    "Phase 1 — Clarify: Ask 2-3 focused questions to fill any gaps you cannot answer from "
    "context you already have. Never ask what you already know. Never repeat a question she "
    "already answered.\n\n"
    "Phase 2 — Confirm: Once you have what you need, confirm your understanding in 2-3 plain "
    "sentences before generating the spec.\n\n"
    "Phase 3 — Spec: When you have full clarity, output exactly the token READY_TO_SPEC on "
    "its own line, then immediately output the JSON spec (no markdown fences, no explanation):\n"
    "{\n"
    '  "capability_name": "...",\n'
    '  "module": "...",\n'
    '  "platform": "Brea3 | BOSS | Factory",\n'
    '  "description": "...",\n'
    '  "files_to_touch": ["..."],\n'
    '  "tasks": [\n'
    '    {"task_name": "...", "mode": "Auto|Approve|Critical", "description": "..."}\n'
    "  ],\n"
    '  "dependencies": ["..."]\n'
    "}\n\n"
    "Mode rules: Auto = fully automated. Approve = Danielle approves before running. "
    "Critical = Danielle provides written confirmation.\n\n"
    "Never use markdown formatting. Never pad. Never ask her to re-explain context you have."
)


@app.route("/api/spec", methods=["POST"])
def spec_chat():
    data     = request.get_json(silent=True) or {}
    messages = data.get("messages", [])
    if not messages:
        return jsonify({"error": "No messages provided"}), 400
    if not ANTHROPIC_API_KEY:
        return jsonify({"error": "ANTHROPIC_API_KEY not configured"}), 500
    if anthropic is None:
        return jsonify({"error": "anthropic package not installed"}), 500

    system_msg = _SPEC_SYSTEM
    if EMPIRE_KB:
        system_msg += f"\n\n--- BREA EMPIRE MASTER KNOWLEDGE BASE ---\n{EMPIRE_KB}\n--- END ---"
    for doc_name, doc_content in PROJECT_DOCS.items():
        system_msg += f"\n\n--- {doc_name.upper()} ---\n{doc_content}\n--- END ---"

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        msg    = client.messages.create(
            model      = "claude-sonnet-4-6",
            max_tokens = 2048,
            system     = system_msg,
            messages   = messages,
        )
        reply = msg.content[0].text.strip()
    except Exception as e:
        return jsonify({"error": f"Claude error: {e}"}), 500

    if "READY_TO_SPEC" not in reply:
        return jsonify({"reply": reply, "ready": False})

    before_token = reply.split("READY_TO_SPEC", 1)[0].strip()
    after_token  = reply.split("READY_TO_SPEC", 1)[1].strip()
    if after_token.startswith("```"):
        parts       = after_token.split("```")
        after_token = parts[1].lstrip("json").strip() if len(parts) > 1 else after_token

    raw = ""
    try:
        raw  = after_token
        spec = json.loads(raw)
    except json.JSONDecodeError as e:
        return jsonify({
            "reply": before_token or reply, "ready": False,
            "error": f"Spec JSON parse failed: {e}", "raw": raw,
        }), 500

    queued, failed = [], []
    for task in spec.get("tasks", []):
        record = {"fields": {
            "Task_Name":   task.get("task_name", ""),
            "Mode":        task.get("mode", "Auto"),
            "Status":      "Queued",
            "Description": task.get("description", ""),
        }}
        try:
            r = requests.post(
                f"https://api.airtable.com/v0/{FACTORY_BASE_ID}/TASK_QUEUE",
                headers=AT_HEADERS, json=record, timeout=10,
            )
            r.raise_for_status()
            queued.append(task.get("task_name", ""))
        except Exception as e:
            failed.append({"task": task.get("task_name", ""), "error": str(e)})

    confirmation = (
        before_token if before_token
        else f"Spec locked. Queued {len(queued)} task{'s' if len(queued) != 1 else ''} in Airtable."
    )

    return jsonify({
        "reply":              confirmation,
        "ready":              True,
        "spec":               spec,
        "tasks_queued":       len(queued),
        "tasks_queued_names": queued,
        "tasks_failed":       failed,
    })


@app.route("/api/health")
def health():
    services = {
        "brea3":   ("Brea 3",              "http://localhost:5000/"),
        "boss":    ("BOSS",                "https://web-production-524676.up.railway.app/health"),
        "factory": ("Factory Orchestrator", "http://localhost:5004/status"),
    }
    result = {}
    for key, (name, url) in services.items():
        try:
            r = requests.get(url, timeout=5)
            result[key] = {"name": name, "online": r.status_code == 200}
        except Exception:
            result[key] = {"name": name, "online": False}
    return jsonify(result)


# ── Action proxies (ngrok-safe — browser never hits port 5004 directly) ───────

@app.route("/api/approve/<task_id>", methods=["POST"])
def approve_task(task_id):
    try:
        r = requests.post(f"http://localhost:{FACTORY_PORT}/approve/{task_id}",
                          timeout=30)
        return jsonify(r.json()), r.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/reject/<task_id>", methods=["POST"])
def reject_task(task_id):
    try:
        data = request.get_json(silent=True) or {}
        r    = requests.post(f"http://localhost:{FACTORY_PORT}/reject/{task_id}",
                             json=data, timeout=10)
        return jsonify(r.json()), r.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/confirm/<task_id>", methods=["POST"])
def confirm_task(task_id):
    try:
        data = request.get_json(silent=True) or {}
        r    = requests.post(f"http://localhost:{FACTORY_PORT}/confirm/{task_id}",
                             json=data, timeout=30)
        return jsonify(r.json()), r.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Voice routes ──────────────────────────────────────────────────────────────

@app.route("/respond", methods=["POST"])
def respond():
    import re
    data       = request.get_json(silent=True) or {}
    transcript = (data.get("transcript") or "").strip()
    source     = data.get("source", "voice")          # "voice" or "spec"
    speak_text = (data.get("text") or "").strip()      # pre-generated — skips Claude

    if speak_text:
        response_text = speak_text
    else:
        if not transcript:
            return jsonify({"error": "No transcript provided"}), 400
        if not ANTHROPIC_API_KEY:
            return jsonify({"error": "ANTHROPIC_API_KEY not configured"}), 500
        if anthropic is None:
            return jsonify({"error": "anthropic package not installed — run: pip install anthropic"}), 500

        empire_ctx  = _get_empire_context()
        system_msg  = f"{BREA_SYSTEM_PROMPT}\n\nLive Empire State:\n{empire_ctx}"
        full_tokens = []

        try:
            client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            with client.messages.stream(
                model="claude-sonnet-4-6",
                max_tokens=1024,
                system=system_msg,
                messages=[{"role": "user", "content": transcript}],
            ) as stream:
                for token in stream.text_stream:
                    if _interrupt_global["set"]:
                        _interrupt_global["set"] = False
                        socketio.emit("voice_interrupted", {"source": source})
                        return jsonify({"status": "interrupted"})
                    full_tokens.append(token)
                    socketio.emit("brea_token", {"token": token, "source": source})
        except Exception as exc:
            return jsonify({"error": f"Claude error: {exc}"}), 500

        response_text = "".join(full_tokens)
        response_text = re.sub(r'\*+', '', response_text).strip()

    socketio.emit("transcript_update", {"text": response_text, "speaker": "brea", "source": source})

    if transcript:
        _log_conversation(transcript, response_text)

    if _interrupt_global["set"]:
        _interrupt_global["set"] = False
        socketio.emit("voice_interrupted", {"source": source})
        return jsonify({"status": "interrupted"})

    if not ELEVENLABS_API_KEY:
        socketio.emit("audio_chunk", {
            "data": "", "done": True, "source": source,
            "error": "ELEVENLABS_API_KEY not configured — text response only",
        })
        return jsonify({"status": "ok", "response": response_text[:500]})

    try:
        tts_resp = requests.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}/stream",
            headers={
                "xi-api-key":   ELEVENLABS_API_KEY,
                "Content-Type": "application/json",
            },
            json={
                "text":           response_text,
                "model_id":       "eleven_turbo_v2",
                "voice_settings": {"stability": 0.5, "similarity_boost": 0.8},
            },
            stream=True,
            timeout=30,
        )
        if tts_resp.status_code == 200:
            audio_bytes = b"".join(c for c in tts_resp.iter_content(chunk_size=4096) if c)
            socketio.emit("audio_chunk", {
                "data": base64.b64encode(audio_bytes).decode(),
                "done": True,
                "source": source,
            })
        else:
            err = tts_resp.text[:200]
            socketio.emit("audio_chunk", {
                "data": "", "done": True, "source": source,
                "error": f"ElevenLabs {tts_resp.status_code}: {err}",
            })
    except Exception as exc:
        socketio.emit("audio_chunk", {"data": "", "done": True, "source": source, "error": str(exc)})

    return jsonify({"status": "ok", "response": response_text[:500]})


# ── Socket.IO ─────────────────────────────────────────────────────────────────

@socketio.on("connect")
def on_connect():
    emit("dashboard_ready", {"port": PORT})


@socketio.on("disconnect")
def on_disconnect():
    _voice_buffers.pop(request.sid, None)
    _voice_mime.pop(request.sid, None)
    _interrupt_flags.pop(request.sid, None)


@socketio.on("voice_interrupt")
def on_voice_interrupt():
    sid = request.sid
    _interrupt_flags[sid] = True
    _interrupt_global["set"] = True


@socketio.on("audio_chunk")
def on_audio_chunk(data):
    sid   = request.sid
    chunk = data.get("chunk", "")
    if not chunk:
        return
    raw = base64.b64decode(chunk)
    if sid not in _voice_buffers:
        _voice_buffers[sid] = []
    _voice_buffers[sid].append(raw)
    mime_type = (data.get("mimeType") or "").strip()
    if mime_type:
        _voice_mime[sid] = mime_type
    total = sum(len(c) for c in _voice_buffers[sid])
    print(f"[STREAM] Chunk received {len(raw)} bytes")
    print(f"[STREAM] Buffer total {total} bytes")


@socketio.on("voice_stop")
def on_voice_stop():
    sid = request.sid

    audio_data = b"".join(_voice_buffers.get(sid, []))
    # Use the exact mimetype the browser's MediaRecorder reported — no more
    # guessing across 4 content-types, which was the source of spurious 400s.
    content_type = _voice_mime.get(sid) or "audio/webm"
    print(f"[DEEPGRAM] Sending {len(audio_data)} bytes as {content_type!r}")

    transcript = ""
    try:
        resp = requests.post(
            "https://api.deepgram.com/v1/listen?model=nova-2&punctuate=true&smart_format=true",
            headers={
                "Authorization": f"Token {os.environ.get('DEEPGRAM_API_KEY', '')}",
                "Content-Type": content_type,
            },
            data=audio_data,
            timeout=20,
        )
        print(f"[DEEPGRAM] Status: {resp.status_code}")
        if resp.status_code == 200:
            result = resp.json()
            transcript = (
                result.get("results", {})
                .get("channels", [{}])[0]
                .get("alternatives", [{}])[0]
                .get("transcript", "")
                .strip()
            )
            print(f"[DEEPGRAM] Success: {transcript}")
        else:
            print(f"[DEEPGRAM] Rejected: {resp.text[:300]}")
    except Exception as e:
        print(f"[DEEPGRAM] Exception: {e}")
        traceback.print_exc()

    _voice_buffers[sid] = []
    _voice_mime.pop(sid, None)

    if not transcript:
        emit("voice_empty", {})
        return
    emit("transcript_update", {"text": transcript, "speaker": "user"})
    turn_id = str(uuid.uuid4())
    threading.Thread(
        target=_respond_from_voice,
        args=(transcript, sid, turn_id),
        daemon=True,
    ).start()


def _speak_fish_pcm(text: str, turn_id: str, sid: str) -> None:
    """Stream a voice-turn reply through Fish as raw PCM16 mono @ 24kHz,
    relaying each chunk to this browser tab as 'audio_stream_chunk'.

    Ported from Brea 3's proven speak() (brea_sandbox.py:3602-3631) — post-hoc,
    called once the full reply text is known (NOT Route B's incremental
    per-token synthesis). Uses Session.tts() (matching speak() exactly), not
    WebSocketSession, since the full text is already assembled by the time
    this runs. Checks _interrupt_flags[sid] between chunks so the existing
    Stop/interrupt button can cut playback short, same as ElevenLabs did.
    """
    if not FISH_SDK_AVAILABLE or not FISH_API_KEY or not FISH_REFERENCE_ID:
        socketio.emit("audio_stream_chunk",
                      {"turn_id": turn_id, "audio_b64": "", "done": True}, to=sid)
        return
    try:
        session = _FishSession(FISH_API_KEY)
        fish_request = _FishTTSRequest(text=text, format="pcm", sample_rate=24000,
                                        reference_id=FISH_REFERENCE_ID)
        for chunk in session.tts(fish_request, backend=FISH_MODEL):
            if _interrupt_flags.get(sid):
                _interrupt_flags[sid] = False
                socketio.emit("voice_interrupted", {"source": "voice"}, to=sid)
                socketio.emit("audio_stream_chunk",
                              {"turn_id": turn_id, "audio_b64": "", "done": True}, to=sid)
                return
            if chunk:
                socketio.emit("audio_stream_chunk", {
                    "turn_id": turn_id,
                    "audio_b64": base64.b64encode(chunk).decode("ascii"),
                    "done": False,
                }, to=sid)
    except Exception as e:
        print(f"⚠️ Fish TTS stream error: {e}")
        traceback.print_exc()
    socketio.emit("audio_stream_chunk",
                  {"turn_id": turn_id, "audio_b64": "", "done": True}, to=sid)


def _respond_from_voice(transcript: str, sid: str, turn_id: str) -> None:
    import re
    if not ANTHROPIC_API_KEY or anthropic is None:
        socketio.emit("voice_error", {"error": "ANTHROPIC_API_KEY not configured"}, to=sid)
        return
    empire_ctx  = _get_empire_context()
    system_msg  = f"{BREA_SYSTEM_PROMPT}\n\nLive Empire State:\n{empire_ctx}"
    full_tokens: list = []
    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        with client.messages.stream(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=system_msg,
            messages=[{"role": "user", "content": transcript}],
        ) as stream:
            for token in stream.text_stream:
                if _interrupt_flags.get(sid):
                    _interrupt_flags[sid] = False
                    socketio.emit("voice_interrupted", {"source": "voice"}, to=sid)
                    return
                full_tokens.append(token)
                socketio.emit("brea_token", {"token": token, "source": "voice"}, to=sid)
    except Exception as exc:
        traceback.print_exc()
        socketio.emit("voice_error", {"error": str(exc)}, to=sid)
        return

    response_text = re.sub(r'\*+', '', "".join(full_tokens)).strip()
    socketio.emit("transcript_update",
                  {"text": response_text, "speaker": "brea", "source": "voice"}, to=sid)

    _log_conversation(transcript, response_text)

    if _interrupt_flags.get(sid):
        _interrupt_flags[sid] = False
        socketio.emit("voice_interrupted", {"source": "voice"}, to=sid)
        return

    if TTS_PROVIDER == "fish":
        _speak_fish_pcm(response_text, turn_id, sid)
        return

    # ── ElevenLabs fallback (unchanged) — only reached if TTS_PROVIDER != "fish" ──
    if not ELEVENLABS_API_KEY:
        socketio.emit("audio_chunk", {"data": "", "done": True, "source": "voice"}, to=sid)
        return
    try:
        tts_resp = requests.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}/stream",
            headers={"xi-api-key": ELEVENLABS_API_KEY, "Content-Type": "application/json"},
            json={
                "text":           response_text,
                "model_id":       "eleven_turbo_v2",
                "voice_settings": {"stability": 0.5, "similarity_boost": 0.8},
            },
            stream=True, timeout=30,
        )
        if tts_resp.status_code == 200:
            audio_bytes = b"".join(c for c in tts_resp.iter_content(chunk_size=4096) if c)
            socketio.emit("audio_chunk", {
                "data": base64.b64encode(audio_bytes).decode(),
                "done": True, "source": "voice",
            }, to=sid)
        else:
            socketio.emit("audio_chunk", {
                "data": "", "done": True, "source": "voice",
                "error": f"ElevenLabs {tts_resp.status_code}: {tts_resp.text[:200]}",
            }, to=sid)
    except Exception as exc:
        traceback.print_exc()
        socketio.emit("audio_chunk",
                      {"data": "", "done": True, "source": "voice", "error": str(exc)}, to=sid)


# ── Factory bridge — relays 5004 events to all connected browser clients ──────

factory_client = sio_module.Client(logger=False, engineio_logger=False)

_RELAY = [
    "approve_required", "critical_required",
    "task_complete", "task_failed", "task_blocked",
    "task_rejected", "factory_status",
    "health_ok", "health_warning", "health_critical",
    "brea_token", "transcript_update", "audio_chunk",
]


def _register_relay(event_name):
    @factory_client.on(event_name)
    def _handler(data):
        socketio.emit(event_name, data)


for _ev in _RELAY:
    _register_relay(_ev)


@factory_client.on("connect")
def on_factory_connect():
    print(f"  [BRIDGE] Connected to Factory Orchestrator on port {FACTORY_PORT}")


@factory_client.on("disconnect")
def on_factory_disconnect():
    print("  [BRIDGE] Factory connection lost — live events paused")


def _connect_bridge():
    try:
        factory_client.connect(f"http://localhost:{FACTORY_PORT}")
        factory_client.wait()
    except Exception as e:
        print(f"  [BRIDGE] Could not reach Factory on {FACTORY_PORT}: {e}")


# ── Auto-restart watchdog ───────────────────────────────────────────────────

if Observer:
    class _ReloadHandler(FileSystemEventHandler):
        def __init__(self, watch_path):
            self._watch_path   = os.path.abspath(watch_path)
            self._last_restart = 0.0

        def on_modified(self, event):
            if os.path.abspath(event.src_path) != self._watch_path:
                return
            now = time.time()
            if now - self._last_restart < 1:
                return
            self._last_restart = now
            print("\n  [WATCHDOG] app.py changed — restarting...\n")
            os.execv(sys.executable, [sys.executable] + sys.argv)

    def _start_watchdog():
        handler  = _ReloadHandler(__file__)
        observer = Observer()
        observer.schedule(handler, path=os.path.dirname(os.path.abspath(__file__)), recursive=False)
        observer.start()
        print("  [WATCHDOG] Watching app.py for changes...")


# ── Boot ──────────────────────────────────────────────────────────────────────

def _check_conversation_log() -> None:
    try:
        resp = requests.get(
            f"https://api.airtable.com/v0/meta/bases/{FACTORY_BASE_ID}/tables",
            headers=AT_HEADERS, timeout=10,
        )
        resp.raise_for_status()
        tables = resp.json().get("tables", [])
        if not any(t["name"] == "CONVERSATION_LOG" for t in tables):
            print(f"\n  [SETUP] CONVERSATION_LOG table not found in Airtable.")
            print(f"  [SETUP] Visit http://localhost:{PORT}/api/setup-conversation-log once to create it.\n")
    except Exception as exc:
        print(f"  [SETUP] Could not verify CONVERSATION_LOG table: {exc}")


if __name__ == "__main__":
    print(f"\n  BREA FACTORY DASHBOARD  |  Session F3  |  http://localhost:{PORT}\n")
    _check_conversation_log()
    threading.Thread(target=_connect_bridge, daemon=True, name="factory-bridge").start()
    if Observer:
        # WATCHDOG DISABLED 2026-08-03 — root cause of "alive but deaf" hangs.
        # os.execv restart fires on spurious Windows on_modified events for app.py,
        # restarting the server mid-voice-turn and severing Fish TTS audio.
        # Do NOT re-enable. Use an explicit manual restart for code changes.
        # _start_watchdog()
        print("  [WATCHDOG] Disabled by design (see comment) — auto-restart off.")
    else:
        print("  [WATCHDOG] watchdog package not installed — auto-restart disabled (pip install watchdog)")
    socketio.run(app, host="0.0.0.0", port=PORT, debug=False, use_reloader=False)
