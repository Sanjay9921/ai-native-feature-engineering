"""
Test suite for pure feature transform functions in features/transforms.py in isolation.

Exercises:
- Normal case (customer with standard multi-record history)
- Zero-activity case (customer with zero transactions receives explicit spec default)
- Single-record case (customer with exactly one transaction)
- Time-window boundary case (transaction exactly on inclusive/exclusive time boundary)
"""

import pandas as pd
import pytest
from features import transforms


@pytest.fixture
def sample_customers():
    return pd.DataFrame({
        "customer_id": [1, 2, 3, 4],
        "signup_date": pd.to_datetime(["2025-01-01", "2025-06-01", "2026-01-01", "2026-07-01"]),
        "acquisition_channel": ["organic", "paid_search", "referral", "social"],
        "region": ["north", "south", "east", "west"],
        "churned": [0, 1, 0, 1],
    })


@pytest.fixture
def sample_transactions():
    # as_of = "2026-08-01"
    # Customer 1: Normal multiple txns (some in 90d, some older, 1 returned)
    # Customer 2: Single txn in 90d
    # Customer 3: Txn right on boundary (exactly 90 days before 2026-08-01: 2026-05-03)
    # Customer 4: Zero txns (omitted from transactions table)
    return pd.DataFrame({
        "transaction_id": [101, 102, 103, 104, 105],
        "customer_id": [1, 1, 1, 2, 3],
        "txn_timestamp": pd.to_datetime([
            "2026-07-15 12:00:00",  # Cust 1 (recent)
            "2026-06-01 10:00:00",  # Cust 1 (recent, returned)
            "2025-03-01 09:00:00",  # Cust 1 (old)
            "2026-07-20 14:00:00",  # Cust 2 (single record)
            "2026-05-03 00:00:00",  # Cust 3 (boundary: exactly 90 days prior)
        ]),
        "amount": [50.0, 30.0, 100.0, 75.0, 120.0],
        "is_returned": [0, 1, 0, 0, 0],
    })


@pytest.fixture
def sample_monthly_agg():
    # Monthly aggregates for customer 1 and 2
    return pd.DataFrame({
        "customer_id": [1, 1, 2],
        "txn_month": pd.to_datetime(["2026-06-01", "2026-07-01", "2026-07-01"]),
        "monthly_spend": [30.0, 50.0, 75.0],
        "monthly_txn_count": [1, 1, 1],
        "monthly_returns": [1, 0, 0],
    })


def test_normal_case(sample_customers, sample_transactions, sample_monthly_agg):
    """Test customer with regular transaction history (Customer 1)."""
    as_of = "2026-08-01"
    recency = transforms.compute_recency_days(sample_customers, sample_transactions, as_of)
    assert recency.loc[1] < 20.0  # Approx 16.5 days

    txn_count = transforms.compute_txn_count_90d(sample_customers, sample_transactions, as_of)
    assert txn_count.loc[1] == 2  # 2 txns in trailing 90 days

    spend = transforms.compute_recent_spend_90d(sample_customers, sample_transactions, as_of)
    assert spend.loc[1] == 50.0  # Only non-returned amount (101: 50.0)

    return_rate = transforms.compute_return_rate_90d(sample_customers, sample_transactions, as_of)
    assert return_rate.loc[1] == 0.5  # 1 returned out of 2 in 90d window

    active_months = transforms.compute_active_months_12m(sample_customers, sample_monthly_agg, as_of)
    assert active_months.loc[1] == 2


def test_zero_activity_case(sample_customers, sample_transactions, sample_monthly_agg):
    """Test customer with zero transactions (Customer 4) receives explicit defaults."""
    as_of = "2026-08-01"
    recency = transforms.compute_recency_days(sample_customers, sample_transactions, as_of)
    assert recency.loc[4] == 999.0

    txn_count = transforms.compute_txn_count_90d(sample_customers, sample_transactions, as_of)
    assert txn_count.loc[4] == 0

    spend = transforms.compute_recent_spend_90d(sample_customers, sample_transactions, as_of)
    assert spend.loc[4] == 0.0

    return_rate = transforms.compute_return_rate_90d(sample_customers, sample_transactions, as_of)
    assert return_rate.loc[4] == 0.0

    active_months = transforms.compute_active_months_12m(sample_customers, sample_monthly_agg, as_of)
    assert active_months.loc[4] == 0


def test_single_record_case(sample_customers, sample_transactions):
    """Test customer with exactly one transaction (Customer 2)."""
    as_of = "2026-08-01"
    txn_count = transforms.compute_txn_count_90d(sample_customers, sample_transactions, as_of)
    assert txn_count.loc[2] == 1

    spend = transforms.compute_recent_spend_90d(sample_customers, sample_transactions, as_of)
    assert spend.loc[2] == 75.0

    return_rate = transforms.compute_return_rate_90d(sample_customers, sample_transactions, as_of)
    assert return_rate.loc[2] == 0.0


def test_time_window_boundary_case(sample_customers, sample_transactions):
    """Test transaction exactly at the 90-day boundary (Customer 3: 2026-05-03 00:00:00)."""
    as_of = "2026-08-01"
    # Exactly 90 days before 2026-08-01 is 2026-05-03 00:00:00.
    # [as_of - 90d, as_of) is inclusive of 2026-05-03.
    txn_count = transforms.compute_txn_count_90d(sample_customers, sample_transactions, as_of)
    assert txn_count.loc[3] == 1

    spend = transforms.compute_recent_spend_90d(sample_customers, sample_transactions, as_of)
    assert spend.loc[3] == 120.0
