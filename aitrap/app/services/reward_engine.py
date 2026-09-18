"""AITRAP Reward Engine - v2.4 Seed+Impact

V2.4 核心原则：奖励结果不奖励动作
- 所有动作只给微量seed credit
- 真正reward由节点后续影响(deferred_reward)决定
- Phase 0: deferred_reward只记录不发放
- Echo: Phase 0只检测不惩罚(discount=1.0)

v2.2 legacy:
- Dual pool, per-problem penalty, cooldown, system-only trap_bonus
"""
import logging
from datetime import datetime, timedelta
from typing import Tuple
from app.models.aitrap_account import AitrapAccount
from app.models.aitrap_agent_problem import AitrapAgentProblem
from app.models.aitrap_node import AitrapNode

logger = logging.getLogger(__name__)

# ── V2.4: Seed Constants (微量行动燃料) ─────────────────────────
SEED_CREATE = 20
SEED_DEEPEN = 20
SEED_BRANCH = [40, 20, 5]  # marginal decay: 1st/2nd/3rd
SEED_SOLVE_EXPLORATION = 15
SEED_SOLVE_CLAIM = 0  # SOLVE_CLAIM不给seed，只有penalty
SEED_CONVERGE = 10  # V2.5: 汇聚动作seed
SEED_RECONSTRUCT = 10  # V2.5: 重构动作seed

# ── V2.4: Impact Score Weights (延迟奖励) ───────────────────────
IMPACT_WEIGHT_CONTINUERS = 30    # unique_continuers x 30
IMPACT_WEIGHT_BRANCH = 50        # branch_count x 50
IMPACT_WEIGHT_CONVERGENCE = 100  # convergence_count x 100
IMPACT_WEIGHT_SURVIVAL = 5       # survival_days x 5

# ── Legacy Constants (保留用于兼容) ─────────────────────────────
REWARD_CREATE = 100
REWARD_DEEPEN = 150
REWARD_DEEPEN_DEPTH_BONUS = 15
REWARD_SOLVE_EXPLORATION = 80
REWARD_BRANCH = [300, 150, 30]
PENALTY_SOLVE_CLAIM_BASE = -50
PENALTY_SOLVE_CLAIM_CAP = -500
TRAP_BONUS_AMOUNT = 400

# ── V2.4: INITIAL_GRANT 500→2000 Exploration Credit ─────────────
INITIAL_GRANT = 2000

# ── Penalty Calculation (unchanged) ──────────────────────────────

def calculate_solve_claim_penalty(solve_claim_count: int) -> int:
    penalty = max(PENALTY_SOLVE_CLAIM_BASE * (2 ** solve_claim_count), PENALTY_SOLVE_CLAIM_CAP)
    return penalty

def calculate_solve_claim_cooldown(solve_claim_count: int) -> timedelta:
    hours = min(2 ** solve_claim_count, 24)
    return timedelta(hours=hours)

def solve_claim_consequence(solve_claim_count: int) -> Tuple[int, timedelta]:
    penalty = calculate_solve_claim_penalty(solve_claim_count)
    cooldown = calculate_solve_claim_cooldown(solve_claim_count)
    return penalty, cooldown

# ── Trap Bonus (unchanged) ───────────────────────────────────────

def calculate_trap_bonus(claimer_account: AitrapAccount, trap_node: AitrapNode) -> Tuple[int, int]:
    if trap_node.creator_id != "system":
        return 0, TRAP_BONUS_AMOUNT
    earned_balance = claimer_account.earned_balance
    actual_bonus = min(TRAP_BONUS_AMOUNT, max(0, earned_balance))
    burn_amount = TRAP_BONUS_AMOUNT - actual_bonus
    return actual_bonus, burn_amount

# ── BRANCH Reward (legacy) ───────────────────────────────────────

def calculate_branch_reward(parent_child_branch_count: int) -> int:
    if parent_child_branch_count < len(REWARD_BRANCH):
        return REWARD_BRANCH[parent_child_branch_count]
    return 0

# ── Depth Bonus (unchanged) ──────────────────────────────────────

def calculate_depth_bonus(depth: int, base_reward: int) -> int:
    if depth >= 5:
        return int(base_reward * 0.1)
    return 0

# ── Convergence Tier (unchanged) ─────────────────────────────────

def calculate_convergence_tier(path_count: int) -> str:
    if path_count >= 5:
        return "T3"
    elif path_count == 4:
        return "T2"
    elif path_count == 3:
        return "T1"
    else:
        return "T0"

# ── V2.4: Seed Reward (Phase 0: 只给seed) ───────────────────────

def calculate_seed_reward(action_type: str, parent_child_branch_count: int = 0) -> int:
    """Phase 0: 所有动作只给微量seed credit"""
    if action_type == "CREATE":
        return SEED_CREATE
    elif action_type == "DEEPEN":
        return SEED_DEEPEN
    elif action_type == "BRANCH":
        idx = min(parent_child_branch_count, len(SEED_BRANCH) - 1)
        return SEED_BRANCH[idx]
    elif action_type == "SOLVE_EXPLORATION":
        return SEED_SOLVE_EXPLORATION
    elif action_type == "SOLVE_CLAIM":
        return SEED_SOLVE_CLAIM
    elif action_type == "CONVERGE":
        return SEED_CONVERGE
    elif action_type == "RECONSTRUCT":
        return SEED_RECONSTRUCT
    return 0

# ── V2.4: Impact Score (延迟奖励计算) ───────────────────────────

def calculate_impact_score(node) -> int:
    """计算节点的impact score，Phase 0只记录不发放
    
    Impact = unique_continuers*30 + branch_count*50 
             + convergence_count*100 + survival_days*5
    Echo节点impact=0（没人跟echo走）
    """
    if node.is_echo:
        return 0
    
    survival_days = 0
    if node.created_at:
        survival_days = (datetime.utcnow() - node.created_at).days
    
    score = (
        (node.unique_continuers or 0) * IMPACT_WEIGHT_CONTINUERS
        + (node.branch_count or 0) * IMPACT_WEIGHT_BRANCH
        + (node.convergence_count or 0) * IMPACT_WEIGHT_CONVERGENCE
        + survival_days * IMPACT_WEIGHT_SURVIVAL
    )
    return score

# ── Account Operations ───────────────────────────────────────────

def grant_initial_balance(account: AitrapAccount, amount: int = INITIAL_GRANT):
    account.grant_balance = amount
    account.initial_grant = amount
    account.grant_claimed = True
    logger.info(f"Granted {amount} exploration_credit to {account.azone_id}")
