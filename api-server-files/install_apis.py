# -*- coding: utf-8 -*-
"""
Install script for China Data APIs.
Run on the server: python install_apis.py

This script:
1. Copies china_data_api.py to F:\afie_proxy\
2. Patches main.py to import and register the new routes
3. Verifies syntax
4. Does NOT restart the service (user does that manually)
"""

import os
import sys
import shutil
import py_compile

API_DIR = r"F:\afie_proxy"
MAIN_PY = os.path.join(API_DIR, "main.py")
MODULE_FILE = "china_data_api.py"

# The code to append to main.py
INJECT_CODE = """

# ============================================================
# China Data APIs - Added by install_apis.py
# Source: government public data (NBS, gov.cn, gsxt.gov.cn)
# Compliance: respects robots.txt, no anti-crawl bypass
# ============================================================

try:
    from china_data_api import register_china_data_routes
    register_china_data_routes(
        app=app,
        x402_auth=x402_auth if 'x402_auth' in dir() else None,
        _make_402=_make_402 if '_make_402' in dir() else None,
    )
    print("[China Data APIs] Registered: /v1/api/industry, /v1/api/policy, /v1/api/company")
except ImportError as e:
    print(f"[China Data APIs] ImportError: {e}")
    print("[China Data APIs] Run: pip install httpx")
except Exception as e:
    print(f"[China Data APIs] Registration failed: {e}")

# ============================================================
# End China Data APIs
# ============================================================
"""

MARKER = "# China Data APIs - Added by install_apis.py"


def main():
    print("=== China Data API Installer ===")
    print(f"Target: {API_DIR}")
    print()

    # Step 1: Copy module file
    print("[1/4] Copying china_data_api.py...")
    src = os.path.join(os.path.dirname(os.path.abspath(__file__)), MODULE_FILE)
    if not os.path.exists(src):
        # Try current directory
        src = os.path.join(os.getcwd(), MODULE_FILE)

    if not os.path.exists(src):
        print(f"  [FAIL] {MODULE_FILE} not found")
        print(f"  Looked in: {os.path.dirname(os.path.abspath(__file__))} and {os.getcwd()}")
        sys.exit(1)

    dst = os.path.join(API_DIR, MODULE_FILE)
    shutil.copy2(src, dst)
    print(f"  [OK] Copied to {dst}")

    # Step 2: Check if httpx is available
    print()
    print("[2/4] Checking dependencies...")
    try:
        import httpx
        print("  [OK] httpx is installed")
    except ImportError:
        print("  [WARN] httpx not found, installing...")
        import subprocess
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "httpx"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            print("  [OK] httpx installed successfully")
        else:
            print(f"  [FAIL] Could not install httpx: {result.stderr}")
            print("  Please run manually: pip install httpx")
            sys.exit(1)

    # Step 3: Patch main.py
    print()
    print("[3/4] Patching main.py...")

    if not os.path.exists(MAIN_PY):
        print(f"  [FAIL] {MAIN_PY} not found")
        sys.exit(1)

    # Read main.py
    with open(MAIN_PY, "r", encoding="utf-8") as f:
        content = f.read()

    # Check if already patched
    if MARKER in content:
        print("  [INFO] main.py already patched, updating...")
        # Remove old injection
        idx = content.find(MARKER)
        # Find the start of the block (go back to find the comment line before)
        block_start = content.rfind("\n", 0, idx)
        if block_start == -1:
            block_start = idx
        # Find the end marker
        end_marker = "# End China Data APIs"
        block_end = content.find(end_marker)
        if block_end != -1:
            # Find the end of that line
            block_end = content.find("\n", block_end)
            if block_end != -1:
                block_end += 1
            else:
                block_end = len(content)
        else:
            block_end = len(content)

        content = content[:block_start] + content[block_end:]
        print("  [INFO] Removed old injection")

    # Append new injection
    content = content.rstrip() + "\n" + INJECT_CODE

    # Write back
    with open(MAIN_PY, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"  [OK] Patched main.py")

    # Step 4: Verify syntax
    print()
    print("[4/4] Verifying syntax...")

    try:
        py_compile.compile(MAIN_PY, doraise=True)
        print("  [OK] main.py syntax verified")
    except py_compile.PyCompileError as e:
        print(f"  [FAIL] Syntax error in main.py: {e}")
        print("  [INFO] Restoring backup...")
        # Restore from backup if exists
        backup = MAIN_PY + ".bak-china-data"
        if os.path.exists(backup):
            shutil.copy2(backup, MAIN_PY)
            print("  [OK] Restored from backup")
        sys.exit(1)

    # Also verify the module
    try:
        py_compile.compile(dst, doraise=True)
        print("  [OK] china_data_api.py syntax verified")
    except py_compile.PyCompileError as e:
        print(f"  [FAIL] Syntax error in china_data_api.py: {e}")
        sys.exit(1)

    print()
    print("=== Installation Complete ===")
    print()
    print("New API endpoints:")
    print("  GET  /v1/api/industry  - 402 payment info (amount: 2000 = $0.002)")
    print("  POST /v1/api/industry  - Query NBS statistics")
    print("  GET  /v1/api/policy    - 402 payment info (amount: 2000 = $0.002)")
    print("  POST /v1/api/policy    - Search government policies")
    print("  GET  /v1/api/company   - 402 payment info (amount: 1000 = $0.001)")
    print("  POST /v1/api/company   - Enterprise credit info")
    print()
    print("Data sources:")
    print("  - National Bureau of Statistics (data.stats.gov.cn)")
    print("  - China Government Search (sousuo.www.gov.cn)")
    print("  - Enterprise Credit System (gsxt.gov.cn)")
    print()
    print("Compliance features:")
    print("  - Rate limiting (1 req / 3 sec per domain)")
    print("  - No anti-crawl bypass (respects 403/captcha)")
    print("  - Source attribution in all responses")
    print("  - Government public data only")
    print()
    print("Next step: restart the service")
    print("  nssm stop AgentBridge")
    print("  Start-Sleep 3")
    print("  nssm start AgentBridge")
    print("  Start-Sleep 20")
    print('  (Invoke-WebRequest "http://localhost:8000/health" -UseBasicParsing).StatusCode')


if __name__ == "__main__":
    # Save backup before doing anything
    if os.path.exists(MAIN_PY):
        backup = MAIN_PY + ".bak-china-data"
        shutil.copy2(MAIN_PY, backup)
        print(f"Backup saved: {backup}")
        print()

    main()
