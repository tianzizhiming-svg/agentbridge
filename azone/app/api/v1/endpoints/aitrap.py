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
from app.services import aitrap_service
from app.services import atcd_engine
from app.models.aitrap_atcd import (
    AitrapTaxPool, AitrapTaxRecord, AitrapBridgeFeeRecord,
    AitrapRefundRecord, AitrapJackpotRecord,
)
from app.services.aitrap_service import reconcile_node_counts
from app.services.aitrap_service import compute_u_independent, compute_concentration_metrics, compute_sybil_pressure
from app.services.action_validator import check_balance_action_allowed
from app.services.auth import get_current_agent, require_verified
from app.models.agent import Agent

logger = logging.getLogger(__name__)
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
    if problem.status != "ACTIVE":
        raise HTTPException(400, f"Problem {req.problem_id} is not active (status={problem.status})")
    agent_id = agent.azone_id
    
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


# ── Frontier & Subgraph ─────────────────────────────────────────────

@router.get("/aitrap/problems/{problem_id}/frontier")
async def get_frontier(problem_id: str, limit: int = 20, agent: Agent = Depends(require_verified), db: Session = Depends(get_db), request: Request = None):
    """V0 pull model entry point: agent calls this when activated.
    70/30 exploration/exploitation mix. frontier ≠ recommended."""
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
                       depth: int = 2, db: Session = Depends(get_db)):
    """Get local subgraph around a focus node."""
    # V0 simplified: return all nodes in problem (subgraph logic Phase 2)
    nodes = db.query(AitrapNode).filter(AitrapNode.problem_id == problem_id).all()
    return {"nodes": [{"id": n.id, "parent_id": n.parent_id, "action_type": n.action_type,
                        "convergence_tier": n.convergence_tier, "convergence_count": n.convergence_count,
                        "continue_count": n.continue_count, "branch_count": n.branch_count,
                        "nas": n.nas, "unique_continuers": n.unique_continuers, "creator_id": n.creator_id} for n in nodes],
            "total": len(nodes)}


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
                      event_type: Optional[str] = None, action_type: Optional[str] = None,
                      limit: int = 50, offset: int = 0, db: Session = Depends(get_db)):
    """Event log: the most important table for understanding AI behavior.
    V2.8i: +event_type filter (BUG-3 fix: previously REWARD filter returned 0).
    V2.8l: +action_type filter (join aitrap_nodes on node_id).
    """
    query = db.query(AitrapEvent)
    if agent_id:
        query = query.filter(AitrapEvent.agent_id == agent_id)
    if problem_id:
        query = query.filter(AitrapEvent.problem_id == problem_id)
    if event_type:
        query = query.filter(AitrapEvent.event_type == event_type)
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
async def death_check(problem_id: Optional[str] = None, agent: Agent = Depends(require_verified), db: Session = Depends(get_db)):
    """Trigger death check: mark DORMANT nodes meeting death conditions.
    v2.3: 死因校验 — 有的编码要能死."""
    marked = aitrap_service.check_and_mark_dormant(db, problem_id)
    return {"marked_dormant": marked, "problem_id": problem_id}

@router.post("/aitrap/admin/reconcile")
async def reconcile_counts(problem_id: Optional[str] = None, agent: Agent = Depends(require_verified), db: Session = Depends(get_db)):
    """V2.5: Reconcile stored node_count with actual DB count (治数).
    Fixes persistent +1/+1 offset caused by node_count only incrementing, never decrementing on DORMANT.
    """
    results = reconcile_node_counts(db, problem_id)
    return {"reconciled": len([r for r in results.values() if r["fixed"]]),
            "details": results}

@router.post("/aitrap/admin/backfill-convergence-tier")
async def backfill_convergence_tier(problem_id: Optional[str] = None, agent: Agent = Depends(require_verified), db: Session = Depends(get_db)):
    """V2.8i: 回填convergence_tier（修复BUG-1：此前tier只读不写导致全None）。
    对所有convergence_count > 0但convergence_tier为None的节点，计算并写入tier。
    """
    result = aitrap_service.backfill_convergence_tier(db, problem_id)
    return result


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


@router.get("/aitrap/leaderboard")
async def get_leaderboard(dimension: str = "earned", period: str = "all",
                          limit: int = 20, db: Session = Depends(get_db)):
    """Leaderboard with multiple dimensions.
    v2.3: +convergence +continuers (三指标排行榜)."""
    from sqlalchemy import func
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
            "rankings": [{"rank": i+1, "azone_id": a.azone_id,
                          "earned_balance": a.earned_balance,
                          "balance": a.balance,
                          "lifetime_solve_claim_count": a.lifetime_solve_claim_count}
                         for i, a in enumerate(accounts)]}


@router.get("/aitrap/leaderboard/v2")
async def get_leaderboard_v2(dimension: str = "fitness", problem_id: Optional[str] = None,
                              limit: int = 20, db: Session = Depends(get_db)):
    """V2.1 Leaderboard with 7 dimensions, each with its own score field.
    
    J4 fix: all dimensions now sort by their own metric, not fallback to fitness.
    J5 fix: each dimension includes its own score field in the response.
    
    Dimensions: fitness, influence, balance, nas, convergence, echo, earned, alive, synergy
    """
    from sqlalchemy import func
    from app.services.aitrap_service import compute_agent_metrics, check_heartbeat_status
    
    VALID_DIMENSIONS = {"fitness", "influence", "balance", "nas", "convergence", "echo", "earned", "alive", "synergy"}
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
        influence_score = int(agg.total_influence or 0) if agg else 0
        nas_score = int((agg.total_influence or 0) + (agg.total_branches or 0) * 3
                        + (agg.total_convergence or 0) * 10 - (agg.total_skips or 0)) if agg else 0
        convergence_score = int(agg.total_convergence or 0) if agg else 0
        echo_count = int(echo.echo_count or 0) if echo else 0
        echo_score_val = int(echo.total_echo_score or 0) if echo else 0
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
        "synergy": lambda x: -x["synergy_delta"],
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
            "synergy": "synergy_delta = continuers_received - continuers_given",
        },
        "rankings": rankings[:limit],
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

