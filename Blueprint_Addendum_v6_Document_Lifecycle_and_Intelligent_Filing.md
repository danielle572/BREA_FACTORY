# Blueprint Addendum v6 — Document Lifecycle & Intelligent Filing
### Brea 3 ONLY — webapp 5000, brain 5001, base `app3Vc2FkBAznznuV`. Never touch BOSS/Factory/ngrok/theme.
### Companion to: Master Blueprint, Addenda v4 (Telephony) & v5 (Marketing), the Brea 3 progress record, the Master KB (v2.5). Extends the Wave 5 Document Vault and Wave 6 Finances pipelines; modifies how upload behaves; invents no new brain.

---

## 0. Why this exists

Today the chat "+" scans a document, runs vision, and **immediately commits it to the Document Vault** (and/or auto-stages a finance "Needs Review" entry). That collapses a whole lifecycle into one step: there's no *holding* a document to talk about it, no *disposition* decision, no *organization*, and no clean *retrieval*. The Vault becomes a dumping ground instead of a filing cabinet.

This addendum turns Brea into an **intelligent filing system**: a document comes in → she analyzes and *holds* it → she proposes what to do with it (in Dee's own words or her own suggestion) → on confirm she routes the *data* and files the *document* with the metadata needed to find it later → Dee retrieves it in plain language → and Brea can generate documents (PDF) into the same lifecycle. She learns Dee's filing preferences over time and never leaves a document unresolved.

**This is the keystone build.** "Put this where it goes" is the core of what Brea is for. Getting it right makes finance, reminders, and retrieval all flow through one clean spine.

---

## 1. The one principle above all — propose, never auto-commit

**Nothing is filed, written to finance, or permanently stored without Dee's confirmation.** This is the direct fix for the current clutter problem and it reuses the empire's existing "propose, never publish" gate (Addendum v5 §Locked). Every upload flows: **analyze → hold → propose → confirm → act.** A held document that is never confirmed simply expires from staging; the Vault only ever contains things Dee deliberately filed.

Preference learning (see §5) makes the *proposal* smarter over time — it never removes the confirm for anything that writes to finance or files permanently.

---

## 2. Document lifecycle — the states

A document (uploaded or Brea-generated) moves through explicit states:

- **Staged** — analyzed, held in the conversation, not in the Vault. Lightweight. Auto-expires if never acted on (configurable window, default 7 days). This is the new default on upload.
- **Proposed** — Brea has offered a disposition (file it / log to finance / set a reminder / all of the above) via a Structured Prompt (§3). Awaiting Dee.
- **Open** — an upload Dee hasn't resolved. **Sticky** — it keeps coming back until deliberately closed (see §6). Distinct from Staged: Staged can quietly expire; Open must be dealt with.
- **Filed** — deliberately committed to the Vault with full recall metadata (§7) and a memory entry written. This is the only state that persists a document long-term.
- **Dismissed** — Dee explicitly said "don't keep this." Closes any open loop; nothing persisted.

The *data* disposition (e.g. a finance record) and the *document* disposition (Filed under a category) are **independent** — she can do one, the other, or both on a single upload.

---

## 3. Component: Brea Structured Prompt (reusable — build first)

**The problem:** Brea's spoken/typed questions run long because she crams every option into a sentence Dee then has to hold in her head. Pure tap-buttons are too rigid — the real answer is often "B, but only for the electric one."

**The fix — a hybrid prompt component:** when Brea asks a multi-option question she renders **tappable options (A/B/C…) AND an open input** so Dee can tap the clean answer or just say/type the real one. Tap when it's simple, talk when it's not.

- Reusable across all of Brea 3 — this is *how Brea asks any multi-option question*, not a document-only widget. The document flow is simply its first consumer.
- Options are structured (label + action payload); the open field routes back through the normal chat/voice understanding path, so a spoken "same as the electric bill but remind me a week early" is understood, not forced into a button.
- Works in text and voice: spoken, she reads the options briefly ("I can file it, log it to finance, or both — or just tell me"); on screen, the taps render as chips (brand gold, matches the existing tappable UI Dee likes).
- Confirm actions ("log to Finance / set reminder / file under Bills — tap to confirm, or tell me what to change") run through this same component.

*Schema:* store an active prompt's option set + the item it concerns so a prompt survives a page refresh (see PROMPT_STATE, §8). Options stored as JSON (house pattern — cf. BOSS FORM_QUESTIONS `Options` long-text JSON).

---

## 4. Upload flow rework — analyze & hold

Rework the chat "+" path (do **not** touch the scanner/vision internals — jscanify client-side clean + Claude Sonnet vision + llama3.2-vision fallback stay exactly as they are):

1. Upload/scan → vision → structured analysis (unchanged).
2. **STOP before any Airtable write.** The result is held as **Staged** in the conversation, not saved to the Vault, not auto-staged to finance.
3. Brea reads it and opens a **type-aware Structured Prompt** (§4a) proposing what to do.
4. On confirm → she executes the chosen disposition(s): file to Vault with metadata + memory entry, and/or route the data (finance disposition waits on the Finance Bridge — §9), and/or set a reminder.
5. If Dee doesn't resolve it → it becomes **Open** and sticky (§6).

The current auto-commit behavior is removed. (The Wave 6 finance "Needs Review" auto-stage is folded into this: a receipt no longer auto-creates a finance row — she *proposes* it.)

### 4a. Type-aware proposed actions

On analysis Brea classifies the document type and offers the actions that type usually needs. She interrogates intelligently rather than just extracting:

- **Invoice / Bill** → "Due [extracted date] — set a reminder? Log it to Finance as a bill owed? File under Bills?" (She proactively surfaces the due date she read.)
- **Receipt** → "Categorize this? (Personal / Boujie Girl / Ask Brea / The Agency) File under Receipts? Is this a business expense you paid personally that the business owes you back?" (the exact case Dee described).
- **Contract / Agreement** → "File under Contracts? Any key date to remind you of (renewal/expiry)?"
- **Statement** → "File under Statements? Log anything to Finance?"
- **Unknown / other** → "What is this, and what would you like me to do with it?" (fully open — she asks rather than guesses).

Type → action templates live in config so they're tunable and white-label-portable. Every proposed action still requires confirm.

---

## 5. Preference learning aimed at documents

This extends the **already-Active Preference Learning capability (042)** — it is not new infrastructure, it's pointing existing learning at the document domain.

- Brea records how Dee dispositions each document type (e.g. "utility bills → log to Finance, remind 3 days before due, file under Bills").
- **Rising-confidence proposal, confirm-gated.** Early on she asks the full question set. Once a pattern is genuinely established, she leads with the pattern: "This looks like your other utility bills — I'd log it, remind you 3 days out, and file under Bills. Same as usual?" — one verifying question, Dee confirms, done.
- **A real threshold, not two-of-two.** She does not go proactive on a thin pattern. Guessing wrong and confidently mis-filing is worse than asking — it recreates the clutter/second-guessing problem in a smarter mask. The verifying question is the safety rail, deliberately kept.
- **The confirm never fully disappears** for anything that writes to Finance or files permanently. As confidence rises the *question shrinks* ("same as usual?") but a confirm tap/word is always required.

*This is the behavior Dee described as the original point of Brea's brain: an assistant that learns what you want and holds it.*

---

## 6. Open-loop tracking — "nothing left unclosed"

An unresolved upload is an **Open** item and behaves **like a notification**:

- **Sticky.** It keeps surfacing until Dee *deliberately* closes it — files it, acts on it, or explicitly dismisses it. Passive ignoring does **not** clear it. This is the guarantee behind "nothing left unclosed."
- **Push to Reminders.** An open item can be pushed into the existing REMINDERS surface so it lives somewhere real, not just in Brea's memory — and there it must be deliberately exed off / canceled / resolved to clear, exactly like a reminder.
- **Thread-aware.** If Dee uploads several documents and resolves some, Brea does not lose the others — she re-raises the unresolved ones ("You never told me what to do with that receipt from Tuesday").
- **Re-raise style is per-person configurable** (a preference, not a hardcode — white-label ready). The *stickiness* is the fixed rule; *how loud* she is about it is the setting:
  - Silent until asked ("any open items?")
  - Surface at natural moments (session start / related topic comes up)
  - Gentle time-based nudge if something sits too long
  - (Default: natural moments.)

---

## 7. Data model — Brea 3 base (`app3Vc2FkBAznznuV`)

**Extend the existing Document Vault table** (do not fork it) with recall + lifecycle fields. All writes use `typecast:true`; absent checkboxes read as `False`; any date filtering for the Files tab uses RANGE syntax, never equality.

Document Vault additions:
| Field | Type | Notes |
|---|---|---|
| Lifecycle_State | Single select | Staged / Proposed / Open / Filed / Dismissed |
| Doc_Type | Single select | Invoice / Bill / Receipt / Contract / Statement / Other |
| Category | Single select | Filing category (Bills / Receipts / Contracts / Statements / …) — tunable |
| Doc_Date | Date | The date *on* the document (invoice date, etc.) |
| Filed_At | Date | When Dee filed it |
| Plain_Description | Long text | Dee's own words about what it is ("business expense, owed back to me") — the recall key |
| Finance_Disposition | Single select | None / Proposed / Logged (set once the Finance Bridge writes) |
| Linked_Reminder | Link → REMINDERS | If a due-date reminder was set |
| Linked_Finance | Link → Finances | If routed to finance |
| Open_Loop | Checkbox | True while Open/sticky |

**New table — DOC_STAGING** (ephemeral held docs, before Filed): staging id, analysis payload, doc type, proposed actions (JSON), created_at, expiry. Cleared on file/dismiss/expiry. Keeps the Vault clean — only Filed rows ever reach it.

**New table — PROMPT_STATE** (so a Structured Prompt survives refresh): prompt id, related item ref, option set (JSON), status (Open/Answered), created_at.

**Memory entry on file.** When a document is Filed, write a Long-Term Memory / Session Summary entry (capabilities 040/041) capturing description + doc date + category. **This is the retrieval mechanism** — "the finance doc I filed on June 3rd" resolves by matching Dee's words against that memory entry + the Vault metadata.

---

## 8. The Files tab — the retrieval face

A new tab in the Brea 3 dashboard (parallel to Finances/Reminders/Calendar), reading `Lifecycle_State = Filed`:

- Browsable by **Category** and **Doc_Type**, sorted by date (RANGE-based date filters).
- Each entry shows the plain-language description, doc date, filed date, and links (to a reminder / finance row if any).
- **Natural-language recall in chat is primary:** "Brea, pull up that finance document I filed on June 3rd" → she resolves via the memory entry + metadata and surfaces it. The tab is the visual browse; chat recall is the everyday path.
- Open items visible/flagged here too, so the open loop has a home.

*Airtable is never named in this UI — it's "your files."*

---

## 9. Seams to the next builds (don't build these here — define the plug)

- **Finance Cognitive Bridge (next build after this arc).** The finance-routing disposition ("log this bill / allocate this as owed back to me") is a *write to Finance with intelligence* — that is the Bridge. Here, Brea **proposes** the finance action and marks `Finance_Disposition = Proposed`; the Bridge performs the actual write and flips it to `Logged`. **The receipt → "owed back to me" case is the Bridge's first real proof.** Registry note: the Bridge gets its own row in the master registry (Scope `Brea 3`) at its closeout.
- **PDF generation.** Brea generates a PDF, surfaces it in chat for download to whatever device (email later, once comms land). A generated PDF is just another document that enters this lifecycle (can be Filed like any other). Build after the Bridge, per roadmap.

---

## 10. Copy button (quick win — independent, ride the next webapp touch)

Add a **copy** control to each message bubble, alongside the existing play/timestamp controls, mirroring the copy affordance in consumer chat UIs. Lets Dee lift Brea's text. Small, high daily value, no dependency — can ship with any webapp pass. (Watch the known duplicate-bubble item: dedupe by turn id so copy attaches to the single surviving bubble.)

---

## 11. Build order — phases with success tests

**Phase D0 — Copy button.** *Test:* Dee copies a reply's text from the bubble on phone and desktop.

**Phase D1 — Structured Prompt component.** Reusable hybrid tap+talk prompt; survives refresh (PROMPT_STATE). *Test:* Brea asks a 3-option question; Dee answers once by tapping, once by talking a modified answer ("B but a week earlier") and it's understood.

**Phase D2 — Analyze & hold.** Rework "+" to Staged (no auto-commit); DOC_STAGING; vision internals untouched. *Test:* upload a receipt → it's held and discussed, nothing appears in the Vault until Dee files it.

**Phase D3 — Type-aware disposition + file with metadata + memory.** Per-type proposed actions via Structured Prompt; on confirm, Vault write with recall fields + memory entry. *Test:* upload an invoice → she surfaces the due date and proposes file+remind; on confirm it's Filed under Bills with description + dates, and a memory entry exists.

**Phase D4 — Files tab + natural-language recall.** *Test:* file a document, then in chat "pull up the [description] I filed on [date]" → she retrieves the right one.

**Phase D5 — Open-loop tracking.** Sticky Open state, push-to-Reminders, per-person re-raise style. *Test:* upload three docs, resolve two; she re-raises the third and won't drop it until Dee files or dismisses it.

**Phase D6 — Preference learning on documents.** Rising-confidence, threshold-gated, confirm always required. *Test:* disposition three utility bills the same way, then upload a fourth → she leads with the pattern and asks one verifying question.

Then: **Finance Cognitive Bridge** (finance-routing disposition goes live; TAX tab unblocks after) → **PDF generation**.

Each phase is proved on the phone before the next. A capability is Active only after live phone confirmation.

---

## 12. Locked decisions (this addendum)

1. **Nothing auto-commits.** Analyze → hold → propose → confirm → act. Staged auto-expires; only Filed persists.
2. **Data disposition and document disposition are independent** on a single upload.
3. **Structured Prompt is tap+talk hybrid**, reusable Brea-wide, refresh-safe. It's how Brea asks any multi-option question.
4. **Preference learning proposes, never auto-acts on finance/permanent-file** — confirm always required; real threshold before proactive; the verifying question is a feature.
5. **Open items are sticky like notifications** — cleared only by deliberate file/act/dismiss; can push to Reminders; re-raise *style* is per-person configurable, stickiness is fixed.
6. **Retrieval is via memory entry + Vault metadata**, natural-language-first; the Files tab is the visual browse.
7. **Finance-routing writes belong to the Finance Cognitive Bridge**, not this arc — this arc proposes and marks the seam.
8. **Vision/scanner internals untouched.** Airtable never named in UI. Airtable rules (typecast on writes, RANGE date filters, absence=False) hold.
9. **Brea 3 only.** No BOSS/Factory/ngrok/theme. New master-registry rows (Scope `Brea 3`) are added at closeout via a Factory-side/manual write — never written to the Factory base from a Brea 3 build session.

---

## 13. White-label note

The intelligent filing cabinet — analyze, propose, file with recall, learn preferences, never lose a loop — is a strong tenant feature (no physical paper trail; "file this for me" / "pull up that document"). Build it clean in Brea 3 first; the type→action templates, categories, and re-raise settings are already config-shaped so the pattern ports to the Factory template later. Not built here — noted so the Brea 3 build stays generalizable.

---

*End of Addendum v6. Slots into the Master Blueprint after v5. Extends Wave 5 (Document Vault) and Wave 6 (Finances); modifies the upload-to-Vault behavior; invents no new brain — composes memory (040/041), preference learning (042), reminders, and the finances panel. Build begins after the registry 403 fix is confirmed (it is, v2.5) and sits ahead of the Finance Cognitive Bridge per Dee's sequencing.*
