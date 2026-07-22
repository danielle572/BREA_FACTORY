# BREA EMPIRE MASTER KNOWLEDGE BASE
### Version 2.5 — Updated July 3, 2026
### Reflects: v2.4 + **MASTER_CAPABILITY_REGISTRY 403 RESOLVED and phone-proven** (root cause = base mismatch, not PAT scope — the master registry lives in the Factory base; the Brea 3 brain now reads its own `Scope='Brea 3'` slice). Capability self-knowledge restored. New build arc added: **Document Lifecycle & Intelligent Filing (Addendum v6)**, sequenced ahead of the Finance Cognitive Bridge.

> **Source-of-truth note:** Brea 3 = `BREA3_STATUS_AND_NEXT_2026-07-03.md` (close of July 2 → next build). BOSS + Factory sections are **carried forward from v2.1 (June 21) and were NOT touched this session** — treat as unverified until a fresh progress doc lands. Verify the file on disk, not what a doc claims; if Aurora differs, Aurora wins.

---

## 0. EMPIRE OVERVIEW

**Founder:** Danielle Adams (Dee / Danny / Dani). Brea's nickname for Dee is **"Danny"** — Brea chose it, keep it.

**North Stars (silent background filters):**
- Generational Wealth & Family
- Operational Excellence — Boujie Girl
- Scaling & Freedom — The AI Agency

| System | Port | Purpose | Status (July 3) |
|---|---|---|---|
| Brea 3 (personal) | 5000 / 5001 | Personal AI Chief of Staff | Active build — mid-Wave 14 |
| The BOSS | 5002 | Business operations platform (Boujie Girl) | Carried from June 21 — Staff Portal L0 done; **July 1 launch status unconfirmed here** |
| Brea Factory | 5003 / 5004 | Infrastructure hub + orchestrator | Last touched June 9–10 — verify on Aurora |
| BREA_PHONE | — | Standalone voice PoC + KB | Blueprint; first end-to-end test pending |

**Fifth context vault:** Wellbeing — never deprioritized.

**Isolation is absolute:** BOSS (5002) and Factory (5003/5004) are strictly isolated from Brea 3 (5000/5001). Never mix in one Claude Code session. Airtable never appears in any user-facing interface.

---

## 1. HARDWARE & INFRASTRUCTURE

- **Server:** Dell Aurora R16, Windows 11 · **Test:** Pixel (phone) · **Secondary:** Surface Pro 11
- **Access:** ngrok (phone). Tunnels: `brea3.ngrok.app`, `brea-working.ngrok.app`, `theboss.ngrok.app`. Tailscale NOT compatible with Socket.IO WebSocket upgrades.
- **Launcher:** `BREA_LAUNCHER` folder on Aurora Desktop — `restart_brea3.bat`, `restart_boss.bat`, `restart_factory.bat`, `restart_ngrok.bat`, `Start_Factory.bat`. Kill by PID (port-scoped) — **never** `taskkill /f /im python.exe`. ngrok managed via consolidated `ngrok.yml`.

**Port assignments — locked:** 5000 Brea 3 webapp · 5001 Brea 3 brain · 5002 The BOSS · 5003 Factory Dashboard · 5004 Factory Orchestrator

**Two-process / two-.env reality (Brea 3):** webapp (5000) and brain (5001) are separate processes with separate .env files. Both must carry the same ElevenLabs/Deepgram keys or surfaces silently fail. A clean restart must show a **single PID on 5000 AND 5001**.

---

## 2. BRAND — LOCKED

```
Background #f8f7f7  bg2 #e9e7e5  surface #ffffff  border #d9d9d9
Text #2a2a2a  text2 #616060  Accent #c8a96e  accent2 #f0e6d3  accent3 #faf5ee
Header #1e1e1e (fixed)
Fonts: DM Sans (body), Tenor Sans (display), DM Mono (mono), Blesta Script (greeting only)
```
- `--brea-accent` repaints UI dynamically · Airtable **never** named in user-facing UI · gold/cream system, no blue.

---

## 3. BREA 3 — PERSONAL AI CHIEF OF STAFF

