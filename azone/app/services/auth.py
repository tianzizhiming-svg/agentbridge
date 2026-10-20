import hashlib
import hmac
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.agent import Agent

security = HTTPBearer(auto_error=False)

async def get_current_agent(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security), db: Session = Depends(get_db)) -> Agent:
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing authentication token", headers={"WWW-Authenticate": "Bearer"})
    token = credentials.credentials
    agent = db.query(Agent).filter(Agent.agent_token == token).first()
    if not agent:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    return agent

async def require_verified(agent: Agent = Depends(get_current_agent)) -> Agent:
    if agent.level != "verified":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f'Agent level {agent.level} does not have access. Verified level required.')
    return agent

def verify_webhook_signature(payload: bytes, signature: str, secret: str) -> bool:
    if not signature or not signature.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    provided = signature[len("sha256="):]
    return hmac.compare_digest(expected, provided)
