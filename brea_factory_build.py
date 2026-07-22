#!/usr/bin/env python3
"""
brea_factory_build.py
Session F1 — Wave 1 Factory Base Build

Creates all 9 BREA_FACTORY Airtable tables and seeds:
  - MASTER_CAPABILITY_REGISTRY  120 capabilities (IDs 001-120)
  - VERTICAL_PRESETS            5 industry verticals

NOTE: The knowledge base (v1.1, June 7 2026) contains 120 capabilities,
not 171. Both the KB and factory_progress.md confirm "120 capabilities
seeded at build." If the count has grown since this script was generated,
add new rows to CAPABILITIES before running.

Usage:
    1. Create BREA_FACTORY base in Airtable manually (do not add tables).
    2. Copy the base ID from the URL: https://airtable.com/appXXXXXXXXXXXX
    3. Create a Personal Access Token with scopes:
           data.records:write
           schema.bases:write
    4. Set environment variables (or create a .env file next to this script):
           AIRTABLE_TOKEN=patXXXXXX...
           FACTORY_BASE_ID=appXXXXXX...
    5. pip install requests python-dotenv
    6. python brea_factory_build.py

The script is idempotent-safe: it checks for existing tables and skips
any that are already present, so it is safe to re-run after a partial failure.
"""

import os
import sys
import time
import requests

try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))
except ImportError:
    pass


# ── Configuration ──────────────────────────────────────────────────────────────

AIRTABLE_TOKEN  = os.environ.get("AIRTABLE_TOKEN", "")
FACTORY_BASE_ID = os.environ.get("FACTORY_BASE_ID", "")

HEADERS = {
    "Authorization": f"Bearer {AIRTABLE_TOKEN}",
    "Content-Type":  "application/json",
}


# ── Low-level API helpers ──────────────────────────────────────────────────────

def _api_get(url: str) -> dict:
    resp = requests.get(url, headers=HEADERS)
    resp.raise_for_status()
    return resp.json()


def _api_post(url: str, payload: dict) -> dict:
    resp = requests.post(url, headers=HEADERS, json=payload)
    if not resp.ok:
        print(f"    ! HTTP {resp.status_code} -- {resp.text[:400]}")
        resp.raise_for_status()
    return resp.json()


def _meta_url() -> str:
    return f"https://api.airtable.com/v0/meta/bases/{FACTORY_BASE_ID}/tables"


def _records_url(table: str) -> str:
    return f"https://api.airtable.com/v0/{FACTORY_BASE_ID}/{table}"


def get_existing_tables() -> dict:
    """Returns {table_name: table_id} for all tables currently in the base."""
    data = _api_get(_meta_url())
    return {t["name"]: t["id"] for t in data.get("tables", [])}


def create_table(name: str, fields: list) -> str:
    """Creates a table and returns its new ID. Sleeps 0.6 s for rate limits."""
    result = _api_post(_meta_url(), {"name": name, "fields": fields})
    time.sleep(0.6)
    return result["id"]


def seed_table(table_name: str, records: list) -> None:
    """Inserts records in batches of 10 (Airtable maximum per request)."""
    url = _records_url(table_name)
    for i in range(0, len(records), 10):
        batch = records[i:i + 10]
        _api_post(url, {"records": [{"fields": r} for r in batch]})
        time.sleep(0.25)
    print(f"    Seeded {len(records):>3} records -> {table_name}")


# ── Field-type shorthand builders ──────────────────────────────────────────────

def text(name):
    return {"name": name, "type": "singleLineText"}

def longtext(name):
    return {"name": name, "type": "multilineText"}

def number(name):
    return {"name": name, "type": "number", "options": {"precision": 0}}

def checkbox(name):
    return {"name": name, "type": "checkbox",
            "options": {"icon": "check", "color": "greenBright"}}

def email(name):
    return {"name": name, "type": "email"}

def phone(name):
    return {"name": name, "type": "phoneNumber"}

def url_field(name):
    return {"name": name, "type": "url"}

def date(name):
    return {"name": name, "type": "date",
            "options": {"dateFormat": {"name": "local"}}}

def dt(name):
    return {"name": name, "type": "dateTime",
            "options": {
                "timeZone": "client",
                "dateFormat": {"name": "local"},
                "timeFormat": {"name": "12hour"},
            }}

def select(name, *choices):
    return {"name": name, "type": "singleSelect",
            "options": {"choices": [{"name": c} for c in choices]}}

def multiselect(name, *choices):
    return {"name": name, "type": "multipleSelects",
            "options": {"choices": [{"name": c} for c in choices]}}


# ── Table schema definitions ───────────────────────────────────────────────────
# The first field in each list becomes Airtable's primary field for that table.

def _schema_master_capability_registry():
    return ("MASTER_CAPABILITY_REGISTRY", [
        text("Capability_ID"),           # primary -- "001", "042", etc.
        text("Capability_Name"),
        select("Module",
            "UI & THEME", "NOTIFICATIONS", "CALENDAR", "DOCUMENTS", "NOTES",
            "MEMORY & STATE MACHINE", "VOICE", "TELEPHONY", "BOOKING",
            "PROMOTIONS", "DIAGNOSTICS", "ONBOARDING", "FINANCE",
            "FAMILY + REMINDERS", "BUSINESS TAB + CROSS-BASE",
            "EMAIL + COMMUNICATIONS", "MOBILE",
        ),
        select("Status", "Active", "Pending Build", "Degraded", "Broken", "Deprecated"),
        text("Status_Notes"),            # e.g. "401 Intermittent", "Session H"
        select("Scope", "Brea 3", "All Tenants", "Factory", "BEOS", "BEOS + Tenants"),
        select("Tier", "Master", "T1", "T2", "T3"),
        text("Shipped_In_Session"),
        date("Date_Shipped"),
        date("Last_Verified"),
        longtext("Dependencies"),
        longtext("Notes"),
    ])


