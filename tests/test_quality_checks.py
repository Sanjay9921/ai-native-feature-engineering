"""
Test suite for data quality checks in features/quality_checks.py.

Asserts that clean input passes checks, while deliberately corrupted input
(injected nulls, extreme values, out-of-range rates, altered counts) correctly
fails and raises ValueError when fatal=True.
"""

import numpy as np
import pandas as pd
import pytest
from features.quality_checks import (
    check_drift,
    check_no_unexpected_nulls,
    check_outliers,
    check_row_reconciliation,
    check_zero_activity_defaults,
    run_all_checks,
)


@pytest.fixture
def clean_features():
    return pd.DataFrame({
        "customer_id": [1, 2, 3],
        "recency_days": [15.0, 45.0, 999.0],
        "txn_count_90d": [3, 1, 0],
        "recent_spend_90d": [150.0, 45.0, 0.0],
        "active_months_12m": [4, 1, 0],
        "return_rate_90d": [0.25, 0.0, 0.0],
        "customer_tenure_days": [300.0, 150.0, 50.0],
        "as_of_date": "2026-08-01",
    })


def test_clean_input_passes(clean_features):
    """Clean features DataFrame passes all checks."""
    res = run_all_checks(
        clean_features,
        expected_count=3,
        zero_activity_customer_ids=[3],
        fatal=True,
    )
    assert res["all_passed"] is True


def test_injected_null_fails(clean_features):
    """Injected null into feature column triggers check failure."""
    bad_df = clean_features.copy()
    bad_df.loc[1, "recent_spend_90d"] = np.nan

    with pytest.raises(ValueError, match="Unexpected nulls detected"):
        check_no_unexpected_nulls(bad_df, fatal=True)

    res = check_no_unexpected_nulls(bad_df, fatal=False)
    assert res["passed"] is False
    assert "recent_spend_90d" in res["failing_features"]


def test_outlier_rate_fails(clean_features):
    """Return rate > 1.0 triggers outlier violation."""
    bad_df = clean_features.copy()
    bad_df.loc[0, "return_rate_90d"] = 1.5

    with pytest.raises(ValueError, match="Feature outlier / range boundaries violated"):
        check_outliers(bad_df, fatal=True)


def test_outlier_spend_fails(clean_features):
    """Spend >= 50,000.0 triggers outlier violation."""
    bad_df = clean_features.copy()
    bad_df.loc[0, "recent_spend_90d"] = 75000.0

    with pytest.raises(ValueError, match="Feature outlier / range boundaries violated"):
        check_outliers(bad_df, fatal=True)


def test_zero_activity_default_violation(clean_features):
    """Zero-activity customer receiving non-default value triggers failure."""
    bad_df = clean_features.copy()
    bad_df.loc[2, "recency_days"] = 12.0  # Customer 3 should be 999.0

    with pytest.raises(ValueError, match="Zero-activity defaults violated"):
        check_zero_activity_defaults(bad_df, zero_activity_customer_ids=[3], fatal=True)


def test_row_reconciliation_fails(clean_features):
    """Mismatched row count triggers reconciliation failure."""
    with pytest.raises(ValueError, match="Row count mismatch"):
        check_row_reconciliation(clean_features, expected_count=1500, fatal=True)


def test_distribution_drift_detection(clean_features):
    """Drift check identifies features whose mean shifted significantly."""
    ref_df = clean_features.copy()
    curr_df = clean_features.copy()
    curr_df["recent_spend_90d"] = curr_df["recent_spend_90d"] * 5.0  # 400% shift

    res = check_drift(curr_df, reference=ref_df, max_mean_pct_drift=0.50, fatal=False)
    assert res["passed"] is False
    assert "recent_spend_90d" in res["failing_features"]
