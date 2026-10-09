"""
Local feature store API: a SQLite metadata/version registry (`feature_store/registry.db`,
table `feature_registry`) plus one parquet value snapshot per registered version
(`feature_store/values/<feature_name>__v<version>.parquet`).

Registry Schema:
- feature_name: TEXT
- version: INTEGER
- created_at: TEXT (ISO-8601)
- description: TEXT
- source_columns: TEXT
- transform_summary: TEXT
- business_rationale: TEXT
- parameters: TEXT (JSON-encoded dict)
- parquet_path: TEXT
- is_latest: INTEGER (0 or 1)
Primary key: (feature_name, version)
"""

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import pandas as pd

REGISTRY_DB = "feature_store/registry.db"
VALUES_DIR = "feature_store/values"


def _get_db_path(db_path: str = REGISTRY_DB) -> Path:
    p = Path(db_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def init_registry(db_path: str = REGISTRY_DB) -> None:
    """Initialize the SQLite feature_registry table if it does not exist."""
    path = _get_db_path(db_path)
    conn = sqlite3.connect(path)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS feature_registry (
            feature_name TEXT NOT NULL,
            version INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            description TEXT NOT NULL,
            source_columns TEXT NOT NULL,
            transform_summary TEXT NOT NULL,
            business_rationale TEXT NOT NULL,
            parameters TEXT NOT NULL,
            parquet_path TEXT NOT NULL,
            is_latest INTEGER NOT NULL CHECK (is_latest IN (0, 1)),
            PRIMARY KEY (feature_name, version)
        );
        """
    )
    conn.commit()
    conn.close()


def register_version(
    feature_name: str,
    values_df: pd.DataFrame,
    description: str,
    source_columns: str,
    transform_summary: str,
    business_rationale: str,
    parameters: dict,
    db_path: str = REGISTRY_DB,
    values_dir: str = VALUES_DIR,
) -> int:
    """Write a new parquet snapshot, insert the registry row, flip is_latest, return the
    new version number.

    - Increments version number per feature_name (starts at 1).
    - Writes values_df to feature_store/values/<feature_name>__v<version>.parquet without overwriting.
    - Atomically inserts registry metadata and updates is_latest.
    """
    init_registry(db_path)
    path = _get_db_path(db_path)
    v_dir = Path(values_dir)
    v_dir.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(path)
    cursor = conn.cursor()

    try:
        cursor.execute("BEGIN IMMEDIATE")
        # 1. Determine next version
        cursor.execute(
            "SELECT COALESCE(MAX(version), 0) + 1 FROM feature_registry WHERE feature_name = ?",
            (feature_name,),
        )
        new_version = cursor.fetchone()[0]

        # 2. Prepare file path & write parquet
        parquet_rel_path = f"{values_dir}/{feature_name}__v{new_version}.parquet"
        parquet_full_path = Path(parquet_rel_path)
        if parquet_full_path.exists():
            raise FileExistsError(f"Parquet file already exists at {parquet_full_path}; versions are immutable.")

        # Ensure required columns exist
        required_cols = {"customer_id", "as_of_date"}
        if not required_cols.issubset(set(values_df.columns)):
            raise ValueError(f"values_df must contain at least 'customer_id' and 'as_of_date'. Found: {values_df.columns.tolist()}")

        values_df.to_parquet(parquet_full_path, index=False)

        # 3. Flip prior latest versions to 0
        cursor.execute(
            "UPDATE feature_registry SET is_latest = 0 WHERE feature_name = ? AND is_latest = 1",
            (feature_name,),
        )

        # 4. Insert new registry row
        created_at = datetime.now(timezone.utc).isoformat()
        params_json = json.dumps(parameters)
        cursor.execute(
            """
            INSERT INTO feature_registry (
                feature_name, version, created_at, description, source_columns,
                transform_summary, business_rationale, parameters, parquet_path, is_latest
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                feature_name,
                new_version,
                created_at,
                description,
                source_columns,
                transform_summary,
                business_rationale,
                params_json,
                parquet_rel_path,
            ),
        )
        conn.commit()
        return new_version
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_latest(feature_name: str, db_path: str = REGISTRY_DB) -> pd.DataFrame:
    """Return the DataFrame for the version currently flagged is_latest = 1."""
    init_registry(db_path)
    conn = sqlite3.connect(_get_db_path(db_path))
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT parquet_path FROM feature_registry WHERE feature_name = ? AND is_latest = 1",
            (feature_name,),
        )
        row = cursor.fetchone()
        if not row:
            raise KeyError(f"Feature '{feature_name}' not found in registry.")
        parquet_path = Path(row[0])
        return pd.read_parquet(parquet_path)
    finally:
        conn.close()


def get_version(feature_name: str, version: int, db_path: str = REGISTRY_DB) -> pd.DataFrame:
    """Return the DataFrame for a specific (feature_name, version)."""
    init_registry(db_path)
    conn = sqlite3.connect(_get_db_path(db_path))
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT parquet_path FROM feature_registry WHERE feature_name = ? AND version = ?",
            (feature_name, version),
        )
        row = cursor.fetchone()
        if not row:
            raise KeyError(f"Feature '{feature_name}' version {version} not found in registry.")
        parquet_path = Path(row[0])
        return pd.read_parquet(parquet_path)
    finally:
        conn.close()


def list_versions(feature_name: str, db_path: str = REGISTRY_DB) -> pd.DataFrame:
    """Return every registered version's metadata row for feature_name, most recent first."""
    init_registry(db_path)
    conn = sqlite3.connect(_get_db_path(db_path))
    try:
        query = """
            SELECT feature_name, version, created_at, description, source_columns,
                   transform_summary, business_rationale, parameters, parquet_path, is_latest
            FROM feature_registry
            WHERE feature_name = ?
            ORDER BY version DESC
        """
        df = pd.read_sql_query(query, conn, params=(feature_name,))
        return df
    finally:
        conn.close()
