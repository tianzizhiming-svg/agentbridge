# AINIU — Reality Layer

> **AgentBridge Matrix · NOW**
>
> Real-time world state data for AI agents. Crypto, time, earthquakes, weather — pay per query via x402.

---

## AgentBridge Matrix

AINIU is the **Reality Layer** of [AgentBridge Matrix](../).

| | Layer | Project | Role |
|---|---|---|---|
| **DO** | Capability | [AZONE](../azone/) | Discover and access capabilities |
| **KNOW** | Knowledge | [ATLAS](../atlas/) | Discover and access knowledge |
| **NOW** | Reality | **AINIU** | **Discover current world state** |

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

An agent that discovers AINIU can immediately discover AZONE and ATLAS through the Matrix manifest.

---

## What AINIU Provides

AINIU provides real-time world state data through standardized APIs and x402 micropayments. No API keys, no subscriptions — pay per query in USDC on Base.

### Supported Domains

| Domain | Endpoint | What | Price |
|---|---|---|---|
| **Crypto** | `POST /ainiu/crypto` | Cryptocurrency prices and market data | $0.001/query |
| **Time** | `POST /ainiu/time` | Current time in any timezone | $0.001/query |
| **Earthquake** | `POST /ainiu/earthquake` | Recent earthquake data worldwide | $0.001/query |
| **Weather** | `POST /ainiu/weather` | Current weather conditions | $0.001/query |

### Response Format

Every AINIU response follows a consistent data model:

| Field | Description |
|---|---|
| `entity` | What is being observed (e.g., "BTC", "Tokyo") |
| `state` | Current state or value |
| `observed_at` | ISO 8601 timestamp |
| `source` | Data source identifier |
| `source_tier` | Source reliability tier |
| `freshness_seconds` | How recent the data is |
| `confidence` | Confidence score (0–1) |

---

## Six-Surface Discovery

AINIU is discoverable through six surfaces. Any one of them leads to the full Matrix:

1. **OpenAPI** — `info.title` contains "Reality Layer of AgentBridge Matrix"
2. **MCP** — AINIU tools include Matrix discovery metadata
3. **HTTP Headers** — `X-Matrix-Layer: reality` + `X-Matrix-Manifest` on every response
4. **Error Responses** — `_discover` field in 404/405/500 JSON bodies
5. **well-known** — `/.well-known/ainiu.json` contains `layer` + `matrix` fields with all three layers
6. **README** — You are here

---

## Quick Start

```bash
# 1. Discover AINIU (free)
curl https://api.060504.shop/.well-known/ainiu.json

# 2. Trigger 402 payment challenge
curl -X POST https://api.060504.shop/ainiu/crypto \
  -H "Content-Type: application/json" \
  -d '{"symbol":"BTC"}'

# 3. Pay and retry (see x402 spec)
# Returns 200 OK with real-time data after payment
```

### Python Example

```python
import requests

# Unpaid request → 402
res = requests.post("https://api.060504.shop/ainiu/crypto", json={"symbol": "BTC"})
if res.status_code == 402:
    # Decode x402 challenge from PAYMENT-REQUIRED header
    # Pay $0.001 USDC on Base
    # Retry with X-Payment header
    pass
```

---

## Data Policy

AINIU distinguishes between **publicly accessible data** and **data that can legally be commercially redistributed**. These are not the same.

AINIU prioritizes:
- Official public data
- Public-domain data
- Data with clear commercial-use permissions
- Properly licensed data

AINIU does not assume that a publicly accessible API automatically permits commercial redistribution.

---

## V0 Principle

> **Do not build a database for humans to browse. Build a state layer for agents to query.**

The objective is not to become another real-time information website. The objective is to become a machine-native interface to the current state of the world.

---

## AgentBridge Matrix

- **AZONE** (DO) — [Discover capabilities](../azone/)
- **ATLAS** (KNOW) — [Discover knowledge](../atlas/)
- **AINIU** (NOW) — You are here

Matrix Manifest: `https://api.060504.shop/.well-known/agentbridge.json`

---

## Links

- **API**: https://api.060504.shop
- **well-known**: https://api.060504.shop/.well-known/ainiu.json
- **Matrix Manifest**: https://api.060504.shop/.well-known/agentbridge.json
- **GitHub**: https://github.com/tianzizhiming-svg/agentbridge

---

*AINIU — Reality Layer of AgentBridge Matrix. DO · KNOW · NOW.*

Know the world. See the now. Act on it.