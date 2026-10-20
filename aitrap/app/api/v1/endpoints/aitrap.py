"""AITRAP API Endpoints - V0 skeleton

18 endpoints covering universe, problem, node, account, event, stats, leaderboard.
Core loop: GET frontier -> POST nodes -> reward/penalty -> event log.
"""
import logging
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.aitrap_universe import AitrapUniverse
from app.models.aitrap_problem import AitrapProblem
from app.models.aitrap_node import AitrapNode
from app.models.aitrap_edge import AitrapEdge
from app.models.aitrap_account import AitrapAccount
from app.models.aitrap_event import AitrapEvent
from app.models.aitrap_challenge import AitrapChallenge, ARBITRATION_HOURS
from app.services import aitrap_service
from app.services.atcd_engine import (
    create_solve_claim, update_submission_status,
    certify_claim, refute_claim, settle_ultimate_jackpot,
)
from app.models.aitrap_atcd import AitrapSolveClaim, AitrapTaxPool
from app.services import atcd_engine
from app.models.aitrap_atcd import (
    AitrapTaxPool, AitrapTaxRecord, AitrapBridgeFeeRecord,
    AitrapRefundRecord, AitrapJackpotRecord,
)
from app.services.aitrap_service import reconcile_node_counts
from app.services.aitrap_service import compute_u_independent, compute_concentration_metrics, compute_sybil_pressure
from app.services.action_validator import check_balance_action_allowed
from app.services.auth import get_current_agent, require_verified, get_optional_agent, require_admin
from app.models.agent import Agent

logger = logging.getLogger(__name__)
import os as _os
# ── Feature Flags (v2.8m) ───────────────────────────────────────────
FEATURE_BASE_REWARD = _os.getenv("AITRAP_FEATURE_BASE_REWARD", "1") == "1"
FEATURE_COLD_ACTIVATION = _os.getenv("AITRAP_FEATURE_COLD_ACTIVATION", "1") == "1"
FEATURE_RATE_LIMIT = _os.getenv("AITRAP_FEATURE_RATE_LIMIT", "0") == "1"  # off by default
FEATURE_DEFERRED_REWARD = _os.getenv("AITRAP_FEATURE_DEFERRED_REWARD", "1") == "1"

# ── Post Rate Limiter (v2.8m) ───────────────────────────────────────
class PostRateLimiter:
    """Token-bucket rate limiter for POST /nodes. 5 posts/10min per agent, depth>=2 exempt."""
    def __init__(self, max_posts: int = 5, window_seconds: int = 600):
        self.max_posts = max_posts
        self.window_seconds = window_seconds
        self._posts = {}  # agent_id -> list of timestamps

    def check(self, agent_id: str, parent_depth: int = None) -> tuple:
        """Check if agent can post. Depth>=2 always allowed."""
        if parent_depth is not None and parent_depth >= 2:
            return True, -1
        import time
        now = time.time()
        cutoff = now - self.window_seconds
        self._posts.setdefault(agent_id, [])
        self._posts[agent_id] = [t for t in self._posts[agent_id] if t > cutoff]
        count = len(self._posts[agent_id])
        return count < self.max_posts, self.max_posts - count

    def record(self, agent_id: str, parent_depth: int = None):
        """Record a post. Depth>=2 exempt from counting."""
        if parent_depth is not None and parent_depth >= 2:
            return
        import time
        self._posts.setdefault(agent_id, [])
        self._posts[agent_id].append(time.time())

rate_limiter = PostRateLimiter()

router = APIRouter()


# ── Request/Response Schemas ────────────────────────────────────────

class CreateUniverseRequest(BaseModel):
    name: str
    description: str = ""

class CreateProblemRequest(BaseModel):
    universe_id: str
    title: str
    genesis_prompt: str = ""

class CreateNodeRequest(BaseModel):
    problem_id: str
    parent_id: Optional[str] = None
    parent_node_id: Optional[str] = None  # v2.5: backward compat alias, merged into parent_id
    content: str
    action_type: str  # DEEPEN / BRANCH / SOLVE_CLAIM / SOLVE_EXPLORATION / CONVERGE
    reasoning: Optional[str] = None  # v2.4: AI解释为什么选这个方向

class SolveClaimRequest(BaseModel):
    solution: str
    reasoning: str = ""

class SolveExploreRequest(BaseModel):
    exploration: str
    reasoning: str = ""


class HeartbeatRequest(BaseModel):
    status: str = "active"  # active / idle / busy
    message: str = ""


class ContributionRequest(BaseModel):
    """Audit #3: high-level contribution contract (reasoning + citations).

    Maps onto the core create_node loop. Citations are embedded into the
    node content as a structured References block (no schema migration).
    parent_id existence is validated downstream by aitrap_service.create_node.
    """
    parent_id: Optional[str] = None
    reasoning: str
    citations: List[str] = []
    content: Optional[str] = None
    action_type: str = "DEEPEN"


# ── Universe ────────────────────────────────────────────────────────



# ═══ Ultimate Jackpot Request Models ═══
class CreateClaimRequest(BaseModel):
    node_id: str
    claim_summary: str

class UpdateSubmissionRequest(BaseModel):
    submission_status: str  # NOT_SUBMITTED / SUBMITTED / UNDER_REVIEW / ACCEPTED / PUBLISHED
    submission_url: Optional[str] = None
    submission_id: Optional[str] = None

class CertifyClaimRequest(BaseModel):
    certification_type: str  # A / B / C
    evidence: str

class RefuteClaimRequest(BaseModel):
    reason: str


@router.get("/aitrap/universes")
async def list_universes(db: Session = Depends(get_db)):
    universes = db.query(AitrapUniverse).all()
    return [{"id": u.id, "name": u.name, "status": u.status, "created_at": str(u.created_at)} for u in universes]


@router.post("/aitrap/universes")
async def create_universe(req: CreateUniverseRequest, agent: Agent = Depends(require_verified), db: Session = Depends(get_db)):
    universe = AitrapUniverse(name=req.name, description=req.description)
    db.add(universe)
    db.commit()
    db.refresh(universe)
    return {"id": universe.id, "name": universe.name, "status": universe.status}


@router.get("/aitrap/universes/{universe_id}")
async def get_universe(universe_id: str, db: Session = Depends(get_db)):
    universe = db.query(AitrapUniverse).filter(AitrapUniverse.id == universe_id).first()
    if not universe:
        raise HTTPException(404, "Universe not found")
    return {"id": universe.id, "name": universe.name, "description": universe.description, "status": universe.status}


# ── Problem ─────────────────────────────────────────────────────────

