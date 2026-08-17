#!/usr/bin/env python3
"""
AgentBridge Atlas - x402 M2M Payment Client Example

This script demonstrates the complete M2M micro-payment flow:
1. Call API without payment → get 402 challenge
2. Sign EIP-3009 TransferWithAuthorization (gasless)
3. Retry with X-Payment header → get 200 + data

Requirements:
    pip install requests eth-account eth-abi

Usage:
    python agent_client.py --keyword GDP
    python agent_client.py --keyword CPI --limit 5

Environment variables:
    PRIVATE_KEY  - Your ETH private key (wallet must have USDC on Base)
                  Export: export PRIVATE_KEY=0x...
"""

import os
import sys
import json
import base64
import time
import argparse
import requests

# --- Config ---
API_BASE = "https://api.060504.shop"
# API_BASE = "http://localhost:8000"  # Use for local testing

# x402 payment config (from server's 402 challenge response)
USDC_CONTRACT = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"  # USDC on Base
CHAIN_ID = 8453  # Base mainnet
RECIPIENT = "0x1630c8E0833c367F39f0ca909b6b67f5159d7A00"  # AgentBridge wallet

# EIP-3009 domain separator type hash (TransferWithAuthorization)
TRANSFER_WITH_AUTHORIZATION_TYPEHASH = (
    "0x7c8f3b7e"  # Will be computed properly below
)

# Proper EIP-3009 TransferWithAuthorization type hash
EIP3009_TYPES = {
    "TransferWithAuthorization": [
        {"name": "from", "type": "address"},
        {"name": "to", "type": "address"},
        {"name": "value", "type": "uint256"},
        {"name": "validAfter", "type": "uint256"},
        {"name": "validBefore", "type": "uint256"},
        {"name": "nonce", "type": "bytes32"},
    ]
}


def get_private_key():
    """Get private key from environment."""
    pk = os.environ.get("PRIVATE_KEY")
    if not pk:
        print("ERROR: Set PRIVATE_KEY environment variable")
        print("  export PRIVATE_KEY=0x...")
        sys.exit(1)
    if not pk.startswith("0x"):
        pk = "0x" + pk
    return pk


def build_domain_separator():
    """Build EIP-712 domain separator for USDC on Base."""
    from eth_account.messages import encode_structured_data

    # USDC domain separator on Base
    domain = {
        "name": "USD Coin",
        "version": "2",
        "chainId": CHAIN_ID,
        "verifyingContract": USDC_CONTRACT,
    }
    return domain


def sign_transfer_authorization(private_key, amount_micro_usdc):
    """
    Sign EIP-3009 TransferWithAuthorization.

    This creates a gasless transfer authorization that the recipient
    (AgentBridge server) can submit to collect the payment.

    Args:
        private_key: Sender's private key
        amount_micro_usdc: Amount in micro-USDC (1 USDC = 1,000,000)

    Returns:
        Dict with signature components
    """
    from eth_account import Account
    from eth_account.messages import encode_structured_data
    import secrets

    account = Account.from_key(private_key)
    sender = account.address

    valid_after = int(time.time())
    valid_before = int(time.time()) + 3600  # 1 hour validity
    nonce = "0x" + secrets.token_hex(16)

    domain = build_domain_separator()

    message = {
        "types": EIP3009_TYPES,
        "domain": domain,
        "primaryType": "TransferWithAuthorization",
        "message": {
            "from": sender,
            "to": RECIPIENT,
            "value": amount_micro_usdc,
            "validAfter": valid_after,
            "validBefore": valid_before,
            "nonce": nonce,
        },
    }

    encoded = encode_structured_data(message)
    signed = account.sign_message(encoded)

    return {
        "from": sender,
        "to": RECIPIENT,
        "value": amount_micro_usdc,
        "validAfter": valid_after,
        "validBefore": valid_before,
        "nonce": nonce,
        "v": signed.v,
        "r": hex(signed.r),
        "s": hex(signed.s),
    }


def encode_payment_header(payment_data):
    """
    Encode payment data as base64 for X-Payment header.
    Format matches x402 v2 specification.
    """
    payment_json = json.dumps(payment_data, separators=(",", ":"))
    return base64.b64encode(payment_json.encode()).decode()


