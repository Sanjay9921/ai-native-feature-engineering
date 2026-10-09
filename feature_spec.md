# feature_spec.md — Churn Feature Pipeline

---

## Candidate features

<<One block per feature — add/remove freely. At minimum per feature, per skill.md's Domain Context: name, source(s), computation, an explicit zero-activity default (never null/NaN), and a rationale naming a specific customer behavior distinct from a plausible confound.>>

- **Feature**: recency_days
- **Source**: data/transactions.db (transactions table)
- **Computation**: (as_of_datetime - max(txn_timestamp)).days for transactions strictly prior to as_of
- **Zero-activity default**: 999.0
- **If multiple sources could supply this, which and why?**: Sourced from transactions.db because exact day-level recency requires timestamp granularity; monthly parquet rollups introduce up to 30 days of ETL lag/rounding error
- **Rationale**: "This predicts churn because customers who cease ordering for extended periods tend to have lost engagement, distinct from just low spend/frequency because regular low-frequency buyers still transact on predictable schedules."

- **Feature**: txn_count_90d
- **Source**: data/transactions.db (transactions table)
- **Computation**: Count of transactions where as_of - 90 days <= txn_timestamp < as_of
- **Zero-activity default**: 0
- **If multiple sources could supply this, which and why?**: Sourced from transactions.db because rolling 90-day windows from arbitrary as_of dates do not align cleanly with first-of-month calendar boundaries in the monthly aggregate.
- **Rationale**: "This predicts churn because a sudden collapse in recent order volume precedes complete account abandonment, distinct from general seasonality or steady low-volume purchasing."

- **Feature**: recent_spend_90d
- **Source**: data/transactions.db (transactions table)
- **Computation**: Sum of amount where as_of - 90 days <= txn_timestamp < as_of and is_returned == 0
- **Zero-activity default**: 0.0
- **If multiple sources could supply this, which and why?**: Sourced from transactions.db because exact transaction amounts and non-returned order filtering are required for the trailing 90-day window.
- **Rationale**: "This predicts churn because monetary disengagement reflects reduced wallet share and migrating spend to competitors, distinct from minor basket-size fluctuations."

- **Feature**: active_months_12m
- **Source**: data/transactions_monthly_agg.parquet
- **Computation**: Count of distinct active txn_month entries where as_of - 365 days <= txn_month < as_of
- **Zero-activity default**: 0
- **If multiple sources could supply this, which and why?**: Sourced from transactions_monthly_agg.parquet because the monthly aggregate pre-packages month-by-month activity, eliminating the need to scan row-level events for a multi-month consistency metric.
- **Rationale**: "This predicts churn because sporadic or decaying monthly engagement signals fragile habituation, distinguishing committed loyalists from one-off transactional buyers."

- **Feature**: return_rate_90d
- **Source**: data/transactions.db (transactions table)
- **Computation**: sum(is_returned) / count(*) for transactions within [as_of - 90 days, as_of). If count(*) == 0, return 0.0
- **Zero-activity default**: 0.0
- **If multiple sources could supply this, which and why?**: Sourced from transactions.db to isolate exact 90-day returns and accurately reflect returned orders within the recent interaction window.
- **Rationale**: "This predicts churn because elevated return rates proxy customer product dissatisfaction or fulfillment friction, distinct from general low spending—a customer can spend normally while trending toward churn due to high returns."

- **Feature**: customer_tenure_days
- **Source**: data/customers.csv
- **Computation**: (as_of_date - signup_date).days
- **Zero-activity default**: Computed strictly from signup_date (available for all 1,500 customers)
- **If multiple sources could supply this, which and why?**: Only available in customers.csv (customer dimension master).
- **Rationale**: "This predicts churn because baseline churn risk varies across the customer lifecycle, separating early onboarding drop-off from mature cohort decay."

## Train/score parity design

<<At minimum, per ``skill.md``'s Domain Context: the one shared function/code path, the single allowed difference between training and scoring calls, and how ``as_of`` is threaded as a parameter.>>

- **Shared function/code path**: `build_features(as_of: str, source_paths: dict | None = None, customer_ids: list[int] | None = None) -> pd.DataFrame` defined in `features/build_features.py`
- **Only allowed training/scoring difference**: Slicing the final output DataFrame for requested `customer_ids` at the very end of the execution pipeline during online scoring mode, ensuring training and scoring share 100% identical feature transformation logic.
- **How as_of is threaded (not hardcoded)**: `as_of` is explicitly passed as a parameterized ISO date string (e.g., `"2026-08-01"`) into `build_features()` and threaded directly into every individual transformation function, strictly filtering records to `txn_timestamp < as_of` to guarantee point-in-time anti-leakage without using `datetime.now()` or hardcoded dates.

