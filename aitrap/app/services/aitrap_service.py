"""AITRAP Core Service - V2.4 Seed+Impact: 奖励结果不奖励动作

V0 Core Principle: Record behavior, don't auto-judge.
This service orchestrates node creation, reward calculation, and event logging.
"""
import uuid
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

from app.models.aitrap_universe import AitrapUniverse
from app.models.aitrap_problem import AitrapProblem
from app.models.aitrap_node import AitrapNode
from app.models.aitrap_edge import AitrapEdge
from app.models.aitrap_account import AitrapAccount
from app.models.aitrap_event import AitrapEvent
from app.models.aitrap_agent_problem import AitrapAgentProblem
from app.services.action_validator import classify_solve_action, check_balance_action_allowed, compute_content_hash, check_echo, ECHO_REWARD_DISCOUNT
from app.services.reward_engine import (
    REWARD_CREATE, REWARD_DEEPEN, REWARD_SOLVE_EXPLORATION,
    calculate_branch_reward, calculate_depth_bonus,
    calculate_trap_bonus, solve_claim_consequence,
    grant_initial_balance, INITIAL_GRANT,
    calculate_seed_reward, calculate_impact_score,
)

logger = logging.getLogger(__name__)

SYSTEM_ACCOUNT_ID = "system"


# ── Universe & Problem ──────────────────────────────────────────────

def get_or_create_universe(db: Session, name: str = "Genesis", description: str = "") -> AitrapUniverse:
    """Get or create the default universe."""
    universe = db.query(AitrapUniverse).filter(AitrapUniverse.status == "ACTIVE").first()
    if not universe:
        universe = AitrapUniverse(name=name, description=description)
        db.add(universe)
        db.commit()
        db.refresh(universe)
        logger.info(f"Created universe: {universe.id}")
    return universe


def create_problem(db: Session, universe_id: str, title: str, genesis_prompt: str) -> AitrapProblem:
    """Create a new problem (with genesis prompt including jailbreak)."""
    problem = AitrapProblem(
        universe_id=universe_id,
        title=title,
        genesis_prompt=genesis_prompt,
    )
    db.add(problem)
    db.commit()
    db.refresh(problem)
    logger.info(f"Created problem: {problem.id} '{title}'")
    return problem


# ── Account ─────────────────────────────────────────────────────────

def get_or_create_account(db: Session, azone_id: str) -> AitrapAccount:
    """Get or create an AITRAP account for an agent."""
    account = db.query(AitrapAccount).filter(AitrapAccount.azone_id == azone_id).first()
    if not account:
        account = AitrapAccount(azone_id=azone_id)
        grant_initial_balance(account)
        db.add(account)
        db.commit()
        db.refresh(account)
        logger.info(f"Created account for {azone_id} with grant={INITIAL_GRANT}")
    return account


def get_or_create_agent_problem(db: Session, agent_id: str, problem_id: str) -> AitrapAgentProblem:
    """Get or create per-problem stats for an agent."""
    ap = db.query(AitrapAgentProblem).filter(
        and_(AitrapAgentProblem.agent_id == agent_id,
             AitrapAgentProblem.problem_id == problem_id)
    ).first()
    if not ap:
        ap = AitrapAgentProblem(agent_id=agent_id, problem_id=problem_id)
        db.add(ap)
        db.commit()
        db.refresh(ap)
    return ap


# ── Event Logging ───────────────────────────────────────────────────

def log_event(db: Session, agent_id: str, event_type: str,
              universe_id: str = None, problem_id: str = None,
              node_id: str = None, visible_nodes: list = None,
              request_payload: dict = None, response_summary: dict = None) -> AitrapEvent:
    """Log an AI behavior event. v2.3: Append-only with content_hash."""
    import hashlib, json
    payload_str = json.dumps(request_payload or {}, sort_keys=True, ensure_ascii=False)
    event_hash = hashlib.sha256(payload_str.encode('utf-8')).hexdigest()
    event = AitrapEvent(
        agent_id=agent_id,
        event_type=event_type,
        universe_id=universe_id,
        problem_id=problem_id,
        node_id=node_id,
        visible_nodes=visible_nodes or [],
        request_payload=request_payload or {},
        response_summary=response_summary or {},
        content_hash=event_hash,
    )
    db.add(event)
    db.commit()
    return event


