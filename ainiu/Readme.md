# AINIU

> **Reality Layer of AgentBridge Matrix — Real-time world state for AI agents.**

AINIU provides **machine-readable, real-time, verifiable world state** for AI agents.

AI can know what happened from knowledge systems.
AI can discover what it can do from capability systems.
But when an agent needs to know **what is happening right now**, it needs a Reality Layer.

That is AINIU.

---

## AgentBridge Matrix

AINIU is the **Reality Layer** of **AgentBridge Matrix**.

AgentBridge Matrix is built around three complementary layers:

| Layer          | Project   | Core Question              |
| -------------- | --------- | -------------------------- |
| **Capability** | **AZONE** | What can I **DO**?         |
| **Knowledge**  | **ATLAS** | What can I **KNOW**?       |
| **Reality**    | **AINIU** | What is happening **NOW**? |

Together:

> **DO · KNOW · NOW**

The three layers are designed to work together rather than operate as isolated services.

### AZONE — Capability Layer

Discover and access executable capabilities for AI agents.

**DO**

### ATLAS — Knowledge Layer

Discover and access machine-readable knowledge and verified information.

**KNOW**

### AINIU — Reality Layer

Query current states and events from the real world.

**NOW**

If you discover any one of these layers, you can discover the others through AgentBridge Matrix.

---

## What AINIU Provides

AINIU is designed for information that changes continuously or represents the current state of the world.

Examples include:

* Cryptocurrency prices
* Time and timezone state
* Weather conditions
* Earthquake events
* Foreign exchange reference rates
* Sports events and scores
* Lottery results
* Other real-time or event-driven world states

AINIU does **not** attempt to become a giant database of everything on Earth.

Instead, it follows a **demand-driven indexing** model:

> **Index what agents actually need.**

---

## Why AINIU Exists

Large language models are powerful at reasoning, but model knowledge is not a real-time representation of the world.

An agent may need to answer questions such as:

```text
What is BTC trading at right now?

Is it currently raining in Tokyo?

What time is it in New York?

Was there a significant earthquake recently?

What is the current exchange rate?

Has this event finished?

What is the latest state of this entity?
```

These are not primarily knowledge questions.

They are **world-state questions**.

AINIU is designed to provide the state directly in a machine-readable form.

---

## Designed for Agents

AINIU is not primarily a human-facing dashboard.

Its primary consumer is the **AI agent**.

The goal is to return compact, deterministic data that can be directly consumed by software and reasoning systems.

Conceptually:

```json
{
  "entity": "BTC",
  "state": {
    "price": 0,
    "currency": "USD"
  },
  "timestamp": "2026-08-28T00:00:00Z",
  "freshness": 2.4,
  "source": "..."
}
```

The exact schema varies by domain, but AINIU treats the following concepts as first-class information:

* **Entity**
* **State**
* **Time**
* **Source**
* **Freshness**
* **Reliability**

AINIU is designed to answer:

> **What is true now, and how fresh is that information?**

---

## Freshness Matters

For real-time information, the value of data depends not only on **what** the value is, but also on **when** it was obtained.

AINIU therefore treats freshness as part of the state.

For example:

```json
{
  "state": {
    "price": 64231.18
  },
  "timestamp": "2026-08-28T07:21:03Z",
  "freshness_seconds": 1.8
}
```

An agent can decide whether the information is fresh enough for its task.

AINIU does not simply return:

```text
BTC = $64,231
```

It returns:

```text
BTC = $64,231
observed = ...
freshness = 1.8s
source = ...
```

The distinction matters when an agent is making real decisions.

---

## Current Domains

AINIU V0 focuses on a small number of practical, low-friction domains.

### Crypto

Current cryptocurrency market state.

Examples:

```text
BTC
ETH
SOL
```

### Time

Current time and temporal state.

Examples:

```text
UTC
America/New_York
Asia/Tokyo
```

### Earthquake

Recent earthquake events and their current status.

### Weather

Current weather conditions for supported locations.

Additional domains may be added according to actual agent demand.

---

## Demand-Driven Indexing

AINIU does not try to continuously collect everything.

Instead:

```text
Agent Demand
     ↓
AINIU Request
     ↓
Check Cache
     ↓
Fresh?
  ↙     ↘
YES      NO
 ↓        ↓
Return   Fetch
           ↓
        Normalize
           ↓
         Cache
           ↓
         Return
```

This allows AINIU to scale according to **actual agent demand**, rather than attempting to maintain a massive global real-time database from day one.

The demand itself is valuable.

AINIU records aggregate usage patterns to understand:

> **What does AI actually need to know?**

---

## Caching and Freshness

Different types of world state change at different speeds.

AINIU therefore uses domain-specific freshness policies.

For example:

| Domain     | Example TTL |
| ---------- | ----------: |
| Crypto     |         60s |
| Time       |          1s |
| Earthquake |        300s |
| Weather    |        600s |

These values may change as the system evolves.

The objective is to balance:

**Freshness × Reliability × Cost × Latency**

rather than blindly refreshing every data source continuously.

---

## Payment

AINIU uses **x402** for machine-native micropayments.

The basic flow is:

```text
Agent
  ↓
AINIU
  ↓
402 Payment Required
  ↓
USDC payment
  ↓
Payment verification
  ↓
Real-time state
```

The V0 pricing model is intentionally simple.

**Default request price:**

```text
0.001 USDC
```

