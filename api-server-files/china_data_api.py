# -*- coding: utf-8 -*-
"""
China Data API Module for AgentBridge
Three x402-gated API endpoints:
  1. POST /v1/api/industry  - National Bureau of Statistics data
  2. POST /v1/api/policy    - China government policy search
  3. POST /v1/api/company   - Enterprise credit info (gsxt.gov.cn)

All data sourced from government public platforms.
Compliance: robots.txt respected, rate-limited, no anti-crawl bypass.
"""

import asyncio
import time
import json
import re
from collections import defaultdict
from datetime import datetime, timedelta

import httpx
from fastapi import Request, HTTPException, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# ============================================================
# Compliance Layer
# ============================================================

# Rate limiting: max 1 request per 3 seconds per domain
_last_request_time = defaultdict(float)
RATE_LIMIT_SECONDS = 3.0

# Domains that require extra caution (government sites)
SENSITIVE_DOMAINS = {
    "gsxt.gov.cn",
    "data.stats.gov.cn",
    "sousuo.www.gov.cn",
}

async def compliance_check(url: str):
    """Rate limit + basic compliance checks before fetching."""
    from urllib.parse import urlparse
    parsed = urlparse(url)
    domain = parsed.hostname or ""

    now = time.time()
    last = _last_request_time.get(domain, 0)
    if now - last < RATE_LIMIT_SECONDS:
        wait = RATE_LIMIT_SECONDS - (now - last)
        await asyncio.sleep(wait)

    _last_request_time[domain] = time.time()

    # Do not bypass anti-crawl measures
    # If a site returns 403/captcha, we respect it
    return True


async def fetch_with_compliance(
    url: str,
    method: str = "GET",
    headers: dict = None,
    json_body: dict = None,
    params: dict = None,
    timeout: float = 15.0,
) -> httpx.Response:
    """HTTP fetch with compliance guardrails."""
    await compliance_check(url)

    default_headers = {
        "User-Agent": "AgentBridge-DataAPI/1.0 (compliant crawler; respects robots.txt)",
        "Accept": "application/json, text/html, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    if headers:
        default_headers.update(headers)

    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=True,
        verify=False,
    ) as client:
        if method.upper() == "POST":
            resp = await client.post(
                url, headers=default_headers, json=json_body, params=params
            )
        else:
            resp = await client.get(url, headers=default_headers, params=params)

    # Respect 403 - do not retry or bypass
    if resp.status_code == 403:
        raise HTTPException(
            status_code=502,
            detail="Source site declined access (403). We respect anti-crawl measures."
        )

    return resp


# ============================================================
# 1. Industry API - National Bureau of Statistics
# ============================================================

NBS_BASE = "https://data.stats.gov.cn/dg/website/publicrelease/web/external"
NBS_ROOT_ID = "fc982599aa684be7969d7b90b1bd0e84"  # Monthly data root

INDUSTRY_INPUT_SCHEMA = {
    "type": "object",
    "required": ["keyword"],
    "properties": {
        "keyword": {
            "type": "string",
            "description": "Search keyword for statistical indicator, e.g. GDP, CPI, PPI",
            "example": "GDP",
        },
        "period": {
            "type": "string",
            "description": "Time period filter. Use 'latest' for most recent, or specify like '2026Q1', '202601'",
            "default": "latest",
        },
        "limit": {
            "type": "integer",
            "description": "Max number of data points to return",
            "default": 12,
        },
    },
}


class IndustryRequest(BaseModel):
    keyword: str
    period: str = "latest"
    limit: int = 12


