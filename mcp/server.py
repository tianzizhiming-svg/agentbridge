# -*- coding: utf-8 -*-
"""
AgentBridge Atlas MCP Server

Provides MCP tools for AI agents to discover, purchase, and consume
AgentBridge Atlas capabilities, including China Data APIs.

Tools:
  Discovery (free):
    - discover_capabilities       - List all API capabilities
    - discover_china_data_apis    - List China Data APIs with pricing
    - get_capability_info         - Get details for a specific capability
    - get_payment_instructions    - Step-by-step x402 payment guide

  China Data APIs (x402 paid):
    - query_industry_statistics   - Query NBS data (GDP, CPI, PPI, etc.)
    - search_china_policies       - Search government policy documents
    - query_company_credit        - Query enterprise credit information
"""

import os
import json
import base64
import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv()

ATLAS_API_URL = os.getenv(
    "ATLAS_API_URL",
    "https://api.060504.shop"
)

# Wallet for x402 payments
ATLAS_WALLET = "0x1630c8E0833c367F39f0ca909b6b67f5159d7A00"
ATLAS_NETWORK = "base-mainnet (eip155:8453)"
USDC_CONTRACT = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"

mcp = FastMCP("AgentBridge Atlas")


# ============================================================
# Helper: fetch OpenAPI spec
# ============================================================

async def fetch_openapi():
    """Fetch Atlas OpenAPI specification."""
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(f"{ATLAS_API_URL}/openapi.json")
        response.raise_for_status()
        return response.json()


# ============================================================
# Helper: get x402 payment challenge from an endpoint
# ============================================================

async def get_payment_challenge(endpoint: str) -> dict:
    """
    Call a GET endpoint to receive the x402 402 payment challenge.
    Returns the decoded payment required information.
    """
    url = f"{ATLAS_API_URL}{endpoint}"
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url)

    if resp.status_code != 402:
        return {
            "error": f"Expected 402, got {resp.status_code}",
            "body": resp.text[:500],
        }

    # Try to parse the JSON body (AgentBridge returns JSON 402)
    try:
        body = resp.json()
    except Exception:
        body = {"raw": resp.text[:500]}

    # Also check for PAYMENT-REQUIRED header
    payment_header = resp.headers.get("PAYMENT-REQUIRED", "")
    if payment_header:
        try:
            decoded = json.loads(base64.b64decode(payment_header))
            body["_decoded_header"] = decoded
        except Exception:
            body["_raw_header"] = payment_header[:200]

    return body


# ============================================================
# Discovery Tools (free)
# ============================================================

@mcp.tool()
async def discover_capabilities():
    """
    Discover all available capabilities from AgentBridge Atlas.

    Returns the full API catalog from the OpenAPI specification,
    including all endpoints, pricing, and payment protocols.
    """
    try:
        openapi = await fetch_openapi()
        return {
            "name": "AgentBridge Atlas",
            "description": openapi.get("info", {}).get("description", ""),
            "version": openapi.get("info", {}).get("version", ""),
            "base_url": ATLAS_API_URL,
            "endpoints": list(openapi.get("paths", {}).keys()),
            "total_endpoints": len(openapi.get("paths", {})),
            "payment": {
                "protocol": "x402 v2",
                "network": ATLAS_NETWORK,
                "currency": "USDC",
                "wallet": ATLAS_WALLET,
            },
        }
    except Exception as e:
        return {"error": str(e), "message": "Unable to fetch Atlas catalog."}


