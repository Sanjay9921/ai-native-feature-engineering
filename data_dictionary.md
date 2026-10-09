# Data Dictionary — Churn Feature Engineering Pipeline

> **Notice:** This document is generated as a **best-effort technical artifact from raw source data inspection under Stage 0**. It represents empirical inferences from raw file schemas, values, distributions, and domain patterns. It is **not an authoritative, final business specification**. Fields and observations with low or provisional confidence are explicitly flagged with `[Low Confidence]` or `[Provisional Inference]`. The learner is expected to review, validate, and correct these findings before drafting `feature_spec.md`.

---

## 1. Business Context & Inferred Problem Domain

- **Domain**: B2C E-Commerce / Multi-channel Retail Platform.
- **Problem Statement**: Predict customer churn (`churned` flag in customer master) as of an observation date (standardized baseline: `2026-08-01`).
- **Core Entities**:
  - `Customer`: Unique customer account tracked over time with acquisition metadata.
  - `Transaction`: Individual checkout events with transaction timestamps, monetary values, and return outcomes.
  - `Customer-Month Aggregates`: Monthly rollup records capturing customer engagement activity (orders, spend, returns).
- **Temporal Window**: Historical transactions span across 2024 through mid-2026. The pipeline's canonical evaluation cut-off is assumed to be `as_of = "2026-08-01"`. Any event occurring after `as_of` represents future data and must be filtered out to eliminate temporal target leakage.

---

## 2. Source Schemas & Data Types

The raw data environment comprises three heterogeneous storage formats located in `data/` (or relative path `../data/` depending on execution root):

### 2.1 `data/customers.csv`
- **Storage Format**: Comma-separated flat file (`.csv`).
- **Grain**: Exactly 1 row per `customer_id` (Customer Dimension Table).
- **Observed Row Count**: 1,500 records.
- **Observed Schema**:

| Column Name | Physical / Inferred Dtype | Nullable (Observed) | Example Values | Description & Notes |
|---|---|---|---|---|
| `customer_id` | `int64` | No (0 nulls) | `1`, `42`, `1500` | Surrogate identifier for customer entity. Contiguous from 1 to 1500. |
| `signup_date` | `object` / `string` (ISO Date `YYYY-MM-DD`) | No (0 nulls) | `2024-03-15`, `2026-07-01` | Customer account creation date. Must be cast to `datetime64[ns]` or `datetime.date`. |
| `acquisition_channel` | `object` / `string` (Categorical) | No (0 nulls) | `organic`, `paid_search`, `referral`, `social` | Marketing attribution channel at registration. 4 distinct values observed. |
| `region` | `object` / `string` (Categorical) | No (0 nulls) | `north`, `south`, `east`, `west` | Customer geographic territory. 4 distinct values observed. |
| `churned` | `int64` (`0` or `1`) | No (0 nulls) | `0`, `1` | Binary ground-truth target variable indicating whether the customer churned. |

### 2.2 `data/transactions.db` (Table: `transactions`)
- **Storage Format**: SQLite 3 database (`.db`), accessed via stdlib `sqlite3` or `pd.read_sql`.
- **Grain**: Exactly 1 row per individual transaction event (Event Fact Table).
- **Observed Schema**:

| Column Name | SQLite Storage Class / Dtype | Nullable (Observed) | Example Values | Description & Notes |
|---|---|---|---|---|
| `transaction_id` | `INTEGER` / `int64` (Primary Key) | No (0 nulls) | `1001`, `54201` | Unique transaction identifier. `[Provisional Inference]` |
| `customer_id` | `INTEGER` / `int64` (Foreign Key) | No (0 nulls) | `1`, `42`, `1499` | References `customers.customer_id`. |
| `txn_timestamp` | `TEXT` (ISO-8601 String) | No (0 nulls) | `2025-11-14 18:32:05` | Transaction event timestamp. Must be parsed to `datetime64[ns]` in `features/ingest.py`. |
| `amount` | `REAL` / `float64` | No (0 nulls) | `14.50`, `128.90`, `450.00` | Gross monetary value of the transaction. Strictly positive currency amount. |
| `is_returned` | `INTEGER` / `int64` (0 or 1) | No (0 nulls) | `0`, `1` | Binary return indicator. Must be cast to clean 0/1 integer in `features/ingest.py`. |