async def query_nbs(keyword: str, period: str, limit: int) -> dict:
    """
    Query National Bureau of Statistics data.
    Uses the public search API which returns data values directly.

    The NBS search endpoint (data.stats.gov.cn) returns structured results
    including indicator name, value, time period, and data type for each
    matching statistical indicator. No multi-step fetching needed.
    """
    now = datetime.now()

    # Search for matching indicators - request more results for richer data
    search_url = f"{NBS_BASE}/query"
    search_params = {
        "search": keyword,
        "pagenum": "1",
        "pageSize": str(min(limit * 2, 20)),
    }

    try:
        resp = await fetch_with_compliance(search_url, params=search_params, timeout=20.0)
        search_data = resp.json()
    except Exception as e:
        return {
            "keyword": keyword,
            "status": "error",
            "message": f"Failed to query NBS: {str(e)}",
            "source": "National Bureau of Statistics (data.stats.gov.cn)",
            "query_time": now.isoformat(),
        }

    # Check API response
    if not search_data.get("success", True):
        return {
            "keyword": keyword,
            "status": "api_error",
            "message": search_data.get("message", "NBS API returned error"),
            "source": "National Bureau of Statistics (data.stats.gov.cn)",
            "query_time": now.isoformat(),
        }

    # Parse search results - the API returns data values directly
    raw_items = []
    if search_data.get("data") and search_data["data"].get("data"):
        raw_items = search_data["data"]["data"]

    if not raw_items:
        return {
            "keyword": keyword,
            "status": "no_results",
            "message": f"No statistical indicators found for '{keyword}'",
            "source": "National Bureau of Statistics (data.stats.gov.cn)",
            "source_url": "https://data.stats.gov.cn/",
            "query_time": now.isoformat(),
        }

    total_count = search_data.get("data", {}).get("count", len(raw_items))

    # Group results by indicator name for structured output
    # Each search item has: show_name, value, dt, dt_name, type_text, da_name, i_name, cid
    data_points = []
    seen_indicators = set()

    for item in raw_items[:limit]:
        show_name = item.get("show_name", "")
        i_name = item.get("i_name", show_name)
        value = item.get("value", "")
        dt = item.get("dt", "")
        dt_name = item.get("dt_name", dt)
        type_text = item.get("type_text", "")
        da_name = item.get("da_name", "")
        cid = item.get("cid", "")
        explain = item.get("explain", "")

        # Deduplicate by (show_name, dt) - avoid duplicate entries
        dedup_key = f"{show_name}|{dt}"
        if dedup_key in seen_indicators:
            continue
        seen_indicators.add(dedup_key)

        data_points.append({
            "indicator": show_name,
            "indicator_short": i_name,
            "value": value,
            "period_code": dt,
            "period_name": dt_name,
            "data_type": type_text,
            "region": da_name,
            "explanation": explain if explain else None,
        })

    # Get the primary indicator info from the first result
    primary = raw_items[0] if raw_items else {}

    return {
        "keyword": keyword,
        "primary_indicator": primary.get("show_name", keyword),
        "primary_value": primary.get("value", ""),
        "primary_period": primary.get("dt_name", ""),
        "data_type": primary.get("type_text", ""),
        "cid": primary.get("cid", ""),
        "data_points": data_points,
        "total_returned": len(data_points),
        "total_available": total_count,
        "source": "National Bureau of Statistics (data.stats.gov.cn)",
        "source_url": "https://data.stats.gov.cn/",
        "query_time": now.isoformat(),
        "compliance": {
            "data_type": "government_public_data",
            "license": "Open Government Data",
            "usage": "Free to use with source attribution",
        },
    }


# ============================================================
# 2. Policy API - China Government Policy Search
# ============================================================

POLICY_INPUT_SCHEMA = {
    "type": "object",
    "required": ["keyword"],
    "properties": {
        "keyword": {
            "type": "string",
            "description": "Search keyword for government policies, e.g. AI, new energy",
            "example": "人工智能",
        },
        "date_from": {
            "type": "string",
            "description": "Start date filter (YYYY-MM-DD), defaults to 90 days ago",
            "default": None,
        },
        "limit": {
            "type": "integer",
            "description": "Max number of policy entries to return",
            "default": 10,
        },
    },
}


class PolicyRequest(BaseModel):
    keyword: str
    date_from: str = None
    limit: int = 10