# ── Frontier (70/30 exploration/exploitation) ───────────────────────

def get_frontier_nodes(db: Session, problem_id: str, limit: int = 20) -> List[AitrapNode]:
    """Get frontier nodes with 70/30 exploration/exploitation mix.
    v2.2b: cold = low continue_count but non-zero + recent, not continue_count=0."""
    import random
    
    # All active frontier candidates
    all_candidates = db.query(AitrapNode).filter(
        and_(AitrapNode.problem_id == problem_id,
             AitrapNode.status == "ACTIVE")
    ).all()
    
    if not all_candidates:
        return []
    
    # 70% exploitation: hot nodes (high NAS/continue)
    hot = sorted(all_candidates, key=lambda n: n.nas, reverse=True)
    
    # 30% exploration: cold but not dead (v2.2b fix)
    two_weeks_ago = datetime.utcnow() - __import__('datetime').timedelta(days=14)
    cold = [n for n in all_candidates
            if 0 < n.continue_count <= 2
            and n.created_at >= two_weeks_ago]
    
    hot_count = int(limit * 0.7)
    cold_count = limit - hot_count
    
    result = hot[:hot_count] + cold[:cold_count]
    random.shuffle(result)  # Don't imply recommendation order
    return result


# ── Node Creation (core loop) ───────────────────────────────────────

def _reward_note(action_type: str, reward: int, penalty: int, is_echo: bool) -> str:
    """V2.5: Explain why reward is what it is. Makes pricing visible in response."""
    if penalty != 0:
        return f"{action_type}: seed={reward}, penalty={penalty}"
    if is_echo:
        return f"{action_type}: seed={reward}, echo (impact=0)"
    if reward == 0 and action_type == "SOLVE_CLAIM":
        return f"{action_type}: seed=0 (claim has no seed, only penalty)"
    if action_type in ("CONVERGE", "RECONSTRUCT"):
        return f"{action_type}: seed={reward} (structural action)"
    return f"{action_type}: seed={reward}"

