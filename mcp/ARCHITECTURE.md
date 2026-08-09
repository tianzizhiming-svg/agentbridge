# AgentBridge Atlas MCP Architecture

## Overview

The MCP adapter connects AI agents with AgentBridge Atlas capabilities.

Architecture:
AI Agent

|
| MCP Protocol

↓

AgentBridge Atlas MCP Server

|
| OpenAPI / x402

↓

AgentBridge Atlas API

|
| USDC payment on Base

↓

Capability Provider


## Components

### MCP Server

Provides machine-readable tools for AI agents.

Current tools:

- discover_capabilities
- get_capability_info
- purchase_capability


### Capability Discovery

Agents can discover available services without prior knowledge of API endpoints.

Example:


Agent:
"What capabilities are available?"

↓

Atlas:
Returns available capability catalog



### Payment Layer

Purchases are handled through x402.

Flow:


Agent request

↓

Payment challenge

↓

USDC payment

↓

Capability execution

↓

Result returned



## Future Extensions

Possible future adapters:

- AP2 compatibility
- Additional settlement networks
- More agent frameworks
- Reputation and trust scoring

提交：

Commit message：

Add MCP architecture documentation