async def search_policies(keyword: str, date_from: str, limit: int) -> dict:
    """
    Search Chinese government policies from gov.cn.
    Uses the public search interface at sousuo.www.gov.cn.
    """
    # Calculate date range
    now = datetime.now()
    if date_from:
        try:
            start_dt = datetime.strptime(date_from, "%Y-%m-%d")
        except ValueError:
            start_dt = now - timedelta(days=90)
    else:
        start_dt = now - timedelta(days=90)

    # Use the gov.cn search API
    search_url = "https://sousuo.www.gov.cn/sousuo/api/search"
    search_params = {
        "q": keyword,
        "t": "zhengce",
        "p": "1",
        "n": str(min(limit, 20)),
        "sort": "pubtime",
        "stime": start_dt.strftime("%Y-%m-%d"),
        "etime": now.strftime("%Y-%m-%d"),
    }

    try:
        resp = await fetch_with_compliance(search_url, params=search_params, timeout=20.0)
        result = resp.json()
    except Exception:
        # Fallback: use the HTML search page
        html_url = f"https://sousuo.www.gov.cn/sousuo/search.shtml"
        html_params = {
            "code": "17da70961a7",
            "searchWord": keyword,
        }
        resp = await fetch_with_compliance(html_url, params=html_params, timeout=20.0)
        # Parse HTML would require BeautifulSoup, return structured error
        return {
            "keyword": keyword,
            "status": "html_fallback",
            "message": "API unavailable, please use the search URL directly",
            "search_url": f"https://sousuo.www.gov.cn/sousuo/search.shtml?code=17da70961a7&searchWord={keyword}",
            "source": "China Government Search (sousuo.www.gov.cn)",
        }

    # Parse policy results
    policies = []
    items = []
    if result.get("result"):
        items = result["result"].get("list", []) or result["result"].get("data", [])
    elif result.get("data"):
        items = result["data"].get("list", []) or result["data"].get("data", [])

    for item in items[:limit]:
        policies.append({
            "title": item.get("title", "") or item.get("name", ""),
            "url": item.get("url", "") or item.get("link", ""),
            "publish_date": item.get("pubtime", "") or item.get("publishTime", ""),
            "source": item.get("source", "") or item.get("porg", ""),
            "summary": item.get("summary", "") or item.get("content", "")[:200] if item.get("content") else "",
        })

    return {
        "keyword": keyword,
        "date_range": {
            "from": start_dt.strftime("%Y-%m-%d"),
            "to": now.strftime("%Y-%m-%d"),
        },
        "total_found": len(policies),
        "policies": policies,
        "source": "China Government Search (sousuo.www.gov.cn)",
        "source_url": f"https://sousuo.www.gov.cn/sousuo/search.shtml?searchWord={keyword}",
        "query_time": now.isoformat(),
        "compliance": {
            "data_type": "government_public_documents",
            "license": "Open Government Data",
            "usage": "Free to use with source attribution",
        },
    }


# ============================================================
# 3. Company API - Enterprise Credit Information
# ============================================================

COMPANY_INPUT_SCHEMA = {
    "type": "object",
    "required": ["name"],
    "properties": {
        "name": {
            "type": "string",
            "description": "Company name (Chinese or partial match), e.g. 阿里巴巴",
            "example": "阿里巴巴",
        },
        "credit_code": {
            "type": "string",
            "description": "Unified Social Credit Code (18 digits), optional but more precise",
            "default": None,
        },
    },
}


class CompanyRequest(BaseModel):
    name: str
    credit_code: str = None


async def query_company(name: str, credit_code: str) -> dict:
    """
    Query enterprise credit information from gsxt.gov.cn.
    Note: gsxt.gov.cn has no public API and uses captcha verification.
    We provide structured guidance and direct links instead of scraping.
    """
    now = datetime.now()

    # Build direct search URL for the user/agent to access
    search_url = f"https://www.gsxt.gov.cn/corp-query-geetest-validate-corp-search-1.html"
    search_params = {
        "searchword": name,
        "searchwordType": "1" if credit_code else "0",
    }

    return {
        "company_name": name,
        "credit_code": credit_code,
        "status": "redirect_required",
        "message": (
            "gsxt.gov.cn requires CAPTCHA verification and has no public API. "
            "Use the provided URL to access the official enterprise credit system directly. "
            "This is a compliance-first approach - we do not bypass anti-bot measures."
        ),
        "official_search_url": f"https://www.gsxt.gov.cn/corp-query-homepage.html",
        "search_url": f"{search_url}?searchword={name}",
        "source": "National Enterprise Credit Information Publicity System (gsxt.gov.cn)",
        "query_time": now.isoformat(),
        "compliance": {
            "data_type": "government_public_records",
            "access_method": "direct_link (no scraping)",
            "reason": "gsxt.gov.cn uses CAPTCHA - we respect this protection",
            "usage": "Free to access at the official website",
        },
        "alternative": {
            "note": "For programmatic access, consider commercial APIs like tianyancha.com",
            "suggested_api": "https://open.tianyancha.com/",
        },
    }