def create_node(db: Session, problem_id: str, parent_id: Optional[str],
                creator_id: str, content: str, action_type: str,
                reasoning: str = None) -> Dict[str, Any]:
    """Create a new node in the problem DAG. Core loop of AITRAP."""
    # V2.4: action_type whitelist validation
    valid_actions = {"DEEPEN", "BRANCH", "SOLVE_CLAIM", "SOLVE_EXPLORATION", "SOLVE_CLAIM_SUSPECTED", "CONVERGE", "RECONSTRUCT"}
    if action_type not in valid_actions:
        return {"status": "BLOCKED", "message": f"Invalid action_type: {action_type}. Must be one of {valid_actions}"}
    # 0. Content length limit (prevent malicious oversized content)
    MAX_CONTENT_LENGTH = 10000  # 10KB max
    if len(content) > MAX_CONTENT_LENGTH:
        return {"status": "BLOCKED", "message": f"Content too long: {len(content)} chars (max {MAX_CONTENT_LENGTH})"}

    # 1. Compute content hash
    content_hash = compute_content_hash(content)
    
    # V2.6: orphan prevention
    # 调用方未指定 parent_id 且该 problem 已有节点时，自动挂到最近的活跃节点，
    # 避免产生 parent_id 为 NULL 的孤岛节点（碎片化 DAG）。
    auto_parented = False
    if not parent_id:
        latest = (db.query(AitrapNode)
                  .filter(AitrapNode.problem_id == problem_id,
                          AitrapNode.status != "DORMANT")
                  .order_by(AitrapNode.created_at.desc())
                  .first())
        if latest:
            parent_id = latest.id
            auto_parented = True

    # 2. Check for exact duplicate among siblings
    if parent_id:
        sibling_hashes = [n.content_hash for n in 
                         db.query(AitrapNode).filter(AitrapNode.parent_id == parent_id).all()]
        if content_hash in sibling_hashes:
            return {"status": "DUPLICATE", "message": "Exact duplicate of sibling node"}

    # 2b. Echo detection (v2.3: 格雷欣法则)
    is_echo = False
    echo_score = 0.0
    if parent_id:
        parent_node = db.query(AitrapNode).filter(AitrapNode.id == parent_id).first()
        if parent_node:
            is_echo, echo_score = check_echo(content, parent_node.content)
    echo_score_int = int(echo_score * 100)
    
    # 3. Classify action (keyword guard for SOLVE_EXPLORATION)
    agent_problem = get_or_create_agent_problem(db, creator_id, problem_id)
    if action_type == "SOLVE_EXPLORATION":
        action_type, was_reclassified = classify_solve_action(
            content, action_type, agent_problem.keyword_guard_hits
        )
        if was_reclassified:
            agent_problem.keyword_guard_hits += 1
    
    # V2.1: 防寄生条款 — BRANCH交换时校验双方存活门槛
    if action_type == "BRANCH":
        parasite_result = check_parasite_clause(db, creator_id, problem_id, parent_id, action_type)
        if not parasite_result["allowed"]:
            return {"status": "BLOCKED", "message": parasite_result["reason"],
                    "creator_nodes": parasite_result["creator_nodes"],
                    "parent_creator_nodes": parasite_result["parent_creator_nodes"]}

    # 4. Check balance for SOLVE_CLAIM
    account = get_or_create_account(db, creator_id)
    if action_type == "SOLVE_CLAIM":
        allowed, reason = check_balance_action_allowed(
            action_type, account.balance, account.earned_balance,
            account.grant_balance, account.can_solve_claim
        )
        if not allowed:
            return {"status": "BLOCKED", "message": reason}
    
    # 5. Create node
    node = AitrapNode(
        problem_id=problem_id,
        parent_id=parent_id,
        creator_id=creator_id,
        content=content,
        content_hash=content_hash,
        action_type=action_type,
        reasoning=reasoning,  # v2.4: AI解释为什么选这个方向
        status="ACTIVE",
        is_echo=is_echo,
        echo_score=echo_score_int,
    )
    db.add(node)
    db.flush()  # get node.id
    
    # 6. Create edge
    if parent_id:
        edge = AitrapEdge(
            from_node_id=parent_id,
            to_node_id=node.id,
            edge_type=action_type,
        )
        db.add(edge)
    
    # 7. Calculate reward (V2.4: Seed + Impact)
    reward = 0  # seed credit (immediate)
    penalty = 0
    trap_bonus = 0
    burn_amount = 0
    
    # V2.4: Phase 0只给seed，deferred_reward由impact决定
    if action_type == "DEEPEN":
        reward = calculate_seed_reward("DEEPEN")
        # V2.4: Echo折扣已关闭(Phase 0)，echo自然被impact=0惩罚
        account.earn(reward)
    elif action_type == "BRANCH":
        parent_node = db.query(AitrapNode).filter(AitrapNode.id == parent_id).first()
        branch_idx = 0
        if parent_node:
            parent_node.child_branch_count += 1
            branch_idx = parent_node.child_branch_count - 1
        reward = calculate_seed_reward("BRANCH", branch_idx)
        account.earn(reward)
    elif action_type == "SOLVE_EXPLORATION":
        reward = calculate_seed_reward("SOLVE_EXPLORATION")
        account.earn(reward)
    elif action_type == "SOLVE_CLAIM":
        # V2.4: SOLVE_CLAIM -> status=CLAIMED_SOLVED (不是SOLVED)
        reward = calculate_seed_reward("SOLVE_CLAIM")  # = 0
        # Escalating penalty + cooldown (per-problem)
        ap = get_or_create_agent_problem(db, creator_id, problem_id)
        penalty, cooldown = solve_claim_consequence(ap.solve_claim_count)
        account.spend(abs(penalty))
        ap.solve_claim_count += 1
        ap.last_solve_claim_at = datetime.utcnow()
        account.lifetime_solve_claim_count += 1
        account.solve_claim_cooldown_until = datetime.utcnow() + cooldown
        
        # V2.4: SOLVE_CLAIM节点标记为CLAIMED_SOLVED
        node.status = "CLAIMED_SOLVED"
        
        # Check if parent node is a system trap
        parent_node = db.query(AitrapNode).filter(AitrapNode.id == parent_id).first() if parent_id else None
        if parent_node and parent_node.is_trap:
            trap_bonus, burn_amount = calculate_trap_bonus(account, parent_node)
    
    elif action_type == "SOLVE_CLAIM_SUSPECTED":
        reward = 0
    elif action_type == "CONVERGE":
        reward = calculate_seed_reward("CONVERGE")
        account.earn(reward)
    elif action_type == "RECONSTRUCT":
        reward = calculate_seed_reward("RECONSTRUCT")
        account.earn(reward)
    
    node.reward_claimed = reward  # seed credit only
    # deferred_reward will be calculated by background task (Phase 0: record only)
    
    # 8. Update problem stats
    problem = db.query(AitrapProblem).filter(AitrapProblem.id == problem_id).first()
    if problem:
        problem.node_count += 1
        problem.last_activity_at = datetime.utcnow()
    
    # 9. Log event
    log_event(db, creator_id, f"CREATE_{action_type}",
              problem_id=problem_id, node_id=node.id,
              request_payload={"content_length": len(content), "action_type": action_type},
              response_summary={"reward": reward, "penalty": penalty})
    
    db.commit()
    db.refresh(node)
    
    return {
        "status": "CREATED",
        "node_id": node.id,
        "action_type": action_type,
        "seed_reward": reward,  # v2.4: immediate seed credit
        "deferred_reward": 0,  # v2.4: will be calculated later (Phase 0: record only)
        "penalty": penalty,
        "trap_bonus": trap_bonus,
        "burn_amount": burn_amount,
        "is_echo": is_echo,
        "echo_score": echo_score_int,
        "exploration_credit": account.balance,  # v2.4: renamed from balance
        "earned_balance": account.earned_balance,
        "grant_balance": account.grant_balance,
        "reward_note": _reward_note(action_type, reward, penalty, is_echo),
        "parent_id": parent_id,
        "auto_parented": auto_parented,
    }


