import streamlit as st
from streamlit_folium import st_folium
import folium
import pandas as pd
import json
import paho.mqtt.client as mqtt
import threading
import time

# --- Dashboard Title ---
st.title("NSW Fuel Price Dashboard (Live via MQTT)")

# MQTT CONFIG
MQTT_BROKER = "172.17.34.107"
MQTT_PORT = 1883
MQTT_TOPIC = "fuelcheck"

# --- Session state for live data ---
if "received_data" not in st.session_state:
    st.session_state["received_data"] = []

# MQTT Callbacks
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Connected to MQTT broker")
        client.subscribe(MQTT_TOPIC)
    else:
        print("Failed to connect, return code", rc)

def on_message(client, userdata, msg):
    try:
        data = json.loads(msg.payload.decode())
        st.session_state["received_data"].append(data)
    except Exception as e:
        print("Error processing MQTT message:", e)

# MQTT Background Thread
def start_mqtt():
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    client.loop_forever()

# Start MQTT client thread once
if "mqtt_thread_started" not in st.session_state:
    mqtt_thread = threading.Thread(target=start_mqtt)
    mqtt_thread.daemon = True
    mqtt_thread.start()
    st.session_state["mqtt_thread_started"] = True

# --- UI Filters ---
fuel_types = list({record["fueltype"] for record in st.session_state["received_data"] if "fueltype" in record})
default_fuel = st.selectbox("Select Fuel Type", sorted(fuel_types)) if fuel_types else "U91"

brands = list({record["brand"] for record in st.session_state["received_data"] if "brand" in record})
selected_brand = st.selectbox("Select Brand", ["All"] + sorted(brands)) if brands else "All"

# --- Filter records ---
filtered_data = []
for record in st.session_state["received_data"]:
    if record.get("fueltype") == default_fuel:
        if selected_brand == "All" or record.get("brand") == selected_brand:
            filtered_data.append(record)

# --- Initialize session state ---
if "center" not in st.session_state:
    st.session_state["center"] = [-33.8688, 151.2093]  # Sydney
if "zoom" not in st.session_state:
    st.session_state["zoom"] = 11

# --- Create map ---
m = folium.Map(location=st.session_state["center"], zoom_start=st.session_state["zoom"])
fg = folium.FeatureGroup(name="Live Stations")

for record in filtered_data:
    lat, lon = record.get("latitude"), record.get("longitude")
    if lat is None or lon is None:
        continue

    try:
        lat, lon = float(lat), float(lon)
    except:
        continue

    tooltip = f"{record.get('brand', 'Unknown')}<br>{record.get('fueltype')}: {record.get('price')}"
    popup_html = f"""
    <b>{record.get('name')}</b><br>
    {record.get('address')}<br><br>
    <b>Price:</b> {record.get('price')}<br>
    <b>Fuel Type:</b> {record.get('fueltype')}<br>
    <b>Updated:</b> {record.get('lastupdated')}
    """

    marker = folium.Marker(
        location=[lat, lon],
        popup=folium.Popup(popup_html, max_width=300),
        tooltip=tooltip,
        icon=folium.Icon(color="blue", icon="info-sign")
    )
    fg.add_child(marker)

m.add_child(fg)

# --- Display Map ---
st_folium(
    m,
    center=st.session_state["center"],
    zoom=st.session_state["zoom"],
    key="newmap",
    feature_group_to_add=fg,
    height=500,
    width=700,
)

st.write(f"Stations shown: {len(filtered_data)}")
