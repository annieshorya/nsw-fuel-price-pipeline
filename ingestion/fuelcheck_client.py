"""
Small, reusable client for the NSW FuelCheck API (OAuth2 client-credentials).

Used by the Postgres loader, the Airflow DAG and the AWS Lambda function, so the
fetch + flatten logic lives in one place. It produces the same columns as the
original stage-2 publisher (stage2-realtime-pipeline/src/publisher.py).

Credentials come from environment variables (see stage2-realtime-pipeline/.env.example):
    FUELCHECK_API_KEY, FUELCHECK_AUTH_HEADER
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime

import requests

TOKEN_URL = "https://api.onegov.nsw.gov.au/oauth/client_credential/accesstoken?grant_type=client_credentials"
PRICES_URL = "https://api.onegov.nsw.gov.au/FuelPriceCheck/v1/fuel/prices"

COLUMNS = [
    "stationid", "brandid", "brand", "code", "name", "address",
    "latitude", "longitude", "isAdBlueAvailable", "fueltype", "price", "lastupdated",
]


def get_access_token(auth_header: str | None = None, timeout: int = 30) -> str:
    """Exchange the Basic auth header for a bearer token."""
    auth_header = auth_header or os.environ["FUELCHECK_AUTH_HEADER"]
    resp = requests.get(TOKEN_URL, headers={"accept": "application/json", "Authorization": auth_header}, timeout=timeout)
    resp.raise_for_status()
    return resp.json()["access_token"]


def fetch_prices(token: str, api_key: str | None = None, timeout: int = 60) -> dict:
    """Return the raw API payload: {"stations": [...], "prices": [...]}."""
    headers = {
        "accept": "application/json",
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
        "apikey": api_key or os.environ["FUELCHECK_API_KEY"],
        "transactionid": str(uuid.uuid4()),
        "requesttimestamp": datetime.utcnow().strftime("%d/%m/%Y %I:%M:%S %p"),
    }
    resp = requests.get(PRICES_URL, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def to_records(payload: dict) -> list[dict]:
    """Join each price to its station -> one row per station x fuel type."""
    stations = {s.get("code"): s for s in payload.get("stations", [])}
    rows = []
    for p in payload.get("prices", []):
        st = stations.get(p.get("stationcode"))
        if not st:
            continue
        loc = st.get("location") or {}
        rows.append({
            "stationid": st.get("stationid"),
            "brandid": st.get("brandid"),
            "brand": st.get("brand"),
            "code": st.get("code"),
            "name": st.get("name"),
            "address": st.get("address"),
            "latitude": loc.get("latitude"),
            "longitude": loc.get("longitude"),
            "isAdBlueAvailable": st.get("isAdBlueAvailable"),
            "fueltype": p.get("fueltype"),
            "price": p.get("price"),
            "lastupdated": p.get("lastupdated"),
        })
    return rows


def pull_snapshot() -> list[dict]:
    """Token -> prices -> flat records, in one call."""
    return to_records(fetch_prices(get_access_token()))
