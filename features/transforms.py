"""
One pure function per candidate feature named in your confirmed `feature_spec.md`.

Each function:
- Is independent of any I/O (takes already-loaded DataFrames in, returns a Series/DataFrame out indexed by customer_id).
- Handles the zero-activity case explicitly, per the default feature_spec.md states.
- Only touches the source(s) feature_spec.md names for that feature.
- Follows strict anti-leakage temporal filtering: records with timestamp >= as_of are strictly excluded.
"""

import numpy as np
import pandas as pd


def compute_recency_days(
    customers: pd.DataFrame,
    transactions: pd.DataFrame,
    as_of: str,
    default_recency: float = 999.0,
) -> pd.Series:
    """Computes days since most recent transaction strictly prior to as_of.

    Source: data/transactions.db (transactions table)
    Zero-activity default: 999.0
    Formula: (as_of_datetime - max(txn_timestamp)).total_seconds() / 86400.0 (or .days)
    """
    as_of_dt = pd.to_datetime(as_of)
    all_cust_ids = pd.Index(customers["customer_id"].unique(), name="customer_id")

    # Anti-leakage filter
    valid_txns = transactions[transactions["txn_timestamp"] < as_of_dt]

    if valid_txns.empty:
        return pd.Series(default_recency, index=all_cust_ids, name="recency_days", dtype=float)

    # Max timestamp per customer
    latest_txn = valid_txns.groupby("customer_id")["txn_timestamp"].max()
    # Days since last transaction
    recency = (as_of_dt - latest_txn).dt.total_seconds() / 86400.0

    # Reindex over all customers, explicitly applying zero-activity default
    recency = recency.reindex(all_cust_ids, fill_value=default_recency)
    recency.name = "recency_days"
    return recency.astype(float)


def compute_txn_count_window(
    customers: pd.DataFrame,
    transactions: pd.DataFrame,
    as_of: str,
    window_days: int = 90,
) -> pd.Series:
    """Computes count of transactions within [as_of - window_days, as_of).

    Source: data/transactions.db (transactions table)
    Zero-activity default: 0
    Parameter: window_days (v1=90, v2=30)
    """
    as_of_dt = pd.to_datetime(as_of)
    start_dt = as_of_dt - pd.Timedelta(days=window_days)
    all_cust_ids = pd.Index(customers["customer_id"].unique(), name="customer_id")

    # Filter window [start_dt, as_of_dt)
    valid_txns = transactions[
        (transactions["txn_timestamp"] >= start_dt) & (transactions["txn_timestamp"] < as_of_dt)
    ]

    if valid_txns.empty:
        return pd.Series(0, index=all_cust_ids, name=f"txn_count_{window_days}d", dtype=int)

    # counts = valid_txns.groupby("customer_id")["transaction_id"].count()
    counts = valid_txns.groupby("customer_id").size()
    counts = counts.reindex(all_cust_ids, fill_value=0)
    counts.name = f"txn_count_{window_days}d"
    return counts.astype(int)


def compute_txn_count_90d(
    customers: pd.DataFrame,
    transactions: pd.DataFrame,
    as_of: str,
) -> pd.Series:
    """Standard candidate feature txn_count_90d (window_days=90)."""
    s = compute_txn_count_window(customers, transactions, as_of, window_days=90)
    s.name = "txn_count_90d"
    return s


def compute_recent_spend_90d(
    customers: pd.DataFrame,
    transactions: pd.DataFrame,
    as_of: str,
) -> pd.Series:
    """Computes sum of amount where as_of - 90 days <= txn_timestamp < as_of and is_returned == 0.

    Source: data/transactions.db (transactions table)
    Zero-activity default: 0.0
    """
    as_of_dt = pd.to_datetime(as_of)
    start_dt = as_of_dt - pd.Timedelta(days=90)
    all_cust_ids = pd.Index(customers["customer_id"].unique(), name="customer_id")

    valid_txns = transactions[
        (transactions["txn_timestamp"] >= start_dt)
        & (transactions["txn_timestamp"] < as_of_dt)
        & (transactions["is_returned"] == 0)
    ]

    if valid_txns.empty:
        return pd.Series(0.0, index=all_cust_ids, name="recent_spend_90d", dtype=float)

    spend = valid_txns.groupby("customer_id")["amount"].sum()
    spend = spend.reindex(all_cust_ids, fill_value=0.0)
    spend.name = "recent_spend_90d"
    return spend.astype(float)