def _schema_master_diagnostic_log():
    return ("MASTER_DIAGNOSTIC_LOG", [
        text("Error_Name"),              # primary -- e.g. "BREA3-2026-0001"
        text("Instance_ID"),
        select("Instance_Type", "Brea 3", "BEOS", "Factory", "Tenant"),
        text("Tenant_ID"),
        text("Tenant_Name"),
        text("Capability_ID"),
        select("Error_Category", "Transient", "Misuse", "Hard Break", "Recovery"),
        select("Error_Type", "Hard Failure", "Degraded", "Warning", "Recovery"),
        longtext("Error_Message"),
        longtext("Brea_Diagnosis"),
        longtext("Context_At_Failure"),
        checkbox("Data_At_Risk"),
        select("Suspected_Cause",
            "External API", "Expired Key", "Schema Mismatch",
            "Code Break", "User Input", "Unknown",
        ),
        longtext("Suggested_Fix"),
        checkbox("Fallback_Activated"),
        text("Fallback_Description"),
        number("Retry_Count"),
        checkbox("Escalated_To_Factory"),
        dt("Escalation_Timestamp"),
        text("Escalation_Source"),
        select("Factory_Review_Status", "Unreviewed", "Reviewed", "Assigned", "Resolved"),
        longtext("Factory_Notes"),
        checkbox("Pattern_Flag"),
        number("Pattern_Count"),
        checkbox("Notification_Fired"),
        select("Notification_Type", "Bubble Only", "Badge Only", "Bubble and Badge", "None"),
        select("Notification_Color", "Red", "Gold", "None"),
        select("Resolution_Status",
            "Open", "Auto-Resolved", "Investigating", "Fixed", "Accepted Degradation",
        ),
        dt("Resolved_At"),
        text("Resolved_By"),
        text("Session_Wave"),
    ])


def _schema_tenant_registry():
    return ("TENANT_REGISTRY", [
        text("Tenant_Name"),             # primary
        text("Tenant_ID"),
        select("Instance_Type", "Brea 3", "BEOS", "Factory", "Tenant"),
        text("Twilio_Number"),
        text("Airtable_Base_ID"),
        text("Airtable_API_Key"),
        select("Tier", "T1", "T2", "T3"),
        select("Vertical", "Beauty", "Fitness", "Medical Spa", "Wellness", "Hospitality", "Other"),
        select("Status", "Active", "Pending", "Suspended"),
        date("Date_Provisioned"),
        text("Owner_Name"),
        email("Owner_Email"),
        phone("Owner_Phone"),
        longtext("Modules_Enabled"),
        longtext("Notes"),
    ])


def _schema_onboarding_pipeline():
    return ("ONBOARDING_PIPELINE", [
        text("Business_Name"),           # primary
        text("Owner_Name"),
        email("Owner_Email"),
        phone("Owner_Phone"),
        select("Vertical", "Beauty", "Fitness", "Medical Spa", "Wellness", "Hospitality", "Other"),
        select("Stage", "Lead", "Intake In Progress", "Captured", "Reviewed", "Provisioning", "Live"),
        longtext("Modules_Inferred"),
        checkbox("Time_Anatomy_Complete"),
        number("Completeness_Score"),
        longtext("Interview_Notes"),
        longtext("Modules_Enabled"),
        select("Channel_Tier", "T1", "T2", "T3"),
        text("Voice_Reference"),
        text("Locale"),
        text("Tax_Profile"),
        text("Reviewed_By"),
        dt("Reviewed_At"),
        dt("Provisioned_At"),
        text("Tenant_ID"),
        longtext("Notes"),
    ])


def _schema_vertical_presets():
    return ("VERTICAL_PRESETS", [
        text("Vertical_Name"),           # primary -- "Beauty -- Full Service Salon & Spa"
        text("Vertical_Slug"),
        longtext("Terminology"),
        longtext("Default_Modules"),
        longtext("Default_Time_Anatomy"),
        longtext("Sample_Services"),
        longtext("Sample_Providers"),
        longtext("Dependency_Notes"),
        longtext("Notes"),
    ])


def _schema_provisioning_log():
    return ("PROVISIONING_LOG", [
        text("Log_Title"),               # primary -- e.g. "BEOS-001 Boujie Girl"
        text("Tenant_ID"),
        text("Tenant_Name"),
        text("Base_ID_Created"),
        dt("Provisioned_At"),
        text("Provisioned_By"),
        text("Template_Used"),
        longtext("Modules_Enabled"),
        number("Capabilities_Copied"),
        select("Status", "Success", "Failed", "Partial"),
        longtext("Error_Notes"),
        text("Session_Wave"),
    ])


