import logging
import ipaddress
from urllib.parse import urlparse
import httpx
from app.core.config import settings

logger = logging.getLogger(__name__)

# SSRF protection: blocked networks
BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]

BLOCKED_HOSTNAMES = {"localhost", "127.0.0.1", "0.0.0.0"}


def validate_endpoint(endpoint: str) -> bool:
    try:
        parsed = urlparse(endpoint)
        if parsed.scheme not in ("http", "https"):
            return False
        host = parsed.hostname
        if not host:
            return False
        if host.lower() in BLOCKED_HOSTNAMES:
            return False
        import socket
        resolved_ip = socket.getaddrinfo(host, None)[0][4][0]
        ip = ipaddress.ip_address(resolved_ip)
        for network in BLOCKED_NETWORKS:
            if ip in network:
                return False
        return True
    except Exception:
        return False


async def probe_agent(endpoint: str) -> tuple:
    if not validate_endpoint(endpoint):
        return "fail", "endpoint blocked (SSRF protection)"
    timeout = settings.PROBE_TIMEOUT_SECONDS
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            resp = await client.get(endpoint)
            if resp.status_code < 500:
                try:
                    ping_url = endpoint.rstrip("/") + "/ping"
                    ping_resp = await client.get(ping_url)
                    if ping_resp.status_code == 200:
                        return "success", "probed"
                except Exception:
                    pass
                return "success", "reachable"
            return "fail", f"HTTP {resp.status_code}"
    except httpx.TimeoutException:
        return "fail", "timeout"
    except Exception as e:
        return "fail", str(e)
