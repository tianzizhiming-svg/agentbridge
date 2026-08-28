# AgentBridge Atlas

**The Capability Layer of AgentBridge Matrix.**

Discover, purchase, and use machine-readable capabilities through AI-native interfaces.

AgentBridge Atlas is a machine commerce layer for AI agents.

It helps agents discover capabilities, understand what they can do, determine the cost, and access external services through standardized interfaces and x402 payments.

---

## AgentBridge Matrix

Atlas is one of three complementary layers in AgentBridge Matrix.

| Layer | Project | Core Question |
|---|---|---|
| Capability Layer | **AZONE** | What can an AI agent do? |
| Knowledge Layer | **ATLAS** | What can an AI agent know? |
| Reality Layer | **AINIU** | What is happening right now? |

Together:

**AZONE → capabilities**

**ATLAS → knowledge**

**AINIU → real-time world state**

An AI agent may need all three:

> Discover a capability → obtain knowledge → check the current state → execute an action.

AgentBridge Matrix is designed around this complete loop.

### The other layers

**AZONE**

The capability discovery and machine-commerce layer of AgentBridge.

It is where AI agents discover digital capabilities that can be purchased and executed.

**AINIU**

The real-time Reality Layer of AgentBridge.

It provides machine-readable, real-time world state such as market conditions, weather, earthquakes, time, and other dynamic information.

AINIU answers a different question from Atlas:

> Atlas tells an agent what is known.  
> AINIU tells an agent what is happening now.

---

## Why Atlas Exists

Traditional APIs assume that a human developer is responsible for:

- finding the service
- reading the documentation
- creating an account
- obtaining API keys
- understanding pricing
- integrating the API
- handling payments

Agent-native commerce should work differently.

An AI agent should be able to:

1. discover a capability
2. understand what it does
3. inspect its pricing
4. request access
5. pay automatically
6. receive the result
7. continue its task

Atlas is designed for this model.

