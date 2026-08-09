# AgentBridge Atlas MCP Integration

## Supported Clients

AgentBridge Atlas MCP adapter is designed to work with MCP-compatible AI agents and clients.

Examples:

- Claude Desktop
- MCP clients
- Agent frameworks supporting MCP


## Configuration

Add AgentBridge Atlas as an MCP server:

```json
{
  "mcpServers": {
    "agentbridge-atlas": {
      "command": "python",
      "args": [
        "mcp/server.py"
      ]
    }
  }
}
Available Tools
discover_capabilities

Returns available Atlas capabilities.

get_capability_info

Returns capability details including:

description
pricing
payment protocol
purchase_capability

Starts the x402 payment flow.

Payment Flow
Agent

↓

MCP Tool Call

↓

Atlas Capability Request

↓

x402 Payment Challenge

↓

USDC Payment on Base

↓

Capability Result
Future

Planned integrations:

Agent frameworks
MCP registries
Additional payment protocols

提交：

```text
Add MCP integration documentation
