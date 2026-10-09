"""
Runnable-standalone data-quality checks (drift / null / outlier) against a built
features DataFrame, implementing every check listed in your confirmed
`feature_spec.md`'s data-quality section.

Each check function returns a clear pass/fail dictionary plus which rows/features
triggered a failure, raising ValueError on fatal data defects.
"""

from typing import Any
import numpy as np
import pandas as pd


def check_no_unexpected_nulls(features: pd.DataFrame, fatal: bool = True) -> dict[str, Any]:
    """Fail if any feature column has null/NaN values after default application.

    Zero-activity defaults guarantee that no feature column should contain nulls.
    """
    feature_cols = [c for c in features.columns if c not in ("customer_id", "as_of_date")]
    null_counts = features[feature_cols].isnull().sum()
    failing_features = null_counts[null_counts > 0].to_dict()

    passed = len(failing_features) == 0
    result = {
        "check": "check_no_unexpected_nulls",
        "passed": passed,
        "failing_features": failing_features,
        "failing_rows": features[features[feature_cols].isnull().any(axis=1)]["customer_id"].tolist(),
    }

    if fatal and not passed:
        raise ValueError(f"Data Quality Failure: Unexpected nulls detected in features: {failing_features}")

    return result


def check_zero_activity_defaults(
    features: pd.DataFrame,
    zero_activity_customer_ids: list[int] | set[int] | None = None,
    fatal: bool = True,
) -> dict[str, Any]:
    """Verify that zero-activity customers strictly receive declared defaults.

    Defaults per feature_spec.md:
    - recency_days == 999.0
    - txn_count_90d == 0
    - recent_spend_90d == 0.0
    - active_months_12m == 0
    - return_rate_90d == 0.0
    """
    if zero_activity_customer_ids is None:
        # Default known 81 customer IDs if not provided
        # or we check rows where txn_count_90d == 0 and active_months_12m == 0
        zero_activity_customer_ids = set()

    expected_defaults = {
        "recency_days": 999.0,
        "txn_count_90d": 0,
        "recent_spend_90d": 0.0,
        "active_months_12m": 0,
        "return_rate_90d": 0.0,
    }

    mismatches = {}
    if zero_activity_customer_ids:
        zero_subset = features[features["customer_id"].isin(zero_activity_customer_ids)]
        for col, expected_val in expected_defaults.items():
            if col in zero_subset.columns:
                bad_mask = zero_subset[col] != expected_val
                if bad_mask.any():
                    mismatches[col] = zero_subset.loc[bad_mask, "customer_id"].tolist()

    passed = len(mismatches) == 0
    result = {
        "check": "check_zero_activity_defaults",
        "passed": passed,
        "mismatches": mismatches,
    }

    if fatal and not passed:
        raise ValueError(f"Data Quality Failure: Zero-activity defaults violated for customers: {mismatches}")

    return result


def check_outliers(features: pd.DataFrame, fatal: bool = True) -> dict[str, Any]:
    """Fail if a feature has values outside declared sane boundaries:

    - return_rate_90d in [0.0, 1.0]
    - recent_spend_90d >= 0.0 and < 50,000.0
    - recency_days >= 0.0
    - txn_count_90d >= 0
    - active_months_12m in [0, 12]
    - customer_tenure_days >= 0
    """
    violations = {}

    if "return_rate_90d" in features.columns:
        bad = features[(features["return_rate_90d"] < 0.0) | (features["return_rate_90d"] > 1.0)]
        if not bad.empty:
            violations["return_rate_90d"] = bad["customer_id"].tolist()

    if "recent_spend_90d" in features.columns:
        bad = features[(features["recent_spend_90d"] < 0.0) | (features["recent_spend_90d"] >= 50000.0)]
        if not bad.empty:
            violations["recent_spend_90d"] = bad["customer_id"].tolist()

    if "recency_days" in features.columns:
        bad = features[features["recency_days"] < 0.0]
        if not bad.empty:
            violations["recency_days"] = bad["customer_id"].tolist()

    if "txn_count_90d" in features.columns:
        bad = features[features["txn_count_90d"] < 0]
        if not bad.empty:
            violations["txn_count_90d"] = bad["customer_id"].tolist()

    if "active_months_12m" in features.columns:
        bad = features[(features["active_months_12m"] < 0) | (features["active_months_12m"] > 12)]
        if not bad.empty:
            violations["active_months_12m"] = bad["customer_id"].tolist()

    if "customer_tenure_days" in features.columns:
        bad = features[features["customer_tenure_days"] < 0]
        if not bad.empty:
            violations["customer_tenure_days"] = bad["customer_id"].tolist()

    passed = len(violations) == 0
    result = {
        "check": "check_outliers",
        "passed": passed,
        "violations": violations,
    }

    if fatal and not passed:
        raise ValueError(f"Data Quality Failure: Feature outlier / range boundaries violated: {violations}")

    return result