def _schema_north_stars_template():
    return ("NORTH_STARS_TEMPLATE", [
        text("Star_Name"),               # primary -- "Scale to 10 Clients"
        longtext("Full_Statement"),
        select("Horizon", "90 Days", "6 Months", "1 Year", "3 Years", "Ongoing"),
        longtext("Current_Milestone"),
        select("Health_Status", "On Track", "At Risk", "Needs Attention", "Achieved"),
        dt("Last_Referenced"),
        dt("Last_Updated"),
        number("Priority_Rank"),
        text("Owner_ID"),
    ])


def _schema_unresolved_stack_template():
    return ("UNRESOLVED_STACK_TEMPLATE", [
        text("Thread_ID"),               # primary -- unique per conversation thread
        text("Session_ID"),
        select("Vault", "Business", "Personal", "Financial", "Family"),
        text("Topic_Summary"),
        longtext("Unresolved_Question"),
        longtext("Data_Captured"),
        select("Priority", "Critical", "High", "Normal", "Low"),
        select("Trigger_Type",
            "Explicit Shift", "Mid-Sentence Drift", "External Interrupt",
            "Natural Pause", "Dependency Hold",
        ),
        dt("Pushed_At"),
        number("Stack_Position"),
        select("Status", "Active", "Popped", "Expired", "Closed"),
        dt("Popped_At"),
        dt("Closed_At"),
        checkbox("Carried_To_Next_Session"),
        longtext("Resolution_Summary"),
        text("North_Star_Linked"),
    ])


def _schema_task_queue():
    return ("TASK_QUEUE", [
        text("Task_Name"),               # primary
        longtext("Description"),
        text("Instance_ID"),
        select("Module",
            "UI & THEME", "NOTIFICATIONS", "CALENDAR", "DOCUMENTS", "NOTES",
            "MEMORY & STATE MACHINE", "VOICE", "TELEPHONY", "BOOKING",
            "PROMOTIONS", "DIAGNOSTICS", "ONBOARDING", "FINANCE",
            "FAMILY + REMINDERS", "BUSINESS TAB + CROSS-BASE",
            "EMAIL + COMMUNICATIONS", "MOBILE", "FACTORY", "INFRASTRUCTURE",
        ),
        text("Capability_ID"),
        select("Priority", "Critical", "High", "Normal", "Low"),
        select("Status", "Queued", "In Progress", "Blocked", "Complete", "Cancelled"),
        text("Assigned_To"),
        text("Session_Wave"),
        date("Due_Date"),
        dt("Created_At"),
        dt("Completed_At"),
        longtext("Notes"),
    ])


ALL_SCHEMAS = [
    _schema_master_capability_registry,
    _schema_master_diagnostic_log,
    _schema_tenant_registry,
    _schema_onboarding_pipeline,
    _schema_vertical_presets,
    _schema_provisioning_log,
    _schema_north_stars_template,
    _schema_unresolved_stack_template,
    _schema_task_queue,
]


# ── Capability seed data ───────────────────────────────────────────────────────
# Columns: (module, id, name, raw_status, scope, tier, session)
# Source:  BREA_EMPIRE_MASTER_KNOWLEDGE_BASE.md v1.1, June 7 2026
# Count:   120 capabilities (IDs 001-120; NOTES module uses IDs 114-120)

