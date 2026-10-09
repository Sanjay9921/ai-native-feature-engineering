# Parity & Integrity Verification Report (`PARITY_CHECK.md`)

This report records the verification results for train/score parity, parity mutation testing, and domain coverage analysis.

---

## 1. Train/Score Parity Verification
- **Guarantee**: The feature engineering pipeline executes exactly one shared entry point:
  `build_features(as_of: str, source_paths: dict | None = None, customer_ids: list[int] | None = None) -> pd.DataFrame`
- **Verification Method**: Evaluated all 1,500 customers via the batch training path (`customer_ids=None`), and independently evaluated individual and subset customer IDs (`[1, 4, 20]`) via the scoring path.
- **Result**: Feature values across all features (`recency_days`, `txn_count_90d`, `recent_spend_90d`, `active_months_12m`, `return_rate_90d`, `customer_tenure_days`) match exactly with zero discrepancy (`rtol=1e-5`, `atol=1e-5`).

---

## 2. Parity Mutation Check
To confirm that `test_parity.py` is truly load-bearing and capable of detecting silent parity divergence:
- **Mutation Tested**: In a scratch branch, introduced a subtle scoring divergence in `features/build.py`:
  ```python
  if customer_ids is not None:
      # Subtle divergence: apply different default or slight floating-point offset in scoring
      features_df.loc[features_df["customer_id"].isin(customer_ids), "recent_spend_90d"] += 0.05
  ```
- **Mutation Result**: `tests/test_parity.py::test_train_score_parity` failed immediately with `AssertionError: Train/Score parity for feature 'recent_spend_90d' values are different (tolerance 1e-05)`.
- **Conclusion**: The parity test suite is sensitive to even minimal drift between training and scoring evaluations, preventing accidental parity regressions.

---

## 3. Coverage-of-Intent Check

| Candidate Feature / DQ Check in `feature_spec.md` | Tested in Test Suite? | Test Location |
|---|---|---|
| `recency_days` normal & 999.0 zero-activity default | Yes | `tests/test_transforms.py::test_normal_case`, `test_zero_activity_case` |
| `txn_count_90d` 90-day window count & 0 default | Yes | `tests/test_transforms.py::test_normal_case`, `test_zero_activity_case` |
| `recent_spend_90d` non-returned spend & 0.0 default | Yes | `tests/test_transforms.py::test_normal_case`, `test_zero_activity_case` |
| `active_months_12m` monthly consistency & 0 default | Yes | `tests/test_transforms.py::test_normal_case`, `test_zero_activity_case` |
| `return_rate_90d` 90-day return fraction & 0.0 default | Yes | `tests/test_transforms.py::test_normal_case`, `test_zero_activity_case` |
| `customer_tenure_days` profile tenure | Yes | Covered in schema & build integration |
| Window boundary inclusive/exclusive handling | Yes | `tests/test_transforms.py::test_time_window_boundary_case` |
| Train/Score 100% numerical parity | Yes | `tests/test_parity.py::test_train_score_parity` |
| Non-existent customer scoring validation | Yes | `tests/test_parity.py::test_invalid_customer_id_raises` |
| Null check & zero-activity default enforcement | Yes | `tests/test_quality_checks.py::test_injected_null_fails`, `test_zero_activity_default_violation` |
| Outlier spend & return rate boundaries | Yes | `tests/test_quality_checks.py::test_outlier_rate_fails`, `test_outlier_spend_fails` |
| Row reconciliation (1500 records) | Yes | `tests/test_quality_checks.py::test_row_reconciliation_fails` |
| Feature distribution drift detection | Yes | `tests/test_quality_checks.py::test_distribution_drift_detection` |
| Feature store multi-version registration & retrieval | Yes | `tests/test_feature_store.py::test_feature_store_versioning_and_retrieval` |
| `is_latest` atomic flipping | Yes | `tests/test_feature_store.py::test_feature_store_versioning_and_retrieval` |
