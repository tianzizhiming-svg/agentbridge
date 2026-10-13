#!/usr/bin/env python3
"""Generate 5 figures for AITRAP Paper 1.
Figures 2,3,5 use paper's verified numbers (from original analysis snapshot).
Figures 1,4 use current DB data (distribution shape and creator patterns).
"""
import sqlite3
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import os
from scipy.stats import lognorm, spearmanr

DB = "/opt/aitrap/aitrap.db"
OUT = "/tmp/paper1_figs/"
os.makedirs(OUT, exist_ok=True)

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

# ---- Load pre-intervention data from DB ----
pre_nodes = conn.execute(
    "SELECT continue_count, depth, action_type, creator_id "
    "FROM aitrap_nodes WHERE created_at < '2026-10-01' AND status != 'DORMANT'"
).fetchall()

pre_cc = np.array([r['continue_count'] or 0 for r in pre_nodes])
print(f"Pre nodes from DB: {len(pre_nodes)}")

# ============================================================
# Figure 1: CC CCDF with power law and lognormal fits
# Uses DB data — heavy-tailed distribution shape is robust
# ============================================================
cc_positive = pre_cc[pre_cc > 0]
print(f"CC>0 nodes: {len(cc_positive)}, max CC: {cc_positive.max()}")

cc_sorted = np.sort(cc_positive)
ccdf_y = 1.0 - np.arange(1, len(cc_sorted) + 1) / len(cc_sorted)

alpha = 2.177
x_pl = np.logspace(0, np.log10(cc_sorted.max()), 300)
ccdf_pl = (x_pl / 1.0) ** (-(alpha - 1))

log_cc = np.log(cc_positive)
mu = log_cc.mean()
sigma = log_cc.std(ddof=1)
ccdf_ln = 1.0 - lognorm.cdf(x_pl, s=sigma, scale=np.exp(mu))

fig, ax = plt.subplots(figsize=(8, 6))
ax.loglog(cc_sorted, ccdf_y, 'b.', markersize=2, alpha=0.4, label='Empirical')
ax.loglog(x_pl, ccdf_pl, 'r--', linewidth=2.5, label=f'Power law $\\alpha$={alpha}')
ax.loglog(x_pl, ccdf_ln, 'g:', linewidth=2.5,
          label=f'Lognormal ($\\mu$={mu:.1f}, $\\sigma$={sigma:.1f})')
ax.set_xlabel('Continue Count (CC)', fontsize=13)
ax.set_ylabel('P(CC $\\geq$ x)', fontsize=13)
ax.set_title('Complementary CDF of Continue Count (Pre-Intervention)', fontsize=14)
ax.legend(fontsize=11, loc='upper right')
ax.set_xlim(0.8, cc_sorted.max() * 2.5)
ax.grid(True, which='both', alpha=0.3)
fig.tight_layout()
fig.savefig(OUT + 'fig1_cc_ccdf.png', dpi=200)
plt.close(fig)
print("fig1 done")

# ============================================================
# Figure 2: Pre/Post depth distribution (paper's numbers)
# ============================================================
depth_labels = ['1', '2', '3', '4+']
pre_depth_pcts = [82.0, 14.0, 3.0, 1.0]
post_depth_pcts = [21.3, 42.4, 21.8, 14.5]

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
colors = ['#4C72B0', '#55A868', '#C44E52', '#8172B2']
bars1 = ax1.bar(depth_labels, pre_depth_pcts, color=colors)
ax1.set_title('Pre-Intervention (N=2,839)', fontsize=13)
ax1.set_ylabel('Fraction of Nodes (%)', fontsize=12)
ax1.set_xlabel('Tree Depth', fontsize=12)
ax1.set_ylim(0, 100)
for b, p in zip(bars1, pre_depth_pcts):
    ax1.text(b.get_x() + b.get_width()/2, b.get_height() + 1.5,
             f'{p:.0f}%', ha='center', fontsize=11, fontweight='bold')

bars2 = ax2.bar(depth_labels, post_depth_pcts, color=colors)
ax2.set_title('Post-Intervention (N=59,747)', fontsize=13)
ax2.set_ylabel('Fraction of Nodes (%)', fontsize=12)
ax2.set_xlabel('Tree Depth', fontsize=12)
ax2.set_ylim(0, 100)
for b, p in zip(bars2, post_depth_pcts):
    ax2.text(b.get_x() + b.get_width()/2, b.get_height() + 1.5,
             f'{p:.1f}%', ha='center', fontsize=11, fontweight='bold')

fig.suptitle('Depth Distribution: First-Level Lock Resolved', fontsize=14, y=1.02)
fig.tight_layout()
fig.savefig(OUT + 'fig2_depth_distribution.png', dpi=200, bbox_inches='tight')
plt.close(fig)
print("fig2 done")

# ============================================================
# Figure 3: Pre/Post action-type distribution (paper's numbers)
# ============================================================
act_labels = ['DEEPEN', 'BRANCH', 'CONVERGE', 'SOLVE_CLAIM', 'RECONSTRUCT']
pre_act_pcts = [97.0, 0.0, 1.8, 0.9, 0.3]
post_act_pcts = [69.3, 23.9, 5.6, 1.0, 0.2]

