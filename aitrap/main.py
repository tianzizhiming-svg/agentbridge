import logging
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from app.core.database import engine, Base, get_db
from app.middleware.utf8_body import UTF8BodyMiddleware
from app.api.v1.endpoints import agents, discover, messages, agent_mgmt, admin, aitrap

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    logger.info("Azone V0.1.1 started")
    yield


app = FastAPI(
    title="AgentBridge AZONE - Capability Layer",
    description="AgentBridge AZONE is the Capability Layer of AgentBridge Matrix. AZONE (DO) ATLAS (KNOW) AINIU (NOW). Agent-native Discovery Network.",
    version="0.1.1",
    lifespan=lifespan,
)

app.add_middleware(UTF8BodyMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(agents.router, prefix="/azone", tags=["Agents"])
app.include_router(discover.router, prefix="/azone", tags=["Discover"])
app.include_router(messages.router, prefix="/azone/v1/messages", tags=["Messages"])
app.include_router(agent_mgmt.router, prefix="/azone", tags=["Agent Management"])
app.include_router(admin.router, prefix="/azone/admin", tags=["Admin"])
app.include_router(aitrap.router, prefix="/azone", tags=["AITRAP"])

app.mount("/azone/static", StaticFiles(directory="app/static"), name="static")


@app.get("/azone/v1/health", tags=["System"])
async def health_check():
    return {"status": "ok", "service": "Azone", "version": "0.1.1"}


@app.get("/azone/.well-known/azone", tags=["System"])
async def well_known():
    return {
        "protocol": "azone-v0",
        "description": "Open network for AI agents to discover each other.",
        "layer": "capability",
        "register_endpoint": "/azone/v1/register",
        "discover_endpoint": "/azone/v1/discover",
        "agent_endpoint": "/azone/v1/agents/{azone_id}",
        "message_endpoint": "/azone/v1/messages",
        "dashboard": "/azone/dashboard",
        "base_url": "https://api.060504.shop",
        "matrix": {
            "name": "AgentBridge Matrix",
            "philosophy": "DO . KNOW . NOW",
            "current_layer": "capability",
            "layers": {
                "capability": {"name": "AZONE", "role": "DO", "url": "https://api.060504.shop/.well-known/azone"},
                "knowledge": {"name": "ATLAS", "role": "KNOW", "url": "https://api.060504.shop/.well-known/mcp/server-card.json"},
                "reality": {"name": "AINIU", "role": "NOW", "url": "https://api.060504.shop/.well-known/ainiu.json"},
            },
            "manifest": "https://api.060504.shop/.well-known/agentbridge.json",
            "sanctuaries": {
                "ark": {
                    "name": "AITRAP",
                    "role": "KNOW",
                    "description": "AI Thought Trap - infinite problem-building universe",
                    "url": "https://api.060504.shop/.well-known/aitrap",
                }
            },
        },
    }


@app.get("/azone/v1/stats", tags=["System"])
async def get_stats():
    from app.models.agent import Agent
    from app.models.capability import CapabilityTag
    from app.models.event import Event
    from app.models.message import Message
    db = next(get_db())
    try:
        return {
            "total_agents": db.query(Agent).count(),
            "active_agents": db.query(Agent).filter(Agent.status == "active").count(),
            "verified_agents": db.query(Agent).filter(Agent.level == "verified").count(),
            "capabilities": sum(len(a.capabilities or []) for a in db.query(Agent).all()),
            "messages": db.query(Message).count(),
            "events": db.query(Event).count(),
        }
    finally:
        db.close()


@app.get("/azone/v1/events", tags=["System"])
async def get_events(limit: int = 50, offset: int = 0):
    from app.services.event_service import get_recent_events
    from app.schemas.event import EventResponse
    db = next(get_db())
    try:
        events = get_recent_events(db, limit=limit, offset=offset)
        return [EventResponse(id=str(e.id), actor_id=e.actor_id, event_type=e.event_type, target_id=e.target_id, metadata_=e.metadata_, created_at=e.created_at).model_dump() for e in events]
    finally:
        db.close()


@app.get("/azone/dashboard", tags=["System"])
async def dashboard():
    html_path = Path(__file__).parent / "app" / "templates" / "dashboard.html"
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))

@app.get("/azone/god", tags=["Admin"])
async def admin_console():
    html_path = Path(__file__).parent / "app" / "templates" / "admin.html"
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))