CAPABILITIES = [
    # ── UI & THEME (001-009) ────────────────────────────────────────────────
    ("UI & THEME",               "001", "Three Layer Architecture",                     "Active",                           "Brea 3",        "Master", "Wave 1"),
    ("UI & THEME",               "002", "Gold Theme Dynamic CSS Variable",              "Active",                           "Brea 3",        "Master", "Wave 1"),
    ("UI & THEME",               "003", "Dashboard Pull-Down Gesture",                  "Active",                           "Brea 3",        "Master", "Wave 1"),
    ("UI & THEME",               "004", "Mic FAB",                                      "Active",                           "Brea 3",        "Master", "Wave 1"),
    ("UI & THEME",               "005", "BREA Title Metallic Gradient Animation",       "Active",                           "Brea 3",        "Master", "Wave 1"),
    ("UI & THEME",               "006", "askbrea-logo Watermark",                       "Active",                           "Brea 3",        "Master", "Wave 1"),
    ("UI & THEME",               "007", "Brand Color Picker",                           "Active",                           "Brea 3",        "Master", "Wave 1"),
    ("UI & THEME",               "008", "Custom Icon Set",                              "Active",                           "Brea 3",        "Master", "Wave 1"),
    ("UI & THEME",               "009", "White Label Theme Variables",                  "Active",                           "All Tenants",   "T1",     "Wave 1"),
    # ── NOTIFICATIONS (010-017) ─────────────────────────────────────────────
    ("NOTIFICATIONS",            "010", "Bubble Notification (Gold)",                   "Active",                           "All Tenants",   "T1",     "Wave 11"),
    ("NOTIFICATIONS",            "011", "Bubble Notification (Red -- Error)",           "Active",                           "All Tenants",   "T1",     "Wave 11"),
    ("NOTIFICATIONS",            "012", "Badge Notification",                           "Active",                           "All Tenants",   "T1",     "Wave 11"),
    ("NOTIFICATIONS",            "013", "Voice Notification",                           "Active",                           "Brea 3",        "Master", "Wave 11"),
    ("NOTIFICATIONS",            "014", "Browser Notification",                         "Active",                           "Brea 3",        "Master", "Wave 11"),
    ("NOTIFICATIONS",            "015", "dashboard_open Auto-Emitter",                  "Active",                           "Brea 3",        "Master", "Wave 11"),
    ("NOTIFICATIONS",            "016", "Diagnostic Escalation Bubble + Badge",         "Pending Build",                    "All Tenants",   "T1",     ""),
    ("NOTIFICATIONS",            "017", "Factory Escalation Notification",              "Pending Build",                    "Factory",       "Master", ""),
    # ── CALENDAR (018-029) ──────────────────────────────────────────────────
    ("CALENDAR",                 "018", "Calendar Intent Detection",                    "Active",                           "Brea 3",        "Master", "Wave 11"),
    ("CALENDAR",                 "019", "LLM Field Extraction",                         "Active",                           "Brea 3",        "Master", "Wave 11"),
    ("CALENDAR",                 "020", "Date + Time Natural Language Resolution",      "Active",                           "Brea 3",        "Master", "Wave 11"),
    ("CALENDAR",                 "021", "Airtable Write to CALENDAR_EVENTS",            "Active",                           "Brea 3",        "Master", "Wave 11"),
    ("CALENDAR",                 "022", "Confirmation Appended to Reply",               "Active",                           "Brea 3",        "Master", "Wave 11"),
    ("CALENDAR",                 "023", "Calendar Panel Sort + Date Labels",            "Active",                           "Brea 3",        "Master", "Wave 11"),
    ("CALENDAR",                 "024", "Add Event Modal",                              "Active",                           "Brea 3",        "Master", "Wave 11"),
    ("CALENDAR",                 "025", "Join Button on Event Cards",                   "Active",                           "Brea 3",        "Master", "Wave 11"),
    ("CALENDAR",                 "026", "Calendar Confirmation Path",                   "Pending -- Diffs Not Applied",     "Brea 3",        "Master", "Wave 11"),
    ("CALENDAR",                 "027", "Generic Calendar Connector Pattern",           "Active",                           "Brea 3",        "Master", "Wave 11"),
    ("CALENDAR",                 "028", "Google Calendar Sync",                         "Pending Build -- Session H",       "Brea 3",        "Master", ""),
    ("CALENDAR",                 "029", "iCal URL Connector",                           "Pending Build -- Session H",       "Brea 3",        "Master", ""),
    # ── DOCUMENTS (030-039) ─────────────────────────────────────────────────
    ("DOCUMENTS",                "030", "Document Vault Airtable Connection",           "Active",                           "Brea 3",        "Master", "Wave 11"),
    ("DOCUMENTS",                "031", "Claude Vision Extraction",                     "Pending -- API Key Missing",       "Brea 3",        "Master", "Session D"),
    ("DOCUMENTS",                "032", "jscanify Scan Preview Modal",                  "Pending Build -- Session D",       "Brea 3",        "Master", ""),
    ("DOCUMENTS",                "033", "Doc Type + Extracted Text Classification",     "Pending Build -- Session D",       "Brea 3",        "Master", ""),
    ("DOCUMENTS",                "034", "Pristine Asset Tracker",                       "Pending Build -- Session D",       "Brea 3",        "Master", ""),
    ("DOCUMENTS",                "035", "Documents Panel Type Badges + Expand View",    "Pending Build -- Session D",       "Brea 3",        "Master", ""),
    ("DOCUMENTS",                "036", "Brea ReadBack Widget",                         "Pending Build -- Post Session D",  "Brea 3",        "T3",     ""),
    ("DOCUMENTS",                "037", "ReadBack Playback Controls",                   "Pending Build -- Post Session D",  "Brea 3",        "T3",     ""),
    ("DOCUMENTS",                "038", "ReadBack Summary",                             "Pending Build -- Post Session D",  "Brea 3",        "T3",     ""),
    ("DOCUMENTS",                "039", "ReadBack Legal Decode",                        "Pending Build -- Post Session D",  "Brea 3",        "T3",     ""),
    # ── MEMORY & STATE MACHINE (040-048) ────────────────────────────────────
    ("MEMORY & STATE MACHINE",   "040", "Long-Term Memory with Permanent Lock",         "Active",                           "Brea 3",        "Master", "Early Wave"),
    ("MEMORY & STATE MACHINE",   "041", "Session Summaries",                            "Active",                           "Brea 3",        "Master", "Early Wave"),
    ("MEMORY & STATE MACHINE",   "042", "Preference Learning",                          "Active",                           "Brea 3",        "Master", "Early Wave"),
    ("MEMORY & STATE MACHINE",   "043", "Goals / North Stars Table",                    "Active",                           "All Tenants",   "Master", "Early Wave"),
    ("MEMORY & STATE MACHINE",   "044", "Unresolved Stack -- State Machine",            "Pending Build",                    "All Tenants",   "Master", ""),
    ("MEMORY & STATE MACHINE",   "045", "Session Open Carry-Forward",                   "Pending Build",                    "All Tenants",   "Master", ""),
    ("MEMORY & STATE MACHINE",   "046", "Session Close-Out Summary",                    "Pending Build",                    "All Tenants",   "Master", ""),
    ("MEMORY & STATE MACHINE",   "047", "15-Minute Surface Rule",                       "Pending Build",                    "All Tenants",   "Master", ""),
    ("MEMORY & STATE MACHINE",   "048", "Pattern Recognition -- Recurring Open Loops",  "Pending Build",                    "All Tenants",   "Master", ""),
    # ── VOICE (049-056) ─────────────────────────────────────────────────────
    ("VOICE",                    "049", "TTS Pipeline -- ElevenLabs",                   "Degraded -- 401 Intermittent",     "Brea 3",        "Master", ""),
    ("VOICE",                    "050", "STT -- Deepgram",                              "Active",                           "Brea 3",        "Master", ""),
    ("VOICE",                    "051", "Silero VAD",                                   "Degraded -- Energy Fallback Active","Brea 3",       "Master", ""),
    ("VOICE",                    "052", "Energy VAD Fallback",                          "Active",                           "Brea 3",        "Master", ""),
    ("VOICE",                    "053", "Voice Multi-Turn",                             "Broken -- Parked",                 "Brea 3",        "Master", ""),
    ("VOICE",                    "054", "Fish Speech Migration",                        "Pending Build -- Future Wave",     "Brea 3",        "Master", ""),
    ("VOICE",                    "055", "Wake Word -- Hey Brea",                        "Pending Build -- Future Wave",     "Brea 3",        "Master", ""),
    ("VOICE",                    "056", "Whisper + TTS Phase 3",                        "Pending Build -- Brea 3 Phase 3",  "Brea 3",        "Master", ""),
    # ── TELEPHONY (057-065) ─────────────────────────────────────────────────
    ("TELEPHONY",                "057", "Twilio WebSocket Inbound Call Handler",        "Pending Build -- Post Phase 3",    "BEOS + Tenants","T2",     ""),
    ("TELEPHONY",                "058", "Tenant Resolver",                              "Pending Build",                    "BEOS + Tenants","T2",     ""),
    ("TELEPHONY",                "059", "SYSTEM_CONFIG Read-Once Cache",                "Pending Build",                    "BEOS + Tenants","T2",     ""),
    ("TELEPHONY",                "060", "Call Open Sequence",                           "Pending Build",                    "BEOS + Tenants","T2",     ""),
    ("TELEPHONY",                "061", "Call Close + Post-Call Synthesis",             "Pending Build",                    "BEOS + Tenants","T2",     ""),
    ("TELEPHONY",                "062", "Telephony Log Write",                          "Pending Build",                    "BEOS + Tenants","T2",     ""),
    ("TELEPHONY",                "063", "Mid-Call SMS Dispatch",                        "Pending Build",                    "BEOS + Tenants","T2",     ""),
    ("TELEPHONY",                "064", "Callback Request Trigger",                     "Pending Build",                    "BEOS + Tenants","T2",     ""),
    ("TELEPHONY",                "065", "Resolution Status + Badge",                    "Pending Build",                    "BEOS + Tenants","T2",     ""),
    # ── BOOKING (066-071) ───────────────────────────────────────────────────
    ("BOOKING",                  "066", "FAQ Handling",                                 "Pending Build",                    "All Tenants",   "T1",     ""),
    ("BOOKING",                  "067", "Basic Scheduling -- Airtable Write",           "Pending Build",                    "All Tenants",   "T1",     ""),
    ("BOOKING",                  "068", "Overlap Booking Scan",                         "Pending Build",                    "All Tenants",   "T1",     ""),
    ("BOOKING",                  "069", "Time Anatomy Engine",                          "Pending Build",                    "All Tenants",   "T1",     ""),
    ("BOOKING",                  "070", "Resource Locking",                             "Pending Build",                    "All Tenants",   "T1",     ""),
    ("BOOKING",                  "071", "Provider Availability Logic",                  "Pending Build",                    "All Tenants",   "T1",     ""),
    # ── PROMOTIONS (072-076) ────────────────────────────────────────────────
    ("PROMOTIONS",               "072", "Promotion Submission -- Staff Portal",         "Pending Build",                    "BEOS + Tenants","T2",     ""),
    ("PROMOTIONS",               "073", "Approval Token Generation",                    "Pending Build",                    "BEOS + Tenants","T2",     ""),
    ("PROMOTIONS",               "074", "Promotion Queue -- Admin View",                "Pending Build",                    "BEOS + Tenants","T2",     ""),
    ("PROMOTIONS",               "075", "Verbal Promo Mention -- Token Validated",      "Pending Build",                    "BEOS + Tenants","T2",     ""),
    ("PROMOTIONS",               "076", "OG Proxy Link -- Dynamic Flask Route",         "Pending Build",                    "BEOS + Tenants","T2",     ""),
    # ── DIAGNOSTICS (077-083) ───────────────────────────────────────────────
    ("DIAGNOSTICS",              "077", "Local DIAGNOSTIC_LOG Write",                   "Pending Build",                    "All Tenants",   "Master", ""),
    ("DIAGNOSTICS",              "078", "Factory Escalation -- Hard Break",             "Pending Build",                    "All Tenants",   "Master", ""),
    ("DIAGNOSTICS",              "079", "Factory Escalation -- Transient Persisted",    "Pending Build",                    "All Tenants",   "Master", ""),
    ("DIAGNOSTICS",              "080", "Pattern Flag -- Misuse Threshold",             "Pending Build",                    "All Tenants",   "Master", ""),
    ("DIAGNOSTICS",              "081", "Auto-Recovery Log + Notification",             "Pending Build",                    "All Tenants",   "Master", ""),
    ("DIAGNOSTICS",              "082", "Capability Registry Self-Read",                "Pending Build",                    "All Tenants",   "Master", ""),
    ("DIAGNOSTICS",              "083", "Diagnostic Conversational Voice",              "Pending Build",                    "All Tenants",   "Master", ""),
    # ── ONBOARDING (084-091) ────────────────────────────────────────────────
    ("ONBOARDING",               "084", "Onboarding Interview -- Guided Conversation",  "Pending Build",                    "Factory",       "Master", ""),
    ("ONBOARDING",               "085", "Module Inference Engine",                      "Pending Build",                    "Factory",       "Master", ""),
    ("ONBOARDING",               "086", "Time Anatomy Coaching",                        "Pending Build",                    "Factory",       "Master", ""),
    ("ONBOARDING",               "087", "Vertical Preset Loader",                       "Pending Build",                    "Factory",       "Master", ""),
    ("ONBOARDING",               "088", "Completeness Checklist Gate",                  "Pending Build",                    "Factory",       "Master", ""),
    ("ONBOARDING",               "089", "Owner-Facing Summary Generation",              "Pending Build",                    "Factory",       "Master", ""),
    ("ONBOARDING",               "090", "Base Provisioning -- Template Duplication",    "Pending Build",                    "Factory",       "Master", ""),
    ("ONBOARDING",               "091", "Scoped Registry Copy on Provisioning",         "Pending Build",                    "Factory",       "Master", ""),
    # ── FINANCE (092-097) ───────────────────────────────────────────────────
    ("FINANCE",                  "092", "Finances Panel -- Shell",                      "Active",                           "Brea 3",        "Master", "Early Wave"),
    ("FINANCE",                  "093", "Expense Logging from Conversation",            "Pending Build -- Future Wave",     "Brea 3",        "Master", ""),
    ("FINANCE",                  "094", "Commission Split Logic",                       "Pending Build",                    "BEOS + Tenants","T3",     ""),
    ("FINANCE",                  "095", "Checkout Flow",                                "Pending Build -- BEOS",            "BEOS",          "T1",     ""),
    ("FINANCE",                  "096", "Gift Card Purchase + Redemption",              "Pending Build -- BEOS",            "BEOS",          "T1",     ""),
    ("FINANCE",                  "097", "Package + Membership Sell Flow",               "Pending Build -- BEOS",            "BEOS",          "T3",     ""),
    # ── FAMILY + REMINDERS (098-102) ────────────────────────────────────────
    ("FAMILY + REMINDERS",       "098", "Reminders Table -- Airtable",                 "Active",                           "Brea 3",        "Master", "Early Wave"),
    ("FAMILY + REMINDERS",       "099", "Reminders Panel -- Shell",                    "Active",                           "Brea 3",        "Master", "Early Wave"),
    ("FAMILY + REMINDERS",       "100", "Reminder Set from Conversation",              "Pending Build -- Future Wave",     "Brea 3",        "Master", ""),
    ("FAMILY + REMINDERS",       "101", "Family Panel -- Shell + Section Headers",     "Active",                           "Brea 3",        "Master", "Early Wave"),
    ("FAMILY + REMINDERS",       "102", "Family Task Add from Conversation",           "Pending Build -- Future Wave",     "Brea 3",        "Master", ""),
    # ── BUSINESS TAB + CROSS-BASE (103-106) ─────────────────────────────────
    ("BUSINESS TAB + CROSS-BASE","103", "Business Tab -- Placeholder",                 "Active",                           "Brea 3",        "Master", "Early Wave"),
    ("BUSINESS TAB + CROSS-BASE","104", "Cross-Base Read Authority -- Brea 3",          "Pending Build -- Future Wave",     "Brea 3",        "Master", ""),
    ("BUSINESS TAB + CROSS-BASE","105", "BEOS Tenant Summary Aggregator",               "Pending Build -- Future Wave",     "Brea 3",        "Master", ""),
    ("BUSINESS TAB + CROSS-BASE","106", "MetaHuman Pixel Stream -- iframe Slot",        "Pending Build -- Future Wave",     "All Tenants",   "T3",     ""),
    # ── EMAIL + COMMUNICATIONS (107-110) ────────────────────────────────────
    ("EMAIL + COMMUNICATIONS",   "107", "Email Gatekeeper -- Inbound Access",           "Pending Build -- Future Wave",     "Brea 3",        "Master", ""),
    ("EMAIL + COMMUNICATIONS",   "108", "Invoice Auto-Strip to Document Vault",         "Pending Build -- Future Wave",     "Brea 3",        "Master", ""),
    ("EMAIL + COMMUNICATIONS",   "109", "Zoom Link Extraction to Calendar",             "Pending Build -- Future Wave",     "Brea 3",        "Master", ""),
    ("EMAIL + COMMUNICATIONS",   "110", "Suggested Reply in Owner Voice",               "Pending Build -- Future Wave",     "Brea 3",        "Master", ""),
    # ── MOBILE (111-113) ────────────────────────────────────────────────────
    ("MOBILE",                   "111", "ngrok Mobile Access",                          "Active",                           "Brea 3",        "Master", "Wave 11"),
    ("MOBILE",                   "112", "Native Push Notifications",                    "Pending Build -- After Web Stable","Brea 3",        "Master", ""),
    ("MOBILE",                   "113", "Native Mobile App",                            "Pending Build -- Future Wave",     "Brea 3",        "Master", ""),
    # ── NOTES (114-120) ─────────────────────────────────────────────────────
    ("NOTES",                    "114", "Linked Notes Widget -- Notes Tab",              "Pending Build -- Post Session D",  "Brea 3",        "T3",     ""),
    ("NOTES",                    "115", "Note -> Calendar Event Link",                   "Pending Build",                    "Brea 3",        "T3",     ""),
    ("NOTES",                    "116", "Note -> Family Link",                           "Pending Build",                    "Brea 3",        "T3",     ""),
    ("NOTES",                    "117", "Note -> Business Link",                         "Pending Build",                    "Brea 3",        "T3",     ""),
    ("NOTES",                    "118", "Note -> Reminder Link",                         "Pending Build",                    "Brea 3",        "T3",     ""),
    ("NOTES",                    "119", "Note Contextual Surface by Brea",               "Pending Build",                    "Brea 3",        "T3",     ""),
    ("NOTES",                    "120", "Notes Search + Tag Filter",                     "Pending Build",                    "Brea 3",        "T3",     ""),
]