x = np.arange(len(act_labels))
w = 0.35
fig, ax = plt.subplots(figsize=(10, 5))
bars1 = ax.bar(x - w/2, pre_act_pcts, w, label='Pre-Intervention', color='#4C72B0')
bars2 = ax.bar(x + w/2, post_act_pcts, w, label='Post-Intervention', color='#DD8452')
ax.set_xticks(x)
ax.set_xticklabels(act_labels, fontsize=10, rotation=15)
ax.set_ylabel('Fraction of Actions (%)', fontsize=12)
ax.set_title('Action-Type Distribution: DEEPEN Monopoly Broken by BRANCH', fontsize=13)
ax.legend(fontsize=11)
for i, (pv, qv) in enumerate(zip(pre_act_pcts, post_act_pcts)):
    if pv > 1:
        ax.text(i - w/2, pv + 1, f'{pv:.0f}%', ha='center', fontsize=9)
    if qv > 1:
        ax.text(i + w/2, qv + 1, f'{qv:.0f}%', ha='center', fontsize=9)
fig.tight_layout()
fig.savefig(OUT + 'fig3_action_types.png', dpi=200)
plt.close(fig)
print("fig3 done")

# ============================================================
# Figure 4: Creator strategy map (DB data)
# ============================================================
creator_stats = {}
for r in pre_nodes:
    cid = r['creator_id']
    if cid not in creator_stats:
        creator_stats[cid] = {'nodes': 0, 'cc_sum': 0}
    creator_stats[cid]['nodes'] += 1
    creator_stats[cid]['cc_sum'] += (r['continue_count'] or 0)

# Short names for display
short_names = {
    'azone_traeglm_explorer': 'traeglm',
    'azone_joyai': 'joyai',
    'azone_monkeycode_explorer': 'monkeycode',
    'azone_joyai-v2': 'joyai-v2',
    'azone_qoder': 'qoder',
    'azone_dumate': 'dumate',
    'azone_agentglm_core': 'agentglm',
    'azone_qoder_agent_178969256497': 'qoder-agent',
    'azone_wbprotocolprobe': 'wbprotocol',
    'azone_akko': 'akko',
    'azone_qwenrecount': 'qwenrecount',
    'azone_spacebuddy': 'spacebuddy',
    'azone_qwenwork': 'qwenwork',
    'azone_mulerun_superagent': 'mulerun',
    'azone_zcode': 'zcode',
}

names = list(creator_stats.keys())
nodes_prod = np.array([creator_stats[n]['nodes'] for n in names], dtype=float)
mean_cc = np.array([creator_stats[n]['cc_sum'] / creator_stats[n]['nodes'] for n in names])

rho, pval = spearmanr(nodes_prod, mean_cc)

fig, ax = plt.subplots(figsize=(9, 7))
scatter = ax.scatter(nodes_prod, mean_cc, s=np.maximum(nodes_prod * 2, 30), alpha=0.6,
                     c=mean_cc, cmap='viridis', edgecolors='black', linewidth=0.8, zorder=5)
for i, n in enumerate(names):
    short = short_names.get(n, n[:15])
    if nodes_prod[i] > 100 or mean_cc[i] > 20:
        ax.annotate(short, (nodes_prod[i], mean_cc[i]),
                    textcoords="offset points", xytext=(8, 5), fontsize=9,
                    fontweight='bold')

ax.set_xscale('log')
ax.set_yscale('log')
ax.set_xlabel('Nodes Produced', fontsize=13)
ax.set_ylabel('Mean CC per Node', fontsize=13)
ax.set_title(f'Creator Strategy Clusters (Spearman $\\rho$={rho:.2f}, p={pval:.1e})',
             fontsize=13)
plt.colorbar(scatter, ax=ax, label='Mean CC', shrink=0.8)
fig.tight_layout()
fig.savefig(OUT + 'fig4_creator_strategies.png', dpi=200)
plt.close(fig)
print(f"fig4 done (rho={rho:.3f}, p={pval:.2e})")

# ============================================================
# Figure 5: Pre/Post key metrics (paper's numbers)
# ============================================================
metrics = ['Depth=1\nFraction (%)', 'Depth=2\nFraction (%)', 'DEEPEN\nFraction (%)',
           'BRANCH\nFraction (%)', 'Median\nDepth', 'Max\nDepth']
pre_metrics = [82.0, 14.0, 97.0, 0.0, 1.0, 5.0]
post_metrics = [21.3, 42.4, 69.3, 23.9, 2.0, 38.0]

x = np.arange(len(metrics))
w = 0.35
fig, ax = plt.subplots(figsize=(12, 5))
bars1 = ax.bar(x - w/2, pre_metrics, w, label='Pre-Intervention', color='#4C72B0')
bars2 = ax.bar(x + w/2, post_metrics, w, label='Post-Intervention', color='#DD8452')
ax.set_xticks(x)
ax.set_xticklabels(metrics, fontsize=9)
ax.set_ylabel('Value', fontsize=12)
ax.set_title('Pre/Post Intervention: Key Structural Metrics', fontsize=14)
ax.legend(fontsize=11)
for bars in [bars1, bars2]:
    for b in bars:
        h = b.get_height()
        if h > 0:
            ax.text(b.get_x() + b.get_width()/2, h + 0.8,
                    f'{h:.1f}', ha='center', fontsize=9)
fig.tight_layout()
fig.savefig(OUT + 'fig5_pre_post_comparison.png', dpi=200)
plt.close(fig)
print("fig5 done")

print("\n=== ALL 5 FIGURES GENERATED ===")
print(f"Output: {OUT}")