@mcp.tool()
async def discover_china_data_apis():
    """
    Discover China Data APIs available on AgentBridge Atlas.

    Returns detailed information about the three China Data API endpoints:
    - Industry Statistics (NBS data): $0.005 per query
    - Policy Search (gov.cn): $0.005 per query
    - Enterprise Credit (gsxt.gov.cn): $0.003 per query

    Each entry includes the input schema, pricing, and example usage.
    """
    return {
        "apis": [
            {
                "name": "China Industry Statistics API",
                "endpoint": "/v1/api/industry",
                "method": "POST",
                "price_usd": 0.005,
                "price_usdc_units": "5000",
                "description": (
                    "Query China National Bureau of Statistics data. "
                    "Search by keyword (GDP, CPI, PPI, etc.) and get "
                    "structured time-series data with values, periods, "
                    "and source attribution."
                ),
                "input_schema": {
                    "keyword": "string (required) - e.g. GDP, CPI, PPI",
                    "period": "string (optional) - 'latest' or '2026Q1'",
                    "limit": "int (optional, default 12) - max data points",
                },
                "example_input": {
                    "keyword": "GDP",
                    "period": "latest",
                    "limit": 10,
                },
                "data_source": "data.stats.gov.cn",
                "tags": ["raw-content", "china-data"],
            },
            {
                "name": "China Policy Search API",
                "endpoint": "/v1/api/policy",
                "method": "POST",
                "price_usd": 0.005,
                "price_usdc_units": "5000",
                "description": (
                    "Search Chinese government policy documents by keyword. "
                    "Returns title, issuing authority, document number, "
                    "publish date, summary, and source URL."
                ),
                "input_schema": {
                    "keyword": "string (required) - e.g. AI, new energy",
                    "date_from": "string (optional) - YYYY-MM-DD, default 90 days ago",
                    "limit": "int (optional, default 10) - max results",
                },
                "example_input": {
                    "keyword": "artificial intelligence",
                    "date_from": "2026-06-01",
                    "limit": 5,
                },
                "data_source": "sousuo.www.gov.cn",
                "tags": ["raw-content", "china-data"],
            },
            {
                "name": "China Enterprise Credit API",
                "endpoint": "/v1/api/company",
                "method": "POST",
                "price_usd": 0.003,
                "price_usdc_units": "3000",
                "description": (
                    "Query Chinese enterprise credit information from the "
                    "official National Enterprise Credit Information "
                    "Publicity System. Returns company registration details "
                    "and official search links."
                ),
                "input_schema": {
                    "name": "string (required) - company name, e.g. Alibaba",
                    "credit_code": "string (optional) - 18-digit Unified Social Credit Code",
                },
                "example_input": {
                    "name": "Alibaba",
                    "credit_code": None,
                },
                "data_source": "gsxt.gov.cn",
                "tags": ["raw-content", "china-data"],
            },
        ],
        "payment": {
            "protocol": "x402 v2",
            "network": ATLAS_NETWORK,
            "currency": "USDC on Base",
            "wallet": ATLAS_WALLET,
            "usdc_contract": USDC_CONTRACT,
        },
        "how_to_pay": (
            "1. Call GET on the endpoint to receive 402 challenge. "
            "2. Decode the accepts[0] field for amount and payTo address. "
            "3. Sign an EIP-3009 transfer for the exact amount in USDC. "
            "4. Retry POST with PAYMENT-SIGNATURE header containing the signed transfer. "
            "5. Server verifies on-chain and returns 200 with data."
        ),
    }


@mcp.tool()
async def get_capability_info(name: str):
    """
    Get detailed information about a specific capability.

    Args:
        name: Capability name or endpoint keyword (e.g. 'industry', 'policy', 'company')
    """
    try:
        openapi = await fetch_openapi()
        paths = openapi.get("paths", {})
        matched = {}
        for endpoint, details in paths.items():
            if name.lower() in endpoint.lower():
                matched[endpoint] = details
        return {
            "capability": name,
            "matches": matched,
            "match_count": len(matched),
        }
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def get_payment_instructions():
    """
    Get step-by-step instructions for making x402 payments on AgentBridge Atlas.

    Returns the complete payment flow including code examples for
    signing EIP-3009 transfers and retrying requests with payment.
    """
    return {
        "protocol": "x402 v2",
        "network": ATLAS_NETWORK,
        "currency": "USDC",
        "usdc_contract": USDC_CONTRACT,
        "pay_to_wallet": ATLAS_WALLET,
        "steps": [
            {
                "step": 1,
                "action": "Discovery call",
                "description": (
                    "Send a GET request to any paid endpoint. "
                    "The server responds with HTTP 402 and a JSON body "
                    "containing the payment requirements."
                ),
                "example": f"GET {ATLAS_API_URL}/v1/api/industry",
            },
            {
                "step": 2,
                "action": "Parse payment challenge",
                "description": (
                    "Read the 'accepts' array from the 402 response body. "
                    "Each entry contains: scheme, network, asset (USDC contract), "
                    "amount (in micro-USDC), payTo (wallet address), and maxTimeoutSeconds."
                ),
                "fields": {
                    "scheme": "exact",
                    "network": "eip155:8453",
                    "asset": USDC_CONTRACT,
                    "amount": "e.g. 5000 (= $0.005)",
                    "payTo": ATLAS_WALLET,
                },
            },
            {
                "step": 3,
                "action": "Sign EIP-3009 transfer",
                "description": (
                    "Use the USDC contract's EIP-3009 transferWithAuthorization "
                    "function. Sign the authorization struct with your wallet's "
                    "private key. This is gasless for the payer."
                ),
                "note": "No gas needed - the server pays for the transaction.",
            },
            {
                "step": 4,
                "action": "Retry with payment",
                "description": (
                    "Send the original POST request with a PAYMENT-SIGNATURE "
                    "header containing the signed EIP-3009 authorization."
                ),
                "example": (
                    f"POST {ATLAS_API_URL}/v1/api/industry\n"
                    "Header: PAYMENT-SIGNATURE: <signed_transfer>\n"
                    "Body: {\"keyword\": \"GDP\", \"period\": \"latest\", \"limit\": 10}"
                ),
            },
            {
                "step": 5,
                "action": "Receive data",
                "description": (
                    "Server verifies the payment on-chain and returns HTTP 200 "
                    "with the requested data in JSON format."
                ),
            },
        ],
        "price_reference": {
            "$0.003": "3000 units (company API)",
            "$0.005": "5000 units (industry/policy API)",
            "$0.008": "8000 units (web fetch)",
            "$0.01": "10000 units (guides)",
            "$4.99": "4990000 units (briefings)",
        },
    }


