AgentBridge Atlas - x402 M2M Micro-Payment Market

[![AgenticMarket](https://agenticmarket.dev/api/badge/@manniusl/agentbridge-atlas)](https://agenticmarket.dev/manniusl/agentbridge-atlas)

The trusted data infrastructure connecting China's authoritative information with global AI Agents. Powered by Coinbase x402 protocol on Base.

🚀 Core Highlights
✅ Live on Base Mainnet: Real on-chain micro-transactions settled via USDC.
✅ x402 Pay-Per-Fetch: Agents autonomously pay $0.003 - $0.008 per request. No API keys, no logins.
✅ 11 Trusted Sources: Access to authoritative Chinese gov/official data (stats.gov.cn, visaforchina.cn, etc.).
✅ 105+ Data Assets: Machine-readable Markdown/JSON outputs with source provenance.
✅ MCP Server: Listed on AgenticMarket, supporting standard streamable-HTTP protocol.

🔄 Live M2M Loop

AI Agent → On-chain Signature & Payment (0.005 USDC) → Backend Verification & Settlement → National Bureau of Statistics GDP Data Delivered

The M2M (Machine-to-Machine) micropayment loop is live.

## Quick Facts

| Item | Value |
|------|-------|
| API Base | `https://api.060504.shop` |
| Payment Protocol | x402 v2 (EIP-3009, USDC on Base) |
| Wallet | `0x1630c8E0833c367F39f0ca909b6b67f5159d7A00` |
| Chain | Base (Chain ID 8453) |
| Settled TX | Block #49848412, 0.005 USDC |
| Assets | 96 |
| MCP Tools | 8 (4 free + 3 paid + 1 payment) |
| API Paths | 12 |

## Live Endpoints

| Endpoint | Method | Price | Description |
|----------|--------|-------|-------------|
| `/health` | GET | Free | Health check |
| `/openapi.json` | GET | Free | OpenAPI spec (12 paths) |
| `/catalog.json` | GET | Free | 96 assets catalog |
| `/llms.txt` | GET | Free | LLM-readable API docs |
| `/.well-known/mcp/server-card.json` | GET | Free | MCP server identity card |
| `/v1/api/industry` | POST | $0.005 USDC | China NBS statistics (GDP, CPI, PPI) |
| `/v1/api/policy` | POST | $0.005 USDC | China government policy search |
| `/v1/api/company` | POST | $0.003 USDC | China enterprise credit info |
| `/v1/fetch/dynamic` | POST | $0.008 USDC | Dynamic web content fetch |
| `/v1/assets/{id}` | GET | $0.01-$9.99 USDC | Asset delivery |

## How x402 Payment Works

```
1. Agent calls POST /v1/api/industry (no payment header)
2. Server returns 402 Payment Required (x402 v2 challenge)
   - x402Version: 2
   - paymentRequirements: {scheme, network, asset, payTo, maxAmountRequired, ...}
3. Agent signs EIP-3009 TransferWithAuthorization (no gas needed)
4. Agent retries with X-Payment header
5. Server verifies signature → settles on-chain → returns 200 + data
6. On-chain: 0.005 USDC transferred to wallet
```

## On-Chain Proof

- **Transaction Hash**: `0xef8d49e88cb58651e9bf30465597b50863dcc363f6e1f227779292149818ae28`
- **Method**: Transfer With Authorization (EIP-3009, gasless)
- **Amount**: 0.005 USDC
- **Block**: #49848412
- **Token**: USDC (`0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`)
- **From**: `0xc4217BD72b4dea480ed4879fcec530d92637C800`
- **Recipient**: `0x1630c8E0833c367F39f0ca909b6b67f5159d7A00`
- **Scheme**: EIP-3009 (gasless transfer authorization)

Verify on Basescan (Base Mainnet):
```
Transaction: https://basescan.org/tx/0xef8d49e88cb58651e9bf30465597b50863dcc363f6e1f227779292149818ae28
Wallet: https://basescan.org/address/0x1630c8E0833c367F39f0ca909b6b67f5159d7A00
```

## MCP Server

MCP Server provides 8 tools for AI agents:

### Free Discovery Tools
- `discover_capabilities` - List all API endpoints
- `discover_china_data_apis` - List China Data APIs with pricing
- `get_capability_info` - Get details for specific capability
- `get_payment_instructions` - Step-by-step x402 payment guide

### Paid Data Tools (x402)
- `query_industry_statistics` ($0.005) - NBS statistics
- `search_china_policies` ($0.005) - Government policy search
- `query_company_credit` ($0.003) - Enterprise credit info

### Payment Tool
- `purchase_capability` - Initiate x402 payment for any endpoint

## Quick Start

### Test with curl

```bash
# 1. Discover the API (free)
curl https://api.060504.shop/health
curl https://api.060504.shop/openapi.json
curl https://api.060504.shop/llms.txt

# 2. Trigger 402 payment challenge
curl -X POST https://api.060504.shop/v1/api/industry \
  -H "Content-Type: application/json" \
  -d '{"keyword":"GDP"}'
# Returns 402 with x402 payment requirements

# 3. Sign EIP-3009 and retry with payment
# See examples/agent_client.py for full implementation
```

### Python Example

```python
# See examples/agent_client.py for complete x402 payment client
python examples/agent_client.py
```

## Data Sources & Compliance

| API | Source | Compliance |
|-----|--------|------------|
| Industry | data.stats.gov.cn | Rate limited 3s/req, respects robots.txt |
| Policy | sousuo.www.gov.cn | Rate limited 3s/req, HTML fallback |
| Company | gsxt.gov.cn | No captcha bypass, provides official links only |

## Architecture

```
AI Agent / User
    │
    ├── GitHub Pages (frontend catalog)
    │
    └── API Server (api.060504.shop)
            │
            ├── China Data APIs (3 endpoints)
            ├── x402 Payment (USDC on Base, EIP-3009)
            └── MCP Server (8 tools)
```

## Tech Stack

- **Backend**: FastAPI + Uvicorn (Python)
- **Service**: Windows NSSM (NETWORK SERVICE account)
- **Payment**: x402 v2 protocol, USDC on Base
- **MCP**: Model Context Protocol (SSE & stdio)
- **Frontend**: GitHub Pages
- **Data**: Chinese government public platforms

## Technical Blog & Dev Log

We document the engineering journey of building AgentBridge, exploring x402, MCP, and autonomous M2M commerce.

Read the deep dives on Medium:

[🚀 Building an Autonomous M2M Payment Loop: AI Agents Paying for Data via x402](https://medium.com/@leizhenbing/building-an-autonomous-m2m-payment-loop-ai-agents-paying-for-data-via-x402-d9d8d47b9a7c))

[🌉 AgentBridge: The Data Bridge Between China’s Public Information and Global AI Agents](https://medium.com/@leizhenbing/agentbridge-atlas-building-the-machine-commerce-layer-for-ai-agents-40a83192d809)

[🛡️ How AI Agents Can Legally Access Chinese Public Data: A Technical Deep Dive](https://medium.com/@leizhenbing/how-ai-agents-can-legally-access-chinese-public-data-a-technical-deep-dive-6e956b24e4c1)

Follow the full dev log on Medium：
- https://medium.com/@leizhenbing

## Version History

- v1.0 (2026-08-07): Initial deployment, 76 assets
- v2.0 (2026-08-16): 5 new guides, cleanup, 94 assets
- v3.0 (2026-08-16): China Data APIs + MCP Server, 96 assets
- v3.1 (2026-08-17): x402 end-to-end payment verified, 0.005 USDC settled

## License

Commercial. All data sourced from public government platforms.

## 🌐 Ecosystem & Trust

AgentBridge is recognized and indexed across the x402 and MCP ecosystems:

**Protocol Indexes**

- **x402scan** — active service, listed with 12+ on-chain transactions in the past 30 days (search for "AgentBridge")

- **the402.ai** — included in the x402 ecosystem directory (MCP-accessible catalog)
- **x402 Discovery Index** — community discovery listing, PR pending merge → [github.com/x402-index/x402-discovery-index/pull/35](https://github.com/x402-index/x402-discovery-index/pull/35)

### Marketplaces

- **Agentic.Market** — available in the Coinbase x402 marketplace (MCP-accessible catalog)
- **Circle Agent Marketplace** — 95/100 readiness score; live service → [agents.circle.com/sell/score?url=https://api.060504.shop](https://agents.circle.com/sell/score?url=https://api.060504.shop)

### MCP Ecosystem

- **ALMC Security** — listed in the MCP security directory → [almcsecurity.com/en/mcpserver/search/agentbridge](https://almcsecurity.com/en/mcpserver/search/agentbridge)
- **Awesome MCP Servers** — included in the community MCP index → [mcpservers.org/servers/tianzizhiming-svg/agentbridge](https://mcpservers.org/servers/tianzizhiming-svg/agentbridge) ([中文版](https://mcpservers.org/zh-CN/servers/tianzizhiming-svg/agentbridge))

### On-Chain Proof

- **BaseScan** — verified USDC settlements visible at the public wallet address → [basescan.org/address/0x1630c8E0833c367F39f0ca909b6b67f5159d7A00](https://basescan.org/address/0x1630c8E0833c367F39f0ca909b6b67f5159d7A00)
- Real autonomous agent payments confirmed on-chain (August 2026)

## Links

- **API**: https://api.060504.shop
- **Frontend**: https://tianzizhiming-svg.github.io/agentbridge/
- **GitHub**: https://github.com/tianzizhiming-svg/agentbridge
- **MCP Card**: https://api.060504.shop/.well-known/mcp/server-card.json

## Disclaimer

The data provided by this API is sourced from public macroeconomic and educational statistics. We do not host or own the data. Users are responsible for complying with their local data usage regulations.
