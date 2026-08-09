# AgentBridge Atlas MCP Adapter

Connect AI agents with machine-readable capabilities through MCP and x402 payments.

AgentBridge Atlas provides a machine commerce layer where AI agents can discover, purchase, and consume digital capabilities.

## Overview

Traditional APIs assume a human developer is responsible for:

- finding the service
- creating an account
- managing API keys
- handling payments

AgentBridge Atlas explores a different model:

AI Agent
|
| MCP
|
AgentBridge Atlas
|
| x402 payment
|
Capability Provider


Agents can discover available capabilities, understand pricing, and access external services through standardized interfaces.

## MCP Tools

The first version exposes:

### discover_capabilities

Find available capabilities in the Atlas marketplace.

Example:


"What China-focused capabilities are available?"


Returns:

- capability name
- description
- category
- pricing model
- endpoint information


### get_capability_info

Retrieve detailed information about a capability.

Example:


"Show details for university employment analysis"



### purchase_capability

Request access to a capability.

Payment flow:


Agent request

↓

x402 payment challenge

↓

USDC payment on Base

↓

Capability execution

↓

Result returned


## Supported Protocols

Current:

- MCP (Model Context Protocol)
- x402 payments
- OpenAPI

Future:

- AP2 compatibility
- additional settlement networks


## Status

Early development.

The goal is to make AgentBridge Atlas discoverable by AI agents and agent frameworks.

## Links

Website:
https://tianzizhiming-svg.github.io/agentbridge/

API:
https://api.060504.shop/openapi.json

GitHub:
https://github.com/tianzizhiming-svg/agentbridge

## Local Development

Install dependencies:

```bash
pip install -r requirements.txt
