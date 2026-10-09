"""
The ONE shared feature-build entry point. Both `scripts/build_training_features.py`
(training path: a historical as-of date, batch of many customers) and
`scripts/score_customer.py` (scoring path: single customer_id, same as-of date) must call
this same function — that is the entire train/score parity guarantee for this pipeline.

There is exactly one code path here. The only conditional difference between training mode
and scoring mode is selecting the requested customer_ids at output.
"""

from typing import Any
import pandas as pd

from features import ingest, transforms


def build_features(
    as_of: str,
    source_paths: dict | None = None,
    customer_ids: list[int] | None = None,
) -> pd.DataFrame:
    """Build the full feature set as of `as_of` for either the whole customer base
    (training path, `customer_ids=None`) or a specific subset (scoring path, one or more
    `customer_ids`).

    Parameters:
    - as_of: Target evaluation timestamp string (e.g., '2026-08-01').
    - source_paths: Optional dictionary overriding file paths for raw sources:
        {"customers": str, "transactions": str, "monthly_agg": str}
    - customer_ids: Optional list of integer customer IDs to filter to at output.
    """
    if source_paths is None:
        source_paths = {
            "customers": "data/customers.csv",
            "transactions": "data/transactions.db",
            "monthly_agg": "data/transactions_monthly_agg.parquet",
        }

    # 1. Ingest raw datasets via pure I/O loaders
    customers_df = ingest.load_customers(source_paths["customers"])
    transactions_df = ingest.load_transactions(source_paths["transactions"])
    monthly_agg_df = ingest.load_monthly_agg(source_paths["monthly_agg"])

    # 2. Compute each candidate feature via pure transform functions
    # Every transform strictly respects point-in-time anti-leakage (< as_of)
    # and reindexes across the full cohort of customers with declared non-null defaults.
    f_recency = transforms.compute_recency_days(customers_df, transactions_df, as_of)
    f_txn_count = transforms.compute_txn_count_90d(customers_df, transactions_df, as_of)
    f_recent_spend = transforms.compute_recent_spend_90d(customers_df, transactions_df, as_of)
    f_active_months = transforms.compute_active_months_12m(customers_df, monthly_agg_df, as_of)
    f_return_rate = transforms.compute_return_rate_90d(customers_df, transactions_df, as_of)
    f_tenure = transforms.compute_customer_tenure_days(customers_df, as_of)

    # 3. Assemble unified feature frame
    all_cust_ids = customers_df["customer_id"].values
    features_df = pd.DataFrame(
        {
            "customer_id": all_cust_ids,
            "recency_days": f_recency.loc[all_cust_ids].values,
            "txn_count_90d": f_txn_count.loc[all_cust_ids].values,
            "recent_spend_90d": f_recent_spend.loc[all_cust_ids].values,
            "active_months_12m": f_active_months.loc[all_cust_ids].values,
            "return_rate_90d": f_return_rate.loc[all_cust_ids].values,
            "customer_tenure_days": f_tenure.loc[all_cust_ids].values,
            "as_of_date": as_of,
        }
    )

    # 4. Filter for specific customer_ids if requested (Scoring Mode)
    # This is the ONLY difference between training and scoring runs.
    if customer_ids is not None:
        missing = set(customer_ids) - set(customers_df["customer_id"])
        if missing:
            raise ValueError(f"Requested customer_id(s) do not exist in customer master: {sorted(list(missing))}")
        features_df = features_df[features_df["customer_id"].isin(customer_ids)].copy()
        # Preserve input order
        features_df = features_df.set_index("customer_id").loc[customer_ids].reset_index()

    return features_df
