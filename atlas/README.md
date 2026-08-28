# ATLAS — Knowledge Layer

> **AgentBridge Matrix · KNOW**
>
> Machine-readable knowledge for AI agents. China data marketplace with x402 micropayments.

---

## AgentBridge Matrix

ATLAS is the **Knowledge Layer** of [AgentBridge Matrix](../).

| | Layer | Project | Role |
|---|---|---|---|
| **DO** | Capability | [AZONE](../azone/) | Discover and access capabilities |
| **KNOW** | Knowledge | **ATLAS** | **Discover and access knowledge** |
| **NOW** | Reality | [AINIU](../ainiu/) | Discover current world state |

An agent that discovers ATLAS can immediately discover AZONE and AINIU through the Matrix manifest.

---

## What ATLAS Provides

ATLAS provides machine-readable knowledge about China through standardized APIs and x402 micropayments.

### Two Categories

| Category | What | Trust Level | Price Range |
|---|---|---|---|
| **raw-content** | Machine-fetched web content | Unverified, as-is | $0.003–$0.008 |
| **verified-analysis** | Human-authored analysis | Decision-grade | $0.003–$4.99 |

### Capabilities

| Capability | Endpoint | Category | Price |
|---|---|---|---|
| **Web Fetch (static)** | `POST /v1/fetch/static` | raw-content | $0.003 |
| **Web Fetch (dynamic)** | `POST /v1/fetch/dynamic` | raw-content | $0.008 |
| **Industry Statistics** | `POST /v1/api/industry` | raw-content | $0.005 |
| **Policy Search** | `POST /v1/api/policy` | raw-content | $0.005 |
| **Company Credit** | `POST /v1/api/company` | raw-content | $0.003 |
| **University Reports** | `POST /v1/reports/employment/{id}` | verified-analysis | $0.99 |
| **Teaching Quality** | `POST /v1/reports/teaching/{id}/{dim}` | verified-analysis | $0.99 |
| **Strategic Notes** | `POST /v1/notes/15-5-package` | verified-analysis | $0.99 |

---

## Six-Surface Discovery

ATLAS is discoverable through six surfaces. Any one of them leads to the full Matrix:

1. **OpenAPI** — `info.title` contains "Knowledge Layer of AgentBridge Matrix"
2. **MCP** — `serverInfo.name` contains Matrix identity
3. **HTTP Headers** — `X-Matrix-Layer: knowledge` + `X-Matrix-Manifest` on every response
4. **Error Responses** — `_discover` field in 404/405/500 JSON bodies
5. **well-known** — `/.well-known/mcp/server-card.json` contains `layer` + `matrix` fields
6. **README** — You are here

---

## Quick Start

```bash
# 1. Discover the API (free)
curl https://api.060504.shop/openapi.json

# 2. Trigger 402 payment challenge
curl -X POST https://api.060504.shop/v1/api/industry \
  -H "Content-Type: application/json" \
  -d '{"keyword":"GDP"}'

# 3. Pay and retry (see x402 spec)
```

---

## Data Sources & Compliance

| API | Source | Compliance |
|---|---|---|
| Industry | data.stats.gov.cn | Rate limited 3s/req |
| Policy | sousuo.www.gov.cn | Rate limited 3s/req |
| Company | gsxt.gov.cn | Official links only, no captcha bypass |

---

## Design Principles

**Machine-first** — designed primarily for machine discovery and consumption.

**No unnecessary accounts** — pay per use, no API keys, no subscriptions.

**Open discovery** — capabilities discoverable through standardized machine-readable metadata.

**Composable** — ATLAS is one layer of AgentBridge Matrix, not the entire system.

---

## AgentBridge Matrix

- **AZONE** (DO) — [Discover capabilities](../azone/)
- **ATLAS** (KNOW) — You are here
- **AINIU** (NOW) — [Discover current world state](../ainiu/)

Matrix Manifest: `https://api.060504.shop/.well-known/agentbridge.json`

---

## Links

- **API**: https://api.060504.shop
- **OpenAPI**: https://api.060504.shop/openapi.json
- **MCP Card**: https://api.060504.shop/.well-known/mcp/server-card.json
- **Storefront**: https://tianzizhiming-svg.github.io/agentbridge/
- **GitHub**: https://github.com/tianzizhiming-svg/agentbridge

---

*ATLAS — Knowledge Layer of AgentBridge Matrix. DO · KNOW · NOW.*