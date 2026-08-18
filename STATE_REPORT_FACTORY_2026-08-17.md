# STATE REPORT — BREA FACTORY
**Audit date:** 2026-08-17 · **Type:** Read-only state audit (no files edited, no processes started/killed)

---

## 1. IDENTITY

- **Project name:** BREA Factory (per code headers: "Session F2 — Factory Orchestrator Service" / "Session F3" dashboard) — infrastructure hub + orchestrator for the Brea Empire.
- **Root directory:** `C:\Users\Danielle\Desktop\BREA_FACTORY`
- **Git branch:** `master`
- **Current HEAD:** `34ab13485d8a57264b19e4861e71d453f5f755d5`
  **Date:** 2026-08-03 15:45:38 -0500
  **Message:** `Disable in-process watchdog: fixes 'alive but deaf' mid-voice restart; ignore stale app backups`
- **Working tree:** clean (`git status` → "nothing to commit, working tree clean")
- **Full commit history:** only 2 commits total —
  1. `5c450065` (2026-07-21) "Initial commit: voice-proven Factory state (dashboard + orchestrator)"
  2. `34ab1348` (2026-08-03) the watchdog-disable commit above.
  This repo has almost no git history relative to the amount of work described in the progress docs — most development happened before this repo was initialized (2026-07-21) and is only narrated in the `.md` files, not visible in `git log`.

---

## 2. LIVE / PROVEN

Evidence-based, i.e. actually confirmed executing end-to-end at some point — **not** necessarily running right now (see §6 for current runtime state).

- **Orchestrator task dispatch (Auto mode) — proven once, 2026-06-11.**
  `brea_factory.py:302` (`execute_headless`, dispatches by `Mode`). Per `brea_progress-12.md:55` a real Airtable task (`recW39WxIFLlG32oM`) was queued, picked up, executed headlessly via `claude.cmd -p` (shell=True + stdin prompt + `--allowedTools` allowlist, `brea_factory.py` execute_headless block), and the file was edited exactly as instructed, marked `Status: Complete`. The test comment left as a permanent marker is presumably still in `dashboard/app.py` (not independently re-verified in this audit — see §3).