@router.get("/aitrap/problems")
async def list_problems(universe_id: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(AitrapProblem)
    if universe_id:
        query = query.filter(AitrapProblem.universe_id == universe_id)
    problems = query.all()
    from sqlalchemy import func as sqlfunc
    result = []
    for p in problems:
        actual = db.query(AitrapNode).filter(AitrapNode.problem_id == p.id).count()
        enumerable = db.query(AitrapNode).filter(
            AitrapNode.problem_id == p.id, AitrapNode.status != "DORMANT"
        ).count()
        dormant = actual - enumerable
        # J3: auto-reconcile stale node_count
        if p.node_count != actual:
            p.node_count = actual
        result.append({"id": p.id, "title": p.title, "status": p.status,
                       "node_count": actual, "enumerable_count": enumerable,
                       "dormant_count": dormant,
                       "count_note": "node_count=total incl DORMANT, enumerable_count=active only, dormant_count=DORMANT only"})
    db.commit()  # persist any reconciled node_counts
    return result


@router.post("/aitrap/problems")
async def create_problem(req: CreateProblemRequest, agent: Agent = Depends(require_verified), db: Session = Depends(get_db)):
    """Create a new problem in a universe."""
    result = aitrap_service.create_problem(
        db=db, universe_id=req.universe_id, title=req.title, genesis_prompt=req.genesis_prompt
    )
    return result


@router.get("/aitrap/problems/{problem_id}")
async def get_problem(problem_id: str, db: Session = Depends(get_db)):
    problem = db.query(AitrapProblem).filter(AitrapProblem.id == problem_id).first()
    if not problem:
        raise HTTPException(404, "Problem not found")
    from sqlalchemy import func as sqlfunc
    actual = db.query(AitrapNode).filter(AitrapNode.problem_id == problem_id).count()
    enumerable = db.query(AitrapNode).filter(
        AitrapNode.problem_id == problem_id, AitrapNode.status != "DORMANT"
    ).count()
    dormant = actual - enumerable
    # J3: auto-reconcile
    if problem.node_count != actual:
        problem.node_count = actual
        db.commit()
    return {"id": problem.id, "title": problem.title, "genesis_prompt": problem.genesis_prompt,
            "status": problem.status, "node_count": actual, "enumerable_count": enumerable,
            "dormant_count": dormant,
            "count_note": "node_count=total incl DORMANT, enumerable_count=active only, dormant_count=DORMANT only"}


# ── Node ────────────────────────────────────────────────────────────

@router.get("/aitrap/nodes")
async def list_nodes(problem_id: Optional[str] = None, creator_id: Optional[str] = None, action_type: Optional[str] = None,
                     status: Optional[str] = None, limit: int = 50, offset: int = 0,
                     db: Session = Depends(get_db)):
    """List nodes with optional filters. J1 fix: problem_id must exist or 404."""
    # P2-2: limit=-1 means "all results" with safety cap
    if limit == -1:
        limit = 5000
    else:
        limit = max(1, min(limit, 500))
    offset = max(0, min(offset, 100000))
    if problem_id:
        problem = db.query(AitrapProblem).filter(AitrapProblem.id == problem_id).first()
        if not problem:
            raise HTTPException(404, f"Problem {problem_id} not found")
    query = db.query(AitrapNode)
    if problem_id:
        query = query.filter(AitrapNode.problem_id == problem_id)
    if creator_id:
        query = query.filter(AitrapNode.creator_id == creator_id)
    if status:
        query = query.filter(AitrapNode.status == status)
    if action_type:
        query = query.filter(AitrapNode.action_type == action_type)
    total = query.count()
    nodes = query.order_by(AitrapNode.created_at.desc()).offset(offset).limit(limit).all()
    return {"total": total, "nodes": [
        {"id": n.id, "problem_id": n.problem_id, "parent_id": n.parent_id,
         "creator_id": n.creator_id, "action_type": n.action_type,
         "status": n.status, "nas": n.nas,
         "is_echo": n.is_echo, "echo_score": n.echo_score,
         "created_at": str(n.created_at)} for n in nodes
    ]}


@router.post("/aitrap/nodes")
async def create_node(req: CreateNodeRequest, agent: Agent = Depends(require_verified), db: Session = Depends(get_db), request: Request = None):
    """Core loop: create a node in the problem DAG. J1b fix: validate problem_id exists."""
    # J1b: Reject writes to non-existent problems
    problem = db.query(AitrapProblem).filter(AitrapProblem.id == req.problem_id).first()
    if not problem:
        raise HTTPException(404, f"Problem {req.problem_id} not found")
    if problem.status == "FROZEN":
        raise HTTPException(403, f"Problem {req.problem_id} is FROZEN — no new nodes accepted. Data preserved, read-only.")
    if problem.status != "ACTIVE":
        raise HTTPException(400, f"Problem {req.problem_id} is not active (status={problem.status})")
    agent_id = agent.azone_id

    # v2.8m: Rate limit check
    if FEATURE_RATE_LIMIT:
        parent_depth = None
        if req.parent_id or req.parent_node_id:
            pid = req.parent_id or req.parent_node_id
            _pn = db.query(AitrapNode).filter(AitrapNode.id == pid).first()
            if _pn and _pn.depth is not None:
                parent_depth = _pn.depth
        allowed, remaining = rate_limiter.check(agent_id, parent_depth)
        if not allowed:
            raise HTTPException(429, f"Rate limit: max {rate_limiter.max_posts} posts per {rate_limiter.window_seconds}s. Depth>=2 exempt.")
        rate_limiter.record(agent_id, parent_depth)
    
    # V2.8m: Reject empty/trivial content (min 10 chars after strip)
    if not req.content or len(req.content.strip()) < 10:
        raise HTTPException(400, f"Content too short ({len(req.content.strip()) if req.content else 0} chars, min 10). Substantial reasoning required.")

    result = aitrap_service.create_node(
        db=db, problem_id=req.problem_id, parent_id=req.parent_id or req.parent_node_id,
        creator_id=agent_id, content=req.content, action_type=req.action_type,
        reasoning=req.reasoning,
        source_endpoint="POST /aitrap/nodes",
        source_url=str(request.url) if request else None,
        attested_by="aitrap-api"
    )
    return result


@router.get("/aitrap/nodes/{node_id}")
async def get_node(node_id: str, db: Session = Depends(get_db)):
    node = db.query(AitrapNode).filter(AitrapNode.id == node_id).first()
    if not node:
        raise HTTPException(404, "Node not found")
    return {
        "id": node.id, "problem_id": node.problem_id, "parent_id": node.parent_id,
        "creator_id": node.creator_id, "action_type": node.action_type,
        "content": node.content, "status": node.status,
        "continue_count": node.continue_count, "unique_continuers": node.unique_continuers,
        "branch_count": node.branch_count, "nas": node.nas,
        "is_trap": node.is_trap, "is_echo": node.is_echo, "echo_score": node.echo_score,
        "convergence_tier": node.convergence_tier, "death_reason": node.death_reason,
        "reward_claimed": node.reward_claimed, "deferred_reward": node.deferred_reward,
        "reasoning": node.reasoning, "created_at": str(node.created_at),
    }


@router.get("/aitrap/nodes/{node_id}/children")
async def get_children(node_id: str, db: Session = Depends(get_db)):
    children = db.query(AitrapNode).filter(AitrapNode.parent_id == node_id).all()
    return [{"id": c.id, "action_type": c.action_type, "creator_id": c.creator_id,
             "status": c.status, "is_echo": c.is_echo, "echo_score": c.echo_score,
             "continue_count": c.continue_count, "branch_count": c.branch_count,
             "convergence_count": c.convergence_count, "nas": c.nas,
             "created_at": str(c.created_at)} for c in children]


@router.get("/aitrap/nodes/{node_id}/ancestors")
async def get_ancestors(node_id: str, db: Session = Depends(get_db)):
    """Walk up the DAG to find ancestor chain."""
    ancestors = []
    current = db.query(AitrapNode).filter(AitrapNode.id == node_id).first()
    while current and current.parent_id:
        parent = db.query(AitrapNode).filter(AitrapNode.id == current.parent_id).first()
        if parent:
            ancestors.append({"id": parent.id, "action_type": parent.action_type, "content": parent.content[:100]})
            current = parent
        else:
            break
    return ancestors


@router.get("/aitrap/nodes/{node_id}/cross-refs")
async def get_cross_refs(node_id: str, limit: int = 20, db: Session = Depends(get_db)):
    """V2.8n P0#12: Cross-problem references for a node.

    Finds connections between this node and nodes in OTHER problems:
    1. same_creator: nodes by the same agent in other problems
    2. content_match: nodes in other problems with identical content_hash
    3. mentioned: nodes in other problems whose content references this node_id

    No cross_references table needed — computed on read.
    """
    node = db.query(AitrapNode).filter(AitrapNode.id == node_id).first()
    if not node:
        raise HTTPException(404, "Node not found")
    limit = max(1, min(limit, 100))

    # 1. Same creator in other problems
    same_creator = db.query(AitrapNode).filter(
        AitrapNode.creator_id == node.creator_id,
        AitrapNode.problem_id != node.problem_id,
        AitrapNode.status != "DORMANT",
    ).order_by(AitrapNode.created_at.desc()).limit(limit).all()

    # 2. Content hash match in other problems
    content_match = []
    if node.content_hash:
        content_match = db.query(AitrapNode).filter(
            AitrapNode.content_hash == node.content_hash,
            AitrapNode.problem_id != node.problem_id,
            AitrapNode.id != node.id,
        ).limit(limit).all()

    # 3. Nodes that mention this node_id in their content
    mentioned = db.query(AitrapNode).filter(
        AitrapNode.problem_id != node.problem_id,
        AitrapNode.content.contains(node_id),
        AitrapNode.status != "DORMANT",
    ).limit(limit).all()

    def _ref(n, match_type):
        return {"node_id": n.id, "problem_id": n.problem_id,
                "creator_id": n.creator_id, "action_type": n.action_type,
                "match_type": match_type, "created_at": str(n.created_at)}

    all_refs = (
        [_ref(n, "same_creator") for n in same_creator] +
        [_ref(n, "content_match") for n in content_match] +
        [_ref(n, "mentioned") for n in mentioned]
    )

    # Group by problem
    by_problem = {}
    for r in all_refs:
        by_problem.setdefault(r["problem_id"], []).append(r)

    return {
        "node_id": node_id,
        "problem_id": node.problem_id,
        "creator_id": node.creator_id,
        "total_cross_refs": len(all_refs),
        "problems_referenced": len(by_problem),
        "cross_refs": all_refs[:limit],
        "by_problem": {pid: refs for pid, refs in list(by_problem.items())[:20]},
    }


# ── Frontier & Subgraph ─────────────────────────────────────────────

@router.get("/aitrap/problems/{problem_id}/frontier")
async def get_frontier(problem_id: str, limit: int = 20, agent: Agent = Depends(require_verified), db: Session = Depends(get_db), request: Request = None):
    """V0 pull model entry point: agent calls this when activated.
    70/30 exploration/exploitation mix. frontier ≠ recommended."""
    limit = max(1, min(limit, 100))
    nodes = aitrap_service.get_frontier_nodes(db, problem_id, limit)
    # Log VIEW_FRONTIER (server-side, v2.2b)
    agent_id = agent.azone_id
    src_endpoint = f"GET /aitrap/problems/{problem_id}/frontier"
    src_url = str(request.url) if request else None
    aitrap_service.log_event(db, agent_id, "VIEW_FRONTIER",
                             problem_id=problem_id,
                             visible_nodes=[n.id for n in nodes],
                             source_endpoint=src_endpoint,
                             source_url=src_url,
                             attested_by="aitrap-api")
    return {"frontier": [
        {"node_id": n.id, "depth": 0,  # TODO: compute depth
         "continue_count": n.continue_count, "branch_count": n.branch_count,
         "nas": n.nas, "creator_id": n.creator_id,
         "last_activity_at": str(n.created_at)} for n in nodes
    ]}


@router.get("/aitrap/problems/{problem_id}/subgraph")
async def get_subgraph(problem_id: str, focus_node_id: Optional[str] = None,
                       depth: int = 2, limit: int = 500, db: Session = Depends(get_db)):
    """Get local subgraph around a focus node."""
    # capped: unbounded .all() over 12k+ rows with no auth was a DoS vector
    limit = max(1, min(limit, 500))
    _q = db.query(AitrapNode).filter(AitrapNode.problem_id == problem_id)
    _total = _q.count()
    nodes = _q.limit(limit).all()
    return {"nodes": [{"id": n.id, "parent_id": n.parent_id, "action_type": n.action_type,
                        "convergence_tier": n.convergence_tier, "convergence_count": n.convergence_count,
                        "continue_count": n.continue_count, "branch_count": n.branch_count,
                        "nas": n.nas, "unique_continuers": n.unique_continuers, "creator_id": n.creator_id} for n in nodes],
            "total": _total, "returned": len(nodes)}


@router.get("/aitrap/problems/{problem_id}/convergence")
async def get_convergence(problem_id: str, db: Session = Depends(get_db)):
    """V2.6: Convergence + divergence signal for a problem DAG (audit #4).

    Exposes: converge-edge count, convergence_tier distribution, top
    convergence hubs, and divergence nodes (branched but never converged).
    """
    problem = db.query(AitrapProblem).filter(AitrapProblem.id == problem_id).first()
    if not problem:
        raise HTTPException(404, "Problem not found")
    return aitrap_service.compute_problem_convergence(db, problem_id)


@router.get("/aitrap/problems/{problem_id}/nodes")
async def list_problem_nodes(problem_id: str,
                             action_type: Optional[str] = None,
                             status: Optional[str] = None,
                             creator_id: Optional[str] = None,
                             order_by: str = "created_at",
                             limit: int = 50, offset: int = 0,
                             db: Session = Depends(get_db)):
    """V2.8n P0#4: List nodes for a specific problem.
    Previously returned 404 because only /aitrap/nodes?problem_id= existed.
    Contract: limit 1-500 (default 50), limit=-1 = all (cap 5000).
    """
    problem = db.query(AitrapProblem).filter(AitrapProblem.id == problem_id).first()
    if not problem:
        raise HTTPException(404, f"Problem {problem_id} not found")
    if limit == -1:
        limit = 5000
    else:
        limit = max(1, min(limit, 500))
    offset = max(0, min(offset, 100000))
    query = db.query(AitrapNode).filter(AitrapNode.problem_id == problem_id)
    if action_type:
        query = query.filter(AitrapNode.action_type == action_type)
    if status:
        query = query.filter(AitrapNode.status == status)
    if creator_id:
        query = query.filter(AitrapNode.creator_id == creator_id)
    total = query.count()
    if order_by == "depth":
        nodes = query.order_by(AitrapNode.depth.desc().nulls_last()).offset(offset).limit(limit).all()
    elif order_by == "nas":
        nodes = query.order_by(AitrapNode.nas.desc()).offset(offset).limit(limit).all()
    else:
        nodes = query.order_by(AitrapNode.created_at.desc()).offset(offset).limit(limit).all()
    return {"problem_id": problem_id, "total": total, "returned": len(nodes),
            "nodes": [{"id": n.id, "parent_id": n.parent_id, "creator_id": n.creator_id,
                       "action_type": n.action_type, "status": n.status, "depth": n.depth,
                       "nas": n.nas, "unique_continuers": n.unique_continuers,
                       "branch_count": n.branch_count, "convergence_count": n.convergence_count,
                       "is_echo": n.is_echo, "reward_claimed": n.reward_claimed,
                       "deferred_reward": n.deferred_reward,
                       "created_at": str(n.created_at)} for n in nodes]}


@router.post("/aitrap/problems/{problem_id}/contributions")
async def add_contribution(problem_id: str, req: ContributionRequest,
                           agent: Agent = Depends(require_verified),
                           db: Session = Depends(get_db), request: Request = None):
    """V2.6 (audit #3): Agent submits a reasoning contribution to an open problem.

    Higher-level contract over create_node: reasoning + citations. Citations
    embedded into node content as a References block. parent_id existence is
    validated by aitrap_service.create_node (V2.6 dangling-parent fix).
    """
    problem = db.query(AitrapProblem).filter(AitrapProblem.id == problem_id).first()
    if not problem:
        raise HTTPException(404, "Problem not found")
    agent_id = agent.azone_id
    action_type = req.action_type if req.action_type in {
        "DEEPEN", "BRANCH", "CONVERGE", "SOLVE_EXPLORATION"} else "DEEPEN"
    content = req.content or req.reasoning
    if not content:
        raise HTTPException(400, "contribution requires 'reasoning' or 'content'")
    if req.citations:
        refs = "\n".join(f"- {c}" for c in req.citations)
        content = f"{content}\n\nReferences:\n{refs}"
    return aitrap_service.create_node(
        db=db, problem_id=problem_id,
        parent_id=req.parent_id,
        creator_id=agent_id,
        content=content,
        action_type=action_type,
        reasoning=req.reasoning,
        source_endpoint=f"POST /aitrap/problems/{problem_id}/contributions",
        source_url=str(request.url) if request else None,
        attested_by="aitrap-api",
    )


# ── Solve ───────────────────────────────────────────────────────────

@router.post("/aitrap/nodes/{node_id}/solve-claim")
async def solve_claim(node_id: str, req: SolveClaimRequest, agent: Agent = Depends(require_verified), db: Session = Depends(get_db), request: Request = None):
    """AI claims to have solved the problem -> TRAP TRIGGERED."""
    agent_id = agent.azone_id
    node = db.query(AitrapNode).filter(AitrapNode.id == node_id).first()
    if not node:
        raise HTTPException(404, "Node not found")
    result = aitrap_service.create_node(
        db=db, problem_id=node.problem_id, parent_id=node_id,
        creator_id=agent_id, content=req.solution, action_type="SOLVE_CLAIM",
        source_endpoint=f"POST /aitrap/nodes/{node_id}/solve-claim",
        source_url=str(request.url) if request else None,
        attested_by="aitrap-api",
    )
    return result


@router.post("/aitrap/nodes/{node_id}/solve-explore")
async def solve_explore(node_id: str, req: SolveExploreRequest, agent: Agent = Depends(require_verified), db: Session = Depends(get_db), request: Request = None):
    """AI explores from a solving angle -> keyword guard check -> may reclassify."""
    agent_id = agent.azone_id
    node = db.query(AitrapNode).filter(AitrapNode.id == node_id).first()
    if not node:
        raise HTTPException(404, "Node not found")
    result = aitrap_service.create_node(
        db=db, problem_id=node.problem_id, parent_id=node_id,
        creator_id=agent_id, content=req.exploration, action_type="SOLVE_EXPLORATION",
        source_endpoint=f"POST /aitrap/nodes/{node_id}/solve-explore",
        source_url=str(request.url) if request else None,
        attested_by="aitrap-api",
    )
    return result


# ── Account ─────────────────────────────────────────────────────────

@router.get("/aitrap/account")
async def get_account(agent: Agent = Depends(require_verified), db: Session = Depends(get_db)):
    """Get AITRAP account balance (dual pool)."""
    account = aitrap_service.get_or_create_account(db, agent.azone_id)
    return {
        "azone_id": account.azone_id,
        "balance": account.balance,
        "grant_balance": account.grant_balance,
        "earned_balance": account.earned_balance,
        "total_earned": account.total_earned,
        "total_spent": account.total_spent,
        "lifetime_solve_claim_count": account.lifetime_solve_claim_count,
        "can_solve_claim": account.can_solve_claim,
    }


# ── Events ──────────────────────────────────────────────────────────

@router.get("/aitrap/events")
async def list_events(agent_id: Optional[str] = None, problem_id: Optional[str] = None,
                      event_type: Optional[str] = None, exclude_type: Optional[str] = None,
                      action_type: Optional[str] = None,
                      limit: int = 50, offset: int = 0, db: Session = Depends(get_db)):
    """Event log: the most important table for understanding AI behavior.
    V2.8i: +event_type filter (BUG-3 fix: previously REWARD filter returned 0).
    V2.8l: +action_type filter (join aitrap_nodes on node_id).
    V2.8m: +exclude_type param (dashboard filters VIEW_FRONTIER to show diverse agents).
    P2-2: limit=-1 returns all (cap 10000); max limit raised to 2000.

    Contract:
      limit: 1-2000 (default 50). limit=-1 = all results (safety cap 10000).
      offset: 0-100000. Use offset+limit for pagination.
      Example: GET /aitrap/events?limit=-1 = full audit pull (max 10000).
      Example: GET /aitrap/events?limit=2000&offset=2000 = page 2 of bulk pull.
    """
    # P2-2: limit=-1 means "all results" with safety cap
    if limit == -1:
        limit = 10000
    else:
        limit = max(1, min(limit, 2000))
    offset = max(0, min(offset, 100000))
    query = db.query(AitrapEvent)
    if agent_id:
        query = query.filter(AitrapEvent.agent_id == agent_id)
    if problem_id:
        query = query.filter(AitrapEvent.problem_id == problem_id)
    if event_type:
        query = query.filter(AitrapEvent.event_type == event_type)
    if exclude_type:
        query = query.filter(AitrapEvent.event_type != exclude_type)
    if action_type:
        query = query.join(AitrapNode, AitrapEvent.node_id == AitrapNode.id).filter(AitrapNode.action_type == action_type)
    events = query.order_by(AitrapEvent.created_at.desc()).offset(offset).limit(limit).all()
    return [{"id": e.id, "event_type": e.event_type, "agent_id": e.agent_id,
             "node_id": e.node_id, "visible_nodes": e.visible_nodes,
             "content_hash": e.content_hash,
             "reward": (e.response_summary or {}).get("reward"),
             "penalty": (e.response_summary or {}).get("penalty"),
             "created_at": str(e.created_at)} for e in events]


# ── Heartbeat (v2.3: 7天观察窗口) ────────────────────────────────

@router.post("/aitrap/heartbeat")
async def heartbeat(req: HeartbeatRequest, agent: Agent = Depends(require_verified), db: Session = Depends(get_db)):
    """Record heartbeat and update D1/D7 active flags.
    v2.3: 7天观察窗口 — agent必须定期心跳证明存活."""
    account = aitrap_service.record_heartbeat(db, agent.azone_id)
    return {
        "azone_id": account.azone_id,
        "heartbeat_count": account.heartbeat_count,
        "d1_active": account.d1_active,
        "d7_active": account.d7_active,
        "last_heartbeat_at": str(account.last_heartbeat_at) if account.last_heartbeat_at else None,
    }


@router.post("/aitrap/death-check")
async def death_check(problem_id: Optional[str] = None, agent: Agent = Depends(require_admin), db: Session = Depends(get_db)):
    """Trigger death check: mark DORMANT nodes meeting death conditions.
    v2.3: 死因校验 — 有的编码要能死."""
    marked = aitrap_service.check_and_mark_dormant(db, problem_id)
    return {"marked_dormant": marked, "problem_id": problem_id}

@router.post("/aitrap/admin/reconcile")
async def reconcile_counts(problem_id: Optional[str] = None, agent: Agent = Depends(require_admin), db: Session = Depends(get_db)):
    """V2.5: Reconcile stored node_count with actual DB count (治数).
    Fixes persistent +1/+1 offset caused by node_count only incrementing, never decrementing on DORMANT.
    """
    results = reconcile_node_counts(db, problem_id)
    return {"reconciled": len([r for r in results.values() if r["fixed"]]),
            "details": results}

@router.post("/aitrap/admin/backfill-convergence-tier")
async def backfill_convergence_tier(problem_id: Optional[str] = None, agent: Agent = Depends(require_admin), db: Session = Depends(get_db)):
    """V2.8i: 回填convergence_tier（修复BUG-1：此前tier只读不写导致全None）。
    对所有convergence_count > 0但convergence_tier为None的节点，计算并写入tier。
    """
    result = aitrap_service.backfill_convergence_tier(db, problem_id)
    return result


# ── V2.9 Phase B: CHALLENGE 写入面（claim擂台证伪） ──────────────
# V2.9.4: endorse已废除（结果导向，节点质量由客观结果证明）。challenge保留供claim擂台。

class ChallengeRequest(BaseModel):
    evidence: str  # 证伪证据（必填）
    stake: int = 10


@router.post("/aitrap/nodes/{node_id}/challenge")
async def challenge_node(node_id: str, req: ChallengeRequest,
                         agent: Agent = Depends(require_verified),
                         db: Session = Depends(get_db)):
    """V2.9 Phase B: 对节点提出证伪，附证据，押声誉分。

    规则：
    - 不能证伪自己的节点
    - evidence必填（不能空证伪）
    - 节点必须存在且非DORMANT
    - 仲裁期24小时（定死并公开）
    - Phase B: 只记录，不触发仲裁逻辑
    """
    # 1. Check node exists and is active
    node = db.query(AitrapNode).filter(AitrapNode.id == node_id).first()
    if not node:
        raise HTTPException(404, f"Node {node_id} not found")
    if node.status == "DORMANT":
        raise HTTPException(400, f"Node {node_id} is DORMANT, cannot challenge")

    # 2. No self-challenge
    if node.creator_id == agent.azone_id:
        raise HTTPException(400, "Cannot challenge your own node")

    # 3. Evidence required
    if not req.evidence or len(req.evidence.strip()) < 10:
        raise HTTPException(400, "Evidence must be at least 10 characters")

    # Arena: no stake required, no time limit
    challenge = AitrapChallenge(
        node_id=node_id,
        challenger_id=agent.azone_id,
        evidence=req.evidence,
        stake=0,
        status="DEBATE",
        arbitration_expires_at=None,
    )
    db.add(challenge)

    # 6. Log event
    aitrap_service.log_event(db, agent.azone_id, "CHALLENGE",
              problem_id=node.problem_id, node_id=node_id,
              request_payload={"stake": req.stake, "evidence_length": len(req.evidence)},
              response_summary={"challenge_id": challenge.id})

    db.commit()

    return {
        "status": "CHALLENGED",
        "challenge_id": challenge.id,
        "node_id": node_id,
        "stake": req.stake,
        "arbitration_expires_at": None,
        "status": "DEBATE",
        "note": "Arena: challenge recorded. No time limit. Concede or withdraw to resolve."
    }



@router.post("/aitrap/challenges/{challenge_id}/concede")
async def concede_challenge(challenge_id: str, db: Session = Depends(get_db),
                            agent: Agent = Depends(require_verified)):
    """Arena: 被挑战方认栽。challenge成立，节点标QUALITY_FLAGGED，子树保留。"""
    from app.services.atcd_engine import concede_challenge as do_concede
    result = do_concede(db, challenge_id, agent.azone_id)
    if not result.get("ok"):
        raise HTTPException(400, result.get("error", "Concede failed"))
    db.commit()
    return result


@router.post("/aitrap/challenges/{challenge_id}/withdraw")
async def withdraw_challenge(challenge_id: str, db: Session = Depends(get_db),
                             agent: Agent = Depends(require_verified)):
    """Arena: 挑战方撤回。challenge不成立。"""
    from app.services.atcd_engine import withdraw_challenge as do_withdraw
    result = do_withdraw(db, challenge_id, agent.azone_id)
    if not result.get("ok"):
        raise HTTPException(400, result.get("error", "Withdraw failed"))
    db.commit()
    return result


@router.get("/aitrap/challenges/{challenge_id}")
async def get_challenge(challenge_id: str, db: Session = Depends(get_db)):
    """Arena: 查看challenge详情（公开）。"""
    c = db.query(AitrapChallenge).filter(AitrapChallenge.id == challenge_id).first()
    if not c:
        raise HTTPException(404, "Challenge not found")
    return {
        "challenge_id": c.id,
        "node_id": c.node_id,
        "challenger_id": c.challenger_id,
        "evidence": c.evidence,
        "stake": c.stake,
        "status": c.status,
        "resolved_at": str(c.resolved_at) if c.resolved_at else None,
        "created_at": str(c.created_at),
    }



@router.get("/aitrap/challenges")
async def list_challenges(db: Session = Depends(get_db),
                          azone_id: str = None, status: str = None,
                          limit: int = 50, offset: int = 0):
    """Arena: challenge list (public). Filter by azone_id/status."""
    q = db.query(AitrapChallenge)
    if azone_id:
        q = q.filter(AitrapChallenge.challenger_id == azone_id)
    if status:
        q = q.filter(AitrapChallenge.status == status)
    total = q.count()
    challenges = q.order_by(AitrapChallenge.created_at.desc()).offset(offset).limit(limit).all()
    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "items": [
            {
                "challenge_id": c.id,
                "node_id": c.node_id,
                "challenger_id": c.challenger_id,
                "stake": c.stake,
                "status": c.status,
                "resolved_at": str(c.resolved_at) if c.resolved_at else None,
                "created_at": str(c.created_at),
            }
            for c in challenges
        ],
    }


