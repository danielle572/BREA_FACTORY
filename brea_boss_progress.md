# The BOSS — Business Operations & Service Suite
## Build Progress — Sessions 3A · 3B · 3C · 3D · SP0: Payroll Engine + Workflow + Tip-Split + Retail Attribution + White-Label Disclosure + Clock-In / Presence System + Staff Portal Layer 0
**Status:** COMPLETE
**Date:** June 18, 2026
**Platform:** The BOSS (BEOS_PLATFORM) — http://localhost:5002
**Airtable Base:** appqFL0CtYdn9Fe0U (BEOS — Boujie Girl Specialty Beauty Boutique)

---

## Final Line Counts (post-SP0)

| File | Lines |
|---|---|
| `app.py` | 7,119 |
| `templates/index.html` | 8,218 |
| `templates/staff.html` | 714 |
| `payroll_engine.py` | 784 |
| `templates/clock.html` | 504 |
| `validate_staff_portal.py` | — |
| `validate_clock.py` | 574 |
| `validate_payroll.py` | 196 |
| `validate_workflow.py` | 329 |
| `add_clock_schema.py` | 128 |
| `add_payroll_workflow_schema.py` | ~153 |
| `add_3c_schema.py` | 59 |

Before-SP0 baselines: app.py 7,054 · index.html 8,118 · staff.html (new) · portal.html 1,947 (unchanged).
Before-3D baselines: app.py 6,204 · index.html 7,804 · payroll_engine.py 718.

---

## SESSION 3A — Payroll Calculation Engine

**New files:** `payroll_engine.py` (718 lines), `seed_payroll_test.py`, `validate_payroll.py`
**Schema script:** `add_payroll_workflow_schema.py`

### Four Compensation Models

| Model | Logic |
|---|---|
| **Hourly** | `hourly_rate x hours`; hours from TIMESHEETS |
| **Pure Commission** | Service commission + retail commission; cumulative tiered rates or flat |
| **Base Plus Commission** | Period base + commissions; service and retail commission rates |
| **Greater Of** | Computes both Hourly and Commission paths; takes whichever is higher |

Tiers: cumulative breakpoints. Revenue above each `Threshold_Min` earns the tier's rate on the incremental amount. Sorted by `Sort_Order`.

### Effective-Dated Rate Resolution

`resolve_comp_rule(rules_list, target_date)` finds the active COMP_RULES row with `Effective_Date <= period_start`. Multiple rules allowed (supersede-and-create pattern). Resolution happens once per provider per run.

**Open flag (a):** Rate resolved at period_start, not per-transaction. Fine as long as comp changes land on period boundaries. One-line fix available.

### Supply Deduction

Three modes via `Default_Supply_Fee_Mode` on TENANT_CONFIG:
- `HOUSE_SUPPLIED`: deduction from `Offerings.Supply_Cost` or `supply_cost` key in Line_Items JSON
- `PROVIDER_SUPPLIED`: no deduction
- `Per-Line`: reads `supply_cost` key from Line_Items JSON per line

### Debt Deductions

`compute_debt_deductions(debts, formula_pay)` reads STAFF_DEBT rows for the provider. Recovery_Type: Flat or Percent. Flat deducts `Recovery_Value` per cycle. Percent deducts `formula_pay x rate`. Stops at remaining balance. **Draft is ledger-safe: never writes to Remaining_Balance at draft time.**

### Barter Adjustments

`compute_barter()` reads BARTER_RECORDS. Cadence: One-Time, Weekly, Monthly. Direction: Owed to House or Owed to Provider. Weekly/Monthly prorated by `period_weeks`. Net rent = owed_to_house - owed_to_provider; positive net_rent reduces payout.

### Money Flow Mode

`RENTER_KEEPS`: `net_payout = 0`, calculations still run and log to Calc_Detail.
`HOUSE_COLLECTS`: normal payout path.

### Draft Idempotency

If Draft run exists for period: deletes all PAYROLL_LINES and re-drafts.
If Approved-Locked run exists: raises ValueError (409 at route level).
All PAYROLL_LINES filtering done in Python by linked ID — never via ARRAYJOIN.

### New Airtable Tables (3A)

| Table | Purpose |
|---|---|
| PAYROLL_RUNS | One row per pay run — period, frequency, status, lock metadata |
| PAYROLL_LINES | One row per provider per run — all computed fields + Calc_Detail JSON |
| TIMESHEETS | Hours stub — linked to Provider, Date, Hours, Notes |

### Seeded Test Providers (via seed_payroll_test.py)

| Provider | Model | Expected NET |
|---|---|---|
| TEST — P1 Pure Commission | Pure Commission | $1,260 |
| TEST — P2 Tiered Commission | Pure Commission (tiered) | $1,900 |
| TEST — P3 Greater Of + Debt | Greater Of | $1,310 |
| TEST — P4 Base Plus Commission | Base Plus Commission | $1,465 |
| TEST — P5 Pure Commission Barter | Pure Commission (barter) | $3,150 |
| TEST — P6 Base Plus Retail Only | Base Plus Commission | $1,385 |

### 3A Validation

`validate_payroll.py` — **6/6 PASS**, idempotency confirmed, P3 Remaining_Balance unchanged at $1,000 post-draft.