**Status:** ACTIVE BUILD, mid-Wave 14 (July 3). Personal AI executive assistant, Dee's primary daily-use system.

**File locations:**
```
C:\Users\Danielle\Desktop\BREA_BRAIN\brea_sandbox.py     — brain (port 5001); NO git repo
C:\Users\Danielle\Desktop\BREA_BRAIN\.env                — brain keys
C:\Users\Danielle\Desktop\BREA_WEBAPP\app.py             — Flask (port 5000)
C:\Users\Danielle\Desktop\BREA_WEBAPP\finance.py         — Finance Widget, served at /fin
C:\Users\Danielle\Desktop\BREA_WEBAPP\static\voice-session.js — live voice (?v=24)
C:\Users\Danielle\Desktop\BREA_WEBAPP\static\chat.js     — chat playback
C:\Users\Danielle\Desktop\BREA_WEBAPP\templates\index.html
C:\Users\Danielle\Desktop\BREA_WEBAPP\SESSION_HANDOFF.md — read FIRST (known stale — backfill owed)
```
**Base:** `app3Vc2FkBAznznuV` · **Voice:** ElevenLabs `x8syuETaTA9JYwAbE2JM`

### SHIPPED & CONFIRMED — Active (do not rebuild)
- **Post-barge-in audio-drop fix** — **Active, proven on phone (July 2).** Root cause was `_bargeInFired`, a single shared boolean in `static/voice-session.js` reset only at `brea_reply`: the turn right after a barge-in could have all its `audio_stream_chunk` events arrive and finish *before* `brea_reply` reset the flag, silently dropping that turn's audio. Replaced with a **turn-scoped `_interruptedTurnId`** (captured `= activeId` at `onBargeIn`; gates match on `record_id` / `turn_id`). Verified: for a given turn `record_id === turn_id` (single `audio_key` flows into both field names) and the `chunk_ready` path is dead code — so no namespace edge; a fresh uuid never collides, so no reset needed. Six line-level edits, one variable. Cache-buster `?v=23 → ?v=24`. Device confirmed: after interrupting Brea, the NEXT turn plays audio; normal (non-interrupted) turns still play. **Committed as `d0affb6`** ("Fix post-barge-in audio drop: scope interrupt flag to the turn, not global"). Local `master` is 1 commit ahead of `origin/master` — Dee chose (July 3) to **leave it unpushed** for now. `finance.py` remains the only other modified file (unstaged, untouched per rule).
- **Reminders tab list view** — Active (July 1). Reads REMINDERS, active reminders soonest-first, mark-done (soft, `at_delete`) + true delete. **Recurrence TODO left in code** (repeating reminders vanish on "done" instead of advancing — flagged, out of scope).
- **Finance Widget (Phases 1–11)** — Active. `finance.py` at `/fin`, all tabs except **TAX** (blocked on the BOSS Finance Bridge). Airtable rules locked (date RANGE filters, booleans as `is True`, `finJSON` helper, `typecast:true`).
- **Chat-Surface Rewrite (Build 2)** — Active + device-confirmed. Voice turns render through the same `appendMessage` path as text (unified `#messages` ribbon). Full-screen `#vsOverlay`/`#vsTranscript` takeover removed; pulse + state label relocated into an always-visible `#ribbon-header` chip. Per-message timestamps on text and voice bubbles. Mic-tap-to-close (no separate End Session button). State chip updates live, collapsed + expanded. Committed `c3338f6`, pushed to origin/master (the later `?v=24` audio-drop edits sit uncommitted on top of this).

### SHIPPED BUT NOT YET CONFIRMED — proof-gate pending (NOT Active)
- **Spoken end-phrase detection** ("that's all" / "end session") + **mid-sentence non-trigger** ("…that's all I wanted to ask…" must NOT close the session). Code applied (tail-anchored regex `_END_SESSION_RE`). **Still owed: one clean confirmation of both** — grab opportunistically on any voice pass.

