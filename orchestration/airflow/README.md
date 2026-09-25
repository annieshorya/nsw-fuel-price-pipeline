# Orchestration (Airflow) — work in progress

`dags/fuel_price_pipeline.py` schedules the pipeline hourly:

1. **extract_load**: pulls a snapshot from the FuelCheck API (`ingestion/fuelcheck_client.py`) and
   appends it to `raw.api_price_snapshot` in Postgres (`warehouse/postgres/load_snapshot.py`, idempotent per pull).
2. **dbt_build**: rebuilds the staging view and marts tables and runs all dbt tests. The run fails if a test fails.

This replaces the `while True: sleep(60)` loop in `stage2-realtime-pipeline/src/publisher.py` with retries,
run history and alerting.

**Status:** both task functions run and are tested outside Airflow. The DAG itself has not yet been deployed.
Next step: an Airflow service in `docker-compose.yml` (or Astronomer's `astro dev start`) with the repo mounted at
`/opt/fuel-pipeline` and a `profiles.yml` in `dbt/fuel_dbt/`.