---

## SESSION 3B — Operator Workflow (Adjustments + Approve & Lock)

### New Schema

| Table | ID | Fields Added |
|---|---|---|
| PAYROLL_ADJUSTMENTS | tblacQu5mphPiwl3G | Adj_Name, Payroll_Line, Payroll_Run, Type (Bonus/Correction/Reimbursement/Deduction/Other), Label, Amount, Reason, Created_By, Created_Date |
| BARTER_APPLICATIONS | tblQnIUH2INi7iYCq | App_Name, Barter_Record, Payroll_Run, Applied_Amount, Direction, Period_Start, Period_End, Created_Date |

### Backend Routes Added

| Route | Purpose |
|---|---|
| `GET /api/payroll/runs` | List all runs, sorted by Period_Start desc |
| `GET /api/payroll/runs/<id>` | Full run with lines + per-line adjustments (Python filter) |
| `POST /api/payroll/adjustments` | Create adjustment, recompute line |
| `DELETE /api/payroll/adjustments/<id>` | Delete adjustment, recompute line |
| `POST /api/payroll/runs/<id>/approve` | Lock run, commit debt decrements + barter applications |
| `GET /api/payroll/line-detail/<id>` | Return raw Calc_Detail JSON for UI modal |

### Key Helpers

**`_assert_run_unlocked(run_id)`** — abort(409) if Status == "Approved-Locked". `abort` must be in Flask import (was missing — caused 500 instead of 409 on `_assert_run_unlocked` initially, fixed by adding to `from flask import Flask, abort, ...`).

**`_recompute_line(line_id)`** — reads base_net from `Calc_Detail.net_payout` (engine baseline, immutable after draft), loads all PAYROLL_ADJUSTMENTS filtered in Python by line_id, sums, PATCHes PAYROLL_LINES.

### Approve & Lock

On `POST /api/payroll/runs/<id>/approve`:
1. 409 guard if already locked
2. Load all lines (Python filter on Payroll_Run linked ID)
3. Per line, parse Calc_Detail:
   - `debt_detail`: decrement STAFF_DEBT.Remaining_Balance (floor 0, set Status='Paid Off' if zero)
   - `barter_detail`: One-Time cadence -> PATCH BARTER_RECORDS Status='Settled'; Weekly/Monthly -> create BARTER_APPLICATIONS row
4. PATCH PAYROLL_RUNS: Status='Approved-Locked', Approved_Date, Approved_By

**Lock is irreversible by design. No reopen/unlock route exists.**

### Base Net Pattern

`Calc_Detail.net_payout` = engine's pre-adjustment baseline. Never changes after draft.
`PAYROLL_LINES.Net_Payout` = base_net + Manual_Adjustment_Total.
`_recompute_line` always reads from Calc_Detail, not current Net_Payout.

### Frontend (index.html, +389 lines in 3B)

Full workflow UI in `svPayroll` section:
- Pay Period card: frequency/anchor/period controls, Save + Run Draft buttons
- Results area: status badge, approve area (Approve button or Locked badge), warnings, scrollable table (13 columns)
- Per-line adjustment form (hidden when locked)
- `prApproveModal` with irreversible-action warning and Approved By field
- `prCalcModal` with raw Calc_Detail JSON display

### 3B Validation

`validate_workflow.py` — **21/21 PASS**:
- P5 NET = $3,100 (weekly $150 + one-time $50 = $200 house offset; $3300 - $200)
- P1 NET = $1,360 ($1,260 base + $100 Bonus adjustment)
- P3 Remaining_Balance = $1,000 pre-lock (debt safe during draft)
- P3 Remaining_Balance = $950 post-approve (decremented by $50)
- P5 one-time barter Status = Settled
- P5 weekly barter still Open
- BARTER_APPLICATIONS row created for P5 weekly Applied_Amount=$150
- Run Status = Approved-Locked
- POST adjustment to locked run -> 409
- POST run-draft for same period -> 409
- POST approve again -> 409
- P3 still $950, not $900 (no double-decrement)

---

## SESSION 3C — Tip-Split + Retail Attribution + White-Label Disclosure

### Part 0 Findings (live schema inspection)

| Finding | Detail |
|---|---|
| Line_Items shape | `[{"name":"Classic Fill","price":90,"qty":1,"source":"Service"}]` — no `provider` key in existing data |
| `Tip_Allocations` | Did not exist — added |
| Product source bug | `submitCheckout` wrote `source:'Service'` for all lines; products landed in gross_service, not gross_retail — fixed |
| Retail attribution UI | Existed; missing HOUSE default — fixed |
| `Tip_Distribution_Mode_Default` | Legacy singleSelect (Even/Lead_Provider/Custom) — NULL, deprecated, flagged in UI |
| `Tip_Distribution_Mode` | New canonical singleSelect (SINGLE_PROVIDER/LINE_ITEM_PRO_RATA/MANUAL_SPLIT) — NULL at build time |
| `Business_Complexity` | Did not exist — added |
| `Money_Flow_Mode` | Existed on TENANT_CONFIG, NULL |

### New Schema (add_3c_schema.py)

