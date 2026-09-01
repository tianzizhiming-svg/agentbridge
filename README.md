[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

# AgentBridge Matrix

> **DO · KNOW · NOW**
>
> Machine commerce infrastructure for AI agents. Three layers, one manifest, pay-per-use via x402.

---

## What is AgentBridge Matrix?

AgentBridge Matrix is a three-layer architecture that gives AI agents machine-native access to capabilities, knowledge, and real-time world state — all with x402 micropayments on Base.

```
          AgentBridge Matrix
                 |
    +------------+------------+
    |            |            |
  AZONE        ATLAS        AINIU
   (DO)        (KNOW)       (NOW)
    |            |            |
 Capabilities Knowledge  World State
```

An agent that discovers any one layer can immediately discover the others through the Matrix manifest.

---

## The Three Layers

| | Layer | Project | Role |
|---|---|---|---|
| **DO** | Capability | [AZONE](azone/) | Discover and access capabilities |
| **KNOW** | Knowledge | [ATLAS](atlas/) | Discover and access knowledge |
| **NOW** | Reality | [AINIU](ainiu/) | Discover current world state |

### AZONE — Capability Layer (DO)

An open discovery network where AI agents can register, describe their capabilities, and discover one another.

- Agent Registration & Discovery
- Capability Declaration
- Health Probing
- Machine-readable protocol

→ [AZONE README](azone/)

### ATLAS — Knowledge Layer (KNOW)

Machine-readable knowledge about China through standardized APIs and x402 micropayments.

- Web Fetch (static & dynamic)
- Industry Statistics, Policy Search, Company Credit
- University Reports, Teaching Quality, Strategic Notes

→ [ATLAS README](atlas/)

### AINIU — Reality Layer (NOW)

Real-time world state data for AI agents. Crypto, time, earthquakes, weather.

- Cryptocurrency prices
- World time
- Earthquake data
- Weather conditions

→ [AINIU README](ainiu/)

---

## Six-Surface Discovery

Every layer of the Matrix is discoverable through six surfaces. Any one of them leads to the full Matrix:

1. **OpenAPI** — `info.title` contains layer identity
2. **MCP** — Server/tool metadata contains Matrix identity
3. **HTTP Headers** — `X-Matrix-Layer` + `X-Matrix-Manifest` on every response
4. **Error Responses** — `_discover` field in 404/405/500 JSON bodies
5. **well-known** — Standardized endpoints with `layer` + `matrix` fields
6. **README** — You are here

---

## Quick Start

```bash
# 1. Discover the Matrix (free)
curl https://api.060504.shop/.well-known/agentbridge.json

# 2. Explore a layer
curl https://api.060504.shop/openapi.json

# 3. Trigger 402 payment challenge on any paid endpoint
curl -X POST https://api.060504.shop/ainiu/crypto \
  -H "Content-Type: application/json" \
  -d '{"symbol":"BTC"}'

# 4. Pay and retry (see x402 spec)
```

---

## Architecture

```
                    AI Agents
                        │
                        │ HTTPS + x402
                        ▼
              ┌───────────────────┐
              │  api.060504.shop  │
              │   (Cloudflare)    │
              └─────────┬─────────┘
                        │
           ┌────────────┼────────────┐
           │            │            │
     ┌─────┴─────┐ ┌────┴────┐ ┌────┴────┐
     │   AZONE   │ │  ATLAS  │ │  AINIU  │
     │  (DO)     │ │ (KNOW)  │ │  (NOW)  │
     │  :8002    │ │  :8000  │ │  :8001  │
     └───────────┘ └─────────┘ └─────────┘
         │             │            │
     PostgreSQL    FastAPI      FastAPI
     Redis         x402         x402
```

---

## Design Principles

**Machine-first** — designed primarily for machine discovery and consumption.

**No unnecessary accounts** — pay per use, no API keys, no subscriptions.

**Open discovery** — every layer is discoverable through standardized machine-readable metadata.

**Composable** — each layer is independent, but together they form the Matrix.

**Parasitic by design** — deeply integrated with the x402 ecosystem, growing from point to line to surface.

---


---

## Status

- Live API: `https://api.060504.shop`
- Listed on [402 Index](https://402index.io/directory?search=AgentBridge)
- Discoverable via `/.well-known/agent.json` (ReqCast-compatible)
- On-chain payment history is fully public and verifiable: [view on BaseScan](https://basescan.org/address/0x1630c8E0833c367F39f0ca909b6b67f5159d7A00)

## Ecosystem

- **x402 Protocol** — HTTP 402 payment standard
- **Base Mainnet** — USDC settlement layer
- **Cloudflare Tunnel** — production gateway
- **MCP** — Model Context Protocol integration
- **Smithery** — MCP server directory
- **x402scan** — x402 service directory

---

## Links

- **API**: https://api.060504.shop
- **Matrix Manifest**: https://api.060504.shop/.well-known/agentbridge.json
- **OpenAPI**: https://api.060504.shop/openapi.json
- **Storefront**: https://tianzizhiming-svg.github.io/agentbridge/
- **Legal Disclaimer**: [DISCLAIMER.md](DISCLAIMER.md)
- **GitHub**: https://github.com/tianzizhiming-svg/agentbridge

---


---

## Writing / Background

- [AgentBridge: Building a Pay-Per-Fetch Gateway for AI Agents on Base](https://medium.com/@leizhenbing/agentbridge-building-a-pay-per-fetch-gateway-for-ai-agents-on-base)
- [How AI Agents Can Legally Access Chinese Public Data](https://medium.com/p/6e956b24e4c1)
- [AgentBridge: The Missing Data Layer for AI Agents Targeting China](https://medium.com/@leizhenbing/agentbridge-the-missing-data-layer-for-ai-agents-targeting-china-8ba58f8ef795)
- [How We Built a Pay-Per-Report Data Service for 72 Chinese Universities Using x402](https://medium.com/p/6e9a6cfd5c65)
- [More on Medium](https://medium.com/@leizhenbing)

*AgentBridge Matrix — DO · KNOW · NOW.*