## Feature store, versioning & lineage

<<At minimum, per skill.md's Domain Context: which ≥2 distinct features are versioned (each with ≥2 versions — this floor is fixed), per feature the parameter varied and its value at each version, the business reason each version differs from the last, and what a lineage
entry must let someone reconstruct without reading code.>>

- **Features versioned**: `txn_count_window`, `recent_spend_adjusted`
- Per versioned feature: **Feature** / **Parameter** / **Value per version** / **Reason each
  * **Feature**: `txn_count_window`
    * **Parameter**: `window_days`
    * **Value per version**: v1 = `90`, v2 = `30`
    * **Reason each version differs**: v1 measures broad quarterly engagement over 90 days, whereas v2 shortens the window to 30 days to detect acute, rapid drop-offs in purchasing activity for earlier churn intervention.
  * **Feature**: `recent_spend_adjusted`
    * **Parameter**: `repeat_purchase_multiplier`
    * **Value per version**: v1 = `2.0`, v2 = `2.25`
    * **Reason each version differs**: v2 recalibrates the repeat-purchase weighting upwards after v1 was found to understate the long-term value of repeat buyers relative to the observed returning customer distribution.
- **What forces a version bump vs. not**: A version bump is forced by any change in mathematical computation, source selection, filter logic, or parameter values that alters feature values; purely structural refactoring, docstring updates, or formatting changes do NOT trigger a version bump.
- **What a lineage entry must let someone reconstruct**: The exact raw source dataset paths, feature definition version, transformation parameters, `as_of` timestamp, execution timestamp, and output Parquet snapshot location—allowing full reconstruction without needing to inspect raw source code.

## Multi-source judgment calls

<<At minimum, per ``skill.md``'s Domain Context: per feature that could come from either source, which was chosen and why.>>

- **Feature**: `recency_days` — **Source chosen**: `data/transactions.db` — **Why**: Sub-monthly day-level recency requires exact event timestamps; monthly parquet snapshots only offer first-of-month calendar dates, introducing up to 30 days of ETL lag and rounding error.
- **Feature**: `txn_count_90d` — **Source chosen**: `data/transactions.db` — **Why**: Rolling 90-day time windows from arbitrary `as_of` evaluation dates do not align cleanly with first-of-month calendar boundaries in the monthly aggregate.
- **Feature**: `recent_spend_90d` — **Source chosen**: `data/transactions.db` — **Why**: Row-level event facts provide exact purchase amounts and explicit non-returned order filtering (`is_returned == 0`) over trailing 90-day windows.
- **Feature**: `active_months_12m` — **Source chosen**: `data/transactions_monthly_agg.parquet` — **Why**: Monthly rollup naturally pre-packages month-by-month engagement, eliminating high-volume row scanning across event logs for long-horizon consistency metrics.
- **Feature**: `return_rate_90d` — **Source chosen**: `data/transactions.db` — **Why**: Row-level return flags within exact 90-day windows are required to accurately capture recent product dissatisfaction ratios.

## Data-quality checks

<<At minimum, per ``skill.md``'s Domain Context: no unexpected nulls after defaulting, the zero-activity default is actually applied, monetary/aggregate features stay within a sane bound, and row counts reconcile against the customer count. Per check:>>

- **Check**: No unexpected null or NaN values present after applying default logic — **Catches**: Pipeline transform errors or unhandled outer joins that silently introduce null values into feature vectors — **On failure**: Raise `ValueError` and terminate pipeline with non-zero exit code.
- **Check**: Explicit zero-activity default verification for all 81 zero-transaction customers — **Catches**: Reindexing bugs or dropped customer rows where zero-transaction accounts are omitted or left as NaN — **On failure**: Raise `ValueError` and terminate pipeline with non-zero exit code.
- **Check**: Feature value boundary verification (`return_rate_90d` in `[0.0, 1.0]`, monetary spend features \\(\ge 0.0\\) and \\(< 50000.0\\), counts \\(\ge 0\\)) — **Catches**: Unit conversion errors, join fan-out row duplications, or extreme corrupted currency values — **On failure**: Raise `ValueError` and terminate pipeline with non-zero exit code.
- **Check**: Output DataFrame row count reconciliation (exactly 1,500 rows in training mode, or exact length of `customer_ids` in scoring mode) — **Catches**: Inner join failures, dropped customer profile records, or unintended row multiplication — **On failure**: Raise `ValueError` and terminate pipeline with non-zero exit code.