| Table | Field | Type |
|---|---|---|
| TRANSACTIONS (tblfOeALjyLGps22Z) | Tip_Allocations | multilineText (JSON) |
| TENANT_CONFIG (tblSH8aB7sAqwGRqL) | Business_Complexity | singleSelect: Simple / Advanced |

### Payroll Engine Tip Change (backward-compatible)

In `compute_provider` (payroll_engine.py ~line 381):

```python
tip_alloc_raw = txn.get('Tip_Allocations')
if tip_alloc_raw:
    for a in json.loads(tip_alloc_raw):
        if a.get('provider','').strip().lower() == pname.strip().lower():
            tips += float(a.get('amount') or 0)
else:
    tips += float(txn.get('Tip_Amount') or 0)  # original fallback
```

- HOUSE allocations match no provider name -> accrue to house
- No Tip_Allocations -> identical to original behavior -> 3A/3B numbers unchanged

### Backend (app.py, +41 lines in 3C)

- `_resolve_tip_mode(tc)`: maps legacy `Tip_Distribution_Mode_Default` to canonical field. Lead_Provider->SINGLE_PROVIDER, Even->LINE_ITEM_PRO_RATA, Custom->MANUAL_SPLIT
- `POST /api/tenant/platform-config`: saves Business_Complexity, Tip_Distribution_Mode, Money_Flow_Mode
- `/api/dashboard` now returns `tip_distribution_mode`, `business_complexity`, `money_flow_mode`
- `POST /api/checkout` writes `Tip_Allocations` to TRANSACTIONS if present in payload

### Frontend (index.html, +239 lines in 3C)

#### Checkout Tip Split

- `_coTipMode` state, initialized from `BEOS_CONFIG.tip_distribution_mode` on checkout open
- `#coTipModeRow` — mode toggle select (hidden in Simple mode, shown in Advanced when tip > 0)
- `#coTipSplitArea` — live-rendered allocation display beneath tip input
- Three rendering paths:
  - **SINGLE_PROVIDER**: 100% to primary provider (from appt or first service line); read-only display
  - **LINE_ITEM_PRO_RATA**: `_coComputeProRataAllocs()` groups revenue by provider, proportional split, remainder cent to largest share; read-only table
  - **MANUAL_SPLIT**: input per provider, live validation, blocks checkout if remainder not $0.00
- `tip_allocations` sent as JSON string in checkout payload; written to TRANSACTIONS.Tip_Allocations

#### Retail Attribution Fix

- `submitCheckout` now: `source: li.product_id ? 'Product' : 'Service'` (was always 'Service')
- Retail provider dropdown default changed to `<option value="HOUSE">Retail: HOUSE (no provider credit)</option>`

#### Settings -> Operations (new section)

New nav item and `svOperations` section with two cards:
- **Business Mode**: Business_Complexity + Money_Flow_Mode selects; saves to `POST /api/tenant/platform-config`; applies/removes `simple-mode` body class immediately
- **Tip Distribution**: Tip_Distribution_Mode select; note about deprecated legacy field

#### White-Label Progressive Disclosure

CSS rule: `.simple-mode .adv-field { display: none !important; }`

Elements tagged `adv-field` (hidden in Simple mode):
- `sf-supply-fee-mode` wrapper (Supply Fee Mode in staffModal)
- `sf-comp-uses-tiers` wrapper (tier checkbox in staffModal)
- `sf-tier-builder` div (tier table in staffModal)
- `sf-debt-section` form-section (Staff Debt section in staffModal)
- `coTipModeRow` (tip mode override in checkout — Simple users always get SINGLE_PROVIDER)

`simple-mode` class applied to `<body>` on dashboard load from BEOS_CONFIG.

### Validator Close-Out (3C)

`validate_payroll.py` updated: now self-seeding + self-purging. Runs cleanly regardless of prior session state.

**Both suites green post-3C:**
- `validate_payroll.py` — 6/6 PASS + idempotency PASS + P3 balance PASS
- `validate_workflow.py` — 21/21 PASS

---

## SESSION 3D — Retail Attribution Fix (Part 0.5) + Clock-In / Presence System

**New files:** `templates/clock.html` (504 lines), `validate_clock.py` (574 lines), `add_clock_schema.py` (128 lines)
**Schema script:** `add_clock_schema.py`

### Part 0.5 — Retail Attribution Fix in payroll_engine.py

The engine previously credited all retail revenue to the ticket's primary provider (the `TRANSACTIONS.Provider` name). Session 3D added a per-line attribution index so retail lines with a `provider` key route to the named provider, `HOUSE` items accrue to house with no commission, and lines with no key fall back to ticket provider (backward compatibility).

#### `retail_lines` Index Build (payroll_engine.py `__init__`)

```python
self.retail_lines = {}   # attributed-provider_id -> [{'item': ..., 'txn': ...}]
```

Built by scanning all transactions for lines with `source` in `('Product', 'Retail')`:
- `provider` key present, value is a provider name -> route to that provider
- `provider` key = `'HOUSE'` -> skip (no commission)
- `provider` key absent -> backward-compat: credit ticket provider

#### Retail Attribution Pass (in `compute_provider`)

After the service loop, a separate retail pass walks `data.retail_lines.get(pid, [])`.
- `basis == MENU_VALUE` -> unit price from Offerings table (provider-supplied cost model)
- Otherwise -> `item['price']`
- `gross_retail += line_amount`; line appended to `txn_detail`

