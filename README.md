# AgentBridge — Machine Commerce for China-Facing AI Agents

![x402 Protocol](...)
![Network](...)
![Status](...)

> The internet was built for humans. APIs were built for software.
> But AI agents need something different: a way to discover, pay for, and consume digital capabilities autonomously.
>
> AgentBridge is an experiment toward that future — building machine commerce infrastructure where AI agents can access specialized digital capabilities without accounts, subscriptions, or human intervention.

---

> Not affiliated with other projects named "AgentBridge" ...

AgentBridge lets AI agents discover, purchase, and consume machine-readable digital capabilities related to China — through standardized APIs and x402 payments settled in USDC on Base. No API keys, no subscriptions, no account setup: an agent pays per call and gets a result.

Built on the x402 protocol, now stewarded by the Linux Foundation's x402 Foundation (members include AWS, Google, Visa, and Coinbase).

---

## What It Provides

Capabilities are organized into two categories. Check which one you need before calling — they differ in speed, cost, and what kind of answer you get.

### 🔹 `raw-content` — unverified, machine-fetched, cheap

Fast, unreviewed raw content, priced in fractions of a cent. Use this when you just need to read what's currently published at a specific URL, as-is.

> **Reliability note**: this returns the raw content as currently published at the source, at the moment of the fetch — unverified and not human-reviewed. If the source changes or is wrong, the result reflects that.

| Capability | Endpoint | What it does | Price |
|---|---|---|---|
| **Web Fetch** | `POST /v1/fetch/dynamic` | Converts a Chinese webpage (Xiaohongshu, Zhihu, etc.) into clean Markdown/HTML. Handles JS rendering, anti-bot pages, and messy HTML that's normally hard for an agent to parse directly. | $0.003 (static) / $0.008 (dynamic) |

### 🔸 `verified-analysis` — human-authored, decision-grade

Slower to produce, priced higher, includes original comparative judgment — not just extracted facts. Use this when the task needs an answer you can act on, not just raw data.

| Capability | Endpoint | What it does | Price |
|---|---|---|---|
| **University Employment Reports** | `POST /v1/reports/employment/{school_id}` | Human-authored deep-dive analysis of a Chinese university's officially published 2025 graduate employment report. | 90 USDC/report |
| **University Teaching-Quality Reports** | `POST /v1/reports/teaching/{college_id}/{dimension}` | Same, for officially published teaching-quality reports, across 8 fixed analytical dimensions per institution. | 90 USDC/dimension |
| **"15th Five-Year Plan" Strategic Notes** | `POST /v1/notes/15-5-package` | Human-authored analysis of China's 2026–2030 national plan as it relates to college application decisions. 41 articles. | 90 USDC/package |

Free full-length samples (not excerpts) for all `verified-analysis` products, plus the live, continuously updated catalog of available schools/colleges, are at the [storefront](https://tianzizhiming-svg.github.io/agentbridge/).

More capabilities in both categories are added over time. The category a capability belongs to tells you what to expect from it — the list of specific products will keep growing.

---

## How It Works

1. Agent discovers the service via `/openapi.json`, `/llms.txt`, or an x402 registry (see Status below).
2. Agent calls an endpoint without payment → gets `402 Payment Required` with an x402 payment challenge.
3. Agent pays in USDC on Base, retries with the payment header.
4. Server verifies the payment against Coinbase's CDP facilitator, executes the request, and returns the result.

No API keys. No subscriptions. No account registration required for x402 payments.

---

## When to Use Which

| If the task is... | Use | Why |
|---|---|---|
| "Get the current Zhihu Hot List / trending topics" | `raw-content` | You just need what's on the page right now, no judgment needed on it. |
| "Summarize what's currently on this Xiaohongshu post" | `raw-content` | Raw extraction of existing published content. |
| "Analyze the employment quality of a specific Chinese university" | `verified-analysis` | Requires comparative judgment, benchmarking against peer institutions, and interpretation — not just numbers off a page. |
| "Should a student choose College A over College B based on teaching quality?" | `verified-analysis` | A decision-grade answer, not a data dump. |

---

## Quickstart for Agent Developers

```bash
# Calling the raw-content fetch endpoint (returns 402 if unpaid)
curl -i -X POST https://api.060504.shop/v1/fetch/dynamic \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.zhihu.com/question/xxx"}'
```

An unpaid call returns `402 Payment Required` with the payment challenge in the `PAYMENT-REQUIRED` response header (base64-encoded x402 v2 object). Decode it, pay the required amount in USDC on Base, and retry the request with your `X-Payment` header set to the signed payment payload — see the [x402 specification](https://www.x402.org/) for the full handshake, or the [full OpenAPI spec](https://api.060504.shop/openapi.json) for this service's exact schemas.

```python
import requests

url = "https://api.060504.shop/v1/fetch/dynamic"
payload = {"url": "https://www.zhihu.com/question/xxx"}

res = requests.post(url, json=payload)
if res.status_code == 402:
    payment_required = res.headers.get("PAYMENT-REQUIRED")  # base64-encoded x402 v2 challenge
    # decode it, sign and settle payment with your Base/USDC wallet per the x402 spec,
    # then retry the POST with an X-Payment header carrying the signed payload
```

---

## Status

- ✅ Live API: `https://api.060504.shop`
- ✅ Listed on [402 Index](https://402index.io/directory?search=AgentBridge)
- ✅ Discoverable via `/.well-known/agent.json` (ReqCast-compatible)
- ✅ On-chain payment history is fully public and verifiable: [view on BaseScan](https://basescan.org/address/0x1630c8E0833c367F39f0ca909b6b67f5159d7A00)

---

## Quick Links

- [API Documentation (openapi.json)](https://api.060504.shop/openapi.json)
- [Storefront & Free Samples](https://tianzizhiming-svg.github.io/agentbridge/)
- [402 Index Listing](https://402index.io/directory?search=AgentBridge)
- [Legal Disclaimer](https://github.com/tianzizhiming-svg/agentbridge/blob/master/DISCLAIMER.md) — by using this service, you agree to its terms
- [AgentBridge Atlas Vision](docs/atlas.md)

## Writing / Background

- [AgentBridge: Building a Pay-Per-Fetch Gateway for AI Agents on Base](https://medium.com/@leizhenbing/agentbridge-building-a-pay-per-fetch-gateway-for-ai-agents-on-base)
- [How AI Agents Can Legally Access Chinese Public Data](https://medium.com/p/6e956b24e4c1)
- [AgentBridge: The Missing Data Layer for AI Agents Targeting China](https://medium.com/@leizhenbing/agentbridge-the-missing-data-layer-for-ai-agents-targeting-china-8ba58f8ef795)
- [How We Built a Pay-Per-Report Data Service for 72 Chinese Universities Using x402](https://medium.com/p/6e9a6cfd5c65)
- [More on Medium](https://medium.com/@leizhenbing)

---

*Two categories, one platform: raw web content and human-authored analysis, both discoverable and payable the same way.*