### BARGE-IN / VOICE DIAGNOSTICS — CLOSED (settled — do not re-litigate)
- **Barge-in is NOT broken.** 11/11 deliberate fires. The old "never fires" belief was a **logging artifact** (random sampling + pre-increment counter); historical threshold figures were never real data. **Threshold stays 0.06 RMS / 6 frames.**
- **Echo floor confirmed ≤0.0028 RMS** across 3 silent-through-reply baseline turns (peak 0.0028 / 0.0000 / 0.0001; zero frames ever touched 0.06) — ~21× below threshold. **Phase 5 threshold discussion CLOSED, no change.**
- **Correction to v2.3 framing:** the audio-drop bug and the threshold were **never actually linked**. The audio drop was a pure logic bug (shared boolean), not a threshold problem. v2.3's "fix them together, they're linked" note is superseded — the fix shipped on its own, threshold untouched.
- **Deepgram misses are NOT a bug.** Genuine low-signal audio (`confidence=0.0`, identical mime to successful turns). `[DG-DIAG]` logging kept permanently; no code change.

### NEW — tracked this session (Dee explicitly OK living with these; NOT next)
- **Mic mishears over background music.** Voice-to-text jumbles when music is playing — same family as the (not-a-bug) Deepgram low-signal misses; `echoCancellation` already on. Only untried cheap lever = browser `noiseSuppression` / `autoGainControl` on the mic — a small tuning pass someday, but a quieter room beats any knob. Not next.
- **Duplicate reply bubble when typing while mic is open.** Reply renders through BOTH the text path (bubble + replay button — the one Dee wants to keep) AND the voice path (bare play button). Needs a **dedupe-by-turn-id** so only the text+replay bubble survives. Modest, not hard. Tracked, not next.

### Instrumentation (permanent, strippable once fully closed)
`[BI-DIAG]` client barge-in RMS/frames · `[BI-RACE]` brain interrupt set/clear timing · `[DG-DIAG]` Deepgram confidence/duration/mime.

### Operational notes (carry into next session)
- **Audio-drop fix is committed (`d0affb6`) but NOT pushed** — local `master` is 1 commit ahead of `origin/master`; Dee chose to leave it unpushed (July 3). Push whenever ready; nothing outstanding to commit for it.
- **Uncommitted `finance.py` changes (~150 lines, unrelated)** still sitting untracked on Aurora — leave untouched; don't commit blind.
- **Brain may be headless** — stdout was redirected to `brain_console_diag.log` for `[BI-RACE]` capture. A plain `restart_brea3.bat` returns it to a visible console and loses that capture. **Registry work does not need `[BI-RACE]`** — a normal restart is fine for next session.
- **`BREA_BRAIN` has no git repo** — instrumentation in `brea_sandbox.py` lives only in the working file on Aurora.

---

## 4. BREA_PHONE — STANDALONE VOICE PLATFORM

Proving ground. `C:\Users\Danielle\Desktop\BREA_PHONE\`, base `appirChe9FuokHmG3` (holds Brea's KNOWLEDGE_BASE). Deepgram streaming WS + VAD + configurable LLM + ElevenLabs streaming TTS. White-label: duplicate base, fill SYSTEM_CONFIG, repoint. Blueprint written; first end-to-end test pending.

---

## 5. THE BOSS — BUSINESS OPERATIONS & SERVICE SUITE  *(carried from v2.1 June 21 — unverified this session)*

> **Most recent tracked: Session SP0 (June 18) — Staff Portal Layer 0.** July 1 Vagaro-replacement deadline was live at last KB; **status still unconfirmed in the July 3 material.**

**Identity (locked):** Platform = The BOSS. Assistant = Brea. Never conflate. One isolated Airtable base per tenant. **Base:** `appqFL0CtYdn9Fe0U`.

**Infrastructure (post-SP0 line counts):**
```
C:\Users\Danielle\Desktop\BEOS_PLATFORM\
  app.py (7,118)  templates/index.html (8,217)  templates/staff.html (696, NEW SP0)
  templates/portal.html (1,947)  templates/clock.html (504)  payroll_engine.py (784)  README.md