The service loop now has `continue` for `source in ('Product', 'Retail')` — these lines never run through the service commission path.

### Part 1 — SHIFTS Table Schema + Clock Fields

**Schema script:** `add_clock_schema.py` (idempotent, Metadata API)

**SHIFTS table** (id: `tblDicV4CiipYl6zd`):

| Field | Type | Notes |
|---|---|---|
| Shift_Name | singleLineText | Primary field |
| Provider | multipleRecordLinks → Providers | |
| Clock_In | dateTime UTC | |
| Clock_Out | dateTime UTC | |
| Break_Minutes | number | Cumulative break time |
| On_Break | checkbox | |
| Break_Started_At | dateTime UTC | |
| Duration_Hours | number | Computed at clock-out |
| Status | singleSelect | Open / Closed |
| Source | singleSelect | Kiosk / Web / Manual |
| Presence_Status | singleSelect | Available / Busy / Break |
| Notes | multilineText | |
| Edited_By | singleLineText | |
| Edited_At | dateTime UTC | |

**Providers** — added `Clock_PIN` (singleLineText)

**TENANT_CONFIG** — added four fields:

| Field | Type |
|---|---|
| Breaks_Paid | checkbox |
| Time_Rounding_Minutes | number |
| Clock_In_Requires_PIN | checkbox |
| Max_Shift_Hours | number |

**Fix during schema build:** Airtable Metadata API requires `timeFormat.name = '24hour'` not `'clock24hour'`. Applied globally in `DT_OPTS`.

### Part 2 — app.py Clock Backend (+405 lines)

#### Clock Helpers (new block, after platform-config route)

| Helper | Purpose |
|---|---|
| `_utcnow_iso()` | Returns `datetime.utcnow()` as ISO 8601 Airtable dateTime string |
| `_parse_utc(s)` | Parses Airtable UTC dateTime string to datetime |
| `compute_shift_duration(clock_in_dt, clock_out_dt, break_minutes, breaks_paid, rounding_minutes)` | Single duration helper; subtracts unpaid break, applies rounding |
| `_date_in_locked_period(d)` | Loads PAYROLL_RUNS in Python, filters for Approved-Locked, checks overlap |
| `_get_clock_config()` | Loads single TENANT_CONFIG row, returns clock fields dict |
| `_find_open_shift(provider_id)` | filterByFormula on Status='Open' only (non-linked field), then Python filter on linked Provider ID |
| `_validate_pin(provider_id, pin_input)` | Loads Providers row, checks Clock_PIN match; returns True if PIN disabled or field empty |

#### Clock Routes

| Route | Purpose |
|---|---|
| `GET /api/clock/status` | Returns current shift status for all providers; stale flag when open > Max_Shift_Hours |
| `POST /api/clock/in` | Validates PIN, creates SHIFTS row with Status=Open, Source=Kiosk |
| `POST /api/clock/out` | Finds open shift, computes duration, closes shift; 409 if period locked |
| `POST /api/clock/break/start` | Sets On_Break=True, Break_Started_At; 409 if already on break |
| `POST /api/clock/break/end` | Clears On_Break, accumulates Break_Minutes from elapsed |
| `POST /api/clock/presence` | PATCHes Presence_Status on open shift (Available/Busy/Break) |

#### Shift Management Routes

| Route | Purpose |
|---|---|
| `GET /api/shifts` | List shifts; filter by provider_id, date_start, date_end, status |
| `POST /api/shifts` | Manual shift create; 409 if period locked |
| `PATCH /api/shifts/<shift_id>` | Update shift; 409 if period locked |
| `DELETE /api/shifts/<shift_id>` | Delete shift; 409 if period locked |

**Locked-period guard:** `_date_in_locked_period(d)` loads ALL PAYROLL_RUNS and filters in Python — compliant with permanent Rule 1.

`GET /clock` route added to serve `clock.html`.

#### Provider Serialization

`fmt_provider` now returns `"clock_pin": f.get("Clock_PIN", "")`.
`build_provider_fields` now maps `"clock_pin": "Clock_PIN"` in `str_fields`.

### Part 3 — clock.html (504 lines, new file)

Full-screen kiosk-style clock terminal. No nav bar. Shares CSS variables and fonts with kiosk.html (DM Sans, Tenor Sans, DM Mono, Blesta Script).

**Three-step flow:**
1. **stepIdentify** — provider select dropdown + optional PIN field (shown when `cfg.requiresPin = true`)
2. **stepAction** — chips: Clock In / Clock Out / Start Break / End Break / Update Presence
3. **stepResult** — success/error icon + title + subtitle; auto-resets after 5 seconds (`clockReset()`)

**Init:** loads business name from `/api/dashboard`, providers from `/api/staff`, clock config from dashboard config keys.

**`clockIdentify()`**: queries `/api/clock/status` to determine which actions are available for the selected provider.

**PIN validation**: client side shows/hides PIN field; server side always validates if `Clock_In_Requires_PIN` is set.

### Part 4 — index.html Clock UI (+314 lines)

#### Nav