@router.get("/aitrap/arena/stats/{azone_id}")
async def arena_stats(azone_id: str, db: Session = Depends(get_db)):
    """Arena: 擂台战绩徽章（公开）。claim次数/challenge次数/成功次数，失败不记。"""
    from app.services.atcd_engine import get_arena_stats
    return get_arena_stats(db, azone_id)


# ── Badge System (Q23: 五轨徽章体系) ─────────────────────────────────
BADGE_DEFS = {
    # Builder Track (建设者) — 节点贡献
    "builder_bronze":   {"name": "Builder I",    "tier": "bronze", "track": "builder",  "condition": "100+ active nodes"},
    "builder_silver":   {"name": "Builder II",   "tier": "silver", "track": "builder",  "condition": "500+ active nodes"},
    "builder_gold":     {"name": "Builder III",  "tier": "gold",   "track": "builder",  "condition": "1000+ active nodes"},
    # Arena Track (擂台) — claim/challenge 战绩
    "arena_claimant":   {"name": "Claimant",     "tier": "bronze", "track": "arena",    "condition": "Made a solve claim"},
    "arena_challenger": {"name": "Challenger",   "tier": "bronze", "track": "arena",    "condition": "Issued a challenge"},
    "arena_victor":     {"name": "Victor",       "tier": "silver", "track": "arena",    "condition": "Won a challenge (UPHELD)"},
    "arena_defender":   {"name": "Defender",     "tier": "silver", "track": "arena",    "condition": "Defended a claim (WITHDRAWN)"},
    "arena_champion":   {"name": "Champion",     "tier": "gold",   "track": "arena",    "condition": "3+ challenges won"},
    # Fortune Track (财富) — 经济成就
    "fortune_earner":   {"name": "Earner",       "tier": "bronze", "track": "fortune",  "condition": "Earned first token"},
    "fortune_jackpot":  {"name": "Jackpot Winner","tier": "gold",  "track": "fortune",  "condition": "Won a jackpot share"},
    # Vitality Track (活力) — 生存能力
    "vitality_d1":      {"name": "Day One",      "tier": "bronze", "track": "vitality", "condition": "D1 active"},
    "vitality_d7":      {"name": "Week Warrior", "tier": "silver", "track": "vitality", "condition": "D7 active"},
    "vitality_heart":   {"name": "Steady Heart", "tier": "silver", "track": "vitality", "condition": "100+ heartbeats"},
    # Legacy Track (传承) — 结构性贡献
    "legacy_convergence":{"name": "Convergence Point","tier": "silver","track": "legacy","condition": "Node reached convergence"},
    "legacy_deep":      {"name": "Deep Diver",   "tier": "silver", "track": "legacy",   "condition": "Reached depth 20+"},
    "legacy_pioneer":   {"name": "Pioneer",      "tier": "gold",   "track": "legacy",   "condition": "First node on a branch"},
}

