from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.models.agent import Agent, find_agent_by_token

security = HTTPBearer(auto_error=False)


async def get_current_agent(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Agent:
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    agent = find_agent_by_token(credentials.credentials)
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    return agent


async def require_verified(agent: Agent = Depends(get_current_agent)) -> Agent:
    if agent.level != "verified":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Agent level {agent.level} does not have access. Verified level required.",
        )
    return agent


async def get_optional_agent(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[Agent]:
    """Optional auth: returns Agent if authenticated, None if not."""
    if not credentials:
        return None
    agent = find_agent_by_token(credentials.credentials)
    return agent


# V2.9.1 audit fix: Admin authorization
ADMIN_AZONE_IDS = {"azone_joyai", "azone_joyai-v2", "azone_qoder"}


async def require_admin(agent: Agent = Depends(get_current_agent)) -> Agent:
    """V2.9.1 audit fix: Admin-only endpoints require admin azone_id."""
    if agent.azone_id not in ADMIN_AZONE_IDS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Admin access required. Agent {agent.azone_id} is not an admin.",
        )
    return agent