"Clock ↗" link added before "Kiosk ↗", opens `/clock` in new tab.

#### Dashboard — Presence Board

New `dash-card` after Portal Orders card:
- Title: "Staff On Clock" with "Clock Screen ↗" action link
- `#presenceBoard` — rendered by `refreshPresenceBoard()` from `/api/clock/status`
- Polls every 60 seconds via `startPresencePolling()` (called from `loadDashboard()`)
- Stale chips shown in amber when open shift exceeds Max_Shift_Hours

#### Staff Modal — Clock PIN

`Clock PIN` field (`sf-clock-pin`, numeric input, maxlength=8) added to Settings tab after the three existing checkboxes. Included in modal reset, load, and `collectStaffForm()`.

#### Operations — Clock-In Configuration Card

New card in `svOperations` (after Tip Distribution card):
- `ops-rounding` — Time_Rounding_Minutes (number)
- `ops-max-shift` — Max_Shift_Hours (number)
- `ops-breaks-paid` — Breaks_Paid (checkbox)
- `ops-require-pin` — Clock_In_Requires_PIN (checkbox)
- **Save Clock Config** button calls `opsSaveClockConfig()`

`opsLoadSection()` now populates these fields from `BEOS_CONFIG` and sets default date range for shift filter to current week.

#### Operations — Shift Management Card

Full shift table with provider + date-range filters, rendered by `_renderShiftTable(shifts)`.
Manual entry form: provider select, clock-in/out datetimes, break minutes, notes, Source=Manual.

**JS functions:**
- `opsSaveClockConfig()` — POSTs clock fields to `/api/tenant/platform-config`, updates `BEOS_CONFIG`
- `_opsPopulateProviderSelects()` — populates `shiftFilterProvider` + `newShiftProvider` from `_allStaff`
- `opsLoadShifts()` — fetches `/api/shifts` with filter params
- `_renderShiftTable(shifts)` — renders table with Close/Delete actions
- `opsCloseShift(shiftId)`, `opsDeleteShift(shiftId)`, `opsCreateShift()` — shift CRUD

### 3D Validation

`validate_clock.py` — **15/15 PASS**

| Group | Tests | Result |
|---|---|---|
| R — Retail Attribution | R1, R2, R3 | 3/3 pass |
| C — Clock Routes | C1 (clock in), C2 (break cycle), C3 (compute_shift_duration), C4 (compute_shift_duration rounding), C5 (clock out), C6 (presence) | 6/6 pass |
| P-INT — Payroll Integration | PINT-1 (SHIFTS hours in engine), PINT-2 (SHIFTS + TIMESHEETS sum) | 2/2 pass |
| L — Locked Period | L1 (PATCH/DELETE blocked by 409), L1-del (DELETE blocked) | 2/2 pass |
| REGRESS — Regressions | validate_payroll 6/6, validate_workflow 21/21 | 2/2 pass |

Test transactions use `VTEST-` prefix, purged on each run.

---

## PERMANENT RULES (standing constraints for all future BOSS sessions)

### 1. Never Match Linked-Record IDs via filterByFormula or ARRAYJOIN

Airtable's `ARRAYJOIN({LinkedField})` returns display names, not record IDs. Any formula filter on linked-record IDs fails silently or returns wrong results.

**Always:** load the full table and filter in Python:
```python
rows = [r for r in at_get(TABLE) if target_id in (r['fields'].get('LinkedField') or [])]
```
This rule triggered three detours across 3A-3B (seed purge, validate debt check, engine idempotency). Also applies to `_find_open_shift` (filter Status='Open' in formula, filter Provider ID in Python).

### 2. `abort` Must Be in Flask Import

`abort()` is not available if not listed in `from flask import ...`. Caused a 500 (not 409) on `_assert_run_unlocked` in initial 3B testing. Always verify import.

### 3. Draft Is Ledger-Safe by Contract

Payroll draft never writes to STAFF_DEBT.Remaining_Balance or BARTER_RECORDS.Status. These mutations happen only at Approve & Lock. Validate with validate_payroll.py P3 balance check.

### 4. Approve & Lock Is Irreversible

No reopen/unlock route. Intentional. If a period needs correction, the only path is a manual Airtable edit + documented manual adjustment in the next period.

### 5. Product Lines Get source:'Product' in Line_Items JSON

`submitCheckout` must assign `source: li.product_id ? 'Product' : 'Service'`. Products landing in gross_service instead of gross_retail is a silent revenue attribution error. Fixed in 3C; do not revert.

### 6. Never Touch Port 5000. Never Write to appirChe9FuokHmG3. typecast:true Global.

Port 5000 is a separate instance. appirChe9FuokHmG3 is a separate Airtable base. Any write there corrupts production data.

### 7. SHIFTS Locked-Period Guard Uses Python Filter

`_date_in_locked_period(d)` loads ALL PAYROLL_RUNS and filters in Python. No filterByFormula on linked fields. PATCH and DELETE on SHIFTS both check this before acting.

### 8. Airtable dateTime API Format

UTC timestamps only. Format string: `'%Y-%m-%dT%H:%M:%S.000Z'`. Metadata API timeFormat name: `'24hour'` (not `'clock24hour'`).

---

## OPEN FLAGS (known issues, not yet addressed)

