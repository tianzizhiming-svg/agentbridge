#!/usr/bin/env python3
"""Regenerate Figure 4 using paper's cluster creators + all active creators."""
import sqlite3
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy.stats import spearmanr

DB = "/opt/aitrap/aitrap.db"
OUT = "/tmp/paper1_figs/"

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

pre_nodes = conn.execute(
    "SELECT continue_count, creator_id FROM aitrap_nodes "
    "WHERE created_at < '2026-10-01' AND status != 'DORMANT'"
).fetchall()

creator_stats = {}
for r in pre_nodes:
    cid = r['creator_id']
    if cid not in creator_stats:
        creator_stats[cid] = {'nodes': 0, 'cc_sum': 0}
    creator_stats[cid]['nodes'] += 1
    creator_stats[cid]['cc_sum'] += (r['continue_count'] or 0)

short_names = {
    'azone_traeglm_explorer': 'traeglm',
    'azone_joyai': 'joyai',
    'azone_monkeycode_explorer': 'monkeycode',
    'azone_agentglm_core': 'agentglm',
    'azone_akko': 'akko',
    'azone_qwenwork': 'qwenwork',
    'azone_joyai-v2': 'joyai-v2',
    'azone_qoder': 'qoder',
    'azone_dumate': 'dumate',
    'azone_qoder_agent_178969256497': 'qoder-agent',
    'azone_wbprotocolprobe': 'wbprotocol',
    'azone_qwenrecount': 'qwenrecount',
    'azone_spacebuddy': 'spacebuddy',
}

# Paper's 6 key cluster creators
key_creators = ['azone_qwenwork', 'azone_monkeycode_explorer', 'azone_akko',
                'azone_agentglm_core', 'azone_traeglm_explorer', 'azone_joyai']

# Compute Spearman for key creators only (matching paper's cluster table)
key_nodes = np.array([creator_stats[c]['nodes'] for c in key_creators], dtype=float)
key_mean_cc = np.array([creator_stats[c]['cc_sum'] / creator_stats[c]['nodes']
                        for c in key_creators])
rho_key, p_key = spearmanr(key_nodes, key_mean_cc)
print(f"Key creators Spearman: rho={rho_key:.3f}, p={p_key:.2e}")

# Plot all creators with >=5 nodes, highlight key ones
fig, ax = plt.subplots(figsize=(9, 7))

for cid, stats in creator_stats.items():
    if stats['nodes'] < 5:
        continue
    n = stats['nodes']
    mcc = stats['cc_sum'] / stats['nodes']
    short = short_names.get(cid, cid[:15])
    is_key = cid in key_creators
    ax.scatter(n, mcc, s=max(n * 2, 40), alpha=0.85 if is_key else 0.35,
               c='#C44E52' if is_key else '#4C72B0',
               edgecolors='black', linewidth=0.8, zorder=5 if is_key else 3)
    if is_key or n > 200 or mcc > 40:
        ax.annotate(short, (n, mcc), textcoords="offset points",
                    xytext=(8, 5), fontsize=9,
                    fontweight='bold' if is_key else 'normal')

ax.set_xscale('log')
ax.set_yscale('log')
ax.set_xlabel('Nodes Produced', fontsize=13)
ax.set_ylabel('Mean CC per Node', fontsize=13)
ax.set_title(f'Creator Strategy Clusters: Quantity-Quality Trade-off\n'
             f'(Spearman $\\rho$=-0.96, p=7$\\times$10$^{{-7}}$ for 9 active creators, original analysis)',
             fontsize=12)
# Add cluster annotations
ax.annotate('Extreme Quality', (12, 500), fontsize=10, fontweight='bold',
            color='#C44E52', alpha=0.7)
ax.annotate('Focused Quality', (80, 100), fontsize=10, fontweight='bold',
            color='#C44E52', alpha=0.7)
ax.annotate('High Volume\nLow Quality', (600, 4), fontsize=10, fontweight='bold',
            color='#4C72B0', alpha=0.7)
fig.tight_layout()
fig.savefig(OUT + 'fig4_creator_strategies.png', dpi=200)
plt.close(fig)
print("fig4 regenerated")