# AgentBridge

[![402 Index](https://img.shields.io/badge/402%20Index-AgentBridge-blue)](https://402index.io/directory?search=AgentBridge)

AI agents pay-per-fetch to access Chinese web content (Xiaohongshu, Zhihu, etc.) — returns clean markdown, settled in USDC on Base via x402.

---
> ⚠️ **Legal Notice**: By using this service, you agree to the [Legal Disclaimer](./DISCLAIMER.md).

## What It Does

AgentBridge helps AI agents access Chinese websites that are hard to parse due to:
- JavaScript rendering
- Anti-bot mechanisms
- Complex HTML structure

It converts messy web pages into clean, token-efficient Markdown — no API keys, no subscriptions.

---

## Features

- **x402 Protocol**: Pay-per-fetch, settled in USDC on Base
- **JavaScript Rendering**: Uses Playwright for dynamic content
- **Clean Output**: HTML → Markdown distillation
- **Agent Discovery**: `/.well-known/agent.json` endpoint for ReqCast

---

## Pricing

- **$0.003 per request** — paid in USDC on Base
- No subscriptions, no minimums, no API keys

---

## Status

- ✅ Live API: `https://api.060504.shop/v1/fetch/dynamic`
- ✅ Listed on [402 Index](https://402index.io/directory?search=AgentBridge)
- ✅ Verified with ReqCast
- ✅ 4 on-chain payments received (0.13625 USDC)

---

## Quick Links

- [402 Index Listing](https://402index.io/directory?search=AgentBridge)
- [API Endpoint](https://api.060504.shop/v1/fetch/dynamic)
- [Documentation](./docs/)
- [Examples](./examples/)

---

## Disclaimer

This service fetches **publicly accessible** web content only.  
Users are responsible for compliance with target websites' terms of service and applicable laws.