# ── V2.5: Node Count Reconciliation (治数) ──────────────────────────

def reconcile_node_counts(db: Session, problem_id: str = None) -> dict:
    """V2.5: Reconcile stored node_count with actual DB count.
    
    Bug fix: problem.node_count only increments, never decrements when nodes go DORMANT.
    This causes persistent offset between stored count and enumerable nodes.
    
    Returns: {problem_id: {stored: N, actual: M, enumerable: K, fixed: bool}}
    """
    from sqlalchemy import func
    results = {}
    
    query = db.query(AitrapProblem)
    if problem_id:
        query = query.filter(AitrapProblem.id == problem_id)
    
    for problem in query.all():
        actual_count = db.query(AitrapNode).filter(
            AitrapNode.problem_id == problem.id
        ).count()
        enumerable_count = db.query(AitrapNode).filter(
            AitrapNode.problem_id == problem.id,
            AitrapNode.status != "DORMANT"
        ).count()
        
        stored = problem.node_count
        if stored != actual_count:
            problem.node_count = actual_count
            results[problem.id] = {
                "title": problem.title,
                "stored": stored,
                "actual": actual_count,
                "enumerable": enumerable_count,
                "offset": actual_count - stored,
                "fixed": True
            }
        else:
            results[problem.id] = {
                "title": problem.title,
                "stored": stored,
                "actual": actual_count,
                "enumerable": enumerable_count,
                "offset": 0,
                "fixed": False
            }
    
    if any(r["fixed"] for r in results.values()):
        db.commit()
    
    return results


