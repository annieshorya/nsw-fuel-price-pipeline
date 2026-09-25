"""
Airflow DAG: pull a FuelCheck snapshot every hour, land it in PostgreSQL,
then rebuild and test the dbt models.

    extract_load  ->  dbt_build

Replaces the `while True: sleep(60)` polling loop in the course version with a
scheduled, retryable, observable job. Expects the repo to be mounted at
FUEL_REPO (default /opt/fuel-pipeline) and POSTGRES_* / FUELCHECK_* variables
to be set in the Airflow environment.

Status: work in progress. The task code is tested outside Airflow; the DAG has
not yet been run on a live Airflow deployment.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

from airflow import DAG

try:  # Airflow 3
    from airflow.providers.standard.operators.bash import BashOperator
    from airflow.providers.standard.operators.python import PythonOperator
except ImportError:  # Airflow 2.x
    from airflow.operators.bash import BashOperator
    from airflow.operators.python import PythonOperator

REPO = os.environ.get("FUEL_REPO", "/opt/fuel-pipeline")


def extract_load(**context):
    sys.path.insert(0, REPO)
    from ingestion.fuelcheck_client import pull_snapshot
    from warehouse.postgres.load_snapshot import connect, load_rows

    rows = pull_snapshot()
    source = f"api_pull_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
    with connect() as conn:
        n = load_rows(conn, rows, source)
    if n == 0:
        raise ValueError("FuelCheck returned no rows")
    return n


with DAG(
    dag_id="fuel_price_pipeline",
    description="FuelCheck API -> PostgreSQL raw -> dbt staging/marts + tests",
    start_date=datetime(2026, 1, 1),
    schedule="@hourly",
    catchup=False,
    max_active_runs=1,
    default_args={"retries": 2, "retry_delay": timedelta(minutes=5)},
    tags=["fuel", "dbt", "postgres"],
) as dag:
    load = PythonOperator(task_id="extract_load", python_callable=extract_load)

    dbt_build = BashOperator(
        task_id="dbt_build",
        bash_command=f"cd {REPO}/dbt/fuel_dbt && dbt build --profiles-dir .",
    )

    load >> dbt_build