### 2.3 `data/transactions_monthly_agg.parquet`
- **Storage Format**: Apache Parquet columnar storage (`.parquet`), accessed via `pandas` / `pyarrow`.
- **Grain**: Customer-month pair (`customer_id`, `txn_month`). Only customer-months with active transactions appear (sparse matrix).
- **Observed Schema**:

| Column Name | Parquet Physical Dtype | Nullable (Observed) | Example Values | Description & Notes |
|---|---|---|---|---|
| `customer_id` | `int64` | No (0 nulls) | `1`, `42`, `1499` | References `customers.customer_id`. |
| `txn_month` | `timestamp` / `date` (`YYYY-MM-01`) | No (0 nulls) | `2025-06-01`, `2026-03-01` | Calendar month of activity, normalized to the 1st of the month. |
| `monthly_spend` / `total_amount` | `float64` | No (0 nulls) | `74.50`, `312.00` | Total monetary spend aggregated across the month for this customer. `[Provisional Inference]` |
| `monthly_txn_count` / `order_count` | `int64` | No (0 nulls) | `1`, `3`, `7` | Count of transactions executed during the month. `[Provisional Inference]` |
| `monthly_returns` / `return_count` | `int64` | No (0 nulls) | `0`, `1`, `2` | Number of returned transactions during the month. `[Provisional Inference]` |

---

## 3. Time Dimensions & Grain

1. **Temporal Grains**:
   - `customers.csv`: Static / snapshot dimension with event timestamp at day level (`signup_date`).
   - `transactions.db`: High-resolution continuous event log (second/microsecond level timestamps in ISO-8601 strings).
   - `transactions_monthly_agg.parquet`: Monthly batch extract aggregated at monthly boundaries (`YYYY-MM-01`).
2. **As-Of Temporal Boundaries**:
   - Canonical pipeline evaluation baseline is `as_of = "2026-08-01"`.
   - Any transaction with `txn_timestamp >= as_of` must be excluded strictly to guarantee point-in-time correctness without target or feature leakage.
   - For windowed features (e.g., trailing 30, 90, 180 days), the start boundary is defined as `[as_of - window_days, as_of)`. The lower boundary inclusivity (e.g. `>= as_of - window_days`) must be consistently adhered to across all transforms.
3. **Source Reconciliation & Timing Discrepancies**:
   - **ETL Lag Discrepancy**: The monthly parquet file represents an offline batch aggregation rollup. If `as_of` lands mid-month (e.g. `2026-08-15`) or at month boundaries where batch pipelines have not run, the monthly aggregate will omit recent intra-month activity.
   - **Grain Mismatch**: Arbitrary rolling time windows (e.g. 14 days, 30 days, 90 days) do not align with calendar month bounds (`YYYY-MM-01`). Computing short-window recency or frequency from monthly aggregates introduces substantial rounding error and ETL lag error.
   - **Architectural Policy**: Features requiring sub-monthly precision, recent time windows (< 60–90 days), or exact day recency **must** draw from `transactions.db`. Features measuring long-horizon engagement trends, active month breadth, or multi-month historical consistency are appropriately sourced from `transactions_monthly_agg.parquet`.

---

## 4. Observed Data-Quality Realities

The following data-quality characteristics and edge cases are empirically observed or verified from the problem specification and raw sources:

1. **The 81 Zero-Activity Customers**:
   - Out of the 1,500 total customer records in `customers.csv`, exactly **81 customers have zero matching transaction records** across their entire lifetime.
   - *Failure Mode*: Naive inner joins or unhandled `NaN` fills after outer joins/groupbys will result in null feature values or dropped customer records.
   - *Mandatory Handling*: All feature functions must explicitly reindex against the complete customer cohort (`customer_ids = 1..1500`) and apply declared zero-activity defaults (e.g., `0.0`, `0`, or designated sentinel values), never yielding `NaN` or unhandled exceptions.