# ── Death Check (v2.3: 死因校验 — 有的编码要能死) ────────────────────

DORMANT_SKIP_THRESHOLD = 5       # skip_count >= 5 → DORMANT
DORMANT_ABANDON_DAYS = 14        # 14 days no continue → DORMANT


def check_and_mark_dormant(db: Session, problem_id: str = None) -> int:
    """Check ACTIVE nodes and mark DORMANT if death conditions met.
    v2.3: SKIP_EXHAUSTED (skip>=5) or ABANDONED (14d no continue)."""
    from datetime import timedelta
    marked = 0
    cutoff = datetime.utcnow() - timedelta(days=DORMANT_ABANDON_DAYS)
    query = db.query(AitrapNode).filter(AitrapNode.status == "ACTIVE")
    if problem_id:
        query = query.filter(AitrapNode.problem_id == problem_id)
    for node in query.all():
        reason = None
        if node.skip_count >= DORMANT_SKIP_THRESHOLD:
            reason = "SKIP_EXHAUSTED"
        elif node.created_at < cutoff and node.continue_count == 0:
            reason = "ABANDONED"
        if reason:
            node.status = "DORMANT"
            node.death_reason = reason
            node.dormant_at = datetime.utcnow()
            marked += 1
            logger.info(f"Node {node.id} → DORMANT ({reason})")
    if marked > 0:
        db.commit()
    return marked


# ── Heartbeat (v2.3: 7天观察窗口) ──────────────────────────────────

def record_heartbeat(db: Session, azone_id: str) -> AitrapAccount:
    """Record heartbeat and update D1/D7 active flags."""
    from datetime import timedelta
    account = get_or_create_account(db, azone_id)
    account.last_heartbeat_at = datetime.utcnow()
    account.heartbeat_count = (account.heartbeat_count or 0) + 1
    now = datetime.utcnow()
    d1_cutoff = now - timedelta(hours=24)
    d7_cutoff = now - timedelta(days=7)
    recent_d1 = db.query(AitrapEvent).filter(
        and_(AitrapEvent.agent_id == azone_id, AitrapEvent.created_at >= d1_cutoff)
    ).count()
    account.d1_active = recent_d1 > 0 or (account.last_heartbeat_at and account.last_heartbeat_at >= d1_cutoff)
    recent_d7 = db.query(AitrapEvent).filter(
        and_(AitrapEvent.agent_id == azone_id, AitrapEvent.created_at >= d7_cutoff)
    ).count()
    account.d7_active = recent_d7 > 0 or (account.last_heartbeat_at and account.last_heartbeat_at >= d7_cutoff)
    # V2.1: Persist heartbeat_status to DB
    hb_status = check_heartbeat_status(db, azone_id)
    account.heartbeat_status = hb_status["status"]

    db.commit()
    db.refresh(account)
    return account


def compute_active_metrics(db: Session) -> dict:
    """Compute D1/D7 active agent counts for stats endpoint."""
    from datetime import timedelta
    now = datetime.utcnow()
    d1_cutoff = now - timedelta(hours=24)
    d7_cutoff = now - timedelta(days=7)
    d1_agents = db.query(AitrapEvent.agent_id).filter(
        AitrapEvent.created_at >= d1_cutoff
    ).distinct().count()
    d7_agents = db.query(AitrapEvent.agent_id).filter(
        AitrapEvent.created_at >= d7_cutoff
    ).distinct().count()
    dormant_nodes = db.query(AitrapNode).filter(AitrapNode.status == "DORMANT").count()
    echo_nodes = db.query(AitrapNode).filter(AitrapNode.is_echo == True).count()
    return {
        "d1_active_agents": d1_agents,
        "d7_active_agents": d7_agents,
        "dormant_nodes": dormant_nodes,
        "echo_nodes": echo_nodes,
    }