def compute_recent_spend_adjusted(
    customers: pd.DataFrame,
    transactions: pd.DataFrame,
    as_of: str,
    repeat_purchase_multiplier: float = 2.0,
    window_days: int = 90,
) -> pd.Series:
    """Computes spend in window with repeat purchase multiplier applied to returning customers.

    If a customer has >= 2 non-returned transactions in the window, their spend is scaled
    by repeat_purchase_multiplier to weight repeat engagement value.
    Source: data/transactions.db
    Zero-activity default: 0.0
    Parameter: repeat_purchase_multiplier (v1=2.0, v2=2.25)
    """
    as_of_dt = pd.to_datetime(as_of)
    start_dt = as_of_dt - pd.Timedelta(days=window_days)
    all_cust_ids = pd.Index(customers["customer_id"].unique(), name="customer_id")

    valid_txns = transactions[
        (transactions["txn_timestamp"] >= start_dt)
        & (transactions["txn_timestamp"] < as_of_dt)
        & (transactions["is_returned"] == 0)
    ]

    if valid_txns.empty:
        return pd.Series(0.0, index=all_cust_ids, name="recent_spend_adjusted", dtype=float)

    grouped = valid_txns.groupby("customer_id").agg(
        total_spend=("amount", "sum"),
        order_count=("amount", "count"),
    )

    # Apply repeat_purchase_multiplier if order_count >= 2
    adjusted_spend = grouped.apply(
        lambda row: row["total_spend"] * repeat_purchase_multiplier
        if row["order_count"] >= 2
        else row["total_spend"],
        axis=1,
    )

    adjusted_spend = adjusted_spend.reindex(all_cust_ids, fill_value=0.0)
    adjusted_spend.name = "recent_spend_adjusted"
    return adjusted_spend.astype(float)


def compute_active_months_12m(
    customers: pd.DataFrame,
    monthly_agg: pd.DataFrame,
    as_of: str,
) -> pd.Series:
    """Computes count of distinct active txn_month entries where as_of - 365 days <= txn_month < as_of.

    Source: data/transactions_monthly_agg.parquet
    Zero-activity default: 0
    """
    as_of_dt = pd.to_datetime(as_of)
    start_dt = as_of_dt - pd.Timedelta(days=365)
    all_cust_ids = pd.Index(customers["customer_id"].unique(), name="customer_id")

    valid_aggs = monthly_agg[
        (monthly_agg["txn_month"] >= start_dt) & (monthly_agg["txn_month"] < as_of_dt)
    ]

    if valid_aggs.empty:
        return pd.Series(0, index=all_cust_ids, name="active_months_12m", dtype=int)

    active_counts = valid_aggs.groupby("customer_id")["txn_month"].nunique()
    active_counts = active_counts.reindex(all_cust_ids, fill_value=0)
    active_counts.name = "active_months_12m"
    return active_counts.astype(int)


def compute_return_rate_90d(
    customers: pd.DataFrame,
    transactions: pd.DataFrame,
    as_of: str,
) -> pd.Series:
    """Computes sum(is_returned) / count(*) for transactions within [as_of - 90 days, as_of).

    If count(*) == 0, returns 0.0.
    Source: data/transactions.db (transactions table)
    Zero-activity default: 0.0
    """
    as_of_dt = pd.to_datetime(as_of)
    start_dt = as_of_dt - pd.Timedelta(days=90)
    all_cust_ids = pd.Index(customers["customer_id"].unique(), name="customer_id")

    valid_txns = transactions[
        (transactions["txn_timestamp"] >= start_dt) & (transactions["txn_timestamp"] < as_of_dt)
    ]

    if valid_txns.empty:
        return pd.Series(0.0, index=all_cust_ids, name="return_rate_90d", dtype=float)

    grouped = valid_txns.groupby("customer_id")["is_returned"].agg(["sum", "count"])
    return_rate = (grouped["sum"] / grouped["count"]).fillna(0.0)

    return_rate = return_rate.reindex(all_cust_ids, fill_value=0.0)
    return_rate.name = "return_rate_90d"
    return return_rate.astype(float)


def compute_customer_tenure_days(
    customers: pd.DataFrame,
    as_of: str,
) -> pd.Series:
    """Computes (as_of_date - signup_date).days.

    Source: data/customers.csv (signup_date)
    Zero-activity default: Computed strictly from signup_date (available for all 1,500 customers).
    """
    as_of_dt = pd.to_datetime(as_of)
    signup = pd.to_datetime(customers.set_index("customer_id")["signup_date"])
    tenure = (as_of_dt - signup).dt.days.astype(float)
    tenure.name = "customer_tenure_days"
    return tenure