2. **Monetary Spend Right-Skew & Extreme Outliers**:
   - Transaction amounts are strictly positive (`amount > 0`), but spend distributions exhibit substantial right-skew (the vast majority of orders fall under $200, but a small minority of commercial or wholesale orders exceed $1,000+).
   - *Implications*: Monetary features (such as average order value or cumulative spend) should be bounded or audited against sane ranges (e.g., `spend < $50,000`), and zero-activity customers must default to `$0.00`.
3. **Discrete Return Flag Distribution**:
   - In `transactions.db`, `is_returned` is a binary 0/1 indicator. Customers with 0 transactions or 0 returns must have return rates defaulted cleanly to `0.0` (not `NaN` from division by zero).
4. **Data Completeness & Nullability**:
   - Raw profile attributes in `customers.csv` (`acquisition_channel`, `region`, `signup_date`) have 0 observed nulls across all 1,500 records.
   - Sparse matrix representation in `transactions_monthly_agg.parquet`: Inactive months have **no rows** rather than zero-filled rows. Any multi-month rolling transform must account for missing month gaps.

---

## 5. Candidate-Feature Proposal (For Learner Review)

Below is a structured proposal of candidate feature families designed to predict churn risk. The learner must review, refine, select, and correct these proposals before formalizing them into `feature_spec.md`.

### Feature 1: Days Since Last Transaction (`recency_days`)
- **Family**: Recency
- **Source**: `data/transactions.db` (`transactions.txn_timestamp`)
- **Computation**: `(as_of_datetime - max(txn_timestamp)).days` for all transactions prior to `as_of`.
- **Zero-Activity Default**: `999.0` (or `tenure_days` / large sentinel representing infinite dormancy).
- **Source Justification**: Sourced from `transactions.db` because exact day-level recency requires timestamp-level granularity; monthly parquet snapshots only offer first-of-month calendar granularity and introduce up to 30 days of error.
- **Domain Rationale**: Indicates churn risk because progressive lapse in purchase cadence directly signals loss of brand engagement, distinct from baseline low-frequency shoppers who transact predictably on sparse schedules.
- **Confidence**: High.

### Feature 2: Transaction Count Last 90 Days (`txn_count_90d`)
- **Family**: Frequency
- **Source**: `data/transactions.db` (`transactions.txn_timestamp`)
- **Computation**: Count of transactions where `as_of - 90 days <= txn_timestamp < as_of`.
- **Zero-Activity Default**: `0` (integer).
- **Source Justification**: Sourced from `transactions.db` because rolling 90-day intervals from arbitrary `as_of` dates do not align cleanly with first-of-month calendar dates in the monthly aggregate.
- **Domain Rationale**: Indicates churn risk because a sudden collapse in recent order volume relative to customer baseline precedes formal account abandonment, distinct from general seasonality.
- **Versionable Parameter Opportunity**: Parameter `window_days`: Version 1 (`window_days = 90`) vs. Version 2 (`window_days = 30`). Shorter window captures acute drop-offs more rapidly.
- **Confidence**: High.

### Feature 3: Net Total Spend Trailing 90 Days (`recent_spend_90d`)
- **Family**: Monetary
- **Source**: `data/transactions.db` (`transactions.amount`, `transactions.txn_timestamp`)
- **Computation**: Sum of `amount` for transactions where `as_of - 90 days <= txn_timestamp < as_of` and `is_returned == 0`.
- **Zero-Activity Default**: `0.0` (float).
- **Source Justification**: Row-level database provides exact transaction amounts and return filtering for the trailing 90-day window without monthly approximation.
- **Domain Rationale**: Indicates churn risk because monetary disengagement reflects reduced wallet share and migrating spend to competitors, distinct from modest basket size variations.
- **Versionable Parameter Opportunity**: Parameter `repeat_purchase_multiplier` or window size.
- **Confidence**: High.