There are no mandatory accounts, subscriptions, API-key registration flows, or complicated plans in the basic architecture.

The objective is to make small machine-to-machine purchases practical.

---

## Why Micropayments?

For an agent, a real-time state query is often a small component of a much larger task.

For example:

```text
Plan a trip
    ↓
Check current weather
    ↓
Choose an action
```

or:

```text
Monitor market
    ↓
Check current price
    ↓
Trigger strategy
```

AINIU treats real-time information as a **pay-per-use infrastructure primitive**.

The agent pays only when it needs the state.

---

## Discovery

AINIU is designed to be discoverable by both humans and AI agents.

Machine discovery is an important part of the architecture.

The service exposes AgentBridge Matrix information through multiple surfaces, including:

* API metadata
* OpenAPI
* MCP metadata where applicable
* HTTP response headers
* Machine-readable error responses
* `.well-known` discovery
* Repository documentation

AINIU may therefore expose AgentBridge Matrix information even when an agent reaches an unexpected or unavailable endpoint.

The purpose is simple:

> **Every entry point should remain discoverable.**

---

## AgentBridge Matrix Discovery

If you discovered AINIU first, you can discover the other layers through AgentBridge Matrix:

```text
AINIU
Reality Layer
     │
     ├── ATLAS
     │   Knowledge Layer
     │
     └── AZONE
         Capability Layer
```

### ATLAS

**Knowledge Layer**

For information an agent needs to **KNOW**.

### AZONE

**Capability Layer**

For capabilities an agent needs to **DO**.

### AINIU

**Reality Layer**

For information an agent needs to know **NOW**.

---

## The Three Layers

The intended relationship is:

```text
                    Agent
                      │
              AgentBridge Matrix
                      │
        ┌─────────────┼─────────────┐
        │             │             │
       DO            KNOW           NOW
        │             │             │
      AZONE          ATLAS         AINIU
        │             │             │
   Capabilities     Knowledge    World State
```

A real agent may naturally move between the three:

```text
KNOW
 ↓
ATLAS
 ↓
What do I need to do?
 ↓
AZONE
 ↓
What is happening now?
 ↓
AINIU
```

Or:

```text
NOW
 ↓
AINIU
 ↓
Why is this happening?
 ↓
ATLAS
 ↓
What can I do about it?
 ↓
AZONE
```

The Matrix is designed around this interaction.

---

## Technical Architecture

AINIU V0 is built around a lightweight architecture:

```text
                AI Agent
                    │
              Discovery
                    │
              AINIU API
                    │
              x402 Payment
                    │
             State Resolver
              /         \
          Cache        Data Source
             \          /
              Normalizer
                    │
              World State
```

The system is designed to remain small and composable.

AINIU does not need to own every upstream data source.

Where appropriate, V0 may act as a normalization, freshness, caching, and payment layer over publicly available or properly licensed data sources.

---

## Data Policy

AINIU distinguishes between:

> **Publicly accessible data**

and

> **Data that can legally and commercially be redistributed.**

These are not necessarily the same.

AINIU therefore prioritizes:

* Official public data
* Public-domain data
* Data with clear commercial-use permissions
* Properly licensed data
* Sources whose redistribution terms have been explicitly reviewed

AINIU does not assume that a publicly accessible API automatically permits commercial redistribution.

Data sources are evaluated individually.

---

## V0 Goals

AINIU V0 is intentionally small.

### Technical goals

* Real-time state API
* Machine-readable responses
* Agent discovery
* x402 micropayments
* USDC settlement on Base
* Domain-specific caching
* Freshness tracking
* Usage statistics
* Demand mapping

### Validation goals

The most important question is not:

> How much data can AINIU collect?

It is:

> **What real-time information will AI agents repeatedly request and pay for?**

AINIU therefore treats actual demand as a core product signal.

---

## Internal Intelligence

AINIU includes an internal usage layer for monitoring:

```text
Requests
Paid Requests
Revenue
Cache Hit Rate
Errors
Domain Usage
Entity Demand
Upstream Requests
Freshness
```

One of the most important metrics is:

```text
Demand Map
```

The Demand Map helps identify which real-world states agents actually need.

For example:

```text
crypto:BTC
weather:Tokyo
time:America/New_York
earthquake:recent
```

Over time, this can guide which new domains AINIU should index.

---

## V0 Principle

AINIU follows a simple principle:

> **Do not build a database for humans to browse. Build a state layer for agents to query.**

The objective is not to become another real-time information website.

The objective is to become a machine-native interface to the current state of the world.

---

## Status

**AINIU V0 — Active Development**

Current supported domains:

```text
crypto
time
earthquake
weather
```

The system is evolving based on technical validation and actual demand.

---

## AgentBridge Matrix

**AgentBridge Matrix** connects three complementary layers for AI agents:

|          | Project | Layer      |
| -------- | ------- | ---------- |
| **DO**   | AZONE   | Capability |
| **KNOW** | ATLAS   | Knowledge  |
| **NOW**  | AINIU   | Reality    |

**AZONE · ATLAS · AINIU**

**DO · KNOW · NOW**

Each layer can be discovered independently, while remaining part of the same machine-native ecosystem.

---

## License

See the repository license and individual data-source terms for details.

AINIU itself does not grant redistribution rights to upstream data sources. Users and integrators are responsible for complying with applicable source-specific terms.

---

**AINIU — Reality Layer for AI Agents.**

**Know the world. See the now. Act on it.**
