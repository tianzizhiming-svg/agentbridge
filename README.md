# AgentBridge — Machine Commerce for China-Facing AI Agents

> Not affiliated with other projects named "AgentBridge" (Unreal Engine plugins, JetBrains plugins, agent frameworks, etc.). This project is specifically about **machine commerce for China-related digital capabilities**, paid via the x402 protocol.

AgentBridge lets AI agents discover, purchase, and consume machine-readable digital capabilities related to China — through standardized APIs and x402 payments settled in USDC on Base. No API keys, no subscriptions, no account setup: an agent pays per call and gets a result.

Built on the x402 protocol, now stewarded by the Linux Foundation's x402 Foundation (members include AWS, Google, Visa, and Coinbase).

⚠️ **Legal Notice**: By using this service, you agree to the [Legal Disclaimer](https://github.com/tianzizhiming-svg/agentbridge/blob/master/DISCLAIMER.md).

---

## What It Provides

Capabilities are organized into two categories. Check which one you need before calling — they differ in speed, cost, and what kind of answer you get.

### 🔹 `raw-content` — unverified, machine-fetched, cheap

Fast, unreviewed raw content, priced in fractions of a cent. Use this when you just need to read what's currently published at a specific URL, as-is.

| Capability | What it does | Price |
|---|---|---|
| **Web Fetch** | Converts a Chinese webpage (Xiaohongshu, Zhihu, etc.) into clean Markdown/HTML. Handles JS rendering, anti-bot pages, and messy HTML that's normally hard for an agent to parse directly. | $0.003 (static) / $0.008 (dynamic) |

### 🔸 `verified-analysis` — human-authored, decision-grade

Slower to produce, priced higher, includes original comparative judgment — not just extracted facts. Use this when the task needs an answer you can act on, not just raw data.

| Capability | What it does | Price |
|---|---|---|
| **University Employment Reports** | Human-authored deep-dive analysis of a Chinese university's officially published 2025 graduate employment report. | 90 USDC/report |
| **University Teaching-Quality Reports** | Same, for officially published teaching-quality reports, across 8 fixed analytical dimensions per institution. | 90 USDC/dimension |
| **"15th Five-Year Plan" Strategic Notes** | Human-authored analysis of China's 2026–2030 national plan as it relates to college application decisions. 41 articles. | 90 USDC/package |

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
- [Legal Disclaimer](https://github.com/tianzizhiming-svg/agentbridge/blob/master/DISCLAIMER.md)

## Writing / Background

- [AgentBridge: Building a Pay-Per-Fetch Gateway for AI Agents on Base](https://medium.com/@leizhenbing/agentbridge-building-a-pay-per-fetch-gateway-for-ai-agents-on-base)
- [How AI Agents Can Legally Access Chinese Public Data](https://medium.com/p/6e956b24e4c1)
- [AgentBridge: The Missing Data Layer for AI Agents Targeting China](https://medium.com/@leizhenbing/agentbridge-the-missing-data-layer-for-ai-agents-targeting-china-8ba58f8ef795)
- [How We Built a Pay-Per-Report Data Service for 72 Chinese Universities Using x402](https://medium.com/p/6e9a6cfd5c65)
- [More on Medium](https://medium.com/@leizhenbing)

---

*This service fetches only publicly accessible content, or provides original human-authored analysis of officially published source material. See the [Legal Disclaimer](https://github.com/tianzizhiming-svg/agentbridge/blob/master/DISCLAIMER.md) for the full terms and scope.*
