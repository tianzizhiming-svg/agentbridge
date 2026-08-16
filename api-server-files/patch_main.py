# -*- coding: utf-8 -*-
"""
Patch script: update the injection in main.py to pass _build_payment_required
Run on server: python patch_main.py
"""
import os
import re
import py_compile

MAIN_PY = r"F:\afie_proxy\main.py"

# Read
with open(MAIN_PY, "r", encoding="utf-8") as f:
    content = f.read()

# Find and replace the register_china_data_routes call
old_call = """register_china_data_routes(
        app=app,
        x402_auth=x402_auth if 'x402_auth' in dir() else None,
        _make_402=_make_402 if '_make_402' in dir() else None,
    )"""

new_call = """register_china_data_routes(
        app=app,
        x402_auth=x402_auth if 'x402_auth' in dir() else None,
        _make_402=_make_402 if '_make_402' in dir() else None,
        _build_payment_required=_build_payment_required if '_build_payment_required' in dir() else None,
    )"""

if old_call in content:
    content = content.replace(old_call, new_call)
    print("[OK] Updated register_china_data_routes call to pass _build_payment_required")
else:
    # Try to find a partial match
    pattern = r"register_china_data_routes\([^)]+\)"
    match = re.search(pattern, content, re.DOTALL)
    if match:
        content = content[:match.start()] + new_call + content[match.end():]
        print("[OK] Replaced register_china_data_routes call (regex match)")
    else:
        print("[WARN] Could not find register_china_data_routes call")
        print("       The injection code may need manual editing")

# Write back
with open(MAIN_PY, "w", encoding="utf-8") as f:
    f.write(content)

# Verify syntax
try:
    py_compile.compile(MAIN_PY, doraise=True)
    print("[OK] Syntax verified")
except py_compile.PyCompileError as e:
    print(f"[FAIL] Syntax error: {e}")
    exit(1)

print("[DONE] Patch complete")