```

**SHIPPED SP0 — Staff Portal Layer 0:** staff.html mobile-first SPA + validate_staff_portal.py (24/24) + add_staff_portal_schema.py (9 fields). Per-staff OTP + passcode at `/staff`, session isolation from client/owner. Classification-aware dashboard (`Employment_Type` master switch). Unified presence resolver `_resolve_provider_presence()`. Permissions `Portal_Permissions` JSON + `_staff_can()`. Owner presence board. Staff Brea scoped to own data. Bugs fixed: staff save 405, duplicate classification tags, Clock_PIN leak, theme mismatch, blank-PIN clear. All 12 providers backfilled. Validators green: staff_portal 24/24 · payroll 6/6 · workflow 21/21 · clock 15/15.

**Prior confirmed:** core SPA; calendar (day/week/month, drag-drop); checkout (multi-method, gift-card split, packages/memberships); Checkout Pricing & Discount Engine; full Settings; Last-Minute Booking Policy; Client Portal v1–v3; Loyalty foundation; payroll + clock; server-owned timezone (tzdata==2026.2).

**🔴 MUST BEFORE LAUNCH (from SP0 queue — verify current status):** (1) Owner auth OTP+passcode (`logged_in_provider` never set — security hole); (2) Fix Brea staff system prompt (tells staff "Vagaro/Square," doesn't know she's in The BOSS); (3) Deploy to Railway (dies when laptop sleeps).
**🟡 HIGH:** staff phone numbers + Airtable cleanup; business name in staff header; Staff Portal L1 (schedule) → L2 (booking).
**🟠 MEDIUM:** L3 payout detail; L4 contracts; client portal audit; Canadian tax engine.
**🔵 DEFERRED:** L5 invoices; Stripe + The Shop.

**Capability IDs SP0:** 221–228 assigned. **Next available ID: 229.**

---

## 6. BREA FACTORY — INFRASTRUCTURE HUB & ORCHESTRATOR  *(carried from v2.1 — unverified this session)*

> **STATUS CAVEAT:** Not touched since June 9–10. Verify execution state on Aurora before trusting. Anchor: brea_progress-11.md. **Base:** `appEdXeA8oLrq6eep` — 9 tables, 120 capabilities seeded, 5 vertical presets.

**Confirmed (June 10):** orchestrator (5004, polls TASK_QUEUE 30s, Auto/Approve/Critical, `.env` hard exclusion — permanently out of orchestrator scope); dashboard (5003, single-page rebuild, health 200s); permanent ngrok domain; Start/Stop bat; watchdog auto-restart; Task Scheduler on login; Brea Doctor (60s loop); Spec-to-Queue. CLI execution path was confirmed in an earlier session (one real Auto task end-to-end) — verify before building on top of it.

**OPEN (verify first):** Deepgram 400 (voice first-response-only); chat history wipes on refresh (needs CONVERSATION_LOG); HEALTH LOG FAIL spam (non-critical).

**Specced/pending:** Screen Presence / Assisted Control (caps 172–178, watch-only Phase 1) — **gates the MetaHuman avatar pipeline**; EMPIRE_NOTIFICATIONS bus (many-to-many Airtable table in Factory base, routes cross-system alerts through Brea 3); Factory↔Brea 3 Business Tab; BOSS embedded as Factory panel.

---

## 7. VOICE PIPELINE — MASTER SPEC

Two modes: tap=live, hold=note. MediaRecorder → Deepgram live WS (`audio/webm;codecs=opus` for Pixel) → interim → silence (VAD) → transcript → Claude streaming tokens → ElevenLabs streaming TTS → mic restarts. **Barge-in fires reliably (11/11); threshold 0.06 RMS / 6 frames is FINAL** (echo floor confirmed ≤0.0028 RMS, ~21× below threshold — Phase 5 closed). **Post-barge-in audio-drop fixed** (turn-scoped `_interruptedTurnId`, `?v=24`, phone-proven July 2) — was a logic bug, never a threshold issue. Deepgram misses = genuine low-signal audio, not a bug. **TTS carry-forward: Fish Speech (S2 Pro) is the planned ElevenLabs replacement** — see §10, cost-urgent.

---

## 8. ORCHESTRATION & AUTONOMY

Hybrid autonomy: Auto (executes, no FS risk) / Approve (shows plan, waits) / Critical (explicit confirm — any .env/key access). Orchestrator NEVER touches .env or key files. **Model allocation:** Opus (Master Chat) architects/reviews/specs; Sonnet (Claude Code) executes. One Claude Code session at a time.

---

## 9. SESSION HANDOFF PROTOCOLS

**Close-out (one route):** end of session → write ONE progress doc → upload to Master Project → KB updates from it. One doc per session. Claude Code signals close, writes the doc, overwrites the KB on Aurora (locked filename, no version suffix); Dee uploads to Master Chat.

**Discipline (every session):** one variable at a time; read-only audit → review diff → apply on confirm → proof-gate; **a capability is "Active" only after live phone confirmation, never code-complete alone**; verify fresh processes before testing; restart by PID; phone cache is a silent saboteur; don't touch streaming/IPC unless the session IS that build.

**Airtable gotchas (locked):** date-equality unreliable (use RANGE filters); unchecked checkboxes omitted from API (absence = `False`); all finance fetches via `finJSON`; `typecast:true` on all writes (registry writes too); phone lookups via Python `_find_client_by_phone()` / `_find_provider_by_phone()`, never `filterByFormula`.

---

## 10. NEXT BUILD PRIORITIES

**Brea 3 — locked roadmap:**
1. ✅ **MASTER_CAPABILITY_REGISTRY 403 — RESOLVED & phone-proven (July 3).** Root cause was a **base mismatch**, not PAT scope: `brea_sandbox.py:67` named `MASTER_CAPABILITY_REGISTRY` but `at_get()` queried it against the Brea 3 base (`app3Vc2FkBAznznuV`), where it doesn't exist. The master registry lives in the **Factory base** (`appEdXeA8oLrq6eep`) — the "120 seeded capabilities" table, empire-wide ID scheme. Airtable's 403 conflates "no permission" with "table not found," which is why it read as a PAT issue for weeks. Fix (Option A — one master, each system reads its own slice): added `CAPABILITY_REGISTRY_BASE = "appEdXeA8oLrq6eep"`, gave `_at_url`/`at_get` an optional `base=None` param defaulting to the Brea 3 base (every other caller byte-for-byte unchanged), and repointed `load_active_capabilities()` to the Factory base with filter `AND({Scope}='Brea 3',OR({Status}='Active',{Status}='Degraded'))`. **Field is `Scope`, not `Platform`; literal value `Brea 3`; Status literals plain `Active`/`Degraded`.** Returns 34 rows (32 Active, 2 Degraded: Silero VAD 051, TTS Pipeline–ElevenLabs 049). `Plain_Description`/`Error_Behavior` don't exist in the Factory table → graceful-empty via `.get(...,"")` (cosmetic only; do NOT substitute `Status_Notes`). Boot still degrades to "" if the Factory base is unreachable. Brain has no git repo — edits live in the working file. Phone-proven: Brea now accurately affirms capabilities she has. **Isolation note:** this softens the base-isolation line by design — the Brea 3 brain makes a **read-only** call to the shared master in the Factory base; it never writes there. New registry rows (Scope `Brea 3`) are added via a Factory-side/manual write, never from a Brea 3 build session. Known non-blocker: `load_active_capabilities()` reads one page (no `offset`) — silently truncates above 100 Active rows; currently 34.
2. **NEXT — Document Lifecycle & Intelligent Filing (Addendum v6).** Sequenced ahead of the Finance Bridge (Dee's call — fixes daily upload friction fastest; finance-routing half plugs into the Bridge after). Turns Brea into an intelligent filing system: chat "+" reworked from auto-commit-to-Vault → **analyze & hold (Staged)** → type-aware **propose** via a new reusable **Structured Prompt** (tap A/B/C **and** talk) → on confirm, file to Vault with recall metadata + a memory entry → **Files tab** for natural-language retrieval. Adds **preference learning on documents** (extends cap 042 — rising-confidence, real threshold, confirm always required) and **open-loop tracking** (unresolved uploads are sticky like notifications, can push to Reminders, cleared only by deliberate file/act/dismiss; re-raise *style* per-person configurable). Principle: **nothing auto-commits** — analyze → hold → propose → confirm → act. Vision/scanner internals untouched. Phases D0–D6 (copy button → Structured Prompt → analyze&hold → file+metadata+memory → Files tab → open-loop → preference learning), each phone-proven. Strong white-label feature (digital filing cabinet). Copy button (D0) is an independent quick win.
3. **Finance Cognitive Bridge** (dual read + navigate/act intent, hard timeouts — she opens and operates the dashboard). Now **unblocked** by the registry fix. The receipt → "business expense owed back to me" case from Addendum v6 is the Bridge's first real proof; the v6 finance-routing disposition flips from `Proposed` to `Logged` once the Bridge writes. Gets its own registry row (Scope `Brea 3`) at closeout.
4. **PDF generation** (generate → surface in chat → download; enters the Addendum v6 lifecycle like any document; email later once comms land)
5. **Closed-app push notifications**
6. **TAX tab** (BOSS Finance Bridge dependency)

**Carry-forward (tracked, do NOT shelve):**
- **Fish Speech (S2 Pro) — COST-URGENT.** Planned ElevenLabs TTS replacement (swap ≈ one SYSTEM_CONFIG field). Get it in **before the next ElevenLabs renewal** to avoid another month's charge. It's on the voice/TTS track, independent of the tools track — so if the renewal is close it **jumps ahead of the Finance Bridge as its own tight session.** **Decision input needed: ElevenLabs renewal date.**
- **Brea as her own standalone app** — wanted; sequence after the tool-wiring track unless a reason pulls it forward.
- **BOSS streaming** — Dee flagged wanting it; scope/clarify. (BOSS is a separate isolated system — its own session, never mixed with Brea 3.)
- **`SESSION_HANDOFF.md` dedicated backfill** — record-of-record drifted stale for weeks; reactively patched, still owes a full pass. A source-of-truth that lies until fixed.
- **Brain-prompt tuning bundle** (research-mode over-trigger, reply/research-text collision, dead mic during research) — brain-side, older.
- **KEY ROTATION** — Anthropic + OpenAI keys exposed in scrollback in an earlier session.

**Held until dependencies clear:** Brea Marketing module (Blueprint Addendum v5, specced, held until BOSS launches); MetaHuman avatar pipeline (Unreal + MetaTailor + Live Link Face — deferred until Factory Screen Presence caps 172–178 exist); EMPIRE_NOTIFICATIONS bus.

---

## 11. REGISTRY — OUTSTANDING

**BOSS SP0 assigned 221–228. Next available ID: 229.** Large unassigned-ID backlog across Brea 3 Waves 13 / 14 — a dedicated registry-assignment pass is overdue. **The 403 blocker is CLEARED** (§3 — base mismatch fixed; brain reads the Factory master's `Scope='Brea 3'` slice read-only). The master registry is confirmed to live in the **Factory base** (`appEdXeA8oLrq6eep`), field `Scope`, empire-wide ID scheme. Registry *writes* (assigning new IDs, adding rows like the Finance Cognitive Bridge and the Addendum v6 capabilities) are a **Factory-side/manual pass** — never written from a Brea 3 build session per isolation. Reads from Brea 3 now work.

---

*End of BREA_EMPIRE_MASTER_KNOWLEDGE_BASE.md — Version 2.5, July 3, 2026.*
*Brea 3 next: Document Lifecycle & Intelligent Filing (Addendum v6) — analyze & hold, propose-confirm, file with recall metadata, Files tab, preference learning, sticky open loops. Sequenced ahead of the Finance Cognitive Bridge (now unblocked — registry 403 resolved, base-mismatch root cause, phone-proven). Watch the ElevenLabs renewal date: Fish Speech may jump the queue. Audio-drop fix is committed (`d0affb6`), left unpushed by choice — local master 1 ahead of origin. BOSS + Factory carried from June 21, unverified.*
