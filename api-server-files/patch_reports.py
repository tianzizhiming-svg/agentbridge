#!/usr/bin/env python3
"""
patch_reports.py - Apply patch to main.py for 9 new industry reports.

Changes:
1. Add 9 entries to ATLAS_MANUAL_FILES dictionary
2. Update _atlas_deliver_manual to support .md files (not just PDF)
3. Sync catalog.json from GitHub to server local data dir
"""
import re
import os
import shutil
import json
import urllib.request

MAIN_PY = r"F:\afie_proxy\main.py"
DATA_DIR = r"F:\afie_proxy\data"
CATALOG_URL = "https://raw.githubusercontent.com/tianzizhiming-svg/agentbridge/master/docs/data/catalog.json"

# 9 new report entries for ATLAS_MANUAL_FILES
NEW_ENTRIES = {
    "report-ai-industry-2026":              "reports/China-AI-Industry-Report-2026.md",
    "report-consumer-market-2026":          "reports/China-Consumer-Market-Report-2026.md",
    "report-ev-industry-2026":              "reports/China-EV-Industry-Report-2026.md",
    "report-humanoid-robot-2026":           "reports/China-Humanoid-Robot-Report-2026.md",
    "report-api-tech-docs-2026":            "reports/China-Industry-API-Tech-Docs-2026.md",
    "report-market-entry-2026":             "reports/China-Market-Entry-Guide-2026.md",
    "report-new-energy-2026":              "reports/China-New-Energy-Report-2026.md",
    "report-semiconductor-2026":           "reports/China-Semiconductor-Report-2026.md",
    "report-university-intelligence-2026": "reports/China-University-Intelligence-Report-2026.md",
}


def main():
    print("=== AgentBridge: Patching main.py for 9 new reports ===")

    # Read main.py
    with open(MAIN_PY, "r", encoding="utf-8") as f:
        content = f.read()

    original = content

    # --- Patch 1: Add entries to ATLAS_MANUAL_FILES ---
    print("\n[1/3] Adding 9 entries to ATLAS_MANUAL_FILES...")

    # Find the closing } of ATLAS_MANUAL_FILES dict
    # Look for the last entry before closing brace
    new_lines = ""
    for asset_id, file_path in NEW_ENTRIES.items():
        # Check if already exists
        if asset_id in content:
            print(f"  [SKIP] Already exists: {asset_id}")
            continue
        new_lines += f'    "{asset_id}": "{file_path}",\n'

    if new_lines:
        # Insert before the closing brace of ATLAS_MANUAL_FILES
        # Find the pattern: the last entry line then closing }
        # The dict ends with a line like:    "guide-business-compliance-china-2026-08": "guides/guide-business-compliance-china-2026-08.md",
        # followed by }
        marker = '"guide-business-compliance-china-2026-08": "guides/guide-business-compliance-china-2026-08.md",'
        if marker in content:
            content = content.replace(marker, marker + "\n" + new_lines.rstrip())
            print(f"  [OK] Added {len(NEW_ENTRIES)} entries")
        else:
            # Alternative: find the closing } after ATLAS_MANUAL_FILES = {
            pattern = r'(ATLAS_MANUAL_FILES\s*=\s*\{[^}]*?)\n\}'
            match = re.search(pattern, content, re.DOTALL)
            if match:
                insert_point = match.end() - 2  # before \n}
                content = content[:insert_point] + new_lines + content[insert_point:]
                print(f"  [OK] Added {len(NEW_ENTRIES)} entries (alternative method)")
            else:
                print("  [ERR] Could not find ATLAS_MANUAL_FILES dict boundary")
                return

    # --- Patch 2: Update _atlas_deliver_manual for .md support ---
    print("\n[2/3] Updating _atlas_deliver_manual for .md support...")

    # Check if already patched
    if 'text/markdown' in content:
        print("  [SKIP] Already patched for .md support")
    else:
        # Replace the hardcoded media_type="application/pdf" in _atlas_deliver_manual
        old_block = '''            return FileResponse(
                path=str(file_path),
                filename=file_name,
                media_type="application/pdf",
            )'''

        new_block = '''            # Determine media type based on file extension
            if file_name.endswith(".md"):
                media_type = "text/markdown; charset=utf-8"
            else:
                media_type = "application/pdf"
            return FileResponse(
                path=str(file_path),
                filename=file_name,
                media_type=media_type,
            )'''

        if old_block in content:
            content = content.replace(old_block, new_block, 1)  # Only first occurrence in _atlas_deliver_manual
            print("  [OK] Patched _atlas_deliver_manual for .md support")
        else:
            print("  [WARN] Could not find exact block to replace. Manual patching needed.")

    # Write patched main.py
    if content != original:
        with open(MAIN_PY, "w", encoding="utf-8") as f:
            f.write(content)
        print("\n  [OK] main.py patched successfully")
    else:
        print("\n  [INFO] No changes needed (already patched)")

    # --- Patch 3: Sync catalog.json from GitHub ---
    print("\n[3/3] Syncing catalog.json from GitHub...")
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        catalog_path = os.path.join(DATA_DIR, "catalog.json")
        urllib.request.urlretrieve(CATALOG_URL, catalog_path)
        with open(catalog_path, "r", encoding="utf-8") as f:
            cat = json.load(f)
        print(f"  [OK] catalog.json synced: {len(cat.get('assets', []))} assets")
    except Exception as e:
        print(f"  [ERR] catalog.json sync failed: {e}")

    # Also sync products.json if it exists
    try:
        products_path = os.path.join(DATA_DIR, "products.json")
        # Check if products.json exists on GitHub
        products_url = "https://raw.githubusercontent.com/tianzizhiming-svg/agentbridge/master/docs/data/products-verified.json"
        urllib.request.urlretrieve(products_url, products_path)
        print(f"  [OK] products.json synced")
    except Exception as e:
        print(f"  [INFO] products.json sync skipped: {e}")

    print("\n=== Patch complete! ===")
    print("Next: nssm restart AgentBridge")


if __name__ == "__main__":
    main()