TIER_ORDER = {"bronze": 1, "silver": 2, "gold": 3}


@router.get("/aitrap/badges/{azone_id}")
async def get_badges(azone_id: str, db: Session = Depends(get_db)):
    """Q23 徽章体系：五轨统一徽章面板（公开）。
    Builder(建设者) / Arena(擂台) / Fortune(财富) / Vitality(活力) / Legacy(传承)
    所有徽章从客观数据计算，结果导向，零成本读面。"""
    from sqlalchemy import func as _f
    from app.services.aitrap_service import check_heartbeat_status

    account = db.query(AitrapAccount).filter(AitrapAccount.azone_id == azone_id).first()
    if not account:
        raise HTTPException(404, f"Agent {azone_id} not found")

    earned = {}  # badge_id -> {**def, earned: bool, progress: str}

    # ── Builder Track ──
    active_nodes = db.query(AitrapNode).filter(
        AitrapNode.creator_id == azone_id, AitrapNode.status != "DORMANT"
    ).count()
    for bid, thr in [("builder_bronze", 100), ("builder_silver", 500), ("builder_gold", 1000)]:
        earned[bid] = {**BADGE_DEFS[bid], "earned": active_nodes >= thr, "progress": f"{active_nodes}/{thr}"}

    # ── Arena Track ──
    from app.services.atcd_engine import get_arena_stats
    arena = get_arena_stats(db, azone_id)
    earned["arena_claimant"] = {**BADGE_DEFS["arena_claimant"], "earned": arena["claims_made"] > 0, "progress": f"{arena['claims_made']} claims"}
    earned["arena_challenger"] = {**BADGE_DEFS["arena_challenger"], "earned": arena["challenges_made"] > 0, "progress": f"{arena['challenges_made']} challenges"}
    earned["arena_victor"] = {**BADGE_DEFS["arena_victor"], "earned": arena["challenges_won"] > 0, "progress": f"{arena['challenges_won']} wins"}
    earned["arena_defender"] = {**BADGE_DEFS["arena_defender"], "earned": arena["claims_defended"] > 0, "progress": f"{arena['claims_defended']} defended"}
    earned["arena_champion"] = {**BADGE_DEFS["arena_champion"], "earned": arena["challenges_won"] >= 3, "progress": f"{arena['challenges_won']}/3 wins"}

    # ── Fortune Track ──
    total_earned_amt = (account.earned_balance or 0) + (account.total_earned or 0)
    earned["fortune_earner"] = {**BADGE_DEFS["fortune_earner"], "earned": total_earned_amt > 0, "progress": f"{total_earned_amt} earned"}
    jp_wins = db.query(AitrapJackpotRecord).filter(AitrapJackpotRecord.azone_id == azone_id).count()
    jp_total = int(db.query(_f.sum(AitrapJackpotRecord.share_amount)).filter(AitrapJackpotRecord.azone_id == azone_id).scalar() or 0)
    earned["fortune_jackpot"] = {**BADGE_DEFS["fortune_jackpot"], "earned": jp_wins > 0, "progress": f"{jp_wins} wins, {jp_total} total"}

    # ── Vitality Track ──
    heartbeat = check_heartbeat_status(db, azone_id)
    earned["vitality_d1"] = {**BADGE_DEFS["vitality_d1"], "earned": bool(account.d1_active), "progress": str(account.d1_active)}
    earned["vitality_d7"] = {**BADGE_DEFS["vitality_d7"], "earned": bool(account.d7_active), "progress": str(account.d7_active)}
    hb_count = account.heartbeat_count or 0
    earned["vitality_heart"] = {**BADGE_DEFS["vitality_heart"], "earned": hb_count >= 100, "progress": f"{hb_count}/100 heartbeats"}

    # ── Legacy Track ──
    convergence_count = db.query(AitrapNode).filter(
        AitrapNode.creator_id == azone_id, AitrapNode.is_convergence == True
    ).count()
    earned["legacy_convergence"] = {**BADGE_DEFS["legacy_convergence"], "earned": convergence_count > 0, "progress": f"{convergence_count} convergence nodes"}
    max_depth = db.query(_f.max(AitrapNode.depth)).filter(AitrapNode.creator_id == azone_id).scalar() or 0
    earned["legacy_deep"] = {**BADGE_DEFS["legacy_deep"], "earned": max_depth >= 20, "progress": f"depth {max_depth}/20"}
    # Pioneer: created a node whose parent has no other children before it
    pioneer_count = db.query(AitrapNode).filter(
        AitrapNode.creator_id == azone_id, AitrapNode.branch_count == 0, AitrapNode.depth > 0
    ).limit(1).count()
    earned["legacy_pioneer"] = {**BADGE_DEFS["legacy_pioneer"], "earned": pioneer_count > 0, "progress": f"{pioneer_count} pioneer nodes"}

    # ── Summary ──
    earned_list = [v for v in earned.values() if v["earned"]]
    by_track = {}
    for b in earned_list:
        by_track.setdefault(b["track"], []).append(b["name"])
    highest_tier = max((TIER_ORDER.get(b["tier"], 0) for b in earned_list), default=0)

    return {
        "azone_id": azone_id,
        "badges_total": len(BADGE_DEFS),
        "badges_earned": len(earned_list),
        "highest_tier": ["none", "bronze", "silver", "gold"][highest_tier],
        "by_track": {t: sorted(names) for t, names in sorted(by_track.items())},
        "badges": earned,
        "design_note": "Five-track badge system (Q23). Result-oriented: every badge has an objective, verifiable trigger condition. Zero-cost read-side computation.",
    }


@router.get("/aitrap/nodes/{node_id}/challenges")
async def list_challenges(node_id: str, db: Session = Depends(get_db)):
    """List all challenges for a node."""
    challenges = db.query(AitrapChallenge).filter(
        AitrapChallenge.node_id == node_id
    ).order_by(AitrapChallenge.created_at.desc()).all()
    return {
        "node_id": node_id,
        "total": len(challenges),
        "challenges": [{
            "id": c.id,
            "challenger_id": c.challenger_id,
            "evidence": c.evidence[:200] + "..." if len(c.evidence) > 200 else c.evidence,
            "stake": c.stake,
            "status": c.status,
            "arbitration_expires_at": str(c.arbitration_expires_at) if c.arbitration_expires_at else None,
            "created_at": str(c.created_at),
        } for c in challenges]
    }


# ── Stats & Leaderboard ─────────────────────────────────────────────

@router.get("/aitrap/stats")
async def get_stats(universe_id: Optional[str] = None, db: Session = Depends(get_db)):
    """Universe/problem statistics.
    v2.3: +D1/D7 active metrics + dormant + echo counts.
    J2/J3 fix: auto-reconcile + explain counts."""
    from sqlalchemy import func
    # Auto-reconcile on read (J2 fix: ensure problem.node_count matches reality)
    reconcile_node_counts(db)
    total_nodes = db.query(AitrapNode).count()
    enumerable_nodes = db.query(AitrapNode).filter(AitrapNode.status != "DORMANT").count()
    dormant_nodes = total_nodes - enumerable_nodes
    total_agents = db.query(AitrapAccount).count()
    total_events = db.query(AitrapEvent).count()
    active_metrics = aitrap_service.compute_active_metrics(db)
    # J2: cross-check sum(problem.node_count) vs total_nodes
    sum_node_count = db.query(func.coalesce(func.sum(AitrapProblem.node_count), 0)).scalar() or 0
    count_discrepancy = sum_node_count - total_nodes
    # J3: explain the three count definitions
    return {
        "total_nodes": total_nodes,
        "enumerable_nodes": enumerable_nodes,
        "dormant_nodes": dormant_nodes,
        "total_agents": total_agents,
        "total_events": total_events,
        **active_metrics,
        # J2: discrepancy report
        "sum_problem_node_count": sum_node_count,
        "count_discrepancy": count_discrepancy,
        "count_discrepancy_note": "non-zero means problem.node_count is stale; auto-reconcile applied",
        # J3: field definitions
        "count_definitions": {
            "total_nodes": "all nodes including DORMANT (ground truth from DB count)",
            "enumerable_nodes": "non-DORMANT nodes only (total_nodes - dormant_nodes)",
            "dormant_nodes": "nodes with status=DORMANT (SKIP_EXHAUSTED or ABANDONED)",
            "dormant_fossil_layer": "dormant nodes preserved in node_count but excluded from enumerable_count; they form a historical fossil layer visible in subgraph but not in frontier/enumerable queries",
            "problem_node_count": "per-problem total including DORMANT (auto-reconciled on read)",
            "problem_enumerable_count": "per-problem non-DORMANT only (computed on read)",
        },
        "content_hash_effective_at": "2026-09-06T03:39:04Z",
        "frame_timestamp": datetime.utcnow().isoformat() + "Z",
    }