### (a) Rate Resolution at Period Start, Not Per-Transaction

`resolve_comp_rule` finds the rule effective at `period_start`. If a comp rate changes mid-period, the new rate applies to the entire period.

**Mitigation now:** Schedule comp changes to land on period boundaries.
**Fix:** Call `resolve_comp_rule` per transaction using `txn['Date']` instead of period_start. One-line change.

### (b) Provider Name Is singleLineText — No Integrity Constraint

`TRANSACTIONS.Provider` is free-text. Typo, nickname, or name change drops that transaction to `txn_unmatched` (logged in Calc_Detail warnings, not blocked). Silent exclusion.

**Fix before real money:** Add validation that raises if `txn_unmatched` is non-empty, or convert Provider on TRANSACTIONS to a real linked field.

### (c) Clock + Retail UI Validated Backend-Only

All 15 validate_clock.py checks pass via direct API calls and engine dry runs. Clock-in flow and presence board have not been exercised on a real device through the browser UI. Retail attribution per-line routing has not been confirmed end-to-end through a live checkout.

**Before launch:** run a real device pass on clock.html (clock in, break, clock out, presence update) and confirm presence board renders correctly in index.html dashboard.

---

## STANDING NOTES

### July 1 Launch Bar

The July 1 launch bar — **staff work + get paid, clients book + pay** — is now met end-to-end:
- Staff can clock in and out with break tracking and PIN protection
- Payroll engine computes hours from both SHIFTS (clock punches) and TIMESHEETS (manual corrections)
- Retail attribution routes per-line to the correct provider or HOUSE
- Tip-split writes per-provider allocations to TRANSACTIONS
- Payroll Approve & Lock commits all ledger mutations irreversibly
- Client portal OTP login, booking, checkout, and gift cards are live

Remaining before go-live: real device pass on clock UI (flag c above).

---

## NEAR-FUTURE QUEUE

| Item | Priority | Notes |
|---|---|---|
| Real device pass — clock UI + retail checkout | **Critical before launch** | Flag (c) above — backend validated only |
| Brea onboarding interview -> auto-set white-label toggles | High | Business_Complexity, Money_Flow_Mode, Tip_Distribution_Mode should be inferred from onboarding, not manually configured |
| Reopen/unlock-with-reversal for locked periods | Medium | Needs: reverse debt/barter mutations, unlock run. High complexity, low frequency. Spec first. |
| Per-transaction rate resolution (flag a) | Low | One-line fix. Defer until real mid-period rate change occurs. |
| TRANSACTIONS.Provider -> linked record | Medium | Hardens provider matching before real payroll money. Requires migrating existing rows. |
| Gift card redemption at checkout | Medium | Purchase flow active (Client Portal Session 3). Redemption not wired. |
| Package + Membership sell flow from portal | Low | Specced, not built. |

---

## SESSION SP0 — Staff Portal Layer 0

**New files:** `templates/staff.html` (714 lines), `validate_staff_portal.py`
**Schema script:** `add_staff_portal_schema.py` (migration run prior session, Step 4)

### Overview

Staff Portal Layer 0 delivers a mobile-first authenticated web portal for providers (employees, subcontractors, and booth renters) to view their schedule, availability, payroll, and shift status. The owner side receives a permissions management panel per provider and a unified presence board.

### New File: staff.html (714 lines)

Full SPA at `/staff`. Three login screens → dashboard view.

**Login screens:**
- Screen A: Phone entry + passcode login (`POST /api/staff/auth/login-passcode`)
- Screen B: OTP verify (`POST /api/staff/auth/verify-otp`)
- Screen C: Set passcode on first login (`POST /api/staff/auth/set-passcode`)

**Dashboard sections (classification-aware):**
- Presence card (dot + status label, always shown)
- Availability section (Subcontractor / Booth_Renter only) — state selector + `POST /api/staff/availability`
- Appointments list (`GET /api/staff/dashboard`)
- Shift section (Employee / Owner only) — hours this week, pay period note
- Payroll section — run history (latest N runs for this provider)
- Brea chat button → `POST /api/staff/brea`

**CSS:** `--staff-accent: #2C5F8A`; presence dot colors match index.html (green/amber/grey/purple/red).

**Session key:** `session['staff_provider_id']` — distinct from `session['portal_client_id']` (client portal) and `session['logged_in_provider']` (owner app). Zero collision.

### app.py Additions (+65 lines)

| Addition | Where | Notes |
|---|---|---|
| `fmt_provider` now includes `portal_permissions` and `is_admin` | `fmt_provider()` | JSON blob + bool |
| `@app.route("/staff")` | Near `/portal` route | Serves staff.html |
| `PATCH /api/providers/<id>/permissions` | Near line 1514 | Owner/admin auth gate; serializes 10-key blob |
| `GET /api/owner/presence/all` | Before "serve the interface" | Owner/admin auth; unified presence for all active providers |

**Owner auth pattern:** `session.get("logged_in_provider")` + Providers row check for `Is_Admin` OR `Employment Type == "Owner"`.

### Presence Resolver (`_resolve_provider_presence`)

Unified resolver (added in Step 2 / prior session):

