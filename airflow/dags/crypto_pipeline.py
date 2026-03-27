"""Airflow DAGs for the crypto Kafka streaming pipeline.

DAGs
----
crypto_dbt_refresh
    Runs ``dbt run`` every 5 minutes to keep mart tables current.
    max_active_runs=1 prevents overlapping executions when a run is slow.

crypto_dbt_test
    Runs ``dbt test`` nightly at 02:00 UTC for data-quality validation.
    Failures surface in the Airflow UI and can trigger alerts.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator

# Paths inside the container — set by volume mounts in compose.airflow.yml
_PROJECT_DIR = "/opt/airflow/project/warehouse/dbt/crypto_dbt"
_PROFILES_DIR = "/opt/airflow/project/warehouse/dbt"

# Redirect all dbt write paths to /tmp so the warehouse mount can stay :ro.
# --log-path   : dbt.log (default: <project-dir>/logs/)
# --target-path: compiled SQL + manifests (default: <project-dir>/target/)
_DBT = (
    f"dbt {{cmd}}"
    f" --project-dir {_PROJECT_DIR}"
    f" --profiles-dir {_PROFILES_DIR}"
    f" --log-path /tmp/dbt-logs"
    f" --target-path /tmp/dbt-target"
)

_DEFAULT_ARGS = {
    "owner": "airflow",
    "retries": 1,
    "retry_delay": timedelta(minutes=2),
}

# ── 5-minute mart refresh ─────────────────────────────────────────────────────

with DAG(
    dag_id="crypto_dbt_refresh",
    description="Refresh dbt mart models every 5 minutes",
    schedule="*/5 * * * *",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    max_active_runs=1,
    default_args=_DEFAULT_ARGS,
    tags=["crypto", "dbt"],
) as _:
    BashOperator(
        task_id="dbt_run",
        bash_command=_DBT.format(cmd="run"),
    )

# ── Nightly data-quality tests ────────────────────────────────────────────────

with DAG(
    dag_id="crypto_dbt_test",
    description="Run dbt data-quality tests nightly at 02:00 UTC",
    schedule="0 2 * * *",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    max_active_runs=1,
    default_args=_DEFAULT_ARGS,
    tags=["crypto", "dbt"],
) as _:
    BashOperator(
        task_id="dbt_test",
        bash_command=_DBT.format(cmd="test"),
    )
