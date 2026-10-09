"""
Pure I/O loaders for the three heterogeneous raw sources described in
`data_dictionary.md`. No feature logic belongs here — only loading and basic
type coercion, so ingestion can be unit-tested and swapped independently of
`transforms.py`.
"""

import sqlite3
from pathlib import Path
import pandas as pd


def _resolve_path(path: str) -> Path:
    """Resolve path checking both relative to cwd and parent directory."""
    p = Path(path)
    if p.exists():
        return p
    parent_p = Path("..") / path
    if parent_p.exists():
        return parent_p
    # Also check if cwd is already inside starter-code or root
    alt_p = Path("../data") / p.name
    if alt_p.exists():
        return alt_p
    return p


def load_customers(path: str = "data/customers.csv") -> pd.DataFrame:
    """Load customers.csv.

    - Read the CSV with pandas.
    - Parse `signup_date` as a date (datetime64[ns]).
    - Return one row per customer_id, unmodified otherwise.
    """
    resolved = _resolve_path(path)
    if not resolved.exists():
        raise FileNotFoundError(f"Customers file not found at {path} or {resolved}")

    df = pd.read_csv(resolved)
    df["signup_date"] = pd.to_datetime(df["signup_date"])
    df["customer_id"] = df["customer_id"].astype(int)
    return df


def load_transactions(path: str = "data/transactions.db") -> pd.DataFrame:
    """Load the row-level `transactions` table from the SQLite database.

    - Connect with sqlite3 against `path`.
    - Cast `txn_timestamp` to a real datetime (SQLite stores it as ISO-8601 text).
    - Cast `is_returned` to a clean 0/1 int.
    - Return the full row-level frame — do not aggregate here.
    """
    resolved = _resolve_path(path)
    if not resolved.exists():
        raise FileNotFoundError(f"Transactions db not found at {path} or {resolved}")

    conn = sqlite3.connect(resolved)
    try:
        query = """SELECT * FROM transactions"""
        df = pd.read_sql_query(query, conn)
    finally:
        conn.close()

    df["txn_timestamp"] = pd.to_datetime(df["txn_timestamp"])
    df["is_returned"] = df["is_returned"].astype(int)
    df["customer_id"] = df["customer_id"].astype(int)
    df["amount"] = df["amount"].astype(float)
    return df


def load_monthly_agg(path: str = "data/transactions_monthly_agg.parquet") -> pd.DataFrame:
    """Load the pre-aggregated customer x month parquet extract.

    - Read the parquet file with pandas / pyarrow.
    - Parse `txn_month` as a date (first-of-month, datetime64[ns]).
    - Return as-is — remember customers/months with zero activity have no row.
    """
    resolved = _resolve_path(path)
    if not resolved.exists():
        raise FileNotFoundError(f"Monthly aggregate parquet not found at {path} or {resolved}")

    df = pd.read_parquet(resolved)
    df["txn_month"] = pd.to_datetime(df["txn_month"])
    df["customer_id"] = df["customer_id"].astype(int)
    return df
