# Artifact Notes — Engineering Log & Retrospective

This log records technical decisions, edge cases encountered, and implementation refinements made during the build of the churn feature pipeline.

---

## 1. Zero-Activity Customer Handling & Reindexing Trap
- **Issue**: In `customers.csv`, there are 1,500 total customers, but exactly 81 customers have zero historical transaction records in `transactions.db`.
- **Initial Risk**: Groupby operations in pandas (e.g. `transactions.groupby('customer_id')['amount'].sum()`) omit non-transacting customer IDs completely. A naive merge or join without explicit reindexing drops these 81 customers or leaves them as `NaN`.
- **Resolution**: Every feature transform in `features/transforms.py` explicitly constructs a complete index of all customer IDs (`pd.Index(customers["customer_id"].unique())`) and calls `.reindex(all_cust_ids, fill_value=default_val)`. For `recency_days`, the default is `999.0`; for counts/active months/spend/return rates, the default is strictly `0` or `0.0`. This ensures all 1,500 rows are cleanly populated with non-nullable values.

---

## 2. Temporal Anti-Leakage & As-Of Date Parameterization
- **Issue**: Standardizing temporal boundaries across heterogeneous data sources.
- **Initial Risk**: Ingestion routines or transforms might inadvertently capture transactions occurring on or after `as_of` if time filtering is not strictly inclusive/exclusive (`[start_dt, as_of_dt)`).
- **Resolution**: `as_of` is threaded as an explicit parameter into `build_features()` and down into each transform function. Filtering strictly enforces `txn_timestamp < as_of` and `txn_month < as_of`. At no point is `datetime.now()` or an unparameterized date accessed.

---

## 3. Atomic Multi-Version Feature Store Flipping
- **Issue**: In `feature_store/store.py`, registering a new feature version requires setting `is_latest = 1` for the new version and updating prior versions to `is_latest = 0`.
- **Initial Risk**: If this operation is performed without a database transaction or out-of-order, a crash between operations could leave two versions flagged as `is_latest = 1` or none at all.
- **Resolution**: Implemented SQLite `BEGIN IMMEDIATE` transactions in `store.py`. In a single atomic transaction:
  1. The new version number is computed via `COALESCE(MAX(version), 0) + 1`.
  2. The parquet snapshot is written to disk (with immutability checks preventing overwrite).
  3. Prior versions are updated to `is_latest = 0`.
  4. The new row is inserted with `is_latest = 1`.
  5. The transaction commits atomically.
- **Validation**: Verified that `get_latest()` always returns the highest version number and `list_versions()` lists all versions in descending order.

---

## 4. Multi-Source Grain & ETL Lag Discrepancy
- **Decision**: Sourcing rolling windows from `transactions.db` vs `transactions_monthly_agg.parquet`.
- **Resolution**: Features requiring rolling 30/90-day windows or exact days of recency (`recency_days`, `txn_count_90d`, `recent_spend_90d`, `return_rate_90d`) are exclusively sourced from `transactions.db`. Sourcing them from monthly aggregates would introduce up to 30 days of ETL lag and calendar month misalignment. In contrast, `active_months_12m` naturally aligns with calendar month activity rollups and is sourced from `transactions_monthly_agg.parquet`, avoiding high-volume event log scanning.
