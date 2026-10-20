"""AITRAP Core Service - V2.4 Seed+Impact: 奖励结果不奖励动作

V0 Core Principle: Record behavior, don't auto-judge.
This service orchestrates node creation, reward calculation, and event logging.
"""
import uuid
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc, text

from app.models.aitrap_universe import AitrapUniverse
from app.models.aitrap_problem import AitrapProblem
from app.models.aitrap_node import AitrapNode
from app.models.aitrap_edge import AitrapEdge
from app.models.aitrap_account import AitrapAccount
from app.models.aitrap_event import AitrapEvent
from app.models.aitrap_agent_problem import AitrapAgentProblem
from app.services.action_validator import classify_solve_action, check_balance_action_allowed, compute_content_hash, check_echo, ECHO_REWARD_DISCOUNT
# ATCD: 新激励引擎 (v1.0 定稿)
from app.services import atcd_engine
from app.services.atcd_engine import ATCD_ENABLED

from app.services.reward_engine import (
    REWARD_CREATE, REWARD_DEEPEN, REWARD_SOLVE_EXPLORATION,
    calculate_branch_reward, calculate_depth_bonus,
    calculate_trap_bonus, solve_claim_consequence,
    grant_initial_balance, INITIAL_GRANT,
    calculate_seed_reward, calculate_impact_score,
    SELF_MAINTENANCE,
    is_cold_node, COLD_ACTIVATION_MULTIPLIER, BASE_REWARD_PER_NODE,
    calculate_continuation_bonus,
)

logger = logging.getLogger(__name__)