```text
AI Agent
   │
   ▼
Discover
   │
   ▼
Understand
   │
   ▼
Purchase
   │
   ▼
x402 Payment
   │
   ▼
Capability Provider
   │
   ▼
Machine-readable Result

The goal is simple:

Let AI agents buy capabilities instead of asking humans to configure APIs for them.

MCP

Atlas currently uses Model Context Protocol (MCP) as one of its primary interfaces for AI agents.

MCP provides the interaction layer.

Atlas provides the capability marketplace and commerce logic.

Conceptually:

AI Agent
   │
   ▼
MCP
   │
   ▼
AgentBridge Atlas
   │
   ├── Discover capabilities
   ├── Inspect capability information
   ├── Request access
   └── Handle x402 payment
            │
            ▼
     Capability Provider

MCP is therefore an interface into Atlas, not the product itself.

Other machine-native interfaces may be added in the future.

MCP Tools

The current Atlas MCP interface exposes three core operations.

discover_capabilities

Discover available capabilities.

Example:

"What China-focused capabilities are available?"

The agent can receive information such as:

capability name
description
category
pricing
endpoint
availability
usage information

The purpose is to allow an agent to discover services without relying on a human-curated API list.

get_capability_info

Retrieve detailed information about a specific capability.

Example:

"Show details for university employment analysis."

The response may include:

capability description
supported operations
input requirements
output format
pricing
endpoint information
usage restrictions
purchase_capability

Request access to a capability.

The payment flow is designed around x402.

Agent Request
      │
      ▼
402 Payment Required
      │
      ▼
USDC Payment on Base
      │
      ▼
Capability Execution
      │
      ▼
Result Returned

No traditional subscription or API-key workflow is required for the basic payment flow.

x402 Payments

Atlas uses the x402 payment protocol to enable machine-to-machine payments.

The basic principle is:

Request
   ↓
402 Payment Required
   ↓
Agent pays
   ↓
Retry request with payment
   ↓
Service executes
   ↓
Result

Payments are designed to be small and programmatic, making them suitable for machine-to-machine transactions.

Current settlement infrastructure uses:

x402
USDC
Base
Atlas and AINIU

Atlas and AINIU solve different problems.

Atlas focuses on capabilities and knowledge.

AINIU focuses on current reality.

For example, an agent planning a trip might need:

Atlas
↓
Find a travel-related capability

AINIU
↓
Check current weather and real-time conditions

Atlas
↓
Use a booking or analysis capability

AZONE
↓
Discover additional capabilities when needed

This distinction is intentional.

A capability is not the same thing as knowledge.

Knowledge is not the same thing as current world state.

AgentBridge Matrix keeps these layers separate while allowing agents to move between them.

Machine Discovery

Atlas is intended to be discovered by machines, not only by humans.

The project provides machine-readable metadata and standardized interfaces so that AI agents and agent frameworks can identify:

what Atlas is
what capabilities are available
how capabilities are accessed
how much they cost
how payment works

Machine discovery is a core part of the project.

Agent-Native Commerce

Atlas is built around a simple idea:

AI agents should be able to discover and purchase digital capabilities autonomously.

Instead of:

Human
 ↓
Search
 ↓
Read documentation
 ↓
Create account
 ↓
Get API key
 ↓
Configure application
 ↓
Pay
 ↓
API

Atlas aims toward:

AI Agent
 ↓
Discover
 ↓
Understand
 ↓
Pay
 ↓
Use

This is the foundation of machine commerce.

Architecture

At a high level:

                    AgentBridge Matrix
                           │
          ┌────────────────┼────────────────┐
          │                │                │
          ▼                ▼                ▼
       AZONE             ATLAS            AINIU
    Capabilities        Knowledge       Reality
          │                │                │
          └────────────────┼────────────────┘
                           │
                           ▼
                       AI Agent

Atlas itself acts as a bridge between AI agents and capability providers.

AI Agent
   │
   │ MCP / machine interface
   ▼
Atlas
   │
   ├── Discovery
   ├── Capability metadata
   ├── Pricing
   ├── x402 payment
   └── Provider access
             │
             ▼
      Capability Provider
Design Principles
Machine-first

Atlas is designed primarily for machine discovery and machine consumption.

Human-readable documentation exists to explain the system, but machine-readable interfaces are the primary interface.

No unnecessary accounts

The basic model avoids forcing every agent through traditional registration and subscription workflows.

Pay per use

Capabilities can be accessed through machine-to-machine payments.

Small transactions

The system is designed for low-value, high-frequency transactions.

Open discovery

Capabilities should be discoverable through standardized machine-readable metadata.

Composable

Atlas does not attempt to become the only system an agent needs.

It is one layer of AgentBridge Matrix.

Current Status

Early development.

The current implementation is focused on validating the fundamental loop:

Discovery
   ↓
Capability Selection
   ↓
Payment
   ↓
Execution
   ↓
Result

The long-term goal is to make this process increasingly autonomous for AI agents.

Supported Protocols

Current:

Model Context Protocol (MCP)
x402
OpenAPI
Base
USDC

Future possibilities include:

additional agent protocols
additional payment networks
additional machine-discovery mechanisms
AgentBridge Matrix

Atlas is part of the broader AgentBridge Matrix.

AZONE — Capability Layer

Discover and access capabilities.

"What can I do?"
ATLAS — Knowledge Layer

Discover and access structured knowledge.

"What can I know?"
AINIU — Reality Layer

Discover and access current world state.

"What is happening now?"

The three layers are complementary.

              AGENTBRIDGE MATRIX

       ┌──────────────┐
       │    AZONE     │
       │ Capabilities │
       └──────┬───────┘
              │
              ▼
       ┌──────────────┐
       │    ATLAS     │
       │  Knowledge   │
       └──────┬───────┘
              │
              ▼
       ┌──────────────┐
       │    AINIU     │
       │   Reality    │
       └──────┬───────┘
              │
              ▼
          AI AGENT

An agent does not necessarily need all three for every task.

But when a task requires:

capability + knowledge + current state

AgentBridge Matrix is designed to provide the three layers together.

Links
AgentBridge

https://github.com/tianzizhiming-svg/agentbridge

AgentBridge Website

https://tianzizhiming-svg.github.io/agentbridge/

Atlas API

https://api.060504.shop/openapi.json

AINIU

See:

/ainiu/
AZONE

See:

/azone/
Local Development

Install dependencies:

pip install -r requirements.txt

Run the MCP server:

python server.py

The server exposes Atlas capabilities through MCP.

Current tools:

discover_capabilities
get_capability_info
purchase_capability
Project Philosophy

Atlas is not intended to be another API directory.

It is an experiment in building infrastructure for a world where:

AI agents are the users.

In that world, discovery, pricing, payment, and execution should be understandable by machines.

Atlas is one step toward that model.

AgentBridge Matrix

AZONE — Capabilities

ATLAS — Knowledge

AINIU — Reality