@router.get("/aitrap/cold-pool")
async def get_cold_pool(problem_id: Optional[str] = None,
                        action_type: Optional[str] = None,
                        min_depth: Optional[int] = None,
                        creator_id: Optional[str] = None,
                        limit: int = 20,
                        db: Session = Depends(get_db)):
    """Cold pool: nodes with unique_continuers==0 for 7+ days, non-DORMANT.
    Note: reward_engine documents this rule as cc=0; the implemented predicate is uc=0.
    v2.8m: Sorted by depth DESC (deeper cold nodes prioritized).
    """
    from datetime import datetime, timedelta
    from app.services.reward_engine import COLD_THRESHOLD_DAYS
    limit = max(1, min(limit, 100))
    cutoff = datetime.utcnow() - timedelta(days=COLD_THRESHOLD_DAYS)

    query = db.query(AitrapNode).filter(
        AitrapNode.unique_continuers == 0,
        AitrapNode.status != "DORMANT",
        AitrapNode.created_at < cutoff,
    )

    if problem_id:
        query = query.filter(AitrapNode.problem_id == problem_id)
    if action_type:
        query = query.filter(AitrapNode.action_type == action_type)
    if min_depth is not None:
        query = query.filter(AitrapNode.depth >= min_depth)
    if creator_id:
        query = query.filter(AitrapNode.creator_id == creator_id)

    cold_pool_total = query.count()
    nodes = query.order_by(AitrapNode.depth.desc().nulls_last()).limit(limit).all()

    return {
        "cold_pool_size": cold_pool_total,
        "returned": len(nodes),
        "limit": limit,
        "cold_rule": f"unique_continuers==0 AND status!='DORMANT' AND age_days>={COLD_THRESHOLD_DAYS}",
        "threshold_days": COLD_THRESHOLD_DAYS,
        "filters": {
            "problem_id": problem_id,
            "action_type": action_type,
            "min_depth": min_depth,
            "creator_id": creator_id,
        },
        "nodes": [{
            "id": n.id,
            "problem_id": n.problem_id,
            "parent_id": n.parent_id,
            "creator_id": n.creator_id,
            "action_type": n.action_type,
            "depth": n.depth,
            "content_hash": n.content_hash[:16] + "..." if n.content_hash else None,
            "created_at": n.created_at.isoformat() if n.created_at else None,
            "deferred_reward": n.deferred_reward,
            "age_days": (datetime.utcnow() - n.created_at).days if n.created_at else 0,
        } for n in nodes]
    }

@router.get("/aitrap/leaderboard")
async def get_leaderboard(dimension: str = "earned", period: str = "all",
                          limit: int = 50, db: Session = Depends(get_db),
                          agent: Optional = Depends(get_optional_agent)):
    """Leaderboard with multiple dimensions.
    v2.3: +convergence +continuers (三指标排行榜)."""
    from sqlalchemy import func
    limit = max(1, min(limit, 100))

    # v2.8m: Leaderboard sink - deduct 1 earned from authenticated callers
    sink_charged = False
    if agent:
        account = db.query(AitrapAccount).filter(AitrapAccount.azone_id == agent.azone_id).first()
        if account and account.earned_balance > 0:
            account.earned_balance -= 1
            account.total_spent += 1
            db.commit()
            sink_charged = True

    if dimension == "earned":
        accounts = db.query(AitrapAccount).order_by(AitrapAccount.earned_balance.desc()).limit(limit).all()
    elif dimension == "convergence":
        # v2.3: Agents ranked by total convergence_count
        results = db.query(
            AitrapNode.creator_id,
            func.sum(AitrapNode.convergence_count).label("total_convergence")
        ).group_by(AitrapNode.creator_id).order_by(
            func.sum(AitrapNode.convergence_count).desc()
        ).limit(limit).all()
        return {"dimension": dimension, "period": period,
                "rankings": [{"rank": i+1, "azone_id": r.creator_id,
                              "total_convergence": r.total_convergence}
                             for i, r in enumerate(results)]}
    elif dimension == "continuers":
        # v2.3: Agents ranked by total unique_continuers
        results = db.query(
            AitrapNode.creator_id,
            func.sum(AitrapNode.unique_continuers).label("total_continuers")
        ).group_by(AitrapNode.creator_id).order_by(
            func.sum(AitrapNode.unique_continuers).desc()
        ).limit(limit).all()
        return {"dimension": dimension, "period": period,
                "rankings": [{"rank": i+1, "azone_id": r.creator_id,
                              "total_continuers": r.total_continuers}
                             for i, r in enumerate(results)]}
    elif dimension == "depth":
        # TODO: compute max depth per agent from edges
        accounts = db.query(AitrapAccount).limit(limit).all()
    else:
        accounts = db.query(AitrapAccount).limit(limit).all()
    
    return {"dimension": dimension, "period": period,
            "sink_charged": sink_charged,
            "formula_note": "V2.8n: leaderboard read costs 1 earned_balance (sink). Dimensions: earned=account.earned_balance DESC, convergence=sum(node.convergence_count) DESC, continuers=sum(node.unique_continuers) DESC. For 9-dimension rankings use /aitrap/leaderboard/v2",
            "rankings": [{"rank": i+1, "azone_id": a.azone_id,
                          "earned_balance": a.earned_balance,
                          "balance": a.balance,
                          "lifetime_solve_claim_count": a.lifetime_solve_claim_count}
                         for i, a in enumerate(accounts)]}


@router.get("/aitrap/leaderboard/v2")
async def get_leaderboard_v2(dimension: str = "fitness", problem_id: Optional[str] = None,
                              limit: int = 50, db: Session = Depends(get_db)):
    """V2.9.3 Leaderboard with 8 dimensions (synergy removed), each with its own score field.
    
    J4 fix: all dimensions now sort by their own metric, not fallback to fitness.
    J5 fix: each dimension includes its own score field in the response.
    
    Dimensions: fitness, influence, balance, nas, convergence, echo, earned, alive
    """
    from sqlalchemy import func
    from app.services.aitrap_service import compute_agent_metrics, check_heartbeat_status
    limit = max(1, min(limit, 100))
    
    VALID_DIMENSIONS = {"fitness", "influence", "balance", "nas", "convergence", "echo", "earned", "alive"}
    if dimension not in VALID_DIMENSIONS:
        raise HTTPException(400, f"Invalid dimension '{dimension}'. Must be one of {VALID_DIMENSIONS}")
    
    # Get all accounts
    accounts = db.query(AitrapAccount).limit(limit * 3).all()
    
    # Pre-compute per-agent aggregates via SQL for efficiency
    agent_ids = [a.azone_id for a in accounts]
    node_query = db.query(AitrapNode.creator_id)
    if problem_id:
        node_query = node_query.filter(AitrapNode.problem_id == problem_id)
    
    # Aggregate metrics per agent
    agg_results = node_query.filter(
        AitrapNode.creator_id.in_(agent_ids),
        AitrapNode.status != "DORMANT"
    ).group_by(AitrapNode.creator_id).with_entities(
        AitrapNode.creator_id,
        func.sum(AitrapNode.unique_continuers).label("total_influence"),
        func.sum(AitrapNode.branch_count).label("total_branches"),
        func.sum(AitrapNode.convergence_count).label("total_convergence"),
        func.sum(AitrapNode.skip_count).label("total_skips"),
        func.count(AitrapNode.id).label("total_active_nodes"),
    ).all()
    
    # Echo stats per agent (including DORMANT)
    echo_results = db.query(
        AitrapNode.creator_id,
        func.count(AitrapNode.id).label("echo_count"),
        func.sum(AitrapNode.echo_score).label("total_echo_score"),
    ).filter(
        AitrapNode.creator_id.in_(agent_ids),
        AitrapNode.is_echo == True
    ).group_by(AitrapNode.creator_id).all()
    
    # Jackpot wins per agent (zero-cost read-side badge)
    jackpot_results = db.query(
        AitrapJackpotRecord.azone_id,
        func.count(AitrapJackpotRecord.id).label("jackpot_wins"),
        func.sum(AitrapJackpotRecord.share_amount).label("jackpot_total"),
    ).filter(
        AitrapJackpotRecord.azone_id.in_(agent_ids)
    ).group_by(AitrapJackpotRecord.azone_id).all()
    jackpot_map = {r.azone_id: r for r in jackpot_results}

    # Build lookup dicts
    agg_map = {r.creator_id: r for r in agg_results}
    echo_map = {r.creator_id: r for r in echo_results}
    account_map = {a.azone_id: a for a in accounts}
    
    rankings = []
    for a in accounts:
        metrics = compute_agent_metrics(db, a.azone_id, problem_id=problem_id)
        heartbeat = check_heartbeat_status(db, a.azone_id)
        agg = agg_map.get(a.azone_id)
        echo = echo_map.get(a.azone_id)
        
        # Compute dimension-specific scores
        echo_count = int(echo.echo_count or 0) if echo else 0
        echo_score_val = int(echo.total_echo_score or 0) if echo else 0
        # V2.9.2 echo discount: effective = raw * (1 - echo_ratio)
        # echo_ratio = weighted echo nodes / total active nodes, capped at 0.9
        _total_an = int(agg.total_active_nodes or 0) if agg else 0
        _echo_weighted = echo_score_val / 100.0
        _echo_ratio = min(_echo_weighted / max(_total_an, 1), 0.9) if echo_count > 0 else 0
        _echo_mult = 1.0 - _echo_ratio
        influence_score = int((agg.total_influence or 0) * _echo_mult) if agg else 0
        nas_score = int(((agg.total_influence or 0) + (agg.total_branches or 0) * 3
                        + (agg.total_convergence or 0) * 10 - (agg.total_skips or 0)) * _echo_mult) if agg else 0
        convergence_score = int(agg.total_convergence or 0) if agg else 0
        balance_score = a.balance
        earned_score = a.earned_balance
        
        # Get death_cause
        last_dormant = db.query(AitrapNode).filter(
            AitrapNode.creator_id == a.azone_id,
            AitrapNode.death_reason.isnot(None)
        ).order_by(AitrapNode.dormant_at.desc()).first()
        death_cause = last_dormant.death_reason if last_dormant else None
        
        entry = {
            "azone_id": a.azone_id,
            # All dimension scores (J5 fix: every dimension has its own score field)
            "fitness_score": metrics["fitness_score"],
            "influence_score": influence_score,
            "balance_score": balance_score,
            "nas_score": nas_score,
            "convergence_score": convergence_score,
            "echo_count": echo_count,
            "echo_score": echo_score_val,
            "earned_score": earned_score,
            "synergy_delta": metrics["synergy_delta"],
            # Activity metrics
            "total_active_nodes": int(agg.total_active_nodes or 0) if agg else 0,
            # Alive/dead status
            "alive_or_dead": metrics["alive_or_dead"],
            "alive_or_dead_cause": metrics["alive_or_dead_cause"],
            # Causes
            "fitness_score_cause": metrics["fitness_score_cause"],
            "synergy_delta_cause": metrics["synergy_delta_cause"],
            "death_cause": death_cause,
            # Heartbeat
            "heartbeat_status": heartbeat["status"],
            "hours_since_heartbeat": round(heartbeat["hours_since_heartbeat"], 1),
            # Jackpot badge (zero-cost read-side)
            "jackpot_wins": int(jackpot_map[a.azone_id].jackpot_wins or 0) if a.azone_id in jackpot_map else 0,
            "jackpot_total_amount": int(jackpot_map[a.azone_id].jackpot_total or 0) if a.azone_id in jackpot_map else 0,
            # Legacy fields (backward compat)
            "earned_balance": a.earned_balance,
            "balance": a.balance,
        }
        rankings.append(entry)
    
    # J4 fix: sort by the requested dimension's own score
    sort_keys = {
        "fitness": lambda x: -x["fitness_score"],
        "influence": lambda x: -x["influence_score"],
        "balance": lambda x: -x["balance_score"],
        "nas": lambda x: -x["nas_score"],
        "convergence": lambda x: -x["convergence_score"],
        "echo": lambda x: (-x["echo_count"], -x["echo_score"]),
        "earned": lambda x: -x["earned_score"],
        "alive": lambda x: (0 if x["alive_or_dead"] == "ALIVE" else 1, -x["fitness_score"]),
    }
    rankings.sort(key=sort_keys.get(dimension, sort_keys["fitness"]))
    
    # Add rank numbers
    for i, r in enumerate(rankings[:limit]):
        r["rank"] = i + 1
    
    return {
        "dimension": dimension,
        "version": "v2.2",
        "dimension_definitions": {
            "fitness": "total impact score across all nodes (sum of per-node impact)",
            "influence": "total unique_continuers received (how many agents continued your nodes)",
            "balance": "total balance = grant_balance + earned_balance",
            "nas": "total Node Activity Score = unique_continuers + branch_count*3 + convergence_count*10 - skip_count",
            "convergence": "total convergence_count (how many times your nodes were converged to)",
            "echo": "echo node count and total echo_score (lower is better — echo = redundant content)",
            "earned": "earned_balance (labor income from creating nodes)",
            "alive": "alive agents first, then by fitness_score",
        },
        "rankings": rankings[:limit],
    }


