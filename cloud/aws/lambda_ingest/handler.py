"""
AWS Lambda: pull a FuelCheck snapshot and land it in S3 as raw JSON (bronze layer).

    s3://$RAW_BUCKET/raw/fuelcheck/dt=YYYY-MM-DD/fuelcheck_YYYYMMDDTHHMMSSZ.json

Triggered hourly by an EventBridge schedule (see template.yaml). Downstream,
Snowflake can read the bucket through an external stage + Snowpipe, or the
Postgres loader can read the files directly.

Status: work in progress. The handler is unit-tested with a stubbed S3 client
(tests/test_ingestion.py). It has not been deployed yet.
"""
import json
import os
from datetime import datetime, timezone

try:  # packaged Lambda: fuelcheck_client.py is copied next to this file
    from fuelcheck_client import pull_snapshot
except ImportError:  # running from the repo root
    from ingestion.fuelcheck_client import pull_snapshot


def lambda_handler(event, context, s3_client=None, pull=pull_snapshot):
    if s3_client is None:
        import boto3
        s3_client = boto3.client("s3")

    bucket = os.environ["RAW_BUCKET"]
    now = datetime.now(timezone.utc)
    rows = pull()
    key = f"raw/fuelcheck/dt={now:%Y-%m-%d}/fuelcheck_{now:%Y%m%dT%H%M%SZ}.json"

    body = json.dumps({"pulled_at": now.isoformat(), "row_count": len(rows), "rows": rows})
    s3_client.put_object(Bucket=bucket, Key=key, Body=body.encode("utf-8"), ContentType="application/json")
    return {"bucket": bucket, "key": key, "row_count": len(rows)}