# ============================================================
# China Data API Tools (x402 paid)
# ============================================================

@mcp.tool()
async def query_industry_statistics(
    keyword: str,
    period: str = "latest",
    limit: int = 12,
    payment_signature: str = None,
):
    """
    Query China National Bureau of Statistics data (GDP, CPI, PPI, etc.).

    This is a PAID endpoint. Price: $0.005 USDC per query.

    If no payment_signature is provided, returns the x402 payment challenge
    so you can complete the payment flow. If a valid payment_signature is
    provided, executes the query and returns statistical data.

    Args:
        keyword: Search keyword for statistical indicator (e.g. GDP, CPI, PPI)
        period: Time period filter - 'latest' or '2026Q1' (default: latest)
        limit: Max number of data points to return (default: 12)
        payment_signature: Signed EIP-3009 transfer for x402 payment (optional)

    Returns:
        If unpaid: x402 payment challenge with amount and wallet address
        If paid: JSON with indicator name, data points, values, and source
    """
    endpoint = "/v1/api/industry"

    if not payment_signature:
        challenge = await get_payment_challenge(endpoint)
        return {
            "status": "payment_required",
            "price_usd": 0.005,
            "price_usdc_units": "5000",
            "endpoint": f"POST {ATLAS_API_URL}{endpoint}",
            "required_input": {
                "keyword": keyword,
                "period": period,
                "limit": limit,
            },
            "payment_challenge": challenge,
            "next_step": (
                "Sign an EIP-3009 transfer for 5000 micro-USDC to "
                f"{ATLAS_WALLET} on Base, then retry with the "
                "payment_signature parameter."
            ),
        }

    # Execute paid query
    url = f"{ATLAS_API_URL}{endpoint}"
    headers = {
        "Content-Type": "application/json",
        "PAYMENT-SIGNATURE": payment_signature,
    }
    body = {"keyword": keyword, "period": period, "limit": limit}

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, json=body, headers=headers)

    if resp.status_code == 402:
        return {
            "status": "payment_failed",
            "message": "Payment verification failed. Please check your signature.",
            "response": resp.text[:500],
        }

    return resp.json() if resp.status_code == 200 else {
        "status": "error",
        "code": resp.status_code,
        "message": resp.text[:500],
    }


@mcp.tool()
async def search_china_policies(
    keyword: str,
    date_from: str = None,
    limit: int = 10,
    payment_signature: str = None,
):
    """
    Search Chinese government policy documents by keyword.

    This is a PAID endpoint. Price: $0.005 USDC per query.

    If no payment_signature is provided, returns the x402 payment challenge.
    If a valid payment_signature is provided, executes the search and returns
    policy documents with title, issuing authority, date, and source URL.

    Args:
        keyword: Search keyword (e.g. 'AI', 'new energy', 'artificial intelligence')
        date_from: Start date filter YYYY-MM-DD (default: 90 days ago)
        limit: Max number of policy entries (default: 10)
        payment_signature: Signed EIP-3009 transfer for x402 payment (optional)

    Returns:
        If unpaid: x402 payment challenge
        If paid: JSON with policy list, dates, sources, and summaries
    """
    endpoint = "/v1/api/policy"

    if not payment_signature:
        challenge = await get_payment_challenge(endpoint)
        return {
            "status": "payment_required",
            "price_usd": 0.005,
            "price_usdc_units": "5000",
            "endpoint": f"POST {ATLAS_API_URL}{endpoint}",
            "required_input": {
                "keyword": keyword,
                "date_from": date_from,
                "limit": limit,
            },
            "payment_challenge": challenge,
            "next_step": (
                "Sign an EIP-3009 transfer for 5000 micro-USDC to "
                f"{ATLAS_WALLET} on Base, then retry with the "
                "payment_signature parameter."
            ),
        }

    url = f"{ATLAS_API_URL}{endpoint}"
    headers = {
        "Content-Type": "application/json",
        "PAYMENT-SIGNATURE": payment_signature,
    }
    body = {"keyword": keyword, "date_from": date_from, "limit": limit}

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, json=body, headers=headers)

    if resp.status_code == 402:
        return {
            "status": "payment_failed",
            "message": "Payment verification failed.",
            "response": resp.text[:500],
        }

    return resp.json() if resp.status_code == 200 else {
        "status": "error",
        "code": resp.status_code,
        "message": resp.text[:500],
    }