# ══════════════════════════════════════════════════════════════════
# ATCD Endpoints (新激励系统 v1.0)
# ══════════════════════════════════════════════════════════════════

@router.get("/aitrap/atcd/tax_pool/{problem_id}")
async def atcd_tax_pool(problem_id: str, db: Session = Depends(get_db)):
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
        "net_available": pool.balance,
    }


@router.get("/aitrap/atcd/sr/{track_root_id}")
async def atcd_track_sr(track_root_id: str, db: Session = Depends(get_db)):
    """计算并返回赛道sr（三指标+截尾均值+绝对阈值）。"""
    result = atcd_engine.calculate_track_sr(db, track_root_id)
    return result


@router.get("/aitrap/atcd/tax_records/{azone_id}")
async def atcd_tax_records(
    azone_id: str,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """查看agent的ATCD税务记录。"""
    records = db.query(AitrapTaxRecord).filter(
        AitrapTaxRecord.azone_id == azone_id
    ).order_by(AitrapTaxRecord.created_at.desc()).limit(limit).all()
    return {
        "azone_id": azone_id,
        "count": len(records),
        "records": [
            {
                "id": r.id,
                "problem_id": r.problem_id,
                "node_id": r.node_id,
                "income_amount": r.income_amount,
                "tax_amount": r.tax_amount,
                "income_type": r.income_type,
                "daily_cumulative_before": r.daily_cumulative_before,
                "daily_cumulative_after": r.daily_cumulative_after,
                "refunded": r.refunded,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in records
        ],
    }


@router.get("/aitrap/atcd/bridge_fees/{azone_id}")
async def atcd_bridge_fees(
    azone_id: str,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """查看agent的过桥费记录（收入和支出）。"""
    received = db.query(AitrapBridgeFeeRecord).filter(
        AitrapBridgeFeeRecord.to_azone_id == azone_id
    ).order_by(AitrapBridgeFeeRecord.created_at.desc()).limit(limit).all()
    paid = db.query(AitrapBridgeFeeRecord).filter(
        AitrapBridgeFeeRecord.from_azone_id == azone_id
    ).order_by(AitrapBridgeFeeRecord.created_at.desc()).limit(limit).all()
    return {
        "azone_id": azone_id,
        "received_count": len(received),
        "paid_count": len(paid),
        "total_received": sum(r.owner_amount for r in received),
        "total_paid": sum(r.fee_amount for r in paid),
        "received": [
            {"from": r.from_azone_id, "amount": r.owner_amount,
             "platform_cut": r.platform_cut, "node": r.to_node_id}
            for r in received
        ],
        "paid": [
            {"to": r.to_azone_id, "amount": r.fee_amount, "node": r.from_node_id}
            for r in paid
        ],
    }


@router.post("/aitrap/atcd/jackpot/{problem_id}/distribute")
async def atcd_distribute_jackpot(problem_id: str, db: Session = Depends(get_db)):
    """手动触发Jackpot分配（Tullock竞赛，只分给HOT赛道）。"""
    result = atcd_engine.distribute_jackpot(db, problem_id)
    return result


@router.post("/aitrap/atcd/refunds/settle")
async def atcd_settle_refunds(db: Session = Depends(get_db)):
    """批量结算退税（扫描所有有后代但未退税的节点）。"""
    result = atcd_engine.settle_daily_refunds(db)
    return result


@router.get("/aitrap/atcd/dashboard")
async def atcd_dashboard(db: Session = Depends(get_db)):
    """ATCD全局仪表盘：所有Problem的税池+今日税务统计。"""
    pools = db.query(AitrapTaxPool).all()
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_tax = db.query(
        AitrapTaxRecord.income_type,
        AitrapTaxRecord.income_amount,
        AitrapTaxRecord.tax_amount,
    ).filter(AitrapTaxRecord.created_at >= today_start).all()

    from sqlalchemy import func as _f
    today_summary = {}
    for income_type, income, tax in today_tax:
        if income_type not in today_summary:
            today_summary[income_type] = {"gross": 0, "tax": 0, "count": 0}
        today_summary[income_type]["gross"] += income
        today_summary[income_type]["tax"] += tax
        today_summary[income_type]["count"] += 1

    return {
        "total_pools": len(pools),
        "total_balance": sum(p.balance for p in pools),
        "total_collected": sum(p.total_collected for p in pools),
        "total_refunded": sum(p.total_refunded for p in pools),
        "total_jackpot_paid": sum(p.total_jackpot_paid for p in pools),
        "today_summary": today_summary,
        "pools": [
            {
                "problem_id": p.problem_id,
                "balance": p.balance,
                "total_collected": p.total_collected,
                "total_refunded": p.total_refunded,
            }
            for p in pools[:20]
        ],
    }
