import requests
from datetime import datetime
import pandas as pd
import json
import time
import paho.mqtt.client as mqtt
from threading import Thread
import streamlit as st
from streamlit_folium import st_folium
import folium

""" CONSTANTS """

API_KEY = "E4s0ZAuZTcikpu0ObVFPDZzPYDWyzsJw"
API_SECRET = "vmX91Mq8DgE4Fke9"
AUTH_HEADER = "Basic RTRzMFpBdVpUY2lrcHUwT2JWRlBEWnpQWURXeXpzSnc6dm1YOTFNcThEZ0U0RmtlOQ=="

BASE_URL = "https://api.onegov.nsw.gov.au/FuelPriceCheck/v1"

MQTT_BROKER = "172.17.34.107"
MQTT_PORT = 1883
MQTT_TOPIC = "fuel/check"
ACCESS_TOKEN = ""

CNT = 0

def get_security_token():

    auth_header = AUTH_HEADER

    url = "https://api.onegov.nsw.gov.au/oauth/client_credential/accesstoken?grant_type=client_credentials"

    headers = {
        "accept": "application/json",
        "Authorization": auth_header
    }

    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        token_data = response.json()
        access_token = token_data.get("access_token")
        return access_token
    else:
        print("Error retrieving token:", response.status_code, response.text)
        return ""



""" Data Retreival """

def retrieve_data():

    global CNT
    global ACCESS_TOKEN

    prices_url = BASE_URL + "/fuel/prices"
    request_timestamp = datetime.now().strftime("%d/%m/%Y %I:%M:%S %p")
    CNT+=1

    headers = {"accept": "application/json", "Authorization": "Bearer "+ ACCESS_TOKEN, "Content-Type": "application/json; charset=utf-8",
        "apikey": API_KEY, "transactionid": str(CNT), "requesttimestamp": request_timestamp}

    prices_response = requests.get(prices_url, headers=headers)

    print("Status:", prices_response.status_code)

    if prices_response.status_code == 200:
        prices_json = prices_response.json()
        print("Prices response keys:", prices_json.keys())

        return prices_json.get("stations", []), prices_json.get("prices", [])
    else:
        print("API Error")
        print("Prices Response:", prices_response.text)
        return [],[]



""" Saving Data to Dataframe """

def process_and_save(stations, prices):

    records = []
    station_lookup = {st.get("code"):
                          {'brandid': st.get("brandid"), 'stationid': st.get("stationid"), 'brand': st.get("brand"),
                           'code': st.get("code"), 'name': st.get("name"), 'address': st.get("address"), 'latitude': st.get("location", {}).get("latitude"),
                           'longitude': st.get("location", {}).get("longitude"),'isAdBlueAvailable': st.get("isAdBlueAvailable")
                          }
                      for st in stations}

    for p in prices:

        station_id = p.get("stationcode")
        station_info = station_lookup.get(station_id)

        if station_info:
            record = {
                **station_info,
                "fueltype": p.get("fueltype"),
                "price": p.get("price"),
                "lastupdated": p.get("lastupdated")
            }
            records.append(record)

    df = pd.DataFrame(records)
    df.to_csv("fuelPrice_data.csv", index=False)
    return df


def clean_dataset(df):

    critical_fields = ["stationid", "address", "latitude", "longitude"]
    df_clean = df.dropna(subset=critical_fields)

    df_clean["latitude"] = pd.to_numeric(df_clean["latitude"], errors="coerce")
    df_clean["longitude"] = pd.to_numeric(df_clean["longitude"], errors="coerce")
    df_clean["isAdBlueAvailable"] = df_clean["isAdBlueAvailable"].astype(bool)

    df_clean = df_clean.dropna(subset=["latitude", "longitude"])

    # NSW approx bounding box: lat -38 to -28, lon 140 to 154
    df_clean = df_clean[
        (df_clean["latitude"].between(-38, -28)) &
        (df_clean["longitude"].between(140, 154))
    ]

    df_clean["brand"] = df_clean["brand"].str.strip().str.title()
    df_clean["name"] = df_clean["name"].str.strip()

    return df_clean



""" Publishing to MQTT Server """

def publish_to_mqtt(df):
    
    client = mqtt.Client(protocol=mqtt.MQTTv311)
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    
    for idx, row in df.iterrows():
        message = row.to_json()
        client.publish(MQTT_TOPIC, message)
        print("Published record ", str(idx+1)+"/"+str(len(df)))
        time.sleep(0.1)
        
    client.disconnect()
    print("All records published to MQTT.")


def run_service():

    while True:
        print(datetime.now(), "Fetching prices...")

        stations, prices = retrieve_data()
        print("Retrieved " + str(len(stations)) + " station records.")
        print("Retrieved " + str(len(prices)) + " price records.")

        df = process_and_save(stations, prices)
        print("Retrieved data with " + str(df.shape) + " rows and columns.")

        df = clean_dataset(df)

        publish_to_mqtt(df)
        time.sleep(60)

if __name__ == "__main__":

    ACCESS_TOKEN = get_security_token()
    print("Access Token:", ACCESS_TOKEN)
    run_service()