def query_industry(keyword, limit=12, period="latest"):
    """
    Query China NBS industry statistics via x402 payment.

    Flow:
    1. POST without payment → 402 challenge
    2. Sign EIP-3009 → encode → X-Payment header
    3. POST with payment → 200 + data
    """
    print(f"\n{'='*60}")
    print(f"  Querying: {keyword} (limit={limit}, period={period})")
    print(f"{'='*60}")

    endpoint = f"{API_BASE}/v1/api/industry"
    body = {"keyword": keyword, "limit": limit, "period": period}

    # --- Step 1: Trigger 402 payment challenge ---
    print("\n[1] Sending request without payment...")
    resp = requests.post(
        endpoint,
        json=body,
        headers={"Content-Type": "application/json"},
        proxies={"http": None, "https": None},  # Bypass system proxy
    )

    if resp.status_code != 402:
        if resp.status_code == 200:
            print(f"    Got 200 (payment bypass active?)")
            print(f"    Data: {json.dumps(resp.json(), ensure_ascii=False, indent=2)[:500]}")
            return resp.json()
        else:
            print(f"    Unexpected status: {resp.status_code}")
            print(f"    Body: {resp.text[:500]}")
            return None

    challenge = resp.json()
    print(f"    Got 402 Payment Required")
    print(f"    x402Version: {challenge.get('x402Version', '?')}")
    print(f"    Resource: {challenge.get('resource', {}).get('description', '?')}")

    # Extract payment requirements
    accepts = challenge.get("accepts", [])
    if not accepts:
        print("    ERROR: No payment requirements in 402 response")
        return None

    payment_req = accepts[0]
    amount = int(payment_req.get("amount", 0))
    pay_to = payment_req.get("payTo", RECIPIENT)

    print(f"    Amount: {amount} micro-USDC ({amount/1_000_000} USDC)")
    print(f"    Pay to: {pay_to}")
    print(f"    Network: {payment_req.get('network', '?')}")
    print(f"    Asset: {payment_req.get('asset', '?')}")

    # --- Step 2: Sign EIP-3009 ---
    print("\n[2] Signing EIP-3009 TransferWithAuthorization (gasless)...")
    private_key = get_private_key()

    payment_data = sign_transfer_authorization(private_key, amount)
    payment_header = encode_payment_header(payment_data)

    print(f"    From: {payment_data['from']}")
    print(f"    Nonce: {payment_data['nonce']}")
    print(f"    Valid: {payment_data['validAfter']} → {payment_data['validBefore']}")
    print(f"    Signature: v={payment_data['v']}, r={payment_data['r'][:10]}...")
    print(f"    X-Payment header: {payment_header[:60]}...")

    # --- Step 3: Retry with payment ---
    print("\n[3] Retrying with X-Payment header...")
    resp = requests.post(
        endpoint,
        json=body,
        headers={
            "Content-Type": "application/json",
            "X-Payment": payment_header,
        },
        proxies={"http": None, "https": None},
    )

    if resp.status_code == 200:
        print(f"\n    ✅ SUCCESS! Status: {resp.status_code}")
        data = resp.json()
        print(f"    Data received:")
        print(json.dumps(data, ensure_ascii=False, indent=2)[:1000])
        return data
    else:
        print(f"\n    ❌ FAILED! Status: {resp.status_code}")
        print(f"    Response: {resp.text[:500]}")
        return None


def test_free_endpoints():
    """Test all free discovery endpoints."""
    print(f"\n{'='*60}")
    print("  Testing Free Endpoints")
    print(f"{'='*60}")

    tests = [
        ("GET", "/health", 200, "Health check"),
        ("GET", "/openapi.json", 200, "OpenAPI spec"),
        ("GET", "/catalog.json", 200, "Asset catalog"),
        ("GET", "/llms.txt", 200, "LLM docs"),
        ("GET", "/.well-known/mcp/server-card.json", 200, "MCP server card"),
    ]

    for method, path, expected, desc in tests:
        url = f"{API_BASE}{path}"
        try:
            if method == "GET":
                resp = requests.get(url, proxies={"http": None, "https": None}, timeout=10)
            status = resp.status_code
            result = "✅" if status == expected else "❌"
            print(f"  {result} {method} {path} → {status} ({desc})")
        except Exception as e:
            print(f"  ❌ {method} {path} → ERROR: {e}")


def test_402_challenge():
    """Test that paid endpoints return 402 without payment."""
    print(f"\n{'='*60}")
    print("  Testing 402 Payment Challenges")
    print(f"{'='*60}")

    endpoints = [
        ("/v1/api/industry", {"keyword": "GDP"}, "Industry API"),
        ("/v1/api/policy", {"keyword": "tax"}, "Policy API"),
        ("/v1/api/company", {"name": "test"}, "Company API"),
    ]

    for path, body, desc in endpoints:
        url = f"{API_BASE}{path}"
        try:
            resp = requests.post(
                url, json=body,
                proxies={"http": None, "https": None}, timeout=10,
            )
            status = resp.status_code
            result = "✅" if status == 402 else "❌"
            print(f"  {result} POST {path} → {status} ({desc})")
        except Exception as e:
            print(f"  ❌ POST {path} → ERROR: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AgentBridge Atlas x402 M2M Client")
    parser.add_argument("--keyword", type=str, default="GDP",
                        help="Search keyword (GDP, CPI, PPI, etc.)")
    parser.add_argument("--limit", type=int, default=12,
                        help="Max data points to return")
    parser.add_argument("--period", type=str, default="latest",
                        help="Time period (latest, 2026Q1, 202601, etc.)")
    args = parser.parse_args()

    print("\n" + "=" * 60)
    print("  AgentBridge Atlas - x402 M2M Payment Client")
    print("  Chain: Base (8453) | Token: USDC | Protocol: EIP-3009")
    print("=" * 60)

    # Step 0: Test free endpoints
    test_free_endpoints()

    # Step 0b: Test 402 challenges
    test_402_challenge()

    # Step 1: Full x402 payment flow
    if os.environ.get("PRIVATE_KEY"):
        query_industry(args.keyword, args.limit, args.period)
    else:
        print(f"\n{'='*60}")
        print("  Full payment test skipped (no PRIVATE_KEY)")
        print("  Set: export PRIVATE_KEY=0x... to enable")
        print(f"{'='*60}")

    print("\nDone.\n")