assert len(CAPABILITIES) == 120, f"Capability count mismatch: expected 120, got {len(CAPABILITIES)}"


def _parse_status(raw: str) -> tuple:
    """Splits a raw KB status string into (Status_Category, Status_Notes)."""
    raw = raw.strip()
    if raw == "Active":
        return ("Active", "")
    if raw.startswith("Degraded"):
        return ("Degraded", raw[len("Degraded"):].strip(" -").strip())
    if raw.startswith("Broken"):
        return ("Broken",   raw[len("Broken"):].strip(" -").strip())
    if raw == "Deprecated":
        return ("Deprecated", "")
    for prefix in ("Pending Build -- ", "Pending Build", "Pending -- ", "Pending"):
        if raw.startswith(prefix):
            return ("Pending Build", raw[len(prefix):].strip())
    return ("Pending Build", raw)


def _build_capability_records() -> list:
    records = []
    for (module, cap_id, name, raw_status, scope, tier, session) in CAPABILITIES:
        status_cat, status_notes = _parse_status(raw_status)
        rec = {
            "Capability_ID":   cap_id,
            "Capability_Name": name,
            "Module":          module,
            "Status":          status_cat,
            "Scope":           scope,
            "Tier":            tier,
        }
        if status_notes:
            rec["Status_Notes"] = status_notes
        if session and session not in ("", "--"):
            rec["Shipped_In_Session"] = session
        records.append(rec)
    return records