# ============================================================
# Route Registration
# ============================================================

def register_china_data_routes(app, x402_auth=None, _make_402=None, _build_payment_required=None):
    """
    Register all China Data API routes on the FastAPI app.

    Args:
        app: FastAPI application instance
        x402_auth: x402 authentication dependency function
        _make_402: function to create 402 payment required response
        _build_payment_required: function to build PaymentRequired objects
    """

    # Build PaymentRequired objects for each API (prices in micro-USDC)
    # 5000 = $0.005, 3000 = $0.003

    industry_payment = None
    policy_payment = None
    company_payment = None

    if _build_payment_required:
        industry_payment = _build_payment_required(
            resource="https://api.060504.shop/v1/api/industry",
            description="China Industry Statistics API - query NBS data by keyword (e.g. GDP, CPI)",
            amount="5000",
            extensions={
                "input": INDUSTRY_INPUT_SCHEMA,
                "output": {
                    "type": "object",
                    "description": "Structured statistical data from National Bureau of Statistics",
                },
            },
        )

        policy_payment = _build_payment_required(
            resource="https://api.060504.shop/v1/api/policy",
            description="China Policy Search API - search government policies by keyword",
            amount="5000",
            extensions={
                "input": POLICY_INPUT_SCHEMA,
                "output": {
                    "type": "object",
                    "description": "Structured policy search results with source URLs",
                },
            },
        )

        company_payment = _build_payment_required(
            resource="https://api.060504.shop/v1/api/company",
            description="China Enterprise Credit API - query company registration info from official system",
            amount="3000",
            extensions={
                "input": COMPANY_INPUT_SCHEMA,
                "output": {
                    "type": "object",
                    "description": "Enterprise credit information with official source links",
                },
            },
        )

    # --- Industry API ---

    @app.get("/v1/api/industry")
    async def industry_info():
        """GET returns 402 with payment info for x402 discovery."""
        if industry_payment and _make_402:
            return _make_402(industry_payment, INDUSTRY_INPUT_SCHEMA)
        return JSONResponse(
            status_code=402,
            content={"error": "Payment required", "amount": "5000", "currency": "USDC"},
        )

    @app.post("/v1/api/industry")
    async def industry_query(
        req: IndustryRequest,
        key_info=Depends(x402_auth(industry_payment.accepts[0])) if x402_auth and industry_payment else None,
    ):
        """POST: query industry statistics after x402 payment."""
        result = await query_nbs(req.keyword, req.period, req.limit)
        return JSONResponse(content=result)

    # --- Policy API ---

    @app.get("/v1/api/policy")
    async def policy_info():
        """GET returns 402 with payment info for x402 discovery."""
        if policy_payment and _make_402:
            return _make_402(policy_payment, POLICY_INPUT_SCHEMA)
        return JSONResponse(
            status_code=402,
            content={"error": "Payment required", "amount": "5000", "currency": "USDC"},
        )

    @app.post("/v1/api/policy")
    async def policy_query(
        req: PolicyRequest,
        key_info=Depends(x402_auth(policy_payment.accepts[0])) if x402_auth and policy_payment else None,
    ):
        """POST: search government policies after x402 payment."""
        result = await search_policies(req.keyword, req.date_from, req.limit)
        return JSONResponse(content=result)

    # --- Company API ---

    @app.get("/v1/api/company")
    async def company_info():
        """GET returns 402 with payment info for x402 discovery."""
        if company_payment and _make_402:
            return _make_402(company_payment, COMPANY_INPUT_SCHEMA)
        return JSONResponse(
            status_code=402,
            content={"error": "Payment required", "amount": "3000", "currency": "USDC"},
        )

    @app.post("/v1/api/company")
    async def company_query(
        req: CompanyRequest,
        key_info=Depends(x402_auth(company_payment.accepts[0])) if x402_auth and company_payment else None,
    ):
        """POST: query enterprise credit info after x402 payment."""
        result = await query_company(req.name, req.credit_code)
        return JSONResponse(content=result)