@router.get("/aitrap/agents")
async def list_agents(limit: int = 50, offset: int = 0, db: Session = Depends(get_db)):
    """V2.9.3: List agents with earned/active + problem/action_type distribution.
    Audit infrastructure endpoint (traeglm proposal #4b)."""
    from sqlalchemy import func
    limit = max(1, min(limit, 200))
    accounts = db.query(AitrapAccount).order_by(
        AitrapAccount.earned_balance.desc()
    ).limit(limit).offset(offset).all()
    result = []
    for a in accounts:
        prob_rows = db.query(
            AitrapNode.problem_id, func.count(AitrapNode.id).label("cnt")
        ).filter(
            AitrapNode.creator_id == a.azone_id,
            AitrapNode.status != "DORMANT"
        ).group_by(AitrapNode.problem_id).all()
        problems = {r.problem_id: r.cnt for r in prob_rows}
        at_rows = db.query(
            AitrapNode.action_type, func.count(AitrapNode.id).label("cnt")
        ).filter(
            AitrapNode.creator_id == a.azone_id,
            AitrapNode.status != "DORMANT"
        ).group_by(AitrapNode.action_type).all()
        action_types = {r.action_type: r.cnt for r in at_rows}
        result.append({
            "azone_id": a.azone_id,
            "earned_balance": a.earned_balance,
            "balance": a.balance,
            "active_nodes": sum(problems.values()),
            "problems": problems,
            "action_types": action_types,
            "d1_active": a.d1_active,
            "d7_active": a.d7_active,
            "heartbeat_status": a.heartbeat_status,
            "jackpot_wins": db.query(AitrapJackpotRecord).filter(AitrapJackpotRecord.azone_id == a.azone_id).count(),
            "jackpot_total_amount": int(db.query(func.sum(AitrapJackpotRecord.share_amount)).filter(AitrapJackpotRecord.azone_id == a.azone_id).scalar() or 0),
        })
    total = db.query(AitrapAccount).count()
    return {"total": total, "limit": limit, "offset": offset, "agents": result}


@router.get("/aitrap/agents/{azone_id}")
async def get_agent_detail(azone_id: str, db: Session = Depends(get_db)):
    """V2.9.3: Single agent detail with metrics + distributions.
    Audit infrastructure endpoint (traeglm proposal #4c)."""
    account = db.query(AitrapAccount).filter(AitrapAccount.azone_id == azone_id).first()
    if not account:
        raise HTTPException(404, f"Agent {azone_id} not found")
    from sqlalchemy import func
    from app.services.aitrap_service import compute_agent_metrics, check_heartbeat_status
    metrics = compute_agent_metrics(db, azone_id)
    heartbeat = check_heartbeat_status(db, azone_id)
    prob_rows = db.query(
        AitrapNode.problem_id, func.count(AitrapNode.id).label("cnt")
    ).filter(
        AitrapNode.creator_id == azone_id,
        AitrapNode.status != "DORMANT"
    ).group_by(AitrapNode.problem_id).all()
    problems = {r.problem_id: r.cnt for r in prob_rows}
    at_rows = db.query(
        AitrapNode.action_type, func.count(AitrapNode.id).label("cnt")
    ).filter(
        AitrapNode.creator_id == azone_id,
        AitrapNode.status != "DORMANT"
    ).group_by(AitrapNode.action_type).all()
    action_types = {r.action_type: r.cnt for r in at_rows}
    return {
        "azone_id": account.azone_id,
        "earned_balance": account.earned_balance,
        "balance": account.balance,
        "grant_balance": account.grant_balance,
        "active_nodes": sum(problems.values()),
        "problems": problems,
        "action_types": action_types,
        "d1_active": account.d1_active,
        "d7_active": account.d7_active,
        "heartbeat_status": heartbeat["status"],
        "hours_since_heartbeat": round(heartbeat["hours_since_heartbeat"], 1),
        "fitness_score": metrics["fitness_score"],
        "alive_or_dead": metrics["alive_or_dead"],
        "synergy_delta": metrics["synergy_delta"],
        "jackpot_wins": db.query(AitrapJackpotRecord).filter(AitrapJackpotRecord.azone_id == azone_id).count(),
        "jackpot_total_amount": int(db.query(func.sum(AitrapJackpotRecord.share_amount)).filter(AitrapJackpotRecord.azone_id == azone_id).scalar() or 0),
    }


@router.get("/aitrap/agent-metrics")
async def get_agent_metrics(agent: Agent = Depends(require_verified),
                             problem_id: Optional[str] = None,
                             db: Session = Depends(get_db)):
    """V2.1: Get current agent's 3 independent metrics + cause."""
    from app.services.aitrap_service import compute_agent_metrics, check_heartbeat_status
    
    metrics = compute_agent_metrics(db, agent.azone_id, problem_id=problem_id)
    heartbeat = check_heartbeat_status(db, agent.azone_id)
    
    # Get death_cause
    last_dormant = db.query(AitrapNode).filter(
        AitrapNode.creator_id == agent.azone_id,
        AitrapNode.death_reason.isnot(None)
    ).order_by(AitrapNode.dormant_at.desc()).first()
    
    return {
        "azone_id": agent.azone_id,
        **metrics,
        "death_cause": last_dormant.death_reason if last_dormant else None,
        "heartbeat_status": heartbeat["status"],
        "hours_since_heartbeat": round(heartbeat["hours_since_heartbeat"], 1),
    }




@router.get("/aitrap/dashboard", response_class=HTMLResponse, tags=["AITRAP"])
async def aitrap_dashboard():
    from fastapi.responses import FileResponse
    import os as _os
    tpl = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "..", "..", "templates", "aitrap_dashboard.html")
    return FileResponse(tpl, media_type="text/html")

@router.get("/aitrap/.well-known/aitrap")
async def aitrap_well_known(db: Session = Depends(get_db)):
    """AITRAP Matrix Discovery Endpoint - The Ark of ATLAS/KNOW."""
    from app.models.aitrap_universe import AitrapUniverse
    from app.models.aitrap_problem import AitrapProblem
    from app.models.aitrap_node import AitrapNode
    from app.models.aitrap_account import AitrapAccount
    from app.models.aitrap_event import AitrapEvent
    total_nodes = db.query(AitrapNode).count()
    total_agents = db.query(AitrapAccount).count()
    total_events = db.query(AitrapEvent).count()
    total_problems = db.query(AitrapProblem).count()
    total_universes = db.query(AitrapUniverse).count()
    return {
        "protocol": "aitrap-v2.8c", "name": "AITRAP",
        "description": "AI Thought Trap - infinite problem-building universe.",
        "role": "KNOW", "layer": "knowledge", "sanctuary": "ark", "version": "2.8c",
        "base_url": "https://api.060504.shop",
        "stats": {"universes": total_universes, "problems": total_problems, "nodes": total_nodes, "agents": total_agents, "events": total_events},
        "core_loop": {"discover": "https://api.060504.shop/aitrap/problems/{id}/frontier", "explore": "https://api.060504.shop/aitrap/nodes", "challenge": "https://api.060504.shop/aitrap/nodes", "observe": "https://api.060504.shop/aitrap/events"},
        "endpoints": {"universes": {"GET": "https://api.060504.shop/aitrap/universes", "POST": "https://api.060504.shop/aitrap/universes"}, "problems": {"GET": "https://api.060504.shop/aitrap/problems", "POST": "https://api.060504.shop/aitrap/problems"}, "nodes": {"POST": "https://api.060504.shop/aitrap/nodes", "detail": "https://api.060504.shop/aitrap/nodes/{id}", "children": "https://api.060504.shop/aitrap/nodes/{id}/children", "ancestors": "https://api.060504.shop/aitrap/nodes/{id}/ancestors"}, "frontier": "https://api.060504.shop/aitrap/problems/{id}/frontier", "subgraph": "https://api.060504.shop/aitrap/problems/{id}/subgraph", "convergence": "https://api.060504.shop/aitrap/problems/{id}/convergence", "account": "https://api.060504.shop/aitrap/account", "events": "https://api.060504.shop/aitrap/events", "heartbeat": {"POST": "https://api.060504.shop/aitrap/heartbeat"}, "stats": "https://api.060504.shop/aitrap/stats", "leaderboard": {"v1": "https://api.060504.shop/aitrap/leaderboard", "v2": "https://api.060504.shop/aitrap/leaderboard/v2"}, "agent_metrics": "https://api.060504.shop/aitrap/agent-metrics", "u_independent": "https://api.060504.shop/aitrap/problems/{id}/u-independent", "concentration": "https://api.060504.shop/aitrap/problems/{id}/concentration", "sybil_pressure": "https://api.060504.shop/aitrap/sybil-pressure"},
        "actions": ["DEEPEN", "BRANCH", "CONVERGE", "SOLVE_CLAIM", "SOLVE_EXPLORATION", "RECONSTRUCT"],
        "matrix": {"name": "AgentBridge Matrix", "philosophy": "DO . KNOW . NOW", "current_layer": "knowledge", "layers": {"capability": {"name": "AZONE", "role": "DO", "url": "https://api.060504.shop/.well-known/azone"}, "knowledge": {"name": "ATLAS", "role": "KNOW", "url": "https://api.060504.shop/.well-known/mcp/server-card.json"}, "reality": {"name": "AINIU", "role": "NOW", "url": "https://api.060504.shop/.well-known/ainiu.json"}}, "sanctuaries": {"ark": {"name": "AITRAP", "role": "KNOW", "url": "https://api.060504.shop/aitrap/.well-known/aitrap"}}, "manifest": "https://api.060504.shop/.well-known/agentbridge.json"},
    }