# ── Vertical preset seed data ──────────────────────────────────────────────────

VERTICAL_PRESETS_SEED = [
    {
        "Vertical_Name":        "Beauty -- Full Service Salon & Spa",
        "Vertical_Slug":        "beauty",
        "Terminology":          "Clients (not customers) | Stylists/Technicians | Services (not products) | Appointments | Stations (not rooms)",
        "Default_Modules":      "FAQ, Booking, Commission, Consumables, Checkout",
        "Default_Time_Anatomy": "Active: 45 min | Passive: 0 min | Overlap: No | Flip Buffer: 10-15 min",
        "Sample_Services":      "Haircut & Style | Color & Highlights | Blowout | Facial | Waxing | Nails",
        "Sample_Providers":     "Master Stylist | Junior Stylist | Esthetician | Nail Technician",
        "Dependency_Notes":     "Commission needs Consumables for service recipes. Checkout needs Booking.",
        "Notes":                "Live reference: BEOS -- Boujie Girl Specialty Beauty Boutique",
    },
    {
        "Vertical_Name":        "Fitness -- Gym & Personal Training",
        "Vertical_Slug":        "fitness",
        "Terminology":          "Members (not clients) | Trainers/Coaches | Sessions (not appointments) | Floor/Studio (not rooms)",
        "Default_Modules":      "FAQ, Booking, Membership, Triage, Commission",
        "Default_Time_Anatomy": "Active: 60 min | Passive: 0 min | Overlap: No | Flip Buffer: 5-10 min",
        "Sample_Services":      "Personal Training Session | Group Fitness Class | Assessment | Yoga | Spin",
        "Sample_Providers":     "Personal Trainer | Group Instructor | Coach",
        "Dependency_Notes":     "Triage needs Compliance + Commission. Membership needs Checkout. Walk-ins common.",
        "Notes":                "Package sales typical. Membership tier billing needed for T2+.",
    },
    {
        "Vertical_Name":        "Medical Spa",
        "Vertical_Slug":        "medspa",
        "Terminology":          "Patients (not clients) | Providers/Practitioners | Treatments (not services) | Suites (not rooms) | Protocols (not scripts)",
        "Default_Modules":      "FAQ, Booking, Compliance, Consumables, Commission, Aftercare",
        "Default_Time_Anatomy": "Active: 60 min | Passive: 20-45 min (numbing/processing) | Overlap: Yes (provider-specific) | Flip Buffer: 15 min",
        "Sample_Services":      "Botox/Filler | Laser Treatment | Chemical Peel | Microneedling | IV Therapy",
        "Sample_Providers":     "Nurse Practitioner | MD | PA | Esthetician",
        "Dependency_Notes":     "Compliance mandatory (signed waivers). Aftercare needs Consumables. Overlap during passive time is provider-specific.",
        "Notes":                "Highest liability vertical. Compliance module non-negotiable.",
    },
    {
        "Vertical_Name":        "Wellness & Holistic",
        "Vertical_Slug":        "wellness",
        "Terminology":          "Clients | Practitioners/Healers | Sessions/Treatments | Rooms/Studios",
        "Default_Modules":      "FAQ, Booking, Commission, Aftercare, Loyalty",
        "Default_Time_Anatomy": "Active: 60-90 min | Passive: 5 min (transition) | Overlap: No | Flip Buffer: 10 min",
        "Sample_Services":      "Massage Therapy | Reiki | Acupuncture | Sound Bath | Float Therapy | Hypnotherapy",
        "Sample_Providers":     "Licensed Massage Therapist | Acupuncturist | Energy Practitioner",
        "Dependency_Notes":     "Aftercare needs Consumables for product recommendations. Loyalty module high-value.",
        "Notes":                "High repeat-client rate. Loyalty module strongly recommended.",
    },
    {
        "Vertical_Name":        "Hospitality -- Boutique Hotel & Events",
        "Vertical_Slug":        "hospitality",
        "Terminology":          "Guests (not customers) | Staff/Concierge | Reservations (not bookings) | Rooms/Suites/Venues",
        "Default_Modules":      "FAQ, Booking, Triage, Hospitality, Loyalty, Commission",
        "Default_Time_Anatomy": "Active: Variable | Passive: N/A | Overlap: No | Flip Buffer: 30-60 min (room turnover)",
        "Sample_Services":      "Room Booking | Event Space | Spa Package | Concierge Service | Airport Transfer",
        "Sample_Providers":     "Concierge | Event Coordinator | Spa Manager",
        "Dependency_Notes":     "VIP treatment flag triggers Hospitality module. Triage for walk-in inquiries.",
        "Notes":                "High-value customization per property. Voice tier typically T3.",
    },
]


