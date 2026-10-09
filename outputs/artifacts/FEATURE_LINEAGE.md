# Feature Lineage Documentation

This document documents the end-to-end data lineage for every feature produced by the churn feature engineering pipeline and stored in `feature_store/`. 

Every candidate feature and every experimental version is registered with immutable version numbers in `feature_store/registry.db` (`feature_registry` table) and value snapshots in `feature_store/values/`.

---

## 1. Candidate Feature Lineage (Base Feature Set `v1`)

### 1.1 `recency_days` (v1)
- **Feature Name**: `recency_days`
- **Version**: `1` (`is_latest = 1`)
- **Source Columns**: `data/transactions.db:transactions.txn_timestamp`
- **Output Data Type**: `float64` (Non-nullable)
- **Transform Summary**: `(as_of - max(txn_timestamp)).days` strictly for transactions `< as_of`. Customers with zero transactions are defaulted to `999.0`.
- **Business Rationale**: Measures temporal disengagement; long lapses in purchasing cadence indicate imminent churn risk.
- **Parameters**: `{}`
- **Parquet Snapshot**: `feature_store/values/recency_days__v1.parquet`

### 1.2 `txn_count_90d` (v1)
- **Feature Name**: `txn_count_90d`
- **Version**: `1` (`is_latest = 1`)
- **Source Columns**: `data/transactions.db:transactions.txn_timestamp`
- **Output Data Type**: `int64` (Non-nullable)
- **Transform Summary**: `count(*)` where `as_of - 90d <= txn_timestamp < as_of`. Customers with zero transactions defaulted to `0`.
- **Business Rationale**: Captures quarterly purchasing frequency; sudden drops precede complete account abandonment.
- **Parameters**: `{"window_days": 90}`
- **Parquet Snapshot**: `feature_store/values/txn_count_90d__v1.parquet`

### 1.3 `recent_spend_90d` (v1)
- **Feature Name**: `recent_spend_90d`
- **Version**: `1` (`is_latest = 1`)
- **Source Columns**: `data/transactions.db:transactions.amount,txn_timestamp,is_returned`
- **Output Data Type**: `float64` (Non-nullable)
- **Transform Summary**: `sum(amount)` where `is_returned == 0` and within trailing 90-day window `[as_of - 90d, as_of)`. Zero-activity defaulted to `0.0`.
- **Business Rationale**: Monetary wallet-share decay signals customer migration to competitors.
- **Parameters**: `{}`
- **Parquet Snapshot**: `feature_store/values/recent_spend_90d__v1.parquet`

### 1.4 `active_months_12m` (v1)
- **Feature Name**: `active_months_12m`
- **Version**: `1` (`is_latest = 1`)
- **Source Columns**: `data/transactions_monthly_agg.parquet:txn_month`
- **Output Data Type**: `int64` (Non-nullable)
- **Transform Summary**: `count(distinct txn_month)` where `as_of - 365d <= txn_month < as_of`. Zero-activity defaulted to `0`.
- **Business Rationale**: Measures habituation consistency across annual cycle; sporadic engagement indicates churn susceptibility.
- **Parameters**: `{}`
- **Parquet Snapshot**: `feature_store/values/active_months_12m__v1.parquet`

### 1.5 `return_rate_90d` (v1)
- **Feature Name**: `return_rate_90d`
- **Version**: `1` (`is_latest = 1`)
- **Source Columns**: `data/transactions.db:transactions.is_returned,txn_timestamp`
- **Output Data Type**: `float64` (Non-nullable)
- **Transform Summary**: `sum(is_returned) / count(*)` over trailing 90-day window `[as_of - 90d, as_of)`. If `count == 0`, defaulted to `0.0`.
- **Business Rationale**: Elevated return rates reflect product mismatch or fulfillment friction preceding churn.
- **Parameters**: `{}`
- **Parquet Snapshot**: `feature_store/values/return_rate_90d__v1.parquet`

### 1.6 `customer_tenure_days` (v1)
- **Feature Name**: `customer_tenure_days`
- **Version**: `1` (`is_latest = 1`)
- **Source Columns**: `data/customers.csv:signup_date`
- **Output Data Type**: `float64` (Non-nullable)
- **Transform Summary**: `(as_of - signup_date).days` across all customer master records.
- **Business Rationale**: Controls for lifecycle baseline hazard rate, separating early onboarding attrition from mature customer churn.
- **Parameters**: `{}`
- **Parquet Snapshot**: `feature_store/values/customer_tenure_days__v1.parquet`

---

## 2. Multi-Version Feature Lineage (Experimentation & Calibration)

### 2.1 Feature: `txn_count_window`
- **Version 1** (`is_latest = 0`):
  - **Parameters**: `{"window_days": 90}`
  - **Transform**: Trailing 90-day transaction count.
  - **Business Rationale**: v1 uses 90-day quarterly window to establish baseline transaction cadence.
  - **Parquet Snapshot**: `feature_store/values/txn_count_window__v1.parquet`
- **Version 2** (`is_latest = 1`):
  - **Parameters**: `{"window_days": 30}`
  - **Transform**: Trailing 30-day transaction count.
  - **Business Rationale**: v2 shortens window to 30 days to detect acute purchasing collapse for rapid churn intervention.
  - **Parquet Snapshot**: `feature_store/values/txn_count_window__v2.parquet`

### 2.2 Feature: `recent_spend_adjusted`
- **Version 1** (`is_latest = 0`):
  - **Parameters**: `{"repeat_purchase_multiplier": 2.0, "window_days": 90}`
  - **Transform**: Trailing 90-day net spend scaled by 2.0x for customers with $\ge 2$ non-returned orders.
  - **Business Rationale**: v1 tests 2.0x weight on returning customers with multiple orders.
  - **Parquet Snapshot**: `feature_store/values/recent_spend_adjusted__v1.parquet`
- **Version 2** (`is_latest = 1`):
  - **Parameters**: `{"repeat_purchase_multiplier": 2.25, "window_days": 90}`
  - **Transform**: Trailing 90-day net spend scaled by 2.25x for customers with $\ge 2$ non-returned orders.
  - **Business Rationale**: v2 recalibrates multiplier to 2.25 after observing underweighted value in returning distribution.
  - **Parquet Snapshot**: `feature_store/values/recent_spend_adjusted__v2.parquet`