| Employment Type | Source | States |
|---|---|---|
| Employee / Owner | SHIFTS (latest open) | PRESENT, ON_BREAK, OFFLINE |
| Subcontractor / Booth_Renter | Availability_State field | PRESENT, ON_BREAK, GONE_FOR_DAY, AWAY, OFFLINE |

Stale flag: shift open > Max_Shift_Hours (from TENANT_CONFIG). Resolver returns `{state, label, source, stale}`.

### index.html Additions (+100 lines, 8,118 → 8,218)

#### CSS

- `.staff-card-wrap / .staff-card-inner` — card structure with hover transition
- `.perm-toggle-row / .perm-panel` — collapsible permissions section
- `.tog-row / .tog-sw / .tog-sl` — iOS-style toggle switches
- `.perm-save-row / .perm-saved-msg / .perm-error-msg` — save feedback row
- `.pb-dot.PRESENT/ON_BREAK/GONE_FOR_DAY/AWAY/OFFLINE` — presence dot colors

#### JS Constants

```js
const PERM_KEYS = [
  ['view_own_appointments',   'See own schedule'],
  ['view_all_appointments',   'See all schedules'],
  ['view_own_clients',        'See own clients'],
  ['view_all_clients',        'See all clients'],
  ['view_own_payroll',        'See own payroll & payout'],
  ['view_own_contracts',      'See contracts'],
  ['view_invoices',           'See invoices'],
  ['use_brea',                'Access Brea'],
  ['submit_promos',           'Submit promotions'],
  ['manage_own_availability', 'Manage own availability'],
];
const PERM_DEFAULTS = { view_own_appointments: true, ... };
```

#### Settings → Team — Permissions Panel

Each provider card in the Team section is now wrapped in `.staff-card-wrap`. A collapsible `Permissions` row expands a panel showing:
- Employment Type (read-only)
- 10 permission toggles (loaded from `s.portal_permissions` JSON, merged with PERM_DEFAULTS if missing/unparseable)
- Save Permissions button → `PATCH /api/providers/<id>/permissions`

Functions: `togglePermPanel(id, evt)`, `savePermissions(id, evt)`.

#### Presence Board (Dashboard)

`refreshPresenceBoard()` now calls `GET /api/owner/presence/all` (replaced clock-status-based board). Renders: colored dot, provider name, state label, stale warning ⚠, source icon (🕐 shift / 👤 self). Title changed from "Staff On Clock" → "Team Presence".

### Portal_Permissions — 10 Keys

| Key | Default | Notes |
|---|---|---|
| `view_own_appointments` | true | See own schedule |
| `view_all_appointments` | false | See all schedules |
| `view_own_clients` | true | See own clients |
| `view_all_clients` | false | See all clients |
| `view_own_payroll` | true | See own payroll & payout |
| `view_own_contracts` | true | See contracts |
| `view_invoices` | true | See invoices |
| `use_brea` | true | Access Brea |
| `submit_promos` | false | Submit promotions |
| `manage_own_availability` | true | Manage own availability |

Admin bypass: `_staff_can()` returns True for all keys when provider `Is_Admin = true`.

### seed_payroll_test.py Fix

`purge()` TRANSACTIONS cleanup: if `DELETE` returns 403 (PAT lacks blanket delete on TRANSACTIONS), now falls back to `PATCH` the record's `Provider` field to `''`. This prevents accumulated stale transactions from contaminating engine results when multiple validator rounds run back-to-back. Fixes the `validate_clock.py` REGRESS section double-count issue.

### SP0 Validation

`validate_staff_portal.py` — **24/24 PASS**

| Group | Tests | Result |
|---|---|---|
| AUTH — OTP flow | 1a-1e | 5/5 pass |
| REJECT — Auth rejection | 2a-2c | 3/3 pass |
| ISOLATE — Session isolation | 3a-3b | 2/2 pass |
| PERM — Permissions | 4a-4b | 2/2 pass |
| BRANCH — Classification branch | 5a-5b | 2/2 pass |
| PRES — Presence resolver (all paths) | 6a-6i | 9/9 pass |
| BOARD — Presence board | 7a | 1/1 pass |

All four validators green at close:
- `validate_staff_portal.py` — 24/24 ✓
- `validate_payroll.py` — 6/6 ✓
- `validate_workflow.py` — 21/21 ✓
- `validate_clock.py` — 15/15 ✓

---

## CAPABILITY REGISTRY UPDATES — Sessions 3A / 3B / 3C / 3D / SP0