def check_row_reconciliation(
    features: pd.DataFrame,
    expected_count: int,
    fatal: bool = True,
) -> dict[str, Any]:
    """Reconcile row count matches expected customer population exactly."""
    actual_count = len(features)
    passed = actual_count == expected_count
    result = {
        "check": "check_row_reconciliation",
        "passed": passed,
        "actual_count": actual_count,
        "expected_count": expected_count,
    }
    if fatal and not passed:
        raise ValueError(
            f"Data Quality Failure: Row count mismatch. Expected {expected_count}, got {actual_count}."
        )
    return result


def check_drift(
    features: pd.DataFrame,
    reference: pd.DataFrame | None = None,
    max_mean_pct_drift: float = 0.50,
    fatal: bool = False,
) -> dict[str, Any]:
    """Compare feature distribution against a reference snapshot.

    Flags features whose mean shifts by more than max_mean_pct_drift.
    """
    if reference is None:
        return {"check": "check_drift", "passed": True, "note": "No reference provided; drift check skipped."}

    feature_cols = [
        c for c in features.columns
        if c in reference.columns and c not in ("customer_id", "as_of_date")
    ]
    drift_metrics = {}
    failing_features = {}

    for col in feature_cols:
        curr_mean = float(features[col].mean())
        ref_mean = float(reference[col].mean())
        if ref_mean != 0:
            pct_diff = abs(curr_mean - ref_mean) / abs(ref_mean)
        else:
            pct_diff = abs(curr_mean - ref_mean)

        drift_metrics[col] = {
            "current_mean": curr_mean,
            "reference_mean": ref_mean,
            "pct_diff": pct_diff,
        }
        if pct_diff > max_mean_pct_drift:
            failing_features[col] = pct_diff

    passed = len(failing_features) == 0
    result = {
        "check": "check_drift",
        "passed": passed,
        "metrics": drift_metrics,
        "failing_features": failing_features,
    }

    if fatal and not passed:
        raise ValueError(f"Data Quality Failure: Significant distribution drift detected: {failing_features}")

    return result


def run_all_checks(
    features: pd.DataFrame,
    expected_count: int | None = 1500,
    zero_activity_customer_ids: list[int] | set[int] | None = None,
    reference: pd.DataFrame | None = None,
    fatal: bool = True,
) -> dict[str, Any]:
    """Run all primary data quality validations and return aggregate report."""
    results = {
        "null_check": check_no_unexpected_nulls(features, fatal=fatal),
        "outlier_check": check_outliers(features, fatal=fatal),
    }

    if expected_count is not None:
        results["row_reconciliation"] = check_row_reconciliation(features, expected_count, fatal=fatal)

    if zero_activity_customer_ids:
        results["zero_activity_check"] = check_zero_activity_defaults(
            features, zero_activity_customer_ids, fatal=fatal
        )

    if reference is not None:
        results["drift_check"] = check_drift(features, reference, fatal=fatal)

    all_passed = all(r.get("passed", True) for r in results.values())
    results["all_passed"] = all_passed
    return results
