# Self-Review & Resolution Log (`review_log.md`)

This log documents the Step 3 code review conducted across all components of the churn feature pipeline (ingestion, transformation, build module, feature store, data quality checks, documentation, and test suites).

---

## 1. Review Scope & Checklist

- [x] **Train/Score Parity**: Exactly one shared code path in `features/build.py`. No hidden conditional branches for scoring mode other than final customer ID row selection.
- [x] **Zero-Activity Default Handling**: All 81 zero-transaction customers explicitly reindexed and assigned non-null spec defaults (`999.0` for recency, `0`/`0.0` for counts, spend, and rates).
- [x] **Temporal Anti-Leakage**: Strict adherence to point-in-time constraints. Timestamp filters use `< as_of` without relying on system clock or hardcoded cutoff dates.
- [x] **Feature Store Multi-Versioning**: At least two distinct features versioned (`txn_count_window` and `recent_spend_adjusted`), each with $\ge 2$ versions registered with parameter differences and distinct business rationales.
- [x] **Atomic Metadata Updates**: SQLite `BEGIN IMMEDIATE` transactions in `store.py` ensure `is_latest` flips atomically and parquet files are strictly immutable.
- [x] **Data Quality & Sane Range Boundaries**: Range checks enforce return rates $\in [0.0, 1.0]$, spend $\in [0.0, 50000.0)$, and reconcile against 1,500 total customer records.

---

## 2. Review Findings & Resolutions

### Finding 1: Path Resolution Portability across Execution Roots
- **Observation**: Depending on whether scripts are run from repository root or `starter-code/`, relative paths like `"data/customers.csv"` might point to `./data` or `../data`.
- **Severity**: Medium.
- **Resolution**: Enhanced `_resolve_path()` in `features/ingest.py` to transparently probe local and parent directories, ensuring seamless execution in both environments without breaking pure I/O separation.

### Finding 2: Parquet Immutability Enforcement
- **Observation**: A buggy registration call might re-register a version number and silently overwrite an existing parquet file on disk.
- **Severity**: High.
- **Resolution**: Added explicit file existence checks in `feature_store/store.py` prior to writing parquet snapshots, raising `FileExistsError` if a versioned artifact already exists.

### Finding 3: Customer Index Ordering in Online Scoring Mode
- **Observation**: When scoring a list of customer IDs like `[42, 1, 1500]`, pandas `.isin()` filtering alters the row order to match the dataframe's natural order rather than the caller's request order.
- **Severity**: Low.
- **Resolution**: In `features/build.py`, explicitly reindexed the filtered scoring DataFrame using `.set_index("customer_id").loc[customer_ids].reset_index()` to guarantee exact row-ordering preservation.

---

## 3. Final Verification Status
All unit and integration tests across `test_transforms.py`, `test_parity.py`, `test_quality_checks.py`, and `test_feature_store.py` pass cleanly. Parity mutation testing confirms that any deviation between training and scoring paths triggers immediate test failure.
