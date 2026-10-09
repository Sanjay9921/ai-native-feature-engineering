"""
Test suite for local feature store in feature_store/store.py.

Verifies:
- Version registration and incrementing version numbers.
- Atomic flipping of `is_latest` (new version gets is_latest=1, prior flips to 0).
- Independent retrievability of all versions via get_version(feature_name, version).
- get_latest(feature_name) always returns highest version.
- list_versions(feature_name) returns all versions descending with valid parquet paths.
"""

from pathlib import Path
import pandas as pd
import pytest
from feature_store import store


@pytest.fixture
def temp_store(tmp_path):
    db_path = str(tmp_path / "test_registry.db")
    val_dir = str(tmp_path / "values")
    return {"db_path": db_path, "val_dir": val_dir}


def test_feature_store_versioning_and_retrieval(temp_store):
    db_path = temp_store["db_path"]
    val_dir = temp_store["val_dir"]

    # Sample DataFrame for v1
    df_v1 = pd.DataFrame({
        "customer_id": [1, 2, 3],
        "txn_count_window": [5, 2, 0],
        "as_of_date": ["2026-08-01", "2026-08-01", "2026-08-01"],
    })

    # Register v1
    v1 = store.register_version(
        feature_name="txn_count_window",
        values_df=df_v1,
        description="Transaction count over 90 days",
        source_columns="data/transactions.db:transactions.txn_timestamp",
        transform_summary="count(*) over 90d window",
        business_rationale="v1 quarterly window",
        parameters={"window_days": 90},
        db_path=db_path,
        values_dir=val_dir,
    )
    assert v1 == 1

    # Check v1 is currently latest
    latest_df = store.get_latest("txn_count_window", db_path=db_path)
    assert len(latest_df) == 3
    assert (latest_df["txn_count_window"] == df_v1["txn_count_window"]).all()

    # Register v2 with updated parameter
    df_v2 = pd.DataFrame({
        "customer_id": [1, 2, 3],
        "txn_count_window": [2, 1, 0],
        "as_of_date": ["2026-08-01", "2026-08-01", "2026-08-01"],
    })

    v2 = store.register_version(
        feature_name="txn_count_window",
        values_df=df_v2,
        description="Transaction count over 30 days",
        source_columns="data/transactions.db:transactions.txn_timestamp",
        transform_summary="count(*) over 30d window",
        business_rationale="v2 acute 30d window",
        parameters={"window_days": 30},
        db_path=db_path,
        values_dir=val_dir,
    )
    assert v2 == 2

    # Verify get_latest now returns v2
    latest_v2 = store.get_latest("txn_count_window", db_path=db_path)
    assert (latest_v2["txn_count_window"] == df_v2["txn_count_window"]).all()

    # Verify both versions are independently retrievable
    retrieved_v1 = store.get_version("txn_count_window", 1, db_path=db_path)
    retrieved_v2 = store.get_version("txn_count_window", 2, db_path=db_path)
    assert (retrieved_v1["txn_count_window"] == df_v1["txn_count_window"]).all()
    assert (retrieved_v2["txn_count_window"] == df_v2["txn_count_window"]).all()

    # Verify list_versions
    versions_df = store.list_versions("txn_count_window", db_path=db_path)
    assert len(versions_df) == 2
    # Ordered descending: row 0 is version 2, row 1 is version 1
    assert versions_df.iloc[0]["version"] == 2
    assert versions_df.iloc[0]["is_latest"] == 1
    assert versions_df.iloc[1]["version"] == 1
    assert versions_df.iloc[1]["is_latest"] == 0

    # Verify parquet paths exist on disk
    for path_str in versions_df["parquet_path"]:
        assert Path(path_str).exists()