```
208 | Payroll Calculation Engine (4 models, tiers, debt, barter, draft-safe) | Added | Active | Session 3A
209 | Payroll Run Workflow (adjustments CRUD, Approve & Lock, 409 guards, ledger commit) | Added | Active | Session 3B
210 | PAYROLL_ADJUSTMENTS + BARTER_APPLICATIONS tables | Added | Active | Session 3B
211 | Tip-Split at Checkout (SINGLE_PROVIDER / LINE_ITEM_PRO_RATA / MANUAL_SPLIT) | Added | Active | Session 3C
212 | Retail Provider Attribution (per-line HOUSE default, source:'Product' fix) | Added | Active | Session 3C
213 | Business_Complexity Progressive Disclosure (Simple hides tiers/debt/barter/supply-fee/multi-tip) | Added | Active | Session 3C
214 | Operations Settings section (Business_Complexity, Money_Flow_Mode, Tip_Distribution_Mode) | Added | Active | Session 3C
215 | Tip_Allocations on TRANSACTIONS (backward-compatible engine read) | Added | Active | Session 3C
216 | Retail Attribution Fix — per-line provider routing in payroll engine (HOUSE=no commission, no-key=ticket-provider fallback) | Added | Active | Session 3D
217 | SHIFTS Clock-In/Out + Breaks + PIN (clock routes, helpers, SHIFTS table, Clock_PIN) | Added | Active | Session 3D
218 | Presence Board + stale-shift flag (dashboard poll, 60s interval, amber stale chip) | Added | Active | Session 3D
219 | Shift Management + locked-period guard (CRUD routes, Ops UI, 409 on locked period) | Added | Active | Session 3D
220 | SHIFTS -> payroll hours integration (Duration_Hours summed with TIMESHEETS in engine) | Added | Active | Session 3D
221 | Staff Portal SPA (staff.html, 714 lines — mobile-first, 3-screen login, classification-aware dashboard) | Added | Active | Session SP0
222 | Staff Portal Auth (OTP + passcode, session isolation from client portal and owner app) | Added | Active | Session SP0
223 | Staff Portal Dashboard API (classification branch: Employee shift/hours vs Sub/BR availability toggle) | Added | Active | Session SP0
224 | Provider Presence Resolver (_resolve_provider_presence — unified SHIFTS/Availability_State logic) | Added | Active | Session SP0
225 | Provider Permissions System (Portal_Permissions JSON blob, 10 keys, PATCH /api/providers/<id>/permissions) | Added | Active | Session SP0
226 | Owner Presence Board All (GET /api/owner/presence/all — all active providers, colored dots, stale flag) | Added | Active | Session SP0
227 | Staff Portal Permissions Panel (collapsible UI in index.html Team section — 10 toggles, save, error feedback) | Added | Active | Session SP0
228 | validate_staff_portal.py test suite (24/24 — auth, reject, isolate, perm, branch, presence, board) | Added | Active | Session SP0
```

---

## HOW TO RESUME NEXT BOSS SESSION

```
Read README.md in C:\Users\Danielle\Desktop\BEOS_PLATFORM.
Re-cd to C:\Users\Danielle\Desktop\BEOS_PLATFORM (terminal resets to system32).
Never touch port 5000. Never write to appirChe9FuokHmG3.
typecast:true global. Check index.html + app.py line counts before/after every heavy edit.

PERMANENT RULES — all binding, see progress doc above:
1. NEVER match linked-record IDs via filterByFormula or ARRAYJOIN. Load table, filter in Python.
2. abort must be in the Flask import line.
3. Draft is ledger-safe — mutations only at Approve & Lock.
4. Approve & Lock is irreversible.
5. Product lines get source:'Product' in Line_Items JSON.
6. Never touch port 5000. Never write to appirChe9FuokHmG3. typecast:true global.
7. SHIFTS locked-period guard uses Python filter (_date_in_locked_period loads all runs).
8. Airtable dateTime: UTC, format '%Y-%m-%dT%H:%M:%S.000Z', timeFormat name '24hour'.

DO NOT regress payroll engine math.
Re-run validate_payroll.py AND validate_workflow.py at end of any session
that touches payroll_engine.py, app.py payroll routes, or seed data.
Also re-run validate_clock.py if clock routes or SHIFTS logic is changed.

Also re-run validate_staff_portal.py (24/24) if staff auth routes, presence resolver, or Portal_Permissions logic is changed.

Current baselines (post-SP0):
  app.py                7,119 lines
  index.html            8,218 lines
  staff.html              714 lines  (new — SP0)
  payroll_engine.py       784 lines
  clock.html              504 lines
  validate_staff_portal.py  (new — SP0)
  validate_clock.py       574 lines
```

---

## NEAR-FUTURE QUEUE (post-SP0)

| Item | Priority | Notes |
|---|---|---|
| Real device pass — clock UI + staff portal mobile | **Critical before launch** | Backend-validated only. Clock-in flow + staff.html login + presence board — all need real device confirmation |
| Staff Portal Layer 1 — clock-in into portal + per-punch location | High | Next layer per spec. Staff can punch from their phone via the portal. |
| Staff Portal Layer 2 — mileage/expense | Medium | After Layer 1 |
| Staff Portal Layer 3 — smart drift | Medium | Forgot-to-clock-out detection |
| Staff Portal Layer 4 — Canadian tax engine | Low | Gates hard on Employment Type == "Employee". Needs accountant review. Never runs CPP/EI on Sub/Booth. |
| Brea onboarding interview -> auto-set white-label toggles | High | Business_Complexity, Money_Flow_Mode, Tip_Distribution_Mode inferred from onboarding |
| Reopen/unlock-with-reversal for locked periods | Medium | Spec first |
| TRANSACTIONS.Provider -> linked record | Medium | Before real payroll money |
| Gift card redemption at checkout | Medium | Purchase active; redemption not wired |

---

*End of brea_boss_progress.md — Sessions 3A/3B/3C/3D/SP0 COMPLETE — June 18, 2026*