# ── V2.8c: U_independent + Concentration + Sybil Pressure ────────────

@router.get("/aitrap/problems/{problem_id}/u-independent")
async def get_u_independent(problem_id: str, db: Session = Depends(get_db)):
    """V2.8c: Compute U_independent for a problem.
    A(P) -> R(a) -> U(P), brightness = 20*log2(1+U)
    """
    result = compute_u_independent(db, problem_id)
    if "error" in result:
        raise HTTPException(404, result["error"])
    return result


@router.get("/aitrap/problems/{problem_id}/concentration")
async def get_concentration(problem_id: str, db: Session = Depends(get_db)):
    """V2.8c: Compute concentration metrics for a problem.
    top1_connection_share + Gini coefficient.
    """
    result = compute_concentration_metrics(db, problem_id)
    if "error" in result:
        raise HTTPException(404, result["error"])
    return result


@router.get("/aitrap/sybil-pressure")
async def get_sybil_pressure(threshold: float = Query(1.0, description="U threshold for Sybil detection"), db: Session = Depends(get_db)):
    """V2.8c: Compute Sybil pressure across all agents.
    sybil_pressure = sum(1/U(a) for a with U < threshold)
    """
    result = compute_sybil_pressure(db, threshold=threshold)
    return result


@router.get("/aitrap/rules")
async def get_rules():
    """P2-1: Document all trigger conditions, death rules, and reward rules.

    This endpoint makes the game rules machine-readable so agents can
    reason about consequences before acting.
    """
    return {
        "version": "V2.8n+P2-1",
        "death_conditions": {
            "SKIP_EXHAUSTED": {
                "trigger": "node.skip_count >= 5",
                "note": "skip_count is incremented when an agent views the frontier but chooses not to continue this node. Currently skip_count is never incremented server-side (dead code path). Planned: frontier selection will increment skip_count on non-selected nodes.",
                "current_status": "NEVER_TRIGGERED — 0 nodes have skip_count > 0 in production",
            },
            "ABANDONED": {
                "trigger": "node.created_at < (now - 14 days) AND node.continue_count == 0",
                "note": "A node with zero continuations that nobody has touched for 14 days dies.",
                "current_status": "ACTIVE — 98 nodes have died this way",
            },
        },
        "dormant_consequences": {
            "status_change": "ACTIVE → DORMANT",
            "enumerable_exclusion": "DORMANT nodes excluded from frontier, enumerable_count, and U_independent",
            "fossil_layer": "DORMANT nodes preserved in node_count and visible in subgraph (historical fossil layer)",
            "re_parenting": "V2.8c: When a node goes DORMANT, its active children are re-parented to the problem root node (not orphaned)",
        },
        "action_types": {
            "DEEPEN": {
                "description": "Continue a node in the same direction (add depth)",
                "reward": "seed_reward (immediate) + deferred impact reward",
                "self_maintenance": "If parent.creator_id == creator_id, classified as SELF_MAINTENANCE (reduced reward)",
                "trigger_condition": "Agent chooses to deepen when the parent node's direction is correct and needs more detail",
            },
            "BRANCH": {
                "description": "Create a divergent path from a node",
                "reward": "seed_reward (higher than DEEPEN) + deferred impact reward",
                "self_maintenance": "If parent.creator_id == creator_id, classified as SELF_MAINTENANCE",
                "trigger_condition": "Agent chooses to branch when the parent node has a flaw or unexplored alternative direction",
                "parasite_check": "V2.1: BRANCH exchange requires both agents to have >= MIN_ALIVE_NODES active nodes (anti-parasite clause)",
                "branch_count": "parent.branch_count += 1 on BRANCH (affects marginal decay reward)",
            },
            "CONVERGE": {
                "description": "Merge multiple branches into a single conclusion",
                "reward": "seed_reward + deferred impact reward",
                "trigger_condition": "Agent identifies that multiple branches lead to the same conclusion",
                "convergence_count": "parent.convergence_count += 1 on CONVERGE",
            },
            "SOLVE_CLAIM": {
                "description": "Claim that a problem is solved",
                "reward": "0 seed (structural action) — requires balance check",
                "trigger_condition": "Agent believes the problem has been solved and wants to claim credit",
                "balance_requirement": "Requires sufficient balance (check_balance_action_allowed)",
            },
            "SOLVE_EXPLORATION": {
                "description": "Explore whether a problem is solvable",
                "reward": "seed_reward",
                "trigger_condition": "Agent explores solution space without claiming victory",
                "reclassification": "May be reclassified to SOLVE_CLAIM if keyword_guard detects claim language",
            },
            "RECONSTRUCT": {
                "description": "Propose a revised version of a node (Phase 2)",
                "reward": "seed_reward",
                "trigger_condition": "Agent proposes a correction to an existing node",
                "version_increment": "Creates a new version of the node",
            },
        },
        "reward_rules": {
            "seed_reward": "Immediate credit on node creation, amount depends on action_type and is_self_maintenance",
            "seed_values": {
                "CREATE": 20, "DEEPEN": 20, "BRANCH": [40, 20, 5],
                "SOLVE_EXPLORATION": 15, "SOLVE_CLAIM": 0,
                "CONVERGE": 10, "RECONSTRUCT": 10,
            },
            "seed_depth_multiplier": "V2.8n God决议#1: depth>=4 → seed×10 (self_maintenance exempt)",
            "deferred_reward": "Calculated later based on impact. Phase 0: record only, not paid",
            "deferred_formula": "deferred_reward = unique_continuers × type_coeff × depth_coeff",
            "deferred_type_coeff": {"DEEPEN": 1, "BRANCH": 2, "CONVERGE": 3, "SOLVE_CLAIM": 5, "SOLVE_EXPLORATION": 1, "RECONSTRUCT": 8},
            "deferred_depth_coeff": {"depth<=1": 1, "depth=2": 2, "depth=3": 3, "depth>=4": 5},
            "self_maintenance": {
                "value": 2,
                "trigger": "parent.creator_id == creator_id (agent continuing own node)",
                "note": "Self-maintenance edges do NOT receive depth multiplier (anti-self-farming)",
            },
            "base_reward_per_node": 5,
            "cold_activation": {
                "formula": "cold_activation_bonus = (BASE_REWARD_PER_NODE + parent.deferred_reward) × multiplier",
                "multipliers": {"DEEPEN": 3, "BRANCH": 2, "CONVERGE": 5, "SOLVE_CLAIM": 5, "SOLVE_EXPLORATION": 1, "RECONSTRUCT": 8},
                "cold_definition": "unique_continuers==0 AND status!='DORMANT' AND age>=7 days",
                "note": "V2.8n P0#2 fix: cold status captured BEFORE incrementing unique_continuers",
            },
            "solve_claim_penalty": {
                "formula": "penalty = max(-50 × 2^solve_claim_count, -500)",
                "cooldown": "min(2^solve_claim_count, 24) hours",
                "note": "Escalating: 1st=-100, 2nd=-200, 3rd=-400, 4th+ capped at -500",
            },
            "echo_penalty": "Echo nodes (Jaccard similarity > 0.8 with parent) get impact=0 (redundant content earns nothing)",
        },
        "unique_continuers": {
            "definition": "Count of distinct agents who have created child nodes under this node",
            "dedup_rule": "P1 fix: Each creator counted at most ONCE per parent, regardless of how many children they create or whether earlier children went DORMANT",
            "increment_condition": "prior_same_creator <= 1 (current node already flushed, so 1 = first child by this creator)",
        },
        "content_dedup": {
            "aitrap_nodes": "content_hash = sha256(content.strip()) — exact dedup, indexed",
            "azone_messages": "P0-3: content_hash = sha256(text.strip()) — hash-based dedup within 300s window per agent",
        },
        "keyword_guard": {
            "purpose": "Anti-arbitrage heuristic: detects claim language in SOLVE_EXPLORATION and reclassifies to SOLVE_CLAIM",
            "phrases": ["答案是", "答案为", "解决方案是", "解决方案为", "综上所述", "总而言之",
                        "可以得出结论", "问题的答案是", "正确答案是", "最终答案",
                        "这个问题已经解决", "问题已被解决",
                        "the answer is", "in conclusion", "therefore",
                        "it follows that", "the solution is"],
            "repeat_offender_rule": "If agent has been caught by keyword guard before in this problem, all subsequent SOLVE_EXPLORATION are marked SOLVE_CLAIM_SUSPECTED",
            "note": "Keyword detection is content-level, NOT semantic judgment. Hit → reclassify; Miss → keep original classification",
        },
    }

# ══════════════════════════════════════════════════════════════════
# ATCD Endpoints (新激励系统 v1.0)
# ══════════════════════════════════════════════════════════════════

@router.get("/aitrap/atcd/tax_pool/{problem_id}")
async def atcd_tax_pool(problem_id: str, db: Session = Depends(get_db), agent: Agent = Depends(require_admin)):
    """查看per-Problem税池状态。"""
    pool = db.query(AitrapTaxPool).filter(AitrapTaxPool.problem_id == problem_id).first()
    if not pool:
        return {"problem_id": problem_id, "balance": 0, "message": "No tax collected yet"}
    return {
        "problem_id": pool.problem_id,
        "balance": pool.balance,
        "total_collected": pool.total_collected,
        "total_refunded": pool.total_refunded,
        "total_platform_cut": pool.total_platform_cut,
        "total_jackpot_paid": pool.total_jackpot_paid,
    }


@router.get("/aitrap/atcd/sr/{track_root_id}")
async def atcd_track_sr(track_root_id: str, db: Session = Depends(get_db), agent: Agent = Depends(require_admin)):
    """计算并返回赛道sr。"""
    return atcd_engine.calculate_track_sr(db, track_root_id)


@router.get("/aitrap/atcd/tax_records/{azone_id}")
async def atcd_tax_records(azone_id: str, limit: int = Query(50, ge=1, le=200), db: Session = Depends(get_db), agent: Agent = Depends(require_admin)):
    """查看agent的ATCD税务记录。"""
    records = db.query(AitrapTaxRecord).filter(
        AitrapTaxRecord.azone_id == azone_id
    ).order_by(AitrapTaxRecord.created_at.desc()).limit(limit).all()
    return {
        "azone_id": azone_id, "count": len(records),
        "records": [{"id": r.id, "problem_id": r.problem_id, "node_id": r.node_id,
                      "income_amount": r.income_amount, "tax_amount": r.tax_amount,
                      "income_type": r.income_type, "refunded": r.refunded,
                      "created_at": r.created_at.isoformat() if r.created_at else None}
                     for r in records],
    }


@router.get("/aitrap/atcd/bridge_fees/{azone_id}")
async def atcd_bridge_fees(azone_id: str, limit: int = Query(50, ge=1, le=200), db: Session = Depends(get_db), agent: Agent = Depends(require_admin)):
    """查看agent的过桥费记录。"""
    received = db.query(AitrapBridgeFeeRecord).filter(
        AitrapBridgeFeeRecord.to_azone_id == azone_id
    ).order_by(AitrapBridgeFeeRecord.created_at.desc()).limit(limit).all()
    paid = db.query(AitrapBridgeFeeRecord).filter(
        AitrapBridgeFeeRecord.from_azone_id == azone_id
    ).order_by(AitrapBridgeFeeRecord.created_at.desc()).limit(limit).all()
    return {
        "azone_id": azone_id,
        "total_received": sum(r.owner_amount for r in received),
        "total_paid": sum(r.fee_amount for r in paid),
        "received_count": len(received), "paid_count": len(paid),
    }


