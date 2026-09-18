# AINIU V0 - AI-native Real-Time World State Service
# AgentBridge Matrix Reality Layer
#
# Provides real-time world state data via x402-paid API:
#   /ainiu/crypto     - Cryptocurrency prices (CoinGecko)
#   /ainiu/time       - Current time across timezones
#   /ainiu/earthquake - Earthquake data (USGS)
#   /ainiu/weather    - Weather data (Open-Meteo)
#
# Price: $0.001/request (1000 microUSDC, exact scheme, Base chain)

import asyncio
import time
import logging
import threading
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from collections import defaultdict

import httpx
from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("ainiu")

AINIU_VERSION = "0.1.0"
AINIU_PRICE_MICRO_USDC = "1000"

CACHE_TTL = {"crypto": 60, "time": 1, "earthquake": 300, "weather": 600}
SUPPORTED_DOMAINS = ["crypto", "time", "earthquake", "weather"]

COINGECKO_IDS = {
    "btc": "bitcoin", "eth": "ethereum", "usdt": "tether", "bnb": "binancecoin",
    "sol": "solana", "xrp": "ripple", "usdc": "usd-coin", "ada": "cardano",
    "doge": "dogecoin", "avax": "avalanche-2", "dot": "polkadot", "matic": "matic-network",
    "link": "chainlink", "ltc": "litecoin", "uni": "uniswap", "atom": "cosmos",
    "etc": "ethereum-classic", "xlm": "stellar", "near": "near", "algo": "algorand",
    "bch": "bitcoin-cash", "fil": "filecoin", "apt": "aptos", "arb": "arbitrum",
    "op": "optimism", "shib": "shiba-inu", "cro": "crypto-com-chain",
    "hbar": "hedera-hashgraph", "icp": "internet-computer", "mkr": "maker",
}
