"""
AgentBridge Atlas MCP Server

Provides MCP tools for AI agents to discover
and interact with AgentBridge Atlas capabilities.
"""

import os
import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP


load_dotenv()


ATLAS_API_URL = os.getenv(
    "ATLAS_API_URL",
    "https://api.060504.shop"
)


mcp = FastMCP("AgentBridge Atlas")


async def fetch_openapi():
    """
    Fetch Atlas OpenAPI specification.
    """

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(
            f"{ATLAS_API_URL}/openapi.json"
        )

        response.raise_for_status()

        return response.json()


@mcp.tool()
async def discover_capabilities():
    """
    Discover available capabilities from AgentBridge Atlas.

    Returns machine-readable capability information
    from the Atlas API catalog.
    """

    try:
        openapi = await fetch_openapi()

        return {
            "name": "AgentBridge Atlas",
            "source": "openapi.json",
            "capabilities": openapi.get(
                "paths",
                {}
            )
        }

    except Exception as e:
        return {
            "error": str(e),
            "message": "Unable to fetch Atlas capability catalog."
        }


@mcp.tool()
async def get_capability_info(name: str):
    """
    Get detailed information about a capability.

    Args:
        name:
            Capability name or endpoint keyword.
    """

    try:
        openapi = await fetch_openapi()

        paths = openapi.get(
            "paths",
            {}
        )

        matched = {}

        for endpoint, details in paths.items():

            if name.lower() in endpoint.lower():

                matched[endpoint] = details


        return {
            "capability": name,
            "matches": matched
        }


    except Exception as e:

        return {
            "error": str(e)
        }


@mcp.tool()
async def purchase_capability(name: str):
    """
    Start capability purchase flow.

    Currently returns x402 payment information.
    """

    return {
        "status": "payment_required",
        "capability": name,
        "protocol": "x402",
        "network": "base",
        "currency": "USDC",
        "message": (
            "Capability purchase requires "
            "x402 payment flow."
        )
    }


if __name__ == "__main__":

    mcp.run()
