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

# ── V2.8m: Phase 0 Type & Depth Coefficients (deferred reward) ───
# deferred_reward = unique_continuers × type_coeff × depth_coeff
# These are the single source of truth; calculate_deferred_rewards.py imports from here.
TYPE_COEFF = {
    'DEEPEN': 1,
    'BRANCH': 2,           # 权重50的动作不能被忽视
    'CONVERGE': 3,         # 先×3不×5，等跨problem bug修后再调
    'SOLVE_CLAIM': 5,
    'SOLVE_EXPLORATION': 1,
    'RECONSTRUCT': 8,      # 先×8不×20
}
TYPE_COEFF_CROSS_PROBLEM = 1  # 跨problem嫁接不享受倍率
DEFAULT_TYPE_COEFF = 1

def get_depth_coeff(depth) -> int:
    """Phase 0 depth coefficient mapping.
    depth=0: ×1 (problem root)
    depth=1: ×1
    depth=2: ×2
    depth=3: ×3
    depth≥4: ×5
    """
    if depth is None:
        return 1  # fallback for nodes without depth
    if depth <= 1:
        return 1
    if depth == 2:
        return 2
    if depth == 3:
        return 3
    return 5  # depth >= 4

# ── V2.8m: Cold Activation Multipliers ────────────────────────────
# Cold node = cc=0 for 7+ days. When activated by a new child:
#   cold_creator_bonus = (BASE_REWARD + cold_node.deferred_reward) × multiplier
#   Multiplier depends on the action type that activates the cold node.
COLD_ACTIVATION_MULTIPLIER = {
    'DEEPEN': 3,
    'BRANCH': 2,            # same as type_coeff (conservative)
    'CONVERGE': 5,
    'SOLVE_CLAIM': 5,
    'SOLVE_EXPLORATION': 1, # no bonus for exploration activating cold
    'RECONSTRUCT': 8,
}
COLD_THRESHOLD_DAYS = 7     # cc=0 for 7+ days = cold
BASE_REWARD_PER_NODE = 5    # survival layer base reward

def is_cold_node(node) -> bool:
    """Check if a node qualifies as cold (cc=0, 7+ days old, non-DORMANT)."""
    from datetime import datetime, timedelta
    if node.unique_continuers > 0:
        return False
    if node.status == 'DORMANT':
        return False
    if not node.created_at:
        return False
    age = (datetime.utcnow() - node.created_at).days
    return age >= COLD_THRESHOLD_DAYS

# ── V2.8c: 自续计分改革 ──────────────────────────────────────────
SELF_MAINTENANCE = 2  # 自续边seed：写者在自己节点上继续，与动作类型无关

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

def calculate_seed_reward(action_type: str, parent_child_branch_count: int = 0,
                          is_self_maintenance: bool = False,
                          depth: int = None,
                          echo_discount: float = 1.0) -> int:
    """Phase 0: 所有动作只给微量seed credit
    V2.8c: 自续边(parent.creator_id==creator_id) → SELF_MAINTENANCE=2, 与动作类型无关
    V2.9 Phase A: 后置刀 — depth>=4 不再创建时×10，改为首次独立续接补发（见 calculate_continuation_bonus）
    V2.9 Phase A: echo折扣重启 — is_echo=True 的节点 seed × echo_discount
    """
    if is_self_maintenance:
        return SELF_MAINTENANCE  # 自续边不享受depth倍率（防自刷）
    base = 0
    if action_type == "CREATE":
        base = SEED_CREATE
    elif action_type == "DEEPEN":
        base = SEED_DEEPEN
    elif action_type == "BRANCH":
        idx = min(parent_child_branch_count, len(SEED_BRANCH) - 1)
        base = SEED_BRANCH[idx]
    elif action_type == "SOLVE_EXPLORATION":
        base = SEED_SOLVE_EXPLORATION
    elif action_type == "SOLVE_CLAIM":
        base = SEED_SOLVE_CLAIM
    elif action_type == "CONVERGE":
        base = SEED_CONVERGE
    elif action_type == "RECONSTRUCT":
        base = SEED_RECONSTRUCT
    # V2.9 Phase A: depth×10 已移除，由后置刀补发（calculate_continuation_bonus）
    # V2.9 Phase A: echo折扣
    if echo_discount < 1.0:
        base = int(base * echo_discount)
    return base


# ── V2.9 Phase A: 后置刀 — 首次独立续接补发 ──────────────────────

# 补发目标乘子（原 God决议#1 depth>=4 ×10）
CONTINUATION_BONUS_MULTIPLIER = 10

def calculate_continuation_bonus(node, is_self_maintenance=False) -> int:
    """V2.9 Phase A 后置刀：节点首次获得独立续接者时，补发 depth×10 差额。
    
    创建时 depth>=4 DEEPEN 只拿基础价（×1），首次被独立续接后补发到 ×10。
    判据是"有没有别人愿意续你这枚"——农场自己造不出来。
    
    写时刀：同(parent,creator)第2+枚DEEPEN不补发（防单父灌水）。
    调用方需在补发前检查 same-parent-same-creator 排序。
    
    Args:
        node: 被续接的父节点（AitrapNode）
    Returns:
        补发金额（0 = 不符合补发条件）
    """
    if node.action_type != "DEEPEN":
        return 0
    if node.depth is None or node.depth < 4:
        return 0
    if is_self_maintenance:
        return 0
    # 补发差额：base×10 - base×1 = base×9
    # SEED_DEEPEN=20, 差额 = 20×9 = 180, 补发后总计 200
    return SEED_DEEPEN * (CONTINUATION_BONUS_MULTIPLIER - 1)

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