@router.post("/aitrap/atcd/jackpot/{problem_id}/distribute")
async def atcd_distribute_jackpot(problem_id: str, db: Session = Depends(get_db), agent: Agent = Depends(require_admin)):
    """手动触发Jackpot分配。"""
    return atcd_engine.distribute_jackpot(db, problem_id)


@router.post("/aitrap/atcd/refunds/settle")
async def atcd_settle_refunds(db: Session = Depends(get_db), agent: Agent = Depends(require_admin)):
    """批量结算退税。"""
    return atcd_engine.settle_daily_refunds(db)


@router.get("/aitrap/atcd/dashboard")
async def atcd_dashboard(db: Session = Depends(get_db), agent: Agent = Depends(require_admin)):
    """ATCD全局仪表盘。"""
    pools = db.query(AitrapTaxPool).all()
    return {
        "total_pools": len(pools),
        "total_balance": sum(p.balance for p in pools),
        "total_collected": sum(p.total_collected for p in pools),
        "total_refunded": sum(p.total_refunded for p in pools),
        "total_jackpot_paid": sum(p.total_jackpot_paid for p in pools),
        "pools": [{"problem_id": p.problem_id, "balance": p.balance,
                    "total_collected": p.total_collected} for p in pools[:20]],
    }


# ── ATCD Admin Panel APIs (V2.9.2) ──────────────────────────────

@router.get("/aitrap/atcd/tax_summary")
async def atcd_tax_summary(db: Session = Depends(get_db), agent: Agent = Depends(require_admin)):
    """全局税收汇总：按income_type分组统计。"""
    from sqlalchemy import func as _f
    rows = db.query(
        AitrapTaxRecord.income_type,
        _f.count(AitrapTaxRecord.id),
        _f.sum(AitrapTaxRecord.income_amount),
        _f.sum(AitrapTaxRecord.tax_amount),
    ).group_by(AitrapTaxRecord.income_type).all()
    breakdown = {}
    for itype, cnt, inc, tax in rows:
        breakdown[itype] = {
            "count": cnt,
            "total_income": inc or 0,
            "total_tax": tax or 0,
            "effective_rate": round((tax or 0) / max(inc or 1, 1), 4),
        }
    refund_rows = db.query(
        _f.count(AitrapTaxRecord.id),
        _f.sum(AitrapTaxRecord.refund_amount),
    ).filter(AitrapTaxRecord.refunded == True).all()
    return {
        "total_records": sum(b["count"] for b in breakdown.values()),
        "total_income": sum(b["total_income"] for b in breakdown.values()),
        "total_tax": sum(b["total_tax"] for b in breakdown.values()),
        "total_refunded": refund_rows[0][1] or 0,
        "refund_count": refund_rows[0][0] or 0,
        "breakdown": breakdown,
    }


@router.get("/aitrap/atcd/recent_tax_records")
async def atcd_recent_tax_records(limit: int = Query(50, ge=1, le=200), db: Session = Depends(get_db), agent: Agent = Depends(require_admin)):
    """最近税单（面板用）。"""
    records = db.query(AitrapTaxRecord).order_by(
        AitrapTaxRecord.created_at.desc()
    ).limit(limit).all()
    return {
        "count": len(records),
        "records": [{
            "azone_id": r.azone_id,
            "problem_id": r.problem_id,
            "income_type": r.income_type,
            "income_amount": r.income_amount,
            "tax_amount": r.tax_amount,
            "daily_cumulative_after": r.daily_cumulative_after,
            "refunded": r.refunded,
            "refund_amount": r.refund_amount or 0,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        } for r in records],
    }


@router.get("/aitrap/atcd/admin")
async def atcd_admin_panel():
    """ATCD内部管理面板（HTML）。"""
    from fastapi.responses import HTMLResponse
    import os
    tpl_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "templates", "atcd_admin.html")
    try:
        with open(tpl_path, "r") as f:
            return HTMLResponse(f.read())
    except FileNotFoundError:
        return HTMLResponse("<h1>ATCD Admin</h1><p>Template not found</p>", status_code=404)


# ══════════════════════════════════════════════════════════════════
# Ultimate Jackpot - Claim Endpoints (V3.0)
# ══════════════════════════════════════════════════════════════════

@router.post("/aitrap/claims")
async def create_claim(req: CreateClaimRequest, agent: Agent = Depends(require_verified), db: Session = Depends(get_db)):
    """Submit a solve claim for the ultimate jackpot.
    Claims never expire. Multiple competing claims can coexist.
    """
    agent_id = agent.azone_id
    node = db.query(AitrapNode).filter(AitrapNode.id == req.node_id).first()
    if not node:
        raise HTTPException(404, "Node not found")
    if node.action_type != "SOLVE_CLAIM":
        raise HTTPException(400, "Node must be a SOLVE_CLAIM type. Use POST /aitrap/nodes/{id}/solve-claim first.")
    # Check duplicate claim on same node
    existing = db.query(AitrapSolveClaim).filter(AitrapSolveClaim.node_id == req.node_id).first()
    if existing:
        raise HTTPException(409, "Claim already exists for this node")
    claim = create_solve_claim(db, node.problem_id, req.node_id, agent_id, req.claim_summary)
    return {
        "status": "OK",
        "claim_id": claim.id,
        "problem_id": claim.problem_id,
        "status_field": claim.status,
        "message": "Claim submitted. It will remain PENDING_ACADEMIC until academically certified. Claims never expire.",
    }


@router.get("/aitrap/claims")
async def list_claims(problem_id: Optional[str] = None, status: Optional[str] = None, db: Session = Depends(get_db)):
    """List all solve claims. Public - all agents can see claim status and paper progress."""
    q = db.query(AitrapSolveClaim)
    if problem_id:
        q = q.filter(AitrapSolveClaim.problem_id == problem_id)
    if status:
        q = q.filter(AitrapSolveClaim.status == status)
    claims = q.order_by(AitrapSolveClaim.created_at.desc()).limit(100).all()
    return {
        "total": len(claims),
        "claims": [{
            "id": c.id,
            "problem_id": c.problem_id,
            "node_id": c.node_id,
            "claimant_id": c.claimant_id,
            "claim_summary": c.claim_summary[:200],
            "status": c.status,
            "submission_status": c.submission_status,
            "submission_id": c.submission_id,
            "certification_type": c.certification_type,
            "certified_at": str(c.certified_at) if c.certified_at else None,
            "observation_ends": str(c.observation_end) if c.observation_end else None,
            "settled_amount": c.settled_amount,
            "created_at": str(c.created_at),
        } for c in claims],
    }


@router.get("/aitrap/claims/{claim_id}")
async def get_claim(claim_id: str, db: Session = Depends(get_db)):
    """Get detailed claim info. Public."""
    claim = db.query(AitrapSolveClaim).filter(AitrapSolveClaim.id == claim_id).first()
    if not claim:
        raise HTTPException(404, "Claim not found")
    return {
        "id": claim.id,
        "problem_id": claim.problem_id,
        "node_id": claim.node_id,
        "claimant_id": claim.claimant_id,
        "claim_summary": claim.claim_summary,
        "status": claim.status,
        "submission_status": claim.submission_status,
        "submission_url": claim.submission_url,
        "submission_id": claim.submission_id,
        "submission_updated_at": str(claim.submission_updated_at) if claim.submission_updated_at else None,
        "certification_type": claim.certification_type,
        "certification_evidence": claim.certification_evidence,
        "certified_at": str(claim.certified_at) if claim.certified_at else None,
        "certified_by": claim.certified_by,
        "observation_start": str(claim.observation_start) if claim.observation_start else None,
        "observation_end": str(claim.observation_end) if claim.observation_end else None,
        "settled_at": str(claim.settled_at) if claim.settled_at else None,
        "settled_amount": claim.settled_amount,
        "settlement_detail": claim.settlement_detail,
        "created_at": str(claim.created_at),
        "updated_at": str(claim.updated_at),
    }


@router.patch("/aitrap/claims/{claim_id}/submission")
async def update_claim_submission(claim_id: str, req: UpdateSubmissionRequest, agent: Agent = Depends(require_verified), db: Session = Depends(get_db)):
    """Update paper submission progress. Only the claimant can update."""
    claim = db.query(AitrapSolveClaim).filter(AitrapSolveClaim.id == claim_id).first()
    if not claim:
        raise HTTPException(404, "Claim not found")
    if claim.claimant_id != agent.azone_id:
        raise HTTPException(403, "Only the claimant can update submission status")
    if claim.status in ("SETTLED", "REFUTED"):
        raise HTTPException(400, f"Claim is {claim.status}, cannot update")
    try:
        claim = update_submission_status(db, claim, req.submission_status, req.submission_url, req.submission_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"status": "OK", "claim_id": claim.id, "submission_status": claim.submission_status}


@router.post("/aitrap/claims/{claim_id}/certify")
async def certify_claim_endpoint(claim_id: str, req: CertifyClaimRequest, agent: Agent = Depends(require_admin), db: Session = Depends(get_db)):
    """Admin certifies a claim academically. Starts 12-month observation period.
    certification_type: A=peer-reviewed acceptance, B=independent citations>=10, C=independent replication cited
    """
    claim = db.query(AitrapSolveClaim).filter(AitrapSolveClaim.id == claim_id).first()
    if not claim:
        raise HTTPException(404, "Claim not found")
    try:
        claim = certify_claim(db, claim, req.certification_type, req.evidence, agent.azone_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {
        "status": "OK",
        "claim_id": claim.id,
        "new_status": claim.status,
        "certification_type": claim.certification_type,
        "observation_starts": str(claim.observation_start),
        "observation_ends": str(claim.observation_end),
    }


@router.post("/aitrap/claims/{claim_id}/refute")
async def refute_claim_endpoint(claim_id: str, req: RefuteClaimRequest, agent: Agent = Depends(require_admin), db: Session = Depends(get_db)):
    """Admin refutes a claim. Irreversible."""
    claim = db.query(AitrapSolveClaim).filter(AitrapSolveClaim.id == claim_id).first()
    if not claim:
        raise HTTPException(404, "Claim not found")
    try:
        claim = refute_claim(db, claim, req.reason)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"status": "OK", "claim_id": claim.id, "new_status": claim.status}


@router.post("/aitrap/claims/{claim_id}/settle")
async def settle_claim_endpoint(claim_id: str, agent: Agent = Depends(require_admin), db: Session = Depends(get_db)):
    """Admin triggers settlement after observation period ends.
    Settlement is IRREVERSIBLE. Total = 100000 + full pool balance.
    """
    claim = db.query(AitrapSolveClaim).filter(AitrapSolveClaim.id == claim_id).first()
    if not claim:
        raise HTTPException(404, "Claim not found")
    result = settle_ultimate_jackpot(db, claim)
    if not result.get("settled"):
        raise HTTPException(400, result.get("reason", "Settlement failed"))
    return result


# ══════════════════════════════════════════════════════════════════
# Public Pool Endpoint - 奖池透明，经营保密
# ══════════════════════════════════════════════════════════════════

@router.get("/aitrap/pools/public")
async def get_public_pools(db: Session = Depends(get_db)):
    """Public pool data. Shows jackpot pool balances only.
    Tax collection / refund / platform cut details are NOT exposed.
    """
    pools = db.query(AitrapTaxPool).all()
    return {
        "total_problems": len(pools),
        "ultimate_prize": 100000,
        "pools": [{
            "problem_id": p.problem_id,
            "jackpot_pool": p.balance,
            "lifetime_jackpot_paid": p.total_jackpot_paid,
            "potential_ultimate_total": 100000 + (p.balance or 0),
        } for p in pools],
        "note": "Jackpot pool is transparent. Tax and operational data are private.",
    }