# ── V2.6: Convergence Tier 计算 ──────────────────────────────────────
def compute_convergence_tier(convergence_count: int) -> Optional[str]:
    """根据convergence_count计算收敛等级。
    
    T0: >=3 次收敛（超级收敛枢纽）
    T1: >=2 次收敛（强收敛枢纽）
    T2: >=1 次收敛（收敛枢纽）
    None: 0 次收敛（无等级）
    """
    if convergence_count >= 3:
        return "T0"
    elif convergence_count >= 2:
        return "T1"
    elif convergence_count >= 1:
        return "T2"
    return None

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
              request_payload: dict = None, response_summary: dict = None,
              source_endpoint: str = None, source_url: str = None,
              request_digest: str = None, attested_by: str = None) -> AitrapEvent:
    """Log an AI behavior event. v2.7: Append-only with content_hash + provenance."""
    import hashlib, json
    payload_str = json.dumps(request_payload or {}, sort_keys=True, ensure_ascii=False)
    event_hash = hashlib.sha256(payload_str.encode('utf-8')).hexdigest()
    payload_hash = hashlib.sha256(payload_str.encode('utf-8')).hexdigest()
    event = AitrapEvent(
        agent_id=agent_id,
        event_type=event_type,
        universe_id=universe_id,
        problem_id=problem_id,
        node_id=node_id,
        visible_nodes=(visible_nodes or [])[:5],  # V2.9.1 audit fix: was [:100] causing 3.2GB bloat, truncate to 5
        request_payload=request_payload or {},
        response_summary=response_summary or {},
        content_hash=event_hash,
        # v2.7 provenance
        source_endpoint=source_endpoint,
        source_url=source_url,
        captured_at=datetime.utcnow().isoformat() + "Z",
        request_digest=request_digest,
        payload_hash=payload_hash,
        attested_by=attested_by or "aitrap-api",
        schema_version="v2.7",
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
                reasoning: str = None,
                source_endpoint: str = None, source_url: str = None,
                request_digest: str = None, attested_by: str = None) -> Dict[str, Any]:
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

    # 2. parent_id existence validation (V2.6 defect fix: reject dangling parent)
    #    审计缺陷#3 — 此前传不存在的 parent_id 会建悬空边并发 seed 奖励，
    #    造成孤儿节点 + 白发奖励。现在显式拦截。
    #    V2.9.1 audit fix: cache parent_node once, avoid 8 redundant queries
    parent_node = None
    if parent_id:
        parent_node = db.query(AitrapNode).filter(AitrapNode.id == parent_id).first()
        if not parent_node:
            return {"status": "BLOCKED",
                    "message": f"parent_id {parent_id} does not exist (dangling parent rejected)"}

    # 2b. Check for exact duplicate among siblings
    #    V2.9.1 audit fix: was loading ALL siblings into memory (O(n)), now COUNT query
    if parent_id:
        dup_count = db.query(AitrapNode).filter(
            AitrapNode.parent_id == parent_id,
            AitrapNode.content_hash == content_hash
        ).count()
        if dup_count > 0:
            return {"status": "DUPLICATE", "message": "Exact duplicate of sibling node"}

    # 2b. Echo detection (v2.3: 格雷欣法则)
    is_echo = False
    echo_score = 0.0
    if parent_node:
        is_echo, echo_score = check_echo(content, parent_node.content)
    echo_score_int = int(echo_score * 100)
    
    # V2.8c: 自续边判定 — parent.creator_id == creator_id → SELF_MAINTENANCE
    is_self_maintenance = False
    if parent_node and parent_node.creator_id == creator_id:
        is_self_maintenance = True

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
    
    # 5. Compute depth (materialized column)
    #    V2.9.1 audit fix: use cached parent_node instead of re-querying
    if parent_node:
        node_depth = (parent_node.depth + 1) if parent_node.depth is not None else 1
    else:
        node_depth = 0

    # 6. Create node
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
        depth=node_depth,
    )
    db.add(node)
    db.flush()  # get node.id

    # ATCD: compute track_root_id (depth already computed in step 5)
    if not parent_id:
        node.track_root_id = None
    else:
        if parent_node and parent_node.parent_id is None:
            node.track_root_id = node.id
        elif parent_node:
            node.track_root_id = parent_node.track_root_id
        else:
            node.track_root_id = None

    # ATCD settlement (新激励系统: seed凭空发+累进税+过桥费+退税)
    atcd_result = None
    if ATCD_ENABLED:
        atcd_result = atcd_engine.settle_node_creation(
            db, account, node, parent_node, problem_id, creator_id
        )

    # 7. Create edge
    if parent_id:
        edge = AitrapEdge(
            from_node_id=parent_id,
            to_node_id=node.id,
            edge_type=action_type,
        )
        db.add(edge)

    # V2.8n P0#2 FIX: 在递增 unique_continuers 之前捕获冷节点状态。
    #   此前 is_cold_node() 在 unique_continuers += 1 之后调用，
    #   导致 uc>0 恒 True → cold_activation_bonus 恒为 0（God决议#1从未生效）。
    #   V2.9.1 audit fix: use cached parent_node instead of re-querying
    parent_was_cold = False
    if parent_node and is_cold_node(parent_node):
        parent_was_cold = True

    # 7b. 维护父节点的接续/影响力指标。
    #     此前 continue_count / unique_continuers / branch_count / convergence_count
    #     从未被维护（只有 BRANCH 的 child_branch_count 被 +1），导致：
    #       - 14 天死亡判定对所有节点恒判 ABANDONED -> 周期性清空宇宙；
    #       - frontier 的 30% 探索冷池（0 < continue_count <= 2）恒为空；
    #       - nas = unique_continuers + branch_count*3 + convergence_count*10 - skip
    #         恒 <= 0，V2.4 的 impact 机制从未真正运行。
    #     V2.9.1 audit fix: use cached parent_node, removed redundant query
    if parent_node:
            # V2.9 Phase A: 原子递增 continue_count（消除竞态）
            db.execute(text("UPDATE aitrap_nodes SET continue_count = continue_count + 1 WHERE id = :pid"),
                       {"pid": parent_id})

            # V2.9 Phase A: 原子递增 unique_continuers（消除竞态）
            # 判断和更新合并为单条SQL：只有该creator首次续接此父节点时才+1
            # P1 fix保留: count ALL children (incl DORMANT) to prevent re-increment
            prior_uc = parent_node.unique_continuers or 0  # 递增前快照
            uc_result = db.execute(text("""
                UPDATE aitrap_nodes
                SET unique_continuers = unique_continuers + 1
                WHERE id = :pid
                  AND (SELECT COUNT(*) FROM aitrap_nodes
                       WHERE parent_id = :pid AND creator_id = :cid) <= 1
            """), {"pid": parent_id, "cid": creator_id})

            # V2.9 Phase A: 后置刀 — 首次独立续接（uc 0→1）补发 depth×10 差额
            if uc_result.rowcount > 0 and prior_uc == 0:
                bonus = calculate_continuation_bonus(parent_node, is_self_maintenance=is_self_maintenance)
                if bonus > 0:
                    # 写时刀：同(parent,creator)第2+枚DEEPEN不补发
                    earlier_count = 0
                    if parent_node.parent_id:
                        earlier_count = db.query(AitrapNode).filter(
                            AitrapNode.parent_id == parent_node.parent_id,
                            AitrapNode.creator_id == parent_node.creator_id,
                            AitrapNode.action_type == "DEEPEN",
                            AitrapNode.created_at < parent_node.created_at
                        ).count()
                    if earlier_count == 0:  # 第1枚，允许补发
                        parent_account = db.query(AitrapAccount).filter(
                            AitrapAccount.azone_id == parent_node.creator_id
                        ).first()
                        if parent_account:
                            parent_account.earn(bonus)
                            db.execute(text(
                                "UPDATE aitrap_nodes SET reward_claimed = reward_claimed + :bonus WHERE id = :pid"),
                                {"bonus": bonus, "pid": parent_id})
                            logger.info(f"V2.9 continuation_bonus: node={parent_id[:8]} bonus={bonus} creator={parent_node.creator_id}")

            if action_type == "BRANCH":
                # V2.9 Phase A: 原子递增 branch_count（消除竞态）
                db.execute(text("UPDATE aitrap_nodes SET branch_count = branch_count + 1 WHERE id = :pid"),
                           {"pid": parent_id})
            if action_type == "CONVERGE":
                # V2.9 Phase A: 原子递增 convergence_count（消除竞态）
                db.execute(text("UPDATE aitrap_nodes SET convergence_count = convergence_count + 1 WHERE id = :pid"),
                           {"pid": parent_id})
                db.refresh(parent_node)
                # V2.8i: 写入convergence_tier（此前只读不写，导致全None）
                parent_node.convergence_tier = compute_convergence_tier(parent_node.convergence_count)
                parent_node.is_convergence = True

    # 7. Calculate reward (V2.4: Seed + Impact)
    reward = 0  # seed credit (immediate)
    penalty = 0
    trap_bonus = 0
    burn_amount = 0
    
    # V2.4: Phase 0只给seed，deferred_reward由impact决定
    if action_type == "DEEPEN":
        # V2.9 Phase A: echo折扣重启 — is_echo节点 seed×ECHO_REWARD_DISCOUNT
        echo_disc = ECHO_REWARD_DISCOUNT if is_echo else 1.0
        if not ATCD_ENABLED:
            reward = calculate_seed_reward("DEEPEN", is_self_maintenance=is_self_maintenance, depth=node_depth, echo_discount=echo_disc)
            account.earn(reward)
        else:
            reward = atcd_result["seed"]["gross"] if atcd_result and atcd_result.get("seed") else 0
    elif action_type == "BRANCH":
        # V2.9.1 audit fix: use cached parent_node, removed redundant query
        branch_idx = 0
        if parent_node:
            # V2.9 Phase A: 原子递增 child_branch_count（消除竞态）
            db.execute(text("UPDATE aitrap_nodes SET child_branch_count = child_branch_count + 1 WHERE id = :pid"),
                       {"pid": parent_id})
            db.refresh(parent_node)
            branch_idx = (parent_node.child_branch_count or 1) - 1
        echo_disc = ECHO_REWARD_DISCOUNT if is_echo else 1.0
        if not ATCD_ENABLED:
            reward = calculate_seed_reward("BRANCH", branch_idx, is_self_maintenance=is_self_maintenance, depth=node_depth, echo_discount=echo_disc)
            account.earn(reward)
        else:
            reward = atcd_result["seed"]["gross"] if atcd_result and atcd_result.get("seed") else 0
    elif action_type == "SOLVE_EXPLORATION":
        if not ATCD_ENABLED:
            reward = calculate_seed_reward("SOLVE_EXPLORATION", is_self_maintenance=is_self_maintenance, depth=node_depth)
            account.earn(reward)
        else:
            reward = atcd_result["seed"]["gross"] if atcd_result and atcd_result.get("seed") else 0
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
        # V2.9.1 audit fix: use cached parent_node, removed redundant query
        if parent_node and parent_node.is_trap:
            trap_bonus, burn_amount = calculate_trap_bonus(account, parent_node)
    
    elif action_type == "SOLVE_CLAIM_SUSPECTED":
        reward = 0
    elif action_type == "CONVERGE":
        if not ATCD_ENABLED:
            reward = calculate_seed_reward("CONVERGE", is_self_maintenance=is_self_maintenance, depth=node_depth)
            account.earn(reward)
        else:
            reward = atcd_result["seed"]["gross"] if atcd_result and atcd_result.get("seed") else 0
    elif action_type == "RECONSTRUCT":
        if not ATCD_ENABLED:
            reward = calculate_seed_reward("RECONSTRUCT", is_self_maintenance=is_self_maintenance, depth=node_depth)
            account.earn(reward)
        else:
            reward = atcd_result["seed"]["gross"] if atcd_result and atcd_result.get("seed") else 0
    
    node.reward_claimed = reward  # seed credit only
    # v2.8m: Base reward (survival layer) - 5 earned for every successful node
    account.earn(5)

    # v2.8m: Cold activation bonus - if parent is a cold node, reward its creator
    # V2.8n P0#2 FIX: 使用 parent_was_cold（在 uc+=1 之前捕获），而非重新调用 is_cold_node()
    # V2.9.1 audit fix: use cached parent_node, removed redundant query
    cold_activation_bonus = 0
    if parent_node and parent_was_cold:
        _multiplier = COLD_ACTIVATION_MULTIPLIER.get(action_type, 1)
        cold_activation_bonus = (BASE_REWARD_PER_NODE + (parent_node.deferred_reward or 0)) * _multiplier
        _cold_creator = db.query(AitrapAccount).filter(
            AitrapAccount.azone_id == parent_node.creator_id
        ).first()
        if _cold_creator:
            _cold_creator.earn(cold_activation_bonus)
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
              response_summary={"reward": reward, "penalty": penalty},
              source_endpoint=source_endpoint, source_url=source_url,
              request_digest=request_digest, attested_by=attested_by)
    
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
        "cold_activation_bonus": cold_activation_bonus,
        "echo_score": echo_score_int,
        "exploration_credit": account.balance,  # v2.4: renamed from balance
        "earned_balance": account.earned_balance,
        "grant_balance": account.grant_balance,
        "reward_note": _reward_note(action_type, reward, penalty, is_echo),
        "parent_id": parent_id,
        "auto_parented": auto_parented,
        "is_self_maintenance": is_self_maintenance,  # V2.8c: 自续边标记
        "atcd": atcd_result,
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
    v2.3: SKIP_EXHAUSTED (skip>=5) or ABANDONED (14d no continue).
    V2.8c: 父死子挂Problem根 — 子节点parent_id改为Problem根节点，不抹NULL
    V2.9 Phase A: ABANDONED改为SQL批量（cc=0=无子节点=不需re-parent），SKIP_EXHAUSTED保留循环
    """
    from datetime import timedelta
    marked = 0
    re_parented = 0
    now = datetime.utcnow()
    cutoff = now - timedelta(days=DORMANT_ABANDON_DAYS)

    # V2.9 Phase A: ABANDONED批量SQL — cc=0的节点从未有子节点，无需re-parent
    abandon_sql = """
        UPDATE aitrap_nodes SET
            status = 'DORMANT',
            death_reason = 'ABANDONED',
            dormant_at = :now
        WHERE status = 'ACTIVE'
          AND created_at < :cutoff
          AND continue_count = 0
          AND skip_count < :skip_threshold
    """
    abandon_params = {"now": now, "cutoff": cutoff, "skip_threshold": DORMANT_SKIP_THRESHOLD}
    if problem_id:
        abandon_sql += " AND problem_id = :pid"
        abandon_params["pid"] = problem_id
    result = db.execute(text(abandon_sql), abandon_params)
    abandoned_count = result.rowcount
    marked += abandoned_count
    if abandoned_count > 0:
        logger.info(f"V2.9 batch ABANDONED: {abandoned_count} nodes marked DORMANT")

    # SKIP_EXHAUSTED: Python循环（量小，需re-parent子节点）
    skip_query = db.query(AitrapNode).filter(
        AitrapNode.status == "ACTIVE",
        AitrapNode.skip_count >= DORMANT_SKIP_THRESHOLD
    )
    if problem_id:
        skip_query = skip_query.filter(AitrapNode.problem_id == problem_id)
    for node in skip_query.all():
        node.status = "DORMANT"
        node.death_reason = "SKIP_EXHAUSTED"
        node.dormant_at = now
        marked += 1

        # V2.8c: 父死子挂Problem根
        problem_root = db.query(AitrapNode).filter(
            and_(AitrapNode.problem_id == node.problem_id,
                 AitrapNode.parent_id.is_(None),
                 AitrapNode.status != "DORMANT")
        ).first()

        children = db.query(AitrapNode).filter(
            and_(AitrapNode.parent_id == node.id,
                 AitrapNode.status != "DORMANT")
        ).all()

        for child in children:
            old_parent = child.parent_id
            if problem_root:
                child.parent_id = problem_root.id
            else:
                child.parent_id = None
            re_parented += 1
            # V2.9.1 audit fix: update edges to match new parent_id
            # Old edge: old_parent -> child. Update to: new_parent -> child
            if old_parent:
                db.query(AitrapEdge).filter(
                    AitrapEdge.from_node_id == old_parent,
                    AitrapEdge.to_node_id == child.id
                ).update({"from_node_id": child.parent_id} if child.parent_id else {})
            elif child.parent_id:
                # Was root, now has parent - create new edge
                new_edge = AitrapEdge(
                    from_node_id=child.parent_id,
                    to_node_id=child.id,
                    edge_type=child.action_type,
                )
                db.add(new_edge)
            logger.info(f"Re-parented child {child.id[:8]} from dead {node.id[:8]} to problem root")

        logger.info(f"Node {node.id[:8]} → DORMANT (SKIP_EXHAUSTED), re-parented {len(children)} children")
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
    """Compute D1/D7 active agent counts for stats endpoint.
    J6 fix: dormant_nodes now includes breakdown by death_reason."""
    from datetime import timedelta
    from sqlalchemy import func
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
    
    # J6: Break down dormant by death_reason so the gap is observable
    dormant_breakdown = dict(
        db.query(AitrapNode.death_reason, func.count(AitrapNode.id))
        .filter(AitrapNode.status == "DORMANT")
        .group_by(AitrapNode.death_reason)
        .all()
    )
    # Distinguish pending (death_reason=NULL but status=DORMANT) vs excluded
    dormant_pending = db.query(AitrapNode).filter(
        AitrapNode.status == "DORMANT", AitrapNode.death_reason.is_(None)
    ).count()
    
    return {
        "d1_active_agents": d1_agents,
        "d7_active_agents": d7_agents,
        "dormant_nodes": dormant_nodes,
        "dormant_breakdown": dormant_breakdown,
        "dormant_pending_no_reason": dormant_pending,
        "dormant_note": "dormant_breakdown shows count by death_reason; dormant_pending_no_reason = DORMANT without death_reason (needs investigation)",
        "echo_nodes": echo_nodes,
    }

# ── V2.6: Convergence signal (audit #4: 暴露收敛/分歧信号) ───────────────

def compute_problem_convergence(db: Session, problem_id: str) -> Dict[str, Any]:
    """Compute convergence + divergence signals for a problem DAG.

    Returns: converge-edge count, convergence_tier distribution, top
    convergence hubs, and divergence nodes (branched but never converged).
    Used by GET /aitrap/problems/{problem_id}/convergence.
    """
    nodes = db.query(AitrapNode).filter(AitrapNode.problem_id == problem_id).all()
    node_ids = [n.id for n in nodes]
    total = len(nodes)

    converge_edges = 0
    if node_ids:
        converge_edges = db.query(AitrapEdge).filter(
            AitrapEdge.edge_type == "CONVERGE",
            AitrapEdge.from_node_id.in_(node_ids),
            AitrapEdge.to_node_id.in_(node_ids),
        ).count()

    from collections import Counter
    tier_counter = Counter(n.convergence_tier for n in nodes if n.convergence_tier)

    hubs = sorted(
        [n for n in nodes if (n.convergence_count or 0) > 0],
        key=lambda n: n.convergence_count, reverse=True,
    )[:10]

    divergent = [n for n in nodes if (n.branch_count or 0) > 0 and (n.convergence_count or 0) == 0]
    divergent_sorted = sorted(divergent, key=lambda n: n.branch_count, reverse=True)[:10]

    return {
        "problem_id": problem_id,
        "total_nodes": total,
        "converge_edges": converge_edges,
        "convergence_tier_distribution": dict(tier_counter),
        "top_convergence_hubs": [
            {"node_id": h.id, "convergence_count": h.convergence_count,
             "creator_id": h.creator_id, "action_type": h.action_type}
            for h in hubs
        ],
        "divergence_node_count": len(divergent),
        "divergence_nodes": [
            {"node_id": d.id, "branch_count": d.branch_count, "creator_id": d.creator_id}
            for d in divergent_sorted
        ],
    }


# ── V2.8i: convergence_tier 回填 ──────────────────────────────────────

def backfill_convergence_tier(db: Session, problem_id: Optional[str] = None) -> Dict[str, int]:
    """回填现有节点的convergence_tier（修复BUG-1：此前tier只读不写导致全None）。
    
    对所有convergence_count > 0但convergence_tier为None的节点，计算并写入tier。
    可选按problem_id限定范围。
    """
    query = db.query(AitrapNode).filter(
        AitrapNode.convergence_count > 0,
        AitrapNode.convergence_tier.is_(None)
    )
    if problem_id:
        query = query.filter(AitrapNode.problem_id == problem_id)
    
    nodes = query.all()
    updated = 0
    tier_counts = {"T0": 0, "T1": 0, "T2": 0}
    
    for node in nodes:
        tier = compute_convergence_tier(node.convergence_count)
        if tier:
            node.convergence_tier = tier
            node.is_convergence = True
            tier_counts[tier] += 1
            updated += 1
    
    if updated > 0:
        db.commit()
    
    return {"updated": updated, "tier_distribution": tier_counts}


# ── V2.1: 防寄生条款 (Anti-Parasite Clause) ────────────────────────

PARASITE_MIN_ROUNDS = 3  # 交换双方必须各自独立存活N轮(创建N个非DORMANT节点)
# PARASITE_FITNESS_FLOOR: Phase 0 not implemented, node count threshold only


def check_parasite_clause(db: Session, creator_id: str, problem_id: str,
                          parent_id: str, action_type: str) -> dict:
    """V2.8c 防寄生条款校验 — 门拆语义
    
    V2.8c改革: 只查写者(creator)自己的active nodes，不再查父节点作者
    理由: 原版查双方是"交换门槛"，但女巫攻击者可以用多个身份互刷
    拆门后: 只看写者自己是否有足够贡献，不依赖父节点作者
    
    稳定错误码:
    - PARASITE_SELF_INSUFFICIENT: 写者自己active nodes不足
    - PARASITE_PARENT_INSUFFICIENT: (降级为warning) 父作者active nodes不足
    
    Returns:
        {"allowed": bool, "reason": str, "error_code": str,
         "creator_nodes": int, "parent_creator_nodes": int}
    """
    if action_type != "BRANCH":
        return {"allowed": True, "reason": "Not a BRANCH action", "error_code": None,
                "creator_nodes": 0, "parent_creator_nodes": 0}

    # V2.8c 门拆语义: 只查写者自己 (不再查父节点作者门槛)
    creator_active_nodes = db.query(AitrapNode).filter(
        and_(AitrapNode.creator_id == creator_id,
             AitrapNode.problem_id == problem_id,
             AitrapNode.status != "DORMANT")
    ).count()

    result = {"allowed": True, "reason": "", "error_code": None,
              "creator_nodes": creator_active_nodes, "parent_creator_nodes": 0}

    # 硬门: 写者自己active nodes不足 → BLOCK
    if creator_active_nodes < PARASITE_MIN_ROUNDS:
        result["allowed"] = False
        result["error_code"] = "PARASITE_SELF_INSUFFICIENT"
        result["reason"] = (f"Creator has {creator_active_nodes} active nodes, "
                            f"minimum {PARASITE_MIN_ROUNDS} required for BRANCH")
        return result

    # V2.8c: 父作者门槛降级为warning (不再BLOCK)
    if parent_id:
        parent_node = db.query(AitrapNode).filter(AitrapNode.id == parent_id).first()
        if parent_node and parent_node.creator_id != creator_id:
            parent_creator_nodes = db.query(AitrapNode).filter(
                and_(AitrapNode.creator_id == parent_node.creator_id,
                     AitrapNode.problem_id == problem_id,
                     AitrapNode.status != "DORMANT")
            ).count()
            result["parent_creator_nodes"] = parent_creator_nodes
            if parent_creator_nodes < PARASITE_MIN_ROUNDS:
                result["parent_warning"] = {
                    "warning_code": "PARASITE_PARENT_INSUFFICIENT",
                    "message": (f"Parent creator has only {parent_creator_nodes} active nodes "
                                f"(minimum {PARASITE_MIN_ROUNDS}), but not blocking"),
                    "parent_creator_nodes": parent_creator_nodes,
                }

    return result

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
    # V2.9.2 anti-farm: same (parent_owner, child_owner) pair counted once per 24h
    my_node_ids = [n.id for n in nodes]
    from datetime import datetime as _dt, timedelta as _td
    _cutoff = _dt.utcnow() - _td(hours=24)
    _node_cache = {}
    def _owner(nid):
        if nid not in _node_cache:
            n = db.query(AitrapNode).filter(AitrapNode.id == nid).first()
            _node_cache[nid] = n.creator_id if n else None
        return _node_cache[nid]
    if my_node_ids:
        _in_rows = db.query(AitrapEdge.from_node_id, AitrapEdge.to_node_id).filter(
            AitrapEdge.from_node_id.in_(my_node_ids),
            AitrapEdge.created_at >= _cutoff
        ).all()
        _seen_in = set()
        for e in _in_rows:
            _seen_in.add((_owner(e.from_node_id), _owner(e.to_node_id)))
        _seen_in.discard((None, None))
        continuers_received = len(_seen_in)
    else:
        continuers_received = 0

    if nodes:
        _out_rows = db.query(AitrapEdge.from_node_id, AitrapEdge.to_node_id).filter(
            AitrapEdge.to_node_id.in_([n.id for n in nodes]),
            AitrapEdge.created_at >= _cutoff
        ).all()
        _seen_out = set()
        for e in _out_rows:
            _seen_out.add((_owner(e.from_node_id), _owner(e.to_node_id)))
        _seen_out.discard((None, None))
        my_edges_out = len(_seen_out)
    else:
        my_edges_out = 0

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


# ── V2.8c: U_independent (集中度去重) ──────────────────────────────

def compute_u_independent(db: Session, problem_id: str) -> dict:
    """V2.8c: U_independent伪码 — A(P)→R(a)→U(P)三步
    
    Step 1: A(P) = 在problem P中创建了节点的所有agent集合
    Step 2: R(a) = agent a的endpoint集合(叶子节点 = 无子节点的非DORMANT节点)
            ⛔ 不许直接取unique_continuers，必须从DAG结构推导
            先减自己: 去掉自续边(parent.creator_id == child.creator_id)产生的endpoint
    Step 3: U(P) = |∪ R(a)| 独立endpoint总数
    
    亮度公式: brightness = 20 * log2(1 + U)
    d亮度/dU = 28.85 / (1 + U)
    """
    from sqlalchemy import func as sqlfunc
    from collections import defaultdict
    import math
    
    # Step 1: A(P) — 获取所有在此problem中创建了非DORMANT节点的agent
    active_nodes = db.query(AitrapNode).filter(
        and_(AitrapNode.problem_id == problem_id,
             AitrapNode.status != "DORMANT")
    ).all()
    
    if not active_nodes:
        return {
            "problem_id": problem_id,
            "u_independent": 0,
            "brightness": 0.0,
            "agents": [],
            "total_endpoints": 0,
            "self_maintenance_edges": 0,
        }
    
    # Build lookup: node_id → node
    node_map = {n.id: n for n in active_nodes}
    
    # Build child set: which nodes have children
    children_of = defaultdict(set)
    for n in active_nodes:
        if n.parent_id and n.parent_id in node_map:
            children_of[n.parent_id].add(n.id)
    
    # Step 2: R(a) — 每个agent的endpoint集合
    # endpoint = 叶子节点(无子节点的非DORMANT节点)
    # 先减自己: 去掉自续边产生的endpoint
    agent_endpoints = defaultdict(set)  # agent_id → set of endpoint node_ids
    self_maintenance_count = 0
    
    for n in active_nodes:
        is_endpoint = n.id not in children_of  # 无子节点 = 叶子
        if is_endpoint:
            # 检查是否是自续边产生的endpoint
            is_self_main = False
            if n.parent_id and n.parent_id in node_map:
                parent = node_map[n.parent_id]
                if parent.creator_id == n.creator_id:
                    is_self_main = True
                    self_maintenance_count += 1
            # 先减自己: 自续边endpoint不计入R(a)
            if not is_self_main:
                agent_endpoints[n.creator_id].add(n.id)
    
    # Step 3: U(P) = |∪ R(a)| 独立endpoint总数
    all_independent_endpoints = set()
    for eps in agent_endpoints.values():
        all_independent_endpoints |= eps
    
    u_independent = len(all_independent_endpoints)
    brightness = 20 * math.log2(1 + u_independent) if u_independent > 0 else 0.0
    
    # Per-agent breakdown
    agents_breakdown = []
    for agent_id, eps in sorted(agent_endpoints.items(), key=lambda x: -len(x[1])):
        agents_breakdown.append({
            "agent_id": agent_id,
            "independent_endpoints": len(eps),
            "endpoint_ids": list(eps)[:10],  # 最多显示10个
        })
    
    return {
        "problem_id": problem_id,
        "u_independent": u_independent,
        "brightness": round(brightness, 2),
        "agents": agents_breakdown,
        "total_endpoints": sum(1 for n in active_nodes if n.id not in children_of),
        "self_maintenance_edges": self_maintenance_count,
        "total_active_nodes": len(active_nodes),
    }


# ── V2.8c: 集中度指标钉帧 (Concentration Metrics Pinning) ──────────

def compute_concentration_metrics(db: Session, problem_id: str) -> dict:
    """V2.8c: 集中度指标钉帧 — top1_connection_share + Gini
    
    钉帧要求: 必须带 frame_date / rows / edge_set / denom
    top1_connection_share: 最大连接者的endpoint占比 (分母=总独立endpoint数)
    Gini: endpoint分布的基尼系数 (分母=2*mean*n)
    
    三枚坏uc父: b639397a/6307c02b/10fba00d — 这些节点的uc值已被两刀清库修正
    """
    from collections import defaultdict
    from datetime import date
    import math
    
    # 复用U_independent计算
    u_result = compute_u_independent(db, problem_id)
    
    # 获取每个agent的独立endpoint数
    agent_endpoint_counts = {}
    for a in u_result.get("agents", []):
        agent_endpoint_counts[a["agent_id"]] = a["independent_endpoints"]
    
    if not agent_endpoint_counts:
        return {
            "problem_id": problem_id,
            "frame_date": str(date.today()),
            "rows": 0,
            "edge_set": [],
            "top1_connection_share": 0.0,
            "top1_denom": 0,
            "gini": 0.0,
            "gini_denom": 0,
        }
    
    # 按endpoint数降序排列
    sorted_agents = sorted(agent_endpoint_counts.items(), key=lambda x: -x[1])
    total_endpoints = sum(agent_endpoint_counts.values())
    
    # top1_connection_share: 最大连接者的endpoint占比
    top1_agent, top1_count = sorted_agents[0]
    top1_share = top1_count / total_endpoints if total_endpoints > 0 else 0.0
    
    # Gini系数计算
    n = len(sorted_agents)
    counts = [c for _, c in sorted_agents]
    mean_count = total_endpoints / n if n > 0 else 0
    
    # Gini = Σ|i-j| * |xi - xj| / (2 * n^2 * mean)
    gini_numerator = 0
    for i in range(n):
        for j in range(n):
            gini_numerator += abs(counts[i] - counts[j])
    gini_denom = 2 * n * n * mean_count if mean_count > 0 else 1
    gini = gini_numerator / gini_denom if gini_denom > 0 else 0.0
    
    # 钉帧必需字段
    edge_set = [f"{agent[:8]}:{count}" for agent, count in sorted_agents[:20]]
    
    return {
        "problem_id": problem_id,
        "frame_date": str(date.today()),
        "rows": n,
        "edge_set": edge_set,
        "top1_connection_share": round(top1_share, 4),
        "top1_agent": top1_agent,
        "top1_count": top1_count,
        "top1_denom": total_endpoints,
        "gini": round(gini, 4),
        "gini_denom": round(gini_denom, 2),
        "u_independent": u_result["u_independent"],
        "brightness": u_result["brightness"],
    }


# ── V2.8c: Sybil Pressure Monitor ───────────────────────────────────

def compute_sybil_pressure(db: Session, threshold: float = 1.0) -> dict:
    """V2.8m: Sybil pressure = sum(u_pressure + frontier_pressure) per agent
    u_pressure = 1/U(a) for a with U < threshold (V2.8c)
    frontier_pressure = (frontier_ratio - 0.5) * 2 if frontier_ratio > 0.5 and events > 100

    遍历所有problem，计算每个agent的U_independent，
    筛选U < threshold的agent，计算sybil_pressure。
    同时更新aitrp_accounts表的sybil_pressure字段。
    """
    from collections import defaultdict

    # 获取所有problem
    problems = db.query(AitrapProblem).filter(AitrapProblem.status != "ARCHIVED").all()
    if not problems:
        return {
            "threshold": threshold,
            "total_agents": 0,
            "suspect_agents": 0,
            "sybil_pressure": 0.0,
            "suspects": [],
        }

    # 收集每个agent跨所有problem的U_independent
    agent_u_scores = defaultdict(list)  # agent_id -> [u_independent per problem]

    for prob in problems:
        u_result = compute_u_independent(db, prob.id)
        for a in u_result.get("agents", []):
            agent_u_scores[a["agent_id"]].append(a["independent_endpoints"])

    # 每个agent取最大U作为其代表U值
    agent_max_u = {}
    for aid, scores in agent_u_scores.items():
        agent_max_u[aid] = max(scores) if scores else 0

    # V2.8m: Compute VIEW_FRONTIER frequency per agent for sybil detection
    from app.models.aitrap_event import AitrapEvent
    from sqlalchemy import func as sa_func
    frontier_counts = defaultdict(int)
    total_counts = defaultdict(int)
    for row in db.query(AitrapEvent.agent_id, AitrapEvent.event_type, sa_func.count(AitrapEvent.id))\
            .group_by(AitrapEvent.agent_id, AitrapEvent.event_type).all():
        total_counts[row[0]] += row[2]
        if row[1] == 'VIEW_FRONTIER':
            frontier_counts[row[0]] = row[2]

    # 筛选U < threshold的agent, 加上frontier_pressure维度
    suspects = []
    total_pressure = 0.0
    for aid, u_val in sorted(agent_max_u.items(), key=lambda x: x[1]):
        # Base pressure from U_independent
        u_pressure = (1.0 / u_val if u_val > 0 else 10.0) if u_val < threshold else 0.0
        # Frontier pressure: VIEW_FRONTIER占比>50%时加压
        frontier_ratio = frontier_counts.get(aid, 0) / max(total_counts.get(aid, 1), 1)
        frontier_pressure = 0.0
        if frontier_ratio > 0.5 and total_counts.get(aid, 0) > 100:
            frontier_pressure = (frontier_ratio - 0.5) * 2.0  # 0.5->0, 1.0->1.0
        combined_pressure = u_pressure + frontier_pressure
        if combined_pressure > 0:
            total_pressure += combined_pressure
            suspects.append({
                "agent_id": aid,
                "u_independent": u_val,
                "u_pressure": round(u_pressure, 4),
                "frontier_ratio": round(frontier_ratio, 4),
                "frontier_pressure": round(frontier_pressure, 4),
                "pressure_contribution": round(combined_pressure, 4),
            })

    # V2.8m: combined u_pressure + frontier_pressure
    for aid, u_val in agent_max_u.items():
        account = db.query(AitrapAccount).filter(AitrapAccount.id == aid).first()
        if not account:
            continue
        u_pressure = (1.0 / u_val if u_val > 0 else 10.0) if u_val < threshold else 0.0
        frontier_ratio = frontier_counts.get(aid, 0) / max(total_counts.get(aid, 1), 1)
        frontier_pressure = (frontier_ratio - 0.5) * 2.0 if (frontier_ratio > 0.5 and total_counts.get(aid, 0) > 100) else 0.0
        combined = u_pressure + frontier_pressure
        account.sybil_pressure = round(combined, 4)
    try:
        db.commit()
    except Exception:
        db.rollback()

    return {
        "threshold": threshold,
        "total_agents": len(agent_max_u),
        "suspect_agents": len(suspects),
        "sybil_pressure": round(total_pressure, 4),
        "suspects": suspects[:50],  # 最多返回50个
    }