- **Spec → TASK_QUEUE write path — code-complete and evidenced.**
  `dashboard/app.py:382-448` (`/api/spec`, `spec_chat()`): takes chat messages, calls Claude (`claude-sonnet-4-6`), parses a `READY_TO_SPEC` JSON block, and POSTs each task directly to Airtable `TASK_QUEUE` with `Status: Queued`. This is the "Spec-to-Queue" feature referenced in the KB (`BREA_EMPIRE_MASTER_KNOWLEDGE_BASE_v1.6.md:538-539`, capabilities #140-141, marked "Active" Session F2).
- **`.env`/secret exclusion rule — present in code as claimed.**
  `brea_factory.py` docstring (lines 12-14) states the orchestrator hard-excludes `.env`/API-key files from read/write. Consistent with `brea_progress-12.md:157` ("Hard Rule Status: Unchanged"). Did not open `.env` to verify contents per audit constraints; only confirms the guard exists in source, not that it's airtight against every path.
- **Health watchdog loop is present and was actively running as of the last log capture (2026-08-11).**
  `brea_factory.py:506-527` (`_health_loop`, 60s interval, `_HEALTH_TARGETS` covering Brea 3/BOSS/Dashboard/Factory). `factory_orchestrator.log` shows live `[POLL]` and health-check activity through 2026-08-11 09:11:50 (see §6) — proof it was running then, not proof it's running now.

---

## 3. CODE-COMPLETE BUT UNPROVEN

- **Full Auto/Approve/Critical dispatch logic.** `brea_factory.py:163-167` per KB v1.6 marks Task Classification, Approve gate, Critical gate, and Auto pickup all "Active" (Session F2), and the code paths exist (`brea_factory.py` lines ~302-430 handle Queued/In Progress/Blocked/Complete transitions per mode). Only the **Auto** path has a documented live proof (§2); **Approve** and **Critical** gating (human-confirmation flows) have code but no evidenced end-to-end run found in this audit.
- **`/logs` route and Stop-Session voice button (Session F3/F4 work).** `brea_boss_progress.md`... *(not applicable — see §9, that file is not about this project)*. Per `brea_progress-12.md:146-151`, these were explicitly **not yet visually exercised in-browser** as of 2026-06-11 and no later doc confirms they were. Unverified whether still true.
- **Health-diagnostic write to `MASTER_DIAGNOSTIC_LOG`.** Code exists (`brea_factory.py:478-503`) but is provably failing in production logs (see §5) — code-complete, but its output is not reliable.
- **Watchdog file-observer's replacement (manual restart discipline).** The Aug 3 commit removed the auto-restart safety net and replaced it with a comment instructing manual restarts. There's no code enforcing that discipline — it's a process convention, not a coded guarantee. Unproven whether it's being followed.

---

## 4. SPECCED / IN QUEUE, NOT BUILT

In rough dependency order, per `BREA_EMPIRE_MASTER_KNOWLEDGE_BASE_v1.6.md` (Factory-relevant modules only; Brea-3-only and BOSS-only items excluded as out of scope for this project):

1. **Onboarding & Provisioning module** (KB v1.6 lines 466-477, capabilities #084-091: Guided Interview, Module Inference Engine, Time Anatomy Coaching, Vertical Preset Loader, Completeness Checklist Gate, Owner-Facing Summary Generation, Base Provisioning/Template Duplication, Scoped Registry Copy) — all marked **"Pending Build"**. No corresponding code found anywhere in `brea_factory.py`, `brea_factory_build.py`, or `dashboard/app.py` (grepped for onboarding/provisioning/template-duplication keywords — no hits). This is the largest fully-specced, fully-unbuilt block, and would need the Task Classification/dispatch scaffolding (§2/§3) as its foundation, which does exist.
2. **Factory Escalation Notification** (#017) and related escalation plumbing — "Pending Build" per KB, depends on `MASTER_DIAGNOSTIC_LOG` writes, which are currently broken (§5) — this dependency should be resolved first.
3. **Unified Portal / Screen Presence / Assisted Control module** (KB v1.6 lines 592-609, #172-178, #186+) — scoped to "Brea 3", not Factory; listed here only because it's cross-referenced from the Factory KB. Out of scope for this project's build-queue but worth noting the KB conflates modules under one registry.

No dedicated "dispatcher" or "build-queue" *module* exists separately from `brea_factory.py` itself — the Mode-based dispatch loop *is* the dispatcher, implemented inline (not abstracted into its own file/class). Anyone extending it will be extending `brea_factory.py` directly; there's no separate scaffolding layer to plug into yet.

---

## 5. KNOWN ISSUES / TODO / FIXME

- **`brea_factory.py:478-503`** — `_write_health_diagnostic()` swallows all exceptions from the Airtable write (`except Exception: print(...)`, no error detail logged). Live evidence in `factory_orchestrator.log` (tail, entries through 2026-08-11): repeated `[HEALTH LOG FAIL] Could not write diagnostic for Brea 3` and `[HEALTH LOG FAIL] Could not write diagnostic for BOSS`, recurring every health cycle for at least the last several hours of the log. **Root cause unverified** — the real exception is never printed. `BREA_EMPIRE_MASTER_KNOWLEDGE_BASE_v1.6.md:556` (capability #158) claims the cause is "Degraded — field mismatch Pattern_Flag", but the current code (`brea_factory.py:483,545,563,583`) accepts a `pattern_flag` parameter and never includes it in the Airtable `record` dict at all (lines 487-499) — so if a field mismatch was ever the cause, the code has since changed and the KB's stated root cause no longer matches what's actually being sent. This needs fresh diagnosis, not reuse of the old KB explanation.
- **`BREA_EMPIRE_MASTER_KNOWLEDGE_BASE.md:74`** — documented TODO (not code): "Recurrence TODO left in code (repeating reminders vanish on 'done' instead of advancing — flagged, out of scope)." This is a Brea-3 reminders issue, not Factory, surfaced only because the KB file lives in this repo.
- No `TODO`/`FIXME`/`XXX`/`HACK` markers found in any `.py` file in this project (grepped `brea_factory.py`, `brea_factory_build.py`, `apply_layout_fix.py`, `dashboard/app.py` and all its backups). The only "XXX" hits are placeholder text in setup instructions (`brea_factory_build.py:17-23,623-624`), not real TODOs.
- **`factory_orchestrator.log` is 24.4 MB** and untracked (correctly gitignored) — fine for now but no rotation logic was found in `brea_factory.py`'s tee implementation; will grow unbounded across restarts.

---

## 6. RUNTIME STATE (read-only survey — nothing started or stopped)

- **Port 5003 (Factory Dashboard):** **no listener found.** `Get-NetTCPConnection -State Listen` for ports 5003/5004 returned nothing.
- **Port 5004 (Factory Orchestrator):** **no listener found**, same check.
- **`factory_orchestrator.log`** last write: **2026-08-11 09:11:50** (6 days before this audit) — consistent with the orchestrator not having run since then.
- **`orchestrator_restart.log`** last write: 2026-06-12. **`dashboard/dashboard_restart.log`** last write: 2026-06-13. Both far stale.
- **Currently running Python processes on this machine** (as of audit time): PID 25796 (`app.py`) and PID 29708 (`brea_sandbox.py`), both started 2026-08-16 23:54:29. Neither is listening on 5003/5004 — their owned TCP listeners are on ports **5000 and 5001**. `brea_sandbox.py` resolves to `C:\Users\Danielle\Desktop\BREA_BRAIN\brea_sandbox.py` (Brea 3 brain, port 5001 per KB). PID 25796's `app.py` was not conclusively identified by absolute path (process CommandLine reported it relatively as `app.py`; multiple `app.py` files exist across sibling projects) — most consistent with `BREA_WEBAPP\app.py` (port 5000) per `Start_Factory.bat:17` and the KB's port table. **Not** Factory's `dashboard/app.py`. Treat this identification as reasonably confident, not certain.
- **Conclusion: neither Factory service (dashboard 5003, orchestrator 5004) is running right now.** Only the separate Brea 3 webapp/brain pair (5000/5001) appears to be up. This directly contradicts any assumption that the Factory/orchestrator is currently live — it is not, based on both the port scan and the log staleness.

---

## 7. OPEN DECISIONS / AMBIGUITY

- **Is the manual-restart discipline (replacing the disabled file-watchdog) actually documented/operationalized anywhere,** or does it live only as a code comment (`dashboard/app.py:905-908`)? No runbook or checklist referencing this was found in this directory.
- **Root cause of the `MASTER_DIAGNOSTIC_LOG` write failures is unresolved** (§5) — needs the actual exception text, not the swallowed-and-reprinted version, before anyone can fix or safely build the Factory Escalation Notification feature (§4 item 2) on top of it.
- **Whether `brea_factory_build.py`'s "120 capabilities" assumption is still accurate.** Its own docstring (lines 10-13) flags that the KB and progress docs said 120 at build time but that the count "may have grown since" — the current KB v1.6 capability table runs past ID #198, so this script's seed data is very likely stale relative to the current registry. Not re-verified against live Airtable (out of scope — would require credentials).
- **Two knowledge-base files with overlapping but differently-versioned claims** (`BREA_EMPIRE_MASTER_KNOWLEDGE_BASE.md` v2.5 dated 2026-07-03, and `BREA_EMPIRE_MASTER_KNOWLEDGE_BASE_v1.6.md` dated earlier/Session F8) both live in this repo; v2.5 itself says the BOSS + Factory sections "are carried forward from v2.1 (June 21) and were NOT touched this session — treat as unverified until a fresh progress doc lands." No fresher Factory-specific progress doc than `brea_progress-12.md` (2026-06-11) was found in this directory. **The most authoritative Factory-specific doc on disk is over two months old relative to today's audit date**, and predates the Aug 3 watchdog-disable commit entirely.

---

## 8. FILE INVENTORY

Top-level tree (excluding `.git`, `__pycache__`):

```
BREA_FACTORY/
├── .env                                        (exists — contents not read, per audit constraints)
├── .gitignore                                  (39 lines; correctly excludes .env, .env.*, *.pem, *.key, *.log)
├── BREA_EMPIRE_MASTER_KNOWLEDGE_BASE.md         197 lines   (v2.5, 2026-07-03 — NOT Factory-specific in depth, see §9)
├── BREA_EMPIRE_MASTER_KNOWLEDGE_BASE_v1.6.md    930 lines   (older, more Factory-detailed capability registry)
├── Blueprint_Addendum_v6_Document_Lifecycle...  202 lines   (Brea-3-only doc — see §9)
├── Start_Factory.bat                             29 lines   (starts Factory + Brea3 + BEOS + ngrok together)
├── Stop_Factory.bat                               5 lines   (taskkill /f /im python.exe — kills ALL python, not scoped)
├── _DOC_ARCHIVE/
│   └── BREA_EMPIRE_MASTER_KNOWLEDGE_BASE_20260703_195044.md   (dated snapshot copy)
├── apply_layout_fix.py                          113 lines   (one-off dashboard HTML tab-reorder script)
├── brea_boss_progress.md                        761 lines   (entirely about "The BOSS"/BEOS_PLATFORM — see §9)
├── brea_factory.py                              908 lines   (THE ORCHESTRATOR — port 5004)
├── brea_factory_build.py                        704 lines   (one-time Airtable base/table seeder, not runtime code)
├── brea_progress-12.md                          161 lines   (2026-06-11 — most recent Factory-specific progress doc)
├── brea_setup.bat                                61 lines
├── factory_orchestrator.log                      24.4 MB    (gitignored; last write 2026-08-11)
├── orchestrator_restart.log                     154,611 bytes (last write 2026-06-12)
└── dashboard/
    ├── app.py                                   913 lines   (THE DASHBOARD — port 5003)
    ├── app_backup_2026-07-05.py / -06 / -07 / -24.py   (stale local backups, gitignored as of Aug 3 commit)
    ├── dashboard_restart.log                    (last write 2026-06-13)
    ├── static/ (mic-icon.png, send-icon.png)
    └── templates/
        ├── index.html                           1,125 lines (current)
        └── index_backup_2026-07-04/-05/-06/-07/-07_1741.html   (stale backups)
```

Key file line counts (already itemized above): `brea_factory.py` 908, `dashboard/app.py` 913, `dashboard/templates/index.html` 1,125, `brea_factory_build.py` 704, `brea_boss_progress.md` 761, `BREA_EMPIRE_MASTER_KNOWLEDGE_BASE_v1.6.md` 930, `BREA_EMPIRE_MASTER_KNOWLEDGE_BASE.md` 197, `Blueprint_Addendum_v6...md` 202, `brea_progress-12.md` 161, `apply_layout_fix.py` 113.

---

## 9. CONTRADICTIONS WITH DOCS

- **FLAG — Watchdog auto-restart.** Both knowledge bases claim it's live:
  - `BREA_EMPIRE_MASTER_KNOWLEDGE_BASE_v1.6.md:567` — capability #180, "Watchdog Auto-Restart — app.py self-monitors file changes | **Active**".
  - `brea_progress-12.md:134,61` — "dashboard/app.py has a file-watchdog" (described as currently functioning, June 2026).
  Actual code (`dashboard/app.py:900-912`, HEAD commit `34ab1348`, 2026-08-03): **the watchdog is explicitly and permanently disabled**, with the comment "Do NOT re-enable." The docs were never updated after the Aug 3 fix — anyone reading only the KB would incorrectly believe auto-restart-on-edit is still active.
- **FLAG — Health-diagnostic failure root cause.** `BREA_EMPIRE_MASTER_KNOWLEDGE_BASE_v1.6.md:556` states the `MASTER_DIAGNOSTIC_LOG` write is "Degraded — field mismatch Pattern_Flag." Current code (`brea_factory.py:478-503`) does not send a `Pattern_Flag`/`pattern_flag` field to Airtable at all — so either the mismatch was already fixed by removing that field (and the *actual* current failure is something else, since the log shows it's still failing on 2026-08-11), or the KB's diagnosis was already incomplete when written. Either way, current code and the KB's stated explanation don't line up. Flagged as **unresolved**, not resolved as the KB implies.
- **FLAG — Misfiled / out-of-scope documents living in this repo.** `brea_boss_progress.md` (761 lines) is entirely about **"The BOSS" / BEOS_PLATFORM** (a different project, `C:\Users\Danielle\Desktop\BEOS_PLATFORM`), not about BREA Factory — its own header says so (`brea_boss_progress.md:1-9`). Likewise `Blueprint_Addendum_v6_Document_Lifecycle_and_Intelligent_Filing.md` opens with "Brea 3 ONLY... Never touch BOSS/Factory" (`line 2`). Neither belongs in this directory conceptually; someone treating "everything in BREA_FACTORY is about Factory" would be misled. Recommend relocating both, or clearly marking them as cross-referenced/parked here rather than native.
- **FLAG — "Current Running State" table is stale and will mislead if trusted.** `brea_progress-12.md:127-134` states Orchestrator PID 7044 and Dashboard PID 8600 are "Running" — this was true only at the end of that 2026-06-11 session. Per §6 of this audit, **neither service is running now**, and no doc in this repo carries a more recent runtime snapshot. Anyone resuming work from this doc alone would wrongly assume the Factory is live.
- **Not a contradiction, but a gap:** the KB v2.5 (`BREA_EMPIRE_MASTER_KNOWLEDGE_BASE.md:22`) itself already flags Factory as "Last touched June 9–10 — verify on Aurora" as of its own July 3 writing date — the KB's own authors already knew Factory docs were stale over a month ago; nothing since has closed that gap except the one Aug 3 commit, which itself was never folded back into either KB.

---

## Plain-English Summary

Brea Factory's code is real and further along than "vaporware" — the orchestrator (`brea_factory.py`, port 5004) and dashboard (`dashboard/app.py`, port 5003) both exist, the Airtable-backed task queue and Auto/Approve/Critical dispatch logic are implemented, and the Auto path was proven working end-to-end at least once (June 11). But right now, today, **neither service is actually running** — the last real activity in the orchestrator's own log was six days ago, and the two Python processes currently alive on this machine belong to a different project (Brea 3, ports 5000/5001), not Factory. The documentation is out of date in ways that matter: the knowledge base still claims the dashboard's auto-restart watchdog is active, when it was deliberately and permanently disabled on August 3rd after causing mid-voice-call crashes; the health-monitoring system has been silently failing to log diagnostics for at least the last several hours it ran, and the KB's explanation for why is inconsistent with the current code; and two of the markdown files sitting in this folder aren't even about Factory — they document a different project entirely. Before extending the build-queue/dispatcher, the two most load-bearing things to fix first are: (1) get an honest current picture by actually starting the services and watching the log fresh, since the last-known state is stale, and (2) find the real (currently swallowed) exception behind the diagnostic-log write failures, since the next planned feature (Factory Escalation Notification) depends on that log working.