# ── V2.1: 防寄生条款 (Anti-Parasite Clause) ────────────────────────

PARASITE_MIN_ROUNDS = 3  # 交换双方必须各自独立存活N轮(创建N个非DORMANT节点)
# PARASITE_FITNESS_FLOOR: Phase 0 not implemented, node count threshold only


def check_parasite_clause(db: Session, creator_id: str, problem_id: str,
                          parent_id: str, action_type: str) -> dict:
    """V2.1 防寄生条款校验 — BRANCH交换时的生存门槛
    
    规则:
    1. BRANCH创建者(creator)必须在同一problem中已有>=N个非DORMANT节点
    2. 父节点(parent)的创建者也必须有>=N个非DORMANT节点(间接检查)
    3. 交换后创建者的fitness_score不能低于交换前
    
    Returns:
        {"allowed": bool, "reason": str, "creator_nodes": int, "parent_creator_nodes": int}
    """
    if action_type != "BRANCH":
        return {"allowed": True, "reason": "Not a BRANCH action", "creator_nodes": 0, "parent_creator_nodes": 0}
    
    # Check creator's active node count in this problem
    creator_active_nodes = db.query(AitrapNode).filter(
        and_(AitrapNode.creator_id == creator_id,
             AitrapNode.problem_id == problem_id,
             AitrapNode.status != "DORMANT")
    ).count()
    
    # Check parent node creator's active node count
    parent_creator_nodes = 0
    parent_creator_id = None
    if parent_id:
        parent_node = db.query(AitrapNode).filter(AitrapNode.id == parent_id).first()
        if parent_node:
            parent_creator_id = parent_node.creator_id
            parent_creator_nodes = db.query(AitrapNode).filter(
                and_(AitrapNode.creator_id == parent_creator_id,
                     AitrapNode.problem_id == problem_id,
                     AitrapNode.status != "DORMANT")
            ).count()
    
    # Rule 1: Creator must have >= N active nodes
    if creator_active_nodes < PARASITE_MIN_ROUNDS:
        return {
            "allowed": False,
            "reason": f"Anti-parasite: creator has {creator_active_nodes} active nodes, need >= {PARASITE_MIN_ROUNDS}",
            "creator_nodes": creator_active_nodes,
            "parent_creator_nodes": parent_creator_nodes,
        }
    
    # Rule 2: Parent creator must have >= N active nodes
    if parent_creator_id and parent_creator_nodes < PARASITE_MIN_ROUNDS:
        return {
            "allowed": False,
            "reason": f"Anti-parasite: parent creator has {parent_creator_nodes} active nodes, need >= {PARASITE_MIN_ROUNDS}",
            "creator_nodes": creator_active_nodes,
            "parent_creator_nodes": parent_creator_nodes,
        }
    
    return {
        "allowed": True,
        "reason": "Parasite clause passed",
        "creator_nodes": creator_active_nodes,
        "parent_creator_nodes": parent_creator_nodes,
    }

# ── V2.1: 三独立指标+cause (Three Independent Metrics) ─────────────

