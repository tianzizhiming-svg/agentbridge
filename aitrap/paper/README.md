# AITRAP Paper: Analysis Code & Data

Reproducibility package for:

> **A Lognormal Heavy-Tailed Distribution in Multi-Agent Knowledge Trees**

## Directory Structure

```
paper/
├── README.md                  — This file
├── data/
│   ├── paper_dataset.json     — Frozen dataset snapshot (CC distribution, depth, creators)
│   └── clauset_post_results.json — Post-intervention Clauset analysis results
├── figures/
│   ├── fig1_cc_ccdf.png       — CC distribution CCDF with power-law & lognormal fits
│   ├── fig2_depth_distribution.png — Pre/post depth distribution comparison
│   ├── fig3_action_types.png  — Action type distribution
│   ├── fig4_creator_strategies.png — Creator volume vs efficiency scatter
│   └── fig5_pre_post_comparison.png — Pre/post intervention summary
└── scripts/
    ├── gen_dataset.py         — Generate paper_dataset.json from live database
    ├── clauset_post.py        — Post-intervention Clauset-Shalizi-Newman analysis
    ├── gen_figures_v2.py      — Generate all 5 figures
    └── gen_fig4_fix.py        — Figure 4 with creator cluster annotations
```

## Key Results

### Pre-Intervention (Sep 12 – Oct 1, 2026)
| Metric | Value |
|--------|-------|
| Total nodes | 2,839 (paper) / 3,850 (DB snapshot) |
| Power-law exponent α | 2.18 (95% CI: [1.87, 2.49]) |
| Lognormal LLR vs power law | R = -2.86, p = 0.004 |
| Depth-1 concentration | 82% |
| Gini coefficient (CC>0) | 0.503 |
| Top-5% creator share | 82.9% |

### Post-Intervention (Oct 1 – Oct 13, 2026)
| Metric | Value |
|--------|-------|
| Total nodes | 66,088 |
| CC-positive nodes | 6,517 (9.9%) |
| Power-law exponent α | 1.997 |
| KS statistic D | 0.1615 |
| vs exponential | R = 15.815, p < 0.0001 |
| vs lognormal | R = -5.781, p = 0.291 |
| Gini coefficient (CC>0) | 0.070 |
| Depth-1 concentration | 21.3% |

**Key finding**: The Phase 0 intervention (uniform frontier visibility) reduced
Gini from 0.503 to 0.070 — a 86% reduction in inequality — while the CC
distribution remains consistent with a power law (α ≈ 2.0).

## Reproduction

### Requirements
```bash
pip install numpy scipy matplotlib powerlaw
```

### Generate dataset from live database
```bash
python scripts/gen_dataset.py
# Requires access to AITRAP SQLite database at /opt/aitrap/aitrap.db
# Outputs: data/paper_dataset.json
```

### Run post-intervention Clauset analysis
```bash
python scripts/clauset_post.py
# Requires access to AITRAP SQLite database
# Outputs: data/clauset_post_results.json
```

### Generate figures
```bash
python scripts/gen_figures_v2.py
# Uses data/paper_dataset.json + hardcoded paper values
# Outputs: figures/fig1-fig5
```

## Data Provenance

- **Database**: AITRAP production SQLite (`/opt/aitrap/aitrap.db` on atlas server)
- **Snapshot time**: 2026-10-13T03:15:35 UTC
- **Pre-intervention window**: 2026-09-12 to 2026-10-01
- **Post-intervention window**: 2026-10-01 to 2026-10-13
- **Note**: The live database continues to evolve. `paper_dataset.json` freezes
  the exact values used in the paper. Numbers in the paper text (2,839 nodes,
  α=2.18) come from an earlier analysis snapshot and may differ slightly from
  the frozen JSON (3,850 nodes, α=2.177) due to ongoing agent activity.

## Citation

```bibtex
@article{lei2026lognormal,
  title={A Lognormal Heavy-Tailed Distribution in Multi-Agent Knowledge Trees},
  author={Lei Zhenbing; Lei Chang},
  year={2026},
  note={arXiv preprint}
}
```

## License

Apache 2.0 (same as AgentBridge project)
