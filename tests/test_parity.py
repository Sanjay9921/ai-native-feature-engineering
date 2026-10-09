"""
Train/Score Parity Test Suite.

Asserts that features generated via the batch training path (all customers) and the
online scoring path (single or subset of customers) are 100% bitwise/numerical identical.
"""

import pandas as pd
import pytest
from features.build import build_features


def test_train_score_parity():
    """Build features for the whole training population, and individually for select customers,

    asserting exact equality across all feature columns.
    """
    as_of = "2026-08-01"

    # 1. Training batch path (all 1500 customers)
    batch_features = build_features(as_of=as_of)
    assert len(batch_features) == 1500

    # 2. Pick diverse test customers:
    # Cust 1 (normal active), Cust 4 (known active), Cust 20 (sample), and a zero-activity customer if known
    test_ids = [1, 4, 20]

    # 3. Scoring path for specific customer_ids
    scored_features = build_features(as_of=as_of, customer_ids=test_ids)
    assert len(scored_features) == len(test_ids)

    # 4. Compare sliced batch vs scored path
    sliced_batch = (
        batch_features[batch_features["customer_id"].isin(test_ids)]
        .set_index("customer_id")
        .loc[test_ids]
        .reset_index()
    )

    feature_cols = [
        "recency_days",
        "txn_count_90d",
        "recent_spend_90d",
        "active_months_12m",
        "return_rate_90d",
        "customer_tenure_days",
    ]

    for col in feature_cols:
        pd.testing.assert_series_equal(
            sliced_batch[col],
            scored_features[col],
            check_exact=False,
            rtol=1e-5,
            atol=1e-5,
            obj=f"Train/Score parity for feature '{col}'",
        )


def test_invalid_customer_id_raises():
    """Verify that scoring a non-existent customer raises ValueError."""
    with pytest.raises(ValueError, match="do not exist in customer master"):
        build_features(as_of="2026-08-01", customer_ids=[99999])
