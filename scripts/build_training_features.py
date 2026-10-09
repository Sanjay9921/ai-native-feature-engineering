#!/usr/bin/env python3
"""
Builds features for the full training population as of a given date, writes a versioned
parquet feature snapshot, and registers every candidate feature into the feature store.

Features Registered:
- All 6 candidate features:
  1. recency_days
  2. txn_count_90d
  3. recent_spend_90d
  4. active_months_12m
  5. return_rate_90d
  6. customer_tenure_days
- Plus versioned feature instances per feature_spec.md:
  * txn_count_window: v1 (90d), v2 (30d)
  * recent_spend_adjusted: v1 (multiplier=2.0), v2 (multiplier=2.25)
"""

import argparse
from pathlib import Path
import pandas as pd

from features.build import build_features
from features.ingest import load_customers, load_transactions
from features import transforms
from features.quality_checks import run_all_checks
from features.schema import FEATURE_SCHEMA
from feature_store import store


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--as-of",
        default="2026-08-01",
        help="As-of date for feature computation (default: 2026-08-01).",
    )
    args = parser.parse_args()
    as_of = args.as_of

    print(f"--> Building training features as of: {as_of}")

    # 1. Execute unified feature build
    features_df = build_features(as_of=as_of)
    print(f"--> Successfully built features for {len(features_df)} customers.")

    # 2. Identify zero-activity customers from raw transactions for validation
    customers_df = load_customers()
    transactions_df = load_transactions()
    as_of_dt = pd.to_datetime(as_of)
    valid_txns = transactions_df[transactions_df["txn_timestamp"] < as_of_dt]
    active_cust_ids = set(valid_txns["customer_id"].unique())
    zero_activity_cust_ids = set(customers_df["customer_id"].unique()) - active_cust_ids
    print(f"--> Identified {len(zero_activity_cust_ids)} zero-activity customers as of {as_of}.")

    # 3. Execute quality checks
    print("--> Running data quality checks...")
    qc_results = run_all_checks(
        features_df,
        expected_count=len(customers_df),
        zero_activity_customer_ids=zero_activity_cust_ids,
        fatal=True,
    )
    print("--> All data quality checks PASSED.")

    # 4. Register candidate features in the feature store
    print("--> Registering candidate features in feature store...")
    schema_map = {f.name: f for f in FEATURE_SCHEMA}

    for feat_name, spec in schema_map.items():
        feat_df = features_df[["customer_id", feat_name, "as_of_date"]].copy()
        v = store.register_version(
            feature_name=feat_name,
            values_df=feat_df,
            description=spec.description,
            source_columns=spec.source,
            transform_summary=spec.transform_summary,
            business_rationale=spec.business_rationale,
            parameters=spec.parameters,
        )
        print(f"    [Registered] {feat_name} v{v}")

    # 5. Register Multi-Version Features required by feature_spec.md
    print("--> Registering versioned feature experiments per feature_spec.md...")

    # Feature Versioned A: txn_count_window (v1=90d, v2=30d)
    # v1 (90d)
    v1_txn_90 = transforms.compute_txn_count_window(customers_df, transactions_df, as_of, window_days=90)
    df_txn_v1 = pd.DataFrame({
        "customer_id": customers_df["customer_id"].values,
        "txn_count_window": v1_txn_90.loc[customers_df["customer_id"]].values,
        "as_of_date": as_of,
    })
    v_a1 = store.register_version(
        feature_name="txn_count_window",
        values_df=df_txn_v1,
        description="Transaction frequency over trailing window parameter.",
        source_columns="data/transactions.db:transactions.txn_timestamp",
        transform_summary="count(*) where as_of - window_days <= txn_timestamp < as_of",
        business_rationale="v1 uses 90-day quarterly window to establish baseline transaction cadence.",
        parameters={"window_days": 90},
    )
    print(f"    [Registered] txn_count_window v{v_a1} (window_days=90)")

    # v2 (30d)
    v2_txn_30 = transforms.compute_txn_count_window(customers_df, transactions_df, as_of, window_days=30)
    df_txn_v2 = pd.DataFrame({
        "customer_id": customers_df["customer_id"].values,
        "txn_count_window": v2_txn_30.loc[customers_df["customer_id"]].values,
        "as_of_date": as_of,
    })
    v_a2 = store.register_version(
        feature_name="txn_count_window",
        values_df=df_txn_v2,
        description="Transaction frequency over trailing window parameter.",
        source_columns="data/transactions.db:transactions.txn_timestamp",
        transform_summary="count(*) where as_of - window_days <= txn_timestamp < as_of",
        business_rationale="v2 shortens window to 30 days to detect acute purchasing collapse for rapid churn intervention.",
        parameters={"window_days": 30},
    )
    print(f"    [Registered] txn_count_window v{v_a2} (window_days=30)")

    # Feature Versioned B: recent_spend_adjusted (v1=2.0, v2=2.25)
    # v1 (multiplier=2.0)
    v1_spend_adj = transforms.compute_recent_spend_adjusted(
        customers_df, transactions_df, as_of, repeat_purchase_multiplier=2.0
    )
    df_spend_v1 = pd.DataFrame({
        "customer_id": customers_df["customer_id"].values,
        "recent_spend_adjusted": v1_spend_adj.loc[customers_df["customer_id"]].values,
        "as_of_date": as_of,
    })
    v_b1 = store.register_version(
        feature_name="recent_spend_adjusted",
        values_df=df_spend_v1,
        description="Recent 90-day net spend scaled by repeat purchase multiplier for loyal buyers.",
        source_columns="data/transactions.db:transactions.amount,txn_timestamp,is_returned",
        transform_summary="sum(amount) * multiplier if order_count >= 2 else sum(amount)",
        business_rationale="v1 tests 2.0x weight on returning customers with multiple orders.",
        parameters={"repeat_purchase_multiplier": 2.0, "window_days": 90},
    )
    print(f"    [Registered] recent_spend_adjusted v{v_b1} (multiplier=2.0)")

    # v2 (multiplier=2.25)
    v2_spend_adj = transforms.compute_recent_spend_adjusted(
        customers_df, transactions_df, as_of, repeat_purchase_multiplier=2.25
    )
    df_spend_v2 = pd.DataFrame({
        "customer_id": customers_df["customer_id"].values,
        "recent_spend_adjusted": v2_spend_adj.loc[customers_df["customer_id"]].values,
        "as_of_date": as_of,
    })
    v_b2 = store.register_version(
        feature_name="recent_spend_adjusted",
        values_df=df_spend_v2,
        description="Recent 90-day net spend scaled by repeat purchase multiplier for loyal buyers.",
        source_columns="data/transactions.db:transactions.amount,txn_timestamp,is_returned",
        transform_summary="sum(amount) * multiplier if order_count >= 2 else sum(amount)",
        business_rationale="v2 recalibrates multiplier to 2.25 after observing underweighted value in returning distribution.",
        parameters={"repeat_purchase_multiplier": 2.25, "window_days": 90},
    )
    print(f"    [Registered] recent_spend_adjusted v{v_b2} (multiplier=2.25)")

    print("--> Training feature build and feature store registration complete.")


if __name__ == "__main__":
    main()
