# Feature Version Comparison Report

This document reports the empirical distribution shifts and impact analysis for the two versioned features defined in `feature_spec.md`, retrieved directly from `feature_store/`.

---

## 1. Feature: `txn_count_window`
- **Versions Compared**: v1 (`window_days = 90`) vs. v2 (`window_days = 30`)
- **Total Population**: 1500 customers
- **Customers with Changed Values**: 1087 (72.5%)
- **Rank Correlation (Spearman)**: 0.6032

### Summary Statistics
| Metric | v1 (90-Day Window) | v2 (30-Day Window) |
|---|---|---|
| **Mean** | 2.277 | 0.791 |
| **Std Dev** | 1.793 | 0.994 |
| **Min** | 0.0 | 0.0 |
| **25%** | 1.0 | 0.0 |
| **Median (50%)** | 2.0 | 1.0 |
| **75%** | 3.0 | 1.0 |
| **Max** | 12.0 | 7.0 |

### Business & Model Interpretation
- **Would a consuming model notice this change?**: **Yes, substantially.**
- **Rationale**: Shortening the rolling observation window from 90 days to 30 days causes a marked contraction in transaction counts across 72.5% of the population. In a 90-day window, customers with sporadic purchasing still register 1–3 transactions, masking recent inactivity. In the 30-day window (v2), recent drop-offs collapse immediately to 0. A tree-based churn model or logistic regression scoring engine will immediately detect this acute inactivity signal, enabling timely churn intervention before a quarterly lapse matures.

---

## 2. Feature: `recent_spend_adjusted`
- **Versions Compared**: v1 (`repeat_purchase_multiplier = 2.0`) vs. v2 (`repeat_purchase_multiplier = 2.25`)
- **Total Population**: 1500 customers
- **Customers with Changed Values**: 886 (59.1%)
- **Rank Correlation (Spearman)**: 0.9998

### Summary Statistics
| Metric | v1 (Multiplier = 2.0) | v2 (Multiplier = 2.25) |
|---|---|---|
| **Mean** | $206.46 | $230.51 |
| **Std Dev** | $236.37 | $266.50 |
| **Min** | $0.00 | $0.00 |
| **25%** | $25.89 | $25.89 |
| **Median (50%)** | $133.40 | $146.77 |
| **75%** | $308.13 | $345.99 |
| **Max** | $2008.44 | $2259.49 |

### Business & Model Interpretation
- **Would a consuming model notice this change?**: **Yes, for high-value segment separation.**
- **Rationale**: Increasing the repeat purchase multiplier from 2.0 to 2.25 affects customers with $\ge 2$ orders in the trailing 90 days. While single-order and zero-activity customers remain unaffected, the upper quartile and maximum spend expand significantly. For high-value churn intervention models (e.g. prioritizing customer success outreach based on expected customer lifetime value at risk), this recalibration widens the risk margin between multi-order repeat buyers and one-and-done buyers.

---

## 3. Registry & Lineage Verification
- All versions are verified as independently retrievable via `feature_store.store.get_version(feature_name, version)`.
- `is_latest` in `feature_registry` correctly flags Version 2 for both versioned features.
