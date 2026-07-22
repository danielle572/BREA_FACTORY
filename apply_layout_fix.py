"""
apply_layout_fix.py
Fixes the Brea Factory dashboard layout:
- Voice tab is first and default
- Spec tab is second  
- Overview tab is third
- Mic button is compact and always visible at top
- Spec input is directly below voice
- No scrolling needed to reach mic or spec input
"""

import re, os, sys, shutil
from pathlib import Path

HTML_PATH = Path(r"C:\Users\Danielle\Desktop\BREA_FACTORY\dashboard\templates\index.html")

if not HTML_PATH.exists():
    print(f"  ERROR: {HTML_PATH} not found")
    sys.exit(1)

# Backup
backup = HTML_PATH.with_suffix(".html.bak")
shutil.copy2(HTML_PATH, backup)
print(f"  Backed up to {backup.name}")

content = HTML_PATH.read_text(encoding="utf-8")

# ── 1. Reorder tab buttons: Voice first (active), Spec second, Overview third
old_tabs = '<button class="tab-btn active" data-tab="overview">Overview</button>\n  <button class="tab-btn" data-tab="voice">Voice</button>\n  <button class="tab-btn" data-tab="spec">Spec</button>'
new_tabs = '<button class="tab-btn active" data-tab="voice">Voice</button>\n  <button class="tab-btn" data-tab="spec">Spec</button>\n  <button class="tab-btn" data-tab="overview">Overview</button>'

if old_tabs in content:
    content = content.replace(old_tabs, new_tabs)
    print("  Tab order updated: Voice > Spec > Overview")
else:
    print("  WARN: Could not find tab buttons in expected format — skipping tab reorder")

# ── 2. Make voice panel compact — mic at top, no big empty space
old_voice_panel_css = """.voice-panel{
  max-width:700px;margin:40px auto;padding:0 16px;
  display:flex;flex-direction:column;align-items:center;gap:32px;
}
.voice-controls{display:flex;flex-direction:column;align-items:center;gap:16px}
.mic-btn{
  width:88px;height:88px;border-radius:50%;border:none;cursor:pointer;
  background:var(--accent);color:#fff;
  display:flex;align-items:center;justify-content:center;
  transition:background .15s,transform .1s,box-shadow .15s;
  box-shadow:0 4px 20px rgba(200,169,110,.35);
}"""

new_voice_panel_css = """.voice-panel{
  max-width:900px;margin:0 auto;padding:16px 16px 0;
  display:grid;grid-template-columns:auto 1fr;gap:20px;align-items:start;
}
.voice-controls{display:flex;flex-direction:column;align-items:center;gap:8px;padding-top:4px}
.mic-btn{
  width:52px;height:52px;border-radius:50%;border:none;cursor:pointer;
  background:var(--accent);color:#fff;
  display:flex;align-items:center;justify-content:center;
  transition:background .15s,transform .1s,box-shadow .15s;
  box-shadow:0 2px 12px rgba(200,169,110,.35);
}"""

if old_voice_panel_css in content:
    content = content.replace(old_voice_panel_css, new_voice_panel_css)
    print("  Voice panel made compact")
else:
    print("  WARN: Voice panel CSS not found in expected format — skipping mic resize")

# ── 3. Make mic SVG smaller to match new button size
content = content.replace(
    '<svg width="32" height="32" viewBox="0 0 24 24"',
    '<svg width="20" height="20" viewBox="0 0 24 24"'
)

# ── 4. Set default tab to voice in JS
old_refresh = "refreshAll();\nsetInterval(refreshAll, 30_000);"
new_refresh  = "refreshAll();\nsetInterval(refreshAll, 30_000);\nswitchTab('voice');"

if old_refresh in content:
    content = content.replace(old_refresh, new_refresh)
    print("  Default tab set to Voice")
else:
    print("  WARN: Could not set default tab — refreshAll pattern not found")

# ── 5. Reorder tab panels: voice first, spec second, overview third
# Find the three panel divs and reorder them
voice_match  = re.search(r'(<div id="tab-voice".*?</div>\s*</div>)\s*\n', content, re.DOTALL)
spec_match   = re.search(r'(<div id="tab-spec".*?</div>\s*</div>)\s*\n', content, re.DOTALL)
overview_match = re.search(r'(<div id="tab-overview".*?</main>\s*</div>)\s*\n', content, re.DOTALL)

if voice_match and spec_match and overview_match:
    # Remove all three panels
    content = content.replace(voice_match.group(0), "")
    content = content.replace(spec_match.group(0), "")
    # Insert in correct order after tab-bar closing div
    insert_after = '</div>\n\n<div id="tab-overview"'
    replacement  = (
        '</div>\n\n'
        + voice_match.group(1) + '\n\n'
        + spec_match.group(1)  + '\n\n'
        + '<div id="tab-overview"'
    )
    content = content.replace(insert_after, replacement, 1)
    print("  Tab panel order updated: Voice > Spec > Overview")
else:
    print("  WARN: Could not reorder tab panels — panel structure not found")

# ── Write updated file
HTML_PATH.write_text(content, encoding="utf-8")
print(f"  Layout fix written to {HTML_PATH.name}")
print("  Done. Hard refresh the browser (Ctrl+Shift+R) to see changes.")
