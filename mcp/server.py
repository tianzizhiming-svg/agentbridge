from mcp.server.fastmcp import FastMCP

mcp = FastMCP("AgentBridge Atlas")


@mcp.tool()
def discover_capabilities():
    """
    Discover available capabilities in AgentBridge Atlas.
    """
    return {
        "capabilities": [
            {
                "name": "china_web_fetch",
                "category": "raw-content",
                "payment": "x402"
            },
            {
                "name": "university_analysis",
                "category": "verified-analysis",
                "payment": "x402"
            }
        ]
    }


@mcp.tool()
def get_capability_info(name: str):
    """
    Get capability information.
    """
    return {
        "name": name,
        "protocol": "x402",
        "network": "base",
        "currency": "USDC"
    }


@mcp.tool()
def purchase_capability(name: str):
    """
    Start capability purchase flow.
    """
    return {
        "status": "payment_required",
        "protocol": "x402",
        "capability": name
    }


if __name__ == "__main__":
    mcp.run()