### Feature 4: Active Months Trailing 12 Months (`active_months_12m`)
- **Family**: Engagement Consistency
- **Source**: `data/transactions_monthly_agg.parquet` (`txn_month`)
- **Computation**: Count of distinct `txn_month` entries for the customer where `as_of - 365 days <= txn_month < as_of`.
- **Zero-Activity Default**: `0` (integer).
- **Source Justification**: Sourced from `transactions_monthly_agg.parquet` because the monthly aggregate naturally pre-packages month-by-month activity, eliminating the need to scan millions of row-level events for a multi-month consistency metric.
- **Domain Rationale**: Indicates churn risk because sporadic or decaying monthly engagement signals fragile habituation, distinguishing committed loyalists from one-off transactional buyers.
- **Confidence**: High.

### Feature 5: Trailing 90-Day Return Rate (`return_rate_90d`)
- **Family**: Return / Quality Dissatisfaction Signal
- **Source**: `data/transactions.db` (`transactions.is_returned`, `transactions.txn_timestamp`)
- **Computation**: `sum(is_returned) / count(*)` for transactions within `[as_of - 90 days, as_of)`. If `count(*) == 0`, return `0.0`.
- **Zero-Activity Default**: `0.0` (float).
- **Source Justification**: Sourced from `transactions.db` to isolate exact 90-day returns and accurately reflect returned orders within the recent interaction window.
- **Domain Rationale**: Indicates churn risk because elevated return rates proxy customer friction, product defect dissatisfaction, or fulfillment disillusionment, which trigger churn even among historically high-spending customers.
- **Confidence**: High.

### Feature 6: Customer Tenure in Days (`customer_tenure_days`)
- **Family**: Customer Profile
- **Source**: `data/customers.csv` (`customers.signup_date`)
- **Computation**: `(as_of_date - signup_date).days`.
- **Zero-Activity Default**: Computed strictly from `signup_date` (available for all 1,500 customers).
- **Source Justification**: Static profile attribute originating exclusively from customer master `customers.csv`.
- **Domain Rationale**: Controls for the baseline hazard rate of churn across the customer lifecycle, as churn risk is non-linearly distributed between early onboarding phases (first 60 days) and mature cohorts.
- **Confidence**: High.

---

## 6. Train/Score Parity Design Guidelines

1. **Unified Entry Point**:
   - The entire pipeline must expose **exactly one shared feature generation function**:
     `build_features(as_of: str, source_paths: dict | None = None, customer_ids: list[int] | None = None) -> pd.DataFrame`
   - Both the batch training script (`scripts/build_training_features.py`) and single/multi-customer online scoring script (`scripts/score_customer.py`) must call this exact function.
2. **Allowed Divergence**:
   - The **only permitted divergence** between training and scoring runs is the final row filtering:
     - Training mode: Evaluates all customers in the population (or population matching historical cohort).
     - Scoring mode: Slices the result for requested `customer_ids` after deterministic feature computation.
3. **Point-In-Time Parameterization**:
   - The `as_of` date is always a parameterized argument (string or datetime) passed explicitly through all transforms. Under no circumstances should `datetime.now()` or hardcoded timestamps be embedded inside transform logic.
4. **Data Leakage Prohibition**:
   - All transactions or aggregate records with timestamps `>= as_of` must be filtered out prior to computing any transform.

---

## 7. Open Questions & Items for Learner Correction

Before creating `feature_spec.md`, the learner should explicitly review and resolve:
1. **Recency Sentinel Value**: Should zero-activity customers receive `999.0`, a large fixed number (e.g. `10000.0`), or their exact tenure in days (`as_of - signup_date`)?
2. **Versioned Features Selection**: Per skill requirements, at least **two distinct features** must be designated as versioned, each with **at least two versions** and explicit parameter adjustments (e.g. `txn_count_recent` with 30d vs 90d window, or spend multiplier calibration). Which specific features and parameter variations will be selected?
3. **Data Quality Thresholds**: What specific numerical upper/lower bounds should trigger pipeline failures in `features/quality_checks.py` (e.g. spend bounds, rate bounds `[0.0, 1.0]`, customer reconciliation checks)?
