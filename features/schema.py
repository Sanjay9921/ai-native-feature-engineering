"""
Versioned output feature schema: the authoritative list of every feature this pipeline
produces, with dtype, nullability, source(s), and feature-set version.

This is generated/maintained from `feature_spec.md`, and is consumed by
`FEATURE_LINEAGE.md` generation and by the feature store registration step.
"""

from dataclasses import dataclass


@dataclass
class FeatureSpec:
    name: str
    dtype: str
    nullable: bool
    source: str
    feature_set_version: str
    description: str
    transform_summary: str
    business_rationale: str
    parameters: dict


# Authoritative feature specifications per confirmed feature_spec.md
FEATURE_SCHEMA: list[FeatureSpec] = [
    FeatureSpec(
        name="recency_days",
        dtype="float64",
        nullable=False,
        source="data/transactions.db:transactions.txn_timestamp",
        feature_set_version="v1",
        description="Days elapsed since the most recent transaction prior to as_of date.",
        transform_summary="(as_of - max(txn_timestamp)).days; zero-activity defaulted to 999.0",
        business_rationale="Measures temporal disengagement; long lapses in purchasing cadence indicate imminent churn risk.",
        parameters={},
    ),
    FeatureSpec(
        name="txn_count_90d",
        dtype="int64",
        nullable=False,
        source="data/transactions.db:transactions.txn_timestamp",
        feature_set_version="v1",
        description="Count of transactions in trailing 90-day window [as_of - 90d, as_of).",
        transform_summary="count(*) where as_of - 90d <= txn_timestamp < as_of; zero-activity defaulted to 0",
        business_rationale="Captures quarterly purchasing frequency; sudden drops precede complete account abandonment.",
        parameters={"window_days": 90},
    ),
    FeatureSpec(
        name="recent_spend_90d",
        dtype="float64",
        nullable=False,
        source="data/transactions.db:transactions.amount,txn_timestamp,is_returned",
        feature_set_version="v1",
        description="Total net spend on non-returned orders in trailing 90 days.",
        transform_summary="sum(amount) where is_returned==0 and within 90d window; zero-activity defaulted to 0.0",
        business_rationale="Monetary wallet-share decay signals customer migration to competitors.",
        parameters={},
    ),
    FeatureSpec(
        name="active_months_12m",
        dtype="int64",
        nullable=False,
        source="data/transactions_monthly_agg.parquet:txn_month",
        feature_set_version="v1",
        description="Count of distinct active calendar months in trailing 12 months.",
        transform_summary="count(distinct txn_month) where within trailing 365d; zero-activity defaulted to 0",
        business_rationale="Measures habituation consistency across annual cycle; sporadic engagement indicates churn susceptibility.",
        parameters={},
    ),
    FeatureSpec(
        name="return_rate_90d",
        dtype="float64",
        nullable=False,
        source="data/transactions.db:transactions.is_returned,txn_timestamp",
        feature_set_version="v1",
        description="Proportion of orders returned in trailing 90 days.",
        transform_summary="sum(is_returned)/count(*) over trailing 90d; zero-activity defaulted to 0.0",
        business_rationale="Elevated return rates reflect product mismatch or fulfillment friction preceding churn.",
        parameters={},
    ),
    FeatureSpec(
        name="customer_tenure_days",
        dtype="float64",
        nullable=False,
        source="data/customers.csv:signup_date",
        feature_set_version="v1",
        description="Account age in days as of evaluation date.",
        transform_summary="(as_of - signup_date).days",
        business_rationale="Controls for lifecycle baseline hazard rate, separating early onboarding attrition from mature customer churn.",
        parameters={},
    ),
]