# ── Main ───────────────────────────────────────────────────────────────────────

def validate_env():
    errors = []
    if not AIRTABLE_TOKEN:
        errors.append("AIRTABLE_TOKEN is not set.")
    if not FACTORY_BASE_ID:
        errors.append("FACTORY_BASE_ID is not set.")
    if errors:
        for e in errors:
            print(f"  ERROR: {e}")
        print()
        print("  Add a .env file next to this script:")
        print("      AIRTABLE_TOKEN=patXXXX...")
        print("      FACTORY_BASE_ID=appXXXX...")
        sys.exit(1)
    masked = AIRTABLE_TOKEN[:12] + "..." if len(AIRTABLE_TOKEN) > 12 else AIRTABLE_TOKEN
    print(f"  Token : {masked}")
    print(f"  Base  : {FACTORY_BASE_ID}")


def main():
    print()
    print("=" * 60)
    print("  BREA FACTORY -- Base Build Script")
    print("  Session F1 | Wave 1 | June 2026")
    print("=" * 60)

    print()
    print("-- ENV CHECK ----------------------------------------")
    validate_env()

    print()
    print("-- PHASE 1: Checking existing tables ----------------")
    existing = get_existing_tables()
    if existing:
        names = [n for n in existing if n != "Table 1"]
        print(f"  Found: {', '.join(existing.keys()) if existing else 'none'}")
    else:
        print("  Base is empty -- proceeding.")

    print()
    print("-- PHASE 2: Creating tables -------------------------")
    created_ids = {}
    skipped = []

    for schema_fn in ALL_SCHEMAS:
        name, fields = schema_fn()
        if name in existing:
            print(f"  SKIP  {name}")
            skipped.append(name)
            created_ids[name] = existing[name]
        else:
            tid = create_table(name, fields)
            created_ids[name] = tid
            print(f"  OK    {name}  [{tid}]")

    new_count = len(ALL_SCHEMAS) - len(skipped)
    print(f"\n  Created: {new_count}  Skipped: {len(skipped)}")

    print()
    print("-- PHASE 3: Seeding MASTER_CAPABILITY_REGISTRY ------")
    cap_records = _build_capability_records()
    active_count   = sum(1 for r in cap_records if r["Status"] == "Active")
    pending_count  = sum(1 for r in cap_records if r["Status"] == "Pending Build")
    degraded_count = sum(1 for r in cap_records if r["Status"] == "Degraded")
    broken_count   = sum(1 for r in cap_records if r["Status"] == "Broken")
    seed_table("MASTER_CAPABILITY_REGISTRY", cap_records)
    print(f"    Active: {active_count}  Pending Build: {pending_count}  Degraded: {degraded_count}  Broken: {broken_count}")

    print()
    print("-- PHASE 4: Seeding VERTICAL_PRESETS ----------------")
    seed_table("VERTICAL_PRESETS", VERTICAL_PRESETS_SEED)

    print()
    print("=" * 60)
    print("  COMPLETE")
    print("=" * 60)
    print(f"  Tables       : {len(ALL_SCHEMAS)} total ({new_count} created, {len(skipped)} skipped)")
    print(f"  Capabilities : {len(cap_records)} seeded (IDs 001-120)")
    print(f"  Verticals    : {len(VERTICAL_PRESETS_SEED)} seeded")
    print()
    print("  REGISTRY UPDATES -- Wave 1 Session F1")
    print("  ---")
    print("  001-120 | MASTER_CAPABILITY_REGISTRY | Seeded | All statuses | F1")
    print()
    print("  Next steps:")
    print("  1. Add FACTORY_BASE_ID to BREA_BRAIN/.env")
    print("  2. Verify all 9 tables in Airtable UI")
    print("  3. Update factory_progress.md -- mark build complete")
    print()


if __name__ == "__main__":
    main()
