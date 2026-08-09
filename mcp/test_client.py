# AgentBridge Atlas MCP Architecture

## Overview

The AgentBridge Atlas MCP Adapter connects AI agents with machine-readable capabilities through the Model Context Protocol (MCP).

It provides a bridge between autonomous agents and the AgentBridge Atlas machine commerce layer.

The architecture enables agents to:

- discover available capabilities
- understand capability requirements
- initiate capability purchases
- receive machine-readable results


## Architecture


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

The MCP server exposes Atlas capabilities as tools that AI agents can call.

Current tools:

- `discover_capabilities`
- `get_capability_info`
- `purchase_capability`


### Capability Discovery

Agents should not need to know every API endpoint in advance.

Through MCP, agents can discover available capabilities dynamically.

Example:


Agent:

"What capabilities are available for China-focused research?"

↓

Atlas MCP Server:

Returns available capabilities,
pricing information,
and payment requirements.



### Capability Information

Agents can request additional information before making a purchase.

Information may include:

- capability description
- category
- pricing model
- payment protocol
- execution endpoint


### Payment Layer

AgentBridge Atlas uses x402 for machine-native payments.

Payment flow:


Agent request

↓

x402 payment challenge

↓

USDC payment on Base

↓

Capability execution

↓

Result returned to agent



## Design Principles

### Machine First

Atlas capabilities are designed for machine consumption rather than traditional human interfaces.

### Discovery Before Transaction

Agents should understand available capabilities before initiating payments.

### Open Protocols

Atlas uses open standards:

- MCP for agent interaction
- OpenAPI for API description
- x402 for payment settlement


## Future Extensions

Potential future development:

- AP2 compatibility
- additional blockchain settlement networks
- more agent frameworks
- capability reputation scoring
- autonomous capability selection


## Goal

The goal of the MCP adapter is to make AgentBridge Atlas discoverable and usable by the next generation of AI agents.