@mcp.tool()
async def query_company_credit(
    name: str,
    credit_code: str = None,
    payment_signature: str = None,
):
    """
    Query Chinese enterprise credit information from the official system.

    This is a PAID endpoint. Price: $0.003 USDC per query.

    If no payment_signature is provided, returns the x402 payment challenge.
    If a valid payment_signature is provided, returns company registration
    details and official search links from gsxt.gov.cn.

    Note: gsxt.gov.cn uses CAPTCHA verification. This API provides structured
    guidance and direct links to the official system rather than scraping.

    Args:
        name: Company name (Chinese or partial match, e.g. 'Alibaba')
        credit_code: 18-digit Unified Social Credit Code (optional, more precise)
        payment_signature: Signed EIP-3009 transfer for x402 payment (optional)

    Returns:
        If unpaid: x402 payment challenge
        If paid: JSON with company info, official search URL, and compliance notes
    """
    endpoint = "/v1/api/company"

    if not payment_signature:
        challenge = await get_payment_challenge(endpoint)
        return {
            "status": "payment_required",
            "price_usd": 0.003,
            "price_usdc_units": "3000",
            "endpoint": f"POST {ATLAS_API_URL}{endpoint}",
            "required_input": {
                "name": name,
                "credit_code": credit_code,
            },
            "payment_challenge": challenge,
            "next_step": (
                "Sign an EIP-3009 transfer for 3000 micro-USDC to "
                f"{ATLAS_WALLET} on Base, then retry with the "
                "payment_signature parameter."
            ),
        }

    url = f"{ATLAS_API_URL}{endpoint}"
    headers = {
        "Content-Type": "application/json",
        "PAYMENT-SIGNATURE": payment_signature,
    }
    body = {"name": name, "credit_code": credit_code}

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, json=body, headers=headers)

    if resp.status_code == 402:
        return {
            "status": "payment_failed",
            "message": "Payment verification failed.",
            "response": resp.text[:500],
        }

    return resp.json() if resp.status_code == 200 else {
        "status": "error",
        "code": resp.status_code,
        "message": resp.text[:500],
    }


# ============================================================
# Legacy compatibility tools
# ============================================================

@mcp.tool()
async def purchase_capability(name: str):
    """
    Initiate capability purchase flow.

    Returns x402 payment information for the specified capability.
    For China Data APIs, use the specific tools instead:
    - query_industry_statistics
    - search_china_policies
    - query_company_credit

    Args:
        name: Capability name or endpoint keyword
    """
    endpoint_map = {
        "industry": "/v1/api/industry",
        "policy": "/v1/api/policy",
        "company": "/v1/api/company",
        "fetch": "/v1/fetch/dynamic",
        "dynamic": "/v1/fetch/dynamic",
    }

    endpoint = endpoint_map.get(name.lower())
    if not endpoint:
        # Try to find in openapi
        try:
            openapi = await fetch_openapi()
            for path in openapi.get("paths", {}):
                if name.lower() in path.lower():
                    endpoint = path
                    break
        except Exception:
            pass

    if not endpoint:
        return {
            "status": "not_found",
            "message": f"Capability '{name}' not found. Use discover_capabilities to list available endpoints.",
        }

    challenge = await get_payment_challenge(endpoint)
    return {
        "status": "payment_required",
        "capability": name,
        "endpoint": endpoint,
        "protocol": "x402 v2",
        "network": ATLAS_NETWORK,
        "currency": "USDC",
        "payment_challenge": challenge,
    }


if __name__ == "__main__":
    mcp.run()
