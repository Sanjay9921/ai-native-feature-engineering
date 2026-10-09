# ABOUT

## Overview

### Core Business Objective

- The goal is to predict customer churn risk as of a specific baseline cut-off date (as_of = "2026-08-01").
- The pipeline extracts behavioral signals—such as purchase recency, order frequency, monetary spend, monthly consistency, return rates, and customer tenure—while enforcing strict point-in-time constraints to prevent temporal data leakage.
- **Observation Cut-Off** (``as_of``): The canonical baseline evaluation date is ``2026-08-01``. To prevent temporal data leakage, any transaction or event occurring on or after ``as_of`` must be filtered out before computing features

### Key Components & Architecture

- **Heterogeneous Data Sourcing**: The pipeline ingests and reconciles data across three distinct storage formats:
  - ``customers.csv``: Customer profile Dimensions Table (1,500 accounts)
    - Flat file containing 1,500 customer records with static metadata (signup_date, acquisition_channel, region, and the target churned label)
  - ``transactions.db``: Event Fact Table
    - SQLite database containing granular, event-level transaction timestamps and amounts (used for high-precision, short-window metrics like 30-day/90-day recency and frequency).
  - ``transactions_monthly_agg.parquet``: Monthly Rollup Extract
    - Monthly aggregated Parquet rollup (used for long-horizon consistency metrics like 12-month active months).
- **Train/Score Parity**: Exposes a single shared ``function—build_features(as_of, source_paths, customer_ids)`` — used for both offline batch training and online single-customer scoring to ensure 100% deterministic parity without skew or logic divergence.
- **Local Feature Store & Versioning**: Registers feature metadata in a local SQLite database (``feature_store/registry.db``) and stores immutable value snapshots in Parquet files. It supports versioning across parameter changes (e.g., comparing a 90-day vs. a 30-day aggregation window) [8, 9, 11].
- **Data Quality & Edge Cases**: Enforces validation checks to catch silent failures, specifically handling the 81 zero-transaction customers by reindexing across the full customer population and applying non-null zero defaults.

### AI-Native Workflow

- The project models an AI-assisted development workflow using Claude Code through a custom gateway:
  - Stage 0: Claude scans raw sources to generate an initial data dictionary (data_dictionary.md) and candidate feature proposal.
  - Human Review: The developer evaluates, corrects, and finalizes the feature specification (feature_spec.md) before any code is built.
  - Stage 1: Claude builds the pipeline infrastructure, scripts, feature store, and test suites under human oversight and testing.

## The Multi-Source Architectural Choice:

- Why use row-level SQLite (transactions.db)? Short-horizon features (<60–90 days), exact day recency, and specific return rates require event-level timestamp precision.
- Sourcing them from monthly Parquet rollups introduces calendar-rounding errors and up to 30 days of ETL lag.
- Why use Parquet rollups (transactions_monthly_agg.parquet)? Long-horizon engagement metrics (e.g., active months in trailing 12 months) naturally benefit from monthly pre-aggregations, saving the system from scanning millions of raw transaction logs.

## The Critical Data-Quality Edge Case: Zero-Activity Accounts

### The Trap

- Out of 1,500 customer accounts in customers.csv, exactly 81 customers have zero transaction history across their entire lifetime.
- The Failure Mode: Naive inner joins or unhandled group-by operations silently drop these 81 customers or produce NaN values.
- The Solution: Feature transformation logic must explicitly reindex against the full 1,500 customer cohort (customer_ids = 1..1500) and apply declared non-null defaults:
  - Recency default: 999.0 days (or customer tenure in days).
  - Frequency/Monetary defaults: 0 / 0.0.
  - Return rate default: 0.0.

## Core Architectural Contracts

### Contract A: 100% Train/Score Parity

- The Skew Problem: In many production ML systems, training features are generated via batch SQL/Python scripts, while online scoring features are re-implemented in API endpoints. Minor logic differences create training-serving skew.
- The Architectural Rule: The pipeline defines exactly one shared feature builder function: build_features(as_of, source_paths, customer_ids) in features/build.py.
- Both batch training (build_training_features.py) and single-customer scoring (score_customer.py) execute this exact code path. The only difference permitted is slicing the requested customer_ids at the very end of computation.

### Contract B: Point-in-Time Anti-Leakage

- Every transformation function takes as_of as an explicit parameter and filters records to txn_timestamp < as_of. Hardcoded timestamps or datetime.now() calls are strictly forbidden.

### Contract C: Local Feature Store & Versioning

- SQLite Metadata Registry (feature_store/registry.db): Manages the feature_registry table, tracking feature name, version, parameters, creation timestamp, and an is_latest boolean flag managed atomically via SQLite transactions.
- Parquet Value Snapshots (feature_store/values/): Stores feature outputs as immutable Parquet snapshots (<feature_name>__v<version>.parquet).
- Feature Versioning: Supports running multiple feature experiments side-by-side (e.g., comparing txn_count_window with a 90-day vs. 30-day window, or recent_spend_adjusted with a 2.0x vs. 2.25x repeat multiplier).

## Verification & Testing Strategy

- The architecture is verified using four distinct test modules:
  - ``test_transforms.py``: Validates calculation logic, window boundaries, and zero-activity default handling.
  - ``test_parity.py``: Verifies numerical/bitwise equality between training batch outputs and single-customer online scoring slices.
  - ``test_quality_checks.py``: Verifies that invalid inputs (nulls, spend > $50,000, return rate > 1.0) trigger immediate pipeline failures.
  - ``test_feature_store.py``: Tests multi-version registration, atomic is_latest flips, and version retrieval.
