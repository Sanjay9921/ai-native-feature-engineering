# AI-Native Churn Feature Engineering Pipeline

## Overview

This repository contains an AI-native, versioned feature engineering pipeline built for an e-commerce customer churn prediction model. The pipeline ingests heterogeneous raw data sources, enforces point-in-time temporal anti-leakage as of a parameterized cut-off date (`as_of = "2026-08-01"`), guarantees 100% train/score parity via a single shared build function, and registers feature definitions and snapshots inside a local SQLite- and Parquet-backed feature store.

---

## Data Sources & Architecture

The pipeline ingests data across three heterogeneous sources:
1. **`data/customers.csv`**: Customer dimension table (1,500 records) containing signup dates, demographics, and ground-truth churn labels.
2. **`data/transactions.db`**: SQLite database containing event-level transaction facts (timestamps, amounts, return flags). Used for low-latency, short-window, and sub-monthly precision features.
3. **`data/transactions_monthly_agg.parquet`**: Parquet columnar extract pre-aggregating transactions by customer and calendar month (`YYYY-MM-01`). Sourced for long-horizon engagement consistency metrics.

---

## Environment Setup

### Prerequisites

* Python 3.10+
* Git

### Virtual Environment & Dependencies

Create and activate a local Python virtual environment, then install the pinned dependencies:

```powershell

# Windows PowerShell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt # (On Linux / macOS / WSL, activate via source .venv/bin/activate).

```

## Executing the Pipeline Scripts

All execution scripts must be invoked using Python's module syntax (python -m scripts.<script_name>) from the project root so package imports resolve cleanly.

### 1. Build Training Features & Register in Feature Store

Generates candidate features for the full 1,500 customer population as of ``2026-08-01``, runs data quality validations, and registers feature versions into ``feature_store/registry.db`` and ``feature_store/values/*.parquet``.

```bash

python -m scripts.build_training_features --as-of 2026-08-01

```

### 2. Single or Multi-Customer Online Scoring

Evaluates online feature scoring using the exact same ``build_features()`` entry point to guarantee bitwise train/score parity.

```bash

# Score a single customer
python -m scripts.score_customer --customer-id 2 --as-of 2026-08-01

# Score multiple customers
python -m scripts.score_customer --customer-ids 2 42 100 --as-of 2026-08-01

```

### 3. Compare Feature Versions

Analyzes statistical distribution shifts, quantile changes, and customer impact metrics across versioned feature parameters (``txn_count_window`` v1/v2 and ``recent_spend_adjusted`` v1/v2).

```bash

python -m scripts.compare_feature_versions

```

## Automated Test Suite

Run pytest to execute all automated test suites, verifying transforms, data quality guardrails, train/score parity, and feature store operations:

```bash

pytest -v

```

### Test Coverage

* ``tests/test_transforms.py``: Validates feature calculations, window boundaries, and zero-activity default handling for inactive accounts.
* ``tests/test_parity.py``: Verifies numerical/bitwise equality between training snapshots and single-customer scoring slices.
* ``tests/test_quality_checks.py``: Verifies that data defects (nulls, extreme spend outliers, bad return rates) trigger pipeline exceptions.
* ``tests/test_feature_store.py``: Tests multi-version registration, atomic ``is_latest`` version flips, and independent version retrieval.

## Feature Store & Lineage Inspection

To query the local SQLite feature registry directly:

```bash

python -c "import sqlite3, pandas as pd; conn = sqlite3.connect('feature_store/registry.db'); print(pd.read_sql('SELECT feature_name, version, is_latest, parquet_path FROM feature_registry ORDER BY feature_name, version', conn))"

```

## Non-Code Artifacts (outputs/artifacts/)

All non-code verification documentation is saved in ``outputs/artifacts/``:

* ``FEATURE_LINEAGE.md``: End-to-end lineage mapping sources, calculations, rationales, and Parquet snapshot paths.
* ``VERSION_COMPARISON.md``: Distribution shifts and business interpretations for versioned features.
* ``PARITY_CHECK.md``: Parity audit log and parity mutation test results.
* ``ARTIFACT_NOTES.md``: Retrospective on zero-activity handling and SQLite transactions.
* ``review_log.md``: Self-review findings and resolutions.
