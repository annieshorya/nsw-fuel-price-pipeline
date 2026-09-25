# AWS ingestion (S3 + Lambda) — work in progress

```
EventBridge (hourly) -> Lambda (handler.py) -> S3 raw/fuelcheck/dt=YYYY-MM-DD/*.json
                                                  |
                          Snowflake external stage + Snowpipe  /  Postgres loader
```

- `lambda_ingest/handler.py` pulls a snapshot with the shared client (`ingestion/fuelcheck_client.py`) and writes
  it to S3, partitioned by date, as immutable raw JSON.
- `lambda_ingest/template.yaml` is an AWS SAM template: private bucket (all public access blocked), function,
  hourly schedule, and API credentials pulled from **Secrets Manager** at deploy time rather than stored in code.

**Status:** the handler is unit-tested with a stubbed S3 client (`tests/test_ingestion.py`). It has not been
deployed. Next steps: deploy to a sandbox account, then point a Snowflake external stage at the bucket.
