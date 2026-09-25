"""Unit tests for the shared FuelCheck client and the Lambda handler (run from repo root: pytest -q)."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "cloud" / "aws" / "lambda_ingest"))

from ingestion.fuelcheck_client import COLUMNS, to_records  # noqa: E402

PAYLOAD = {
    "stations": [
        {"stationid": "1-ABC", "brandid": "B1", "brand": "Shell", "code": 42, "name": "Shell Newtown",
         "address": "1 King St, Newtown NSW 2042", "location": {"latitude": -33.9, "longitude": 151.18},
         "isAdBlueAvailable": False},
    ],
    "prices": [
        {"stationcode": 42, "fueltype": "U91", "price": 189.9, "lastupdated": "25/09/2026 07:15:00"},
        {"stationcode": 42, "fueltype": "E10", "price": 187.9, "lastupdated": "25/09/2026 07:15:00"},
        {"stationcode": 999, "fueltype": "DL", "price": 199.9, "lastupdated": "25/09/2026 07:15:00"},  # unknown station
    ],
}


def test_to_records_joins_prices_to_stations():
    rows = to_records(PAYLOAD)
    assert len(rows) == 2                       # the price for an unknown station is dropped
    assert list(rows[0].keys()) == COLUMNS      # same columns as the publisher / raw table
    assert rows[0]["latitude"] == -33.9 and rows[0]["fueltype"] == "U91"


class FakeS3:
    def __init__(self):
        self.calls = []

    def put_object(self, **kwargs):
        self.calls.append(kwargs)


def test_lambda_writes_partitioned_json(monkeypatch):
    from handler import lambda_handler

    monkeypatch.setenv("RAW_BUCKET", "test-bucket")
    s3 = FakeS3()
    out = lambda_handler({}, None, s3_client=s3, pull=lambda: to_records(PAYLOAD))

    assert out["row_count"] == 2
    call = s3.calls[0]
    assert call["Bucket"] == "test-bucket"
    assert call["Key"].startswith("raw/fuelcheck/dt=") and call["Key"].endswith(".json")
    assert json.loads(call["Body"])["row_count"] == 2
