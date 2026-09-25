"""
Load a FuelCheck price snapshot into PostgreSQL (raw.api_price_snapshot).

    python warehouse/postgres/load_snapshot.py                          # repo sample CSV
    python warehouse/postgres/load_snapshot.py --csv path/to/file.csv
    python warehouse/postgres/load_snapshot.py --live                   # pull from the API now

Idempotent: each source file (or live pull) is recorded in raw.load_log and
is skipped if it has already been loaded. Connection settings come from
POSTGRES_* environment variables (see .env.example).
"""
import argparse
import csv
import io
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg2

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from ingestion.fuelcheck_client import COLUMNS  # noqa: E402

SAMPLE = ROOT / "stage2-realtime-pipeline" / "sample-data" / "fuelPrice_data.csv"
RAW_COLS = [c.lower() for c in COLUMNS] + ["_source_file"]


def connect():
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except ImportError:
        pass
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=os.getenv("POSTGRES_DB", "fuel"),
        user=os.getenv("POSTGRES_USER", "fuel"),
        password=os.getenv("POSTGRES_PASSWORD", "fuel"),
    )


def ensure_schema(cur):
    cur.execute((ROOT / "warehouse" / "postgres" / "01_schema.sql").read_text())


def load_rows(conn, rows, source_file):
    """COPY rows (list of dicts keyed like COLUMNS) into the raw table. Returns rows loaded (0 if skipped)."""
    with conn.cursor() as cur:
        ensure_schema(cur)
        cur.execute("SELECT 1 FROM raw.load_log WHERE source_file = %s", (source_file,))
        if cur.fetchone():
            print(f"skip: {source_file} already loaded")
            return 0
        buf = io.StringIO()
        w = csv.writer(buf)
        for r in rows:
            w.writerow([r.get(c, "") for c in COLUMNS] + [source_file])
        buf.seek(0)
        cur.copy_expert(
            f"COPY raw.api_price_snapshot ({', '.join(RAW_COLS)}) FROM STDIN WITH (FORMAT csv)", buf
        )
        cur.execute("INSERT INTO raw.load_log (source_file, row_count) VALUES (%s, %s)", (source_file, len(rows)))
    conn.commit()
    print(f"loaded {len(rows):,} rows from {source_file}")
    return len(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", type=Path, default=SAMPLE)
    ap.add_argument("--live", action="store_true", help="pull a fresh snapshot from the FuelCheck API")
    args = ap.parse_args()

    if args.live:
        from ingestion.fuelcheck_client import pull_snapshot
        rows = pull_snapshot()
        source = f"api_pull_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
    else:
        with open(args.csv, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        source = args.csv.name

    with connect() as conn:
        load_rows(conn, rows, source)


if __name__ == "__main__":
    main()