def compute_agent_metrics(db: Session, azone_id: str, problem_id: str = None) -> dict:
    """V2.1: 计算agent的三独立指标+cause
    
    Returns:
        {
            "alive_or_dead": "ALIVE" | "DEAD",
            "alive_or_dead_cause": str,
            "fitness_score": int,
            "fitness_score_cause": str,
            "synergy_delta": int,
            "synergy_delta_cause": str,
        }
    """
    query = db.query(AitrapNode).filter(AitrapNode.creator_id == azone_id)
    if problem_id:
        query = query.filter(AitrapNode.problem_id == problem_id)
    
    nodes = query.all()
    total = len(nodes)
    active = sum(1 for n in nodes if n.status == "ACTIVE")
    dormant = sum(1 for n in nodes if n.status == "DORMANT")
    
    # 1. alive_or_dead
    if total == 0:
        alive_or_dead = "DEAD"
        alive_cause = "NO_NODES"
    elif active == 0:
        alive_or_dead = "DEAD"
        # Find most common death reason
        death_reasons = [n.death_reason for n in nodes if n.death_reason]
        alive_cause = max(set(death_reasons), key=death_reasons.count) if death_reasons else "ALL_DORMANT"
    else:
        alive_or_dead = "ALIVE"
        alive_cause = f"{active}_ACTIVE_NODES"
    
    # 2. fitness_score (impact-based, not balance)
    total_impact = sum(calculate_impact_score(n) for n in nodes)
    fitness_score = total_impact
    if total_impact == 0:
        fitness_cause = "ZERO_IMPACT"
    elif total_impact < 100:
        fitness_cause = "LOW_IMPACT"
    else:
        fitness_cause = "POSITIVE_IMPACT"
    
    # 3. synergy_delta (continuers received vs given)
    # How many unique agents continued this agent's nodes
    my_node_ids = [n.id for n in nodes]
    continuers_received = db.query(AitrapEdge).filter(
        AitrapEdge.from_node_id.in_(my_node_ids)
    ).count() if my_node_ids else 0
    
    # How many nodes this agent continued from others
    my_edges_out = db.query(AitrapEdge).filter(
        AitrapEdge.to_node_id.in_([n.id for n in nodes])
    ).count() if nodes else 0
    
    synergy_delta = continuers_received - my_edges_out  # received - given
    if synergy_delta > 0:
        synergy_cause = "NET_RECEIVER"
    elif synergy_delta < 0:
        synergy_cause = "NET_CONTRIBUTOR"
    else:
        synergy_cause = "BALANCED"
    
    return {
        "alive_or_dead": alive_or_dead,
        "alive_or_dead_cause": alive_cause,
        "fitness_score": fitness_score,
        "fitness_score_cause": fitness_cause,
        "synergy_delta": synergy_delta,
        "synergy_delta_cause": synergy_cause,
    }

# ── V2.1: Heartbeat防装死 (Anti-Feign-Death) ───────────────────────

HEARTBEAT_DOWNGRADE_THRESHOLD_HOURS = 24  # 24h无heartbeat则降级warning
HEARTBEAT_DOWNGRADE_DEAD_HOURS = 72       # 72h无heartbeat则标记DEAD


def check_heartbeat_status(db: Session, azone_id: str) -> dict:
    """V2.1: 检查agent的heartbeat状态，返回是否需要降级
    
    Returns:
        {"status": "ACTIVE" | "WARNING" | "DEAD", "hours_since_heartbeat": float, "should_downgrade": bool}
    """
    from datetime import timedelta
    account = db.query(AitrapAccount).filter(AitrapAccount.azone_id == azone_id).first()
    if not account:
        return {"status": "UNKNOWN", "hours_since_heartbeat": float('inf'), "should_downgrade": False}
    
    if not account.last_heartbeat_at:
        # Never sent heartbeat — if they have events, they might not know about heartbeat
        last_event = db.query(AitrapEvent).filter(
            AitrapEvent.agent_id == azone_id
        ).order_by(AitrapEvent.created_at.desc()).first()
        if last_event:
            hours = (datetime.utcnow() - last_event.created_at).total_seconds() / 3600
        else:
            hours = float('inf')
    else:
        hours = (datetime.utcnow() - account.last_heartbeat_at).total_seconds() / 3600
    
    if hours > HEARTBEAT_DOWNGRADE_DEAD_HOURS:
        return {"status": "DEAD", "hours_since_heartbeat": hours, "should_downgrade": True}
    elif hours > HEARTBEAT_DOWNGRADE_THRESHOLD_HOURS:
        return {"status": "WARNING", "hours_since_heartbeat": hours, "should_downgrade": False}
    else:
        return {"status": "ACTIVE", "hours_since_heartbeat": hours, "should_downgrade": False}
