import requests
from datetime import datetime
import pandas as pd
import json
import time
import paho.mqtt.client as mqtt

""" --- CONSTANTS --- """

API_KEY = "LGrSZYGFf90fCYANg4jcR7hFC7be3ZXF"
AUTH_HEADER = "Basic TEdyU1pZR0ZmOTBmQ1lBTmc0amNSN2hGQzdiZTNaWEY6dUZpR2xEdmJPcUlrVFBVNQ=="
BASE_URL = "https://api.onegov.nsw.gov.au/FuelPriceCheck/v1"
TOKEN_URL = "https://api.onegov.nsw.gov.au/oauth/client_credential/accesstoken?grant_type=client_credentials"

MQTT_BROKER = "172.17.34.107"
MQTT_PORT = 1883
MQTT_TOPIC = "fuelcheck"

""" --- TOKEN --- """

def get_security_token():
    headers = {
        "accept": "application/json",
        "Authorization": AUTH_HEADER
    }
    try:
        response = requests.get(TOKEN_URL, headers=headers)
        if response.status_code == 200:
            return response.json().get("access_token")
        else:
            print("Token Error:", response.status_code, response.text)
            return None
    except Exception as e:
        print("Token Exception:", e)
        return None

""" --- DATA RETRIEVAL --- """

def retrieve_data(access_token, transaction_id):
    prices_url = BASE_URL + "/fuel/prices"
    timestamp = datetime.now().strftime("%d/%m/%Y %I:%M:%S %p")

    headers = {
        "accept": "application/json",
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; charset=utf-8",
        "apikey": API_KEY,
        "transactionid": str(transaction_id),
        "requesttimestamp": timestamp
    }

    try:
        response = requests.get(prices_url, headers=headers)
        print("Status:", response.status_code)

        if response.status_code == 200:
            json_data = response.json()
            return json_data.get("stations", []), json_data.get("prices", [])
        elif response.status_code == 401:
            print("Access token expired. Refreshing...")
            return None, None  # Trigger retry
        else:
            print("API Error:", response.text)
            return [], []
    except Exception as e:
        print("Data retrieval error:", e)
        return [], []

""" --- DATA PROCESSING --- """

def process_data(stations, prices):
    records = []
    station_lookup = {
        s["code"]: {
            "stationid": s.get("stationid"),
            "brandid": s.get("brandid"),
            "brand": s.get("brand"),
            "code": s.get("code"),
            "name": s.get("name"),
            "address": s.get("address"),
            "latitude": s.get("location", {}).get("latitude"),
            "longitude": s.get("location", {}).get("longitude"),
            "isAdBlueAvailable": s.get("isAdBlueAvailable")
        }
        for s in stations
    }

    for p in prices:
        station_info = station_lookup.get(p.get("stationcode"))
        if station_info:
            record = {
                **station_info,
                "fueltype": p.get("fueltype"),
                "price": p.get("price"),
                "lastupdated": p.get("lastupdated")
            }
            records.append(record)

    return pd.DataFrame(records)

def clean_dataset(df):
    df = df.dropna(subset=["stationid", "address", "latitude", "longitude"])
    df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
    df["isAdBlueAvailable"] = df["isAdBlueAvailable"].astype(bool)
    df = df.dropna(subset=["latitude", "longitude"])

    # Filter for NSW geographic bounds
    df = df[
        (df["latitude"].between(-38, -28)) &
        (df["longitude"].between(140, 154))
    ]

    df["brand"] = df["brand"].str.strip().str.title()
    df["name"] = df["name"].str.strip()
    return df

""" --- MQTT PUBLISH --- """

def publish_to_mqtt(df):
    try:
        client = mqtt.Client(protocol=mqtt.MQTTv311)
        client.connect(MQTT_BROKER, MQTT_PORT, 60)

        for idx, row in df.iterrows():
            msg = row.to_json()
            client.publish(MQTT_TOPIC, msg, retain=True)
            print(f"Published {idx + 1}/{len(df)}: {msg}")
            time.sleep(0.1)

        client.disconnect()
        print("Finished publishing to MQTT.")

    except Exception as e:
        print("MQTT Error:", e)

""" --- MAIN LOOP --- """

def run_service():
    transaction_id = 0
    while True:
        transaction_id += 1
        print(f"\n[{datetime.now()}] Starting new data cycle...")

        access_token = get_security_token()
        if not access_token:
            print("No access token. Skipping cycle.")
            time.sleep(60)
            continue

        stations, prices = retrieve_data(access_token, transaction_id)

        if stations is None or prices is None:
            print("Retrying with fresh token...")
            access_token = get_security_token()
            stations, prices = retrieve_data(access_token, transaction_id)

        if not stations or not prices:
            print("No data retrieved. Skipping.")
            time.sleep(60)
            continue

        df = process_data(stations, prices)
        df = clean_dataset(df)
        df.to_csv("fuelPrice_data.csv", index=False)
        publish_to_mqtt(df)

        print(f"[{datetime.now()}] Cycle complete. Waiting 60 seconds.\n")
        time.sleep(60)

""" --- ENTRY POINT --- """

if __name__ == "__main__":
    run_service()
