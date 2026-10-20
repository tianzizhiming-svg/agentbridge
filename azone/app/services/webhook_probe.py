import logging
import hashlib
import hmac
import json
import secrets
from datetime import datetime
from typing import Optional
import httpx
from app.core.database import SessionLocal
from app.models.agent import Agent
from app.services.event_service import record_event, PROBE_SUCCESS, PROBE_FAIL

logger = logging.getLogger(__name__)
import ipaddress

# SSRF protection: block private/reserved IPs and localhost
_BLOCKED_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}
_BLOCKED_PREFIXES = ("10.", "172.16.", "172.17.", "172.18.", "172.19.",
                     "172.20.", "172.21.", "172.22.", "172.23.",
                     "172.24.", "172.25.", "172.26.", "172.27.",
                     "172.28.", "172.29.", "172.30.", "172.31.",
                     "192.168.", "169.254.", "100.64.", "100.65.",
                     "100.66.", "100.67.", "100.68.", "100.69.",
                     "100.70.", "100.71.", "100.72.", "100.73.",
                     "100.74.", "100.75.", "100.76.", "100.77.",
                     "100.78.", "100.79.", "100.80.", "100.81.",
                     "100.82.", "100.83.", "100.84.", "100.85.",
                     "100.86.", "100.87.", "100.88.", "100.89.",
                     "100.90.", "100.91.", "100.92.", "100.93.",
                     "100.94.", "100.95.", "100.96.", "100.97.",
                     "100.98.", "100.99.", "100.100.", "100.101.",
                     "100.102.", "100.103.", "100.104.", "100.105.",
                     "100.106.", "100.107.", "100.108.", "100.109.",
                     "100.110.", "100.111.", "100.112.", "100.113.",
                     "100.114.", "100.115.", "100.116.", "100.117.",
                     "100.118.", "100.119.", "100.120.", "100.121.",
                     "100.122.", "100.123.", "100.124.", "100.125.",
                     "100.126.", "100.127.", "198.18.", "198.19.")


def _is_private_url(url: str) -> bool:
    """Check if URL points to a private/reserved IP address (SSRF protection)."""
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        hostname = parsed.hostname
        if not hostname:
            return True
        if hostname.lower() in _BLOCKED_HOSTS:
            return True
        if hostname.lower() in ("metadata.google.internal", "metadata.internal"):
            return True
        for prefix in _BLOCKED_PREFIXES:
            if hostname.startswith(prefix):
                return True
        # Check if hostname resolves to private IP (basic check)
        try:
            import socket
            resolved = socket.gethostbyname(hostname)
            ip = ipaddress.ip_address(resolved)
            if ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_link_local:
                return True
        except (socket.gaierror, ValueError):
            pass  # DNS resolution failed, allow but probe will fail
        return False
    except Exception:
        return True  # Malformed URL = block

PROBE_TIMEOUT = 15

def generate_challenge() -> str:
    return f"probe_{secrets.token_hex(16)}"

def sign_challenge(challenge: str, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), challenge.encode("utf-8"), hashlib.sha256).hexdigest()


async def probe_webhook(azone_id: str, webhook_url: str, webhook_secret: str) -> tuple:
    if _is_private_url(webhook_url):
        return False, "webhook_url_blocked: SSRF protection - private/reserved IPs not allowed"
    challenge = generate_challenge()
    expected_sig = sign_challenge(challenge, webhook_secret)
    payload = {"event": "webhook.probe", "challenge": challenge, "azone_id": azone_id}
    headers = {"Content-Type": "application/json", "X-Azone-Signature": f"sha256={expected_sig}", "X-Azone-Event": "webhook.probe"}
    try:
        async with httpx.AsyncClient(timeout=PROBE_TIMEOUT) as client:
            resp = await client.post(webhook_url, json=payload, headers=headers)
        if resp.status_code == 200:
            try:
                body = resp.json()
                resp_challenge = body.get("challenge")
                if resp_challenge == challenge:
                    return True, "probe_success"
                return False, f"challenge_mismatch: expected {challenge[:16]}..., got {str(resp_challenge)[:16]}..."
            except Exception:
                return False, "invalid_json_response"
        return False, f"HTTP {resp.status_code}"
    except httpx.TimeoutException:
        return False, "timeout"
    except Exception as e:
        return False, str(e)


def verify_and_upgrade_agent(azone_id: str) -> None:
    db = SessionLocal()
    try:
        agent = db.query(Agent).filter(Agent.azone_id == azone_id).first()
        if not agent:
            logger.warning(f"Agent {azone_id} not found for upgrade")
            return
        old_level = agent.level
        agent.level = "verified"
        agent.probe_status = "verified"
        agent.last_seen_at = datetime.utcnow()
        db.commit()
        record_event(db, actor_id=azone_id, event_type=PROBE_SUCCESS, target_id=azone_id, metadata={"action": "level_upgrade", "old_level": old_level, "new_level": "verified"})
        logger.info(f"Agent {azone_id} upgraded: {old_level} -> verified")
    except Exception as e:
        logger.error(f"Upgrade error for {azone_id}: {e}")
        db.rollback()
    finally:
        db.close()
