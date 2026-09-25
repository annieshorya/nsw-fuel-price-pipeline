import streamlit as st
import json
import paho.mqtt.client as mqtt
from streamlit_folium import st_folium
import folium
import threading
import queue
import time

# ─── MQTT CONFIG ──────────────────────────────────────────────────────────────
MQTT_BROKER = "172.17.34.107"
MQTT_PORT = 1883
MQTT_TOPIC = "fuelcheck"

# Thread-safe queue to carry MQTT messages into Streamlit's main thread
message_queue = queue.Queue()

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        client.subscribe(MQTT_TOPIC)
        print("✅ Subscribed to topic:", MQTT_TOPIC)
    else:
        print("❌ MQTT connect failed:", rc)

def on_message(client, userdata, msg):
    try:
        data = json.loads(msg.payload.decode())
        message_queue.put(data)
    except Exception as e:
        print("❌ MQTT decode error:", e)

def start_mqtt():
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    client.loop_forever()

# ─── STREAMLIT SETUP ───────────────────────────────────────────────────────────
st.set_page_config(layout="wide")
st.title("NSW Live Fuel Prices Dashboard")

# Initialize session state
if "stations" not in st.session_state:
    st.session_state["stations"] = {}
if "mqtt_thread_started" not in st.session_state:
    threading.Thread(target=start_mqtt, daemon=True).start()
    st.session_state["mqtt_thread_started"] = True

# ─── UI CONTROLS ───────────────────────────────────────────────────────────────
fuel_options = ["All", "E10", "U91", "U95", "U98", "Diesel"]
selected_fuel = st.selectbox("Select Fuel Type", options=fuel_options, index=0)

# ─── LIVE MAP PLACEHOLDER ──────────────────────────────────────────────────────
placeholder = st.empty()

# ─── MAIN LIVE LOOP ────────────────────────────────────────────────────────────
while True:
    # Process incoming MQTT messages
    while not message_queue.empty():
        msg = message_queue.get()
        print("✅ Processing MQTT Message:", msg)
        sid = msg.get("stationid")
        ftype = msg.get("fueltype")
        print(f"📦 Station ID: {sid}, Fuel Type: {ftype}, Price: {msg.get('price')}, Lat: {msg.get('latitude')}, Lon: {msg.get('longitude')}")
        if not sid or not ftype:
            continue

        if sid not in st.session_state["stations"]:
            st.session_state["stations"][sid] = {
                "stationid": sid,
                "brandid": msg.get("brandid"),
                "brand": msg.get("brand"),
                "name": msg.get("name"),
                "address": msg.get("address"),
                "latitude": msg.get("latitude"),
                "longitude": msg.get("longitude"),
                "fuels": {}
            }

        st.session_state["stations"][sid]["fuels"][ftype] = {
            "price": msg.get("price"),
            "lastupdated": msg.get("lastupdated")
        }
        print(f"Station ID: {sid}, Fuel Type: {ftype}, Price: {msg.get('price')}, Lat: {msg.get('latitude')}")


    # Render live map and station count
    with placeholder.container():
        m = folium.Map(location=[-33.8688, 151.2093], zoom_start=8)
        display_count = 0

        for station in st.session_state["stations"].values():
            lat = station.get("latitude")
            lon = station.get("longitude")
            if lat is None or lon is None:
                continue

            fuels = station["fuels"]
            if selected_fuel != "All" and selected_fuel not in fuels:
                continue

            popup = f"<b>{station['name']}</b><br>{station['address']}<br><b>Prices:</b><br>"
            for ft, info in fuels.items():
                popup += f"{ft}: ${info['price']} ({info['lastupdated']})<br>"

            tooltip = station["brand"]
            if selected_fuel != "All" and selected_fuel in fuels:
                tooltip += f" – {selected_fuel}: ${fuels[selected_fuel]['price']}"

            folium.Marker(
                location=[float(lat), float(lon)],
                tooltip=tooltip,
                popup=popup,
                icon=folium.Icon(color="blue", icon="info-sign")
            ).add_to(m)
            display_count += 1

        st_folium(m, width=1000, height=600, key=f"map_{int(time.time())}")
        st.markdown(f"**Stations displayed:** {display_count}")
        for sid, station in st.session_state["stations"].items():
            st.write(f"📍 {station['name']} at ({station['latitude']}, {station['longitude']}) with fuels: {list(station['fuels'].keys())}")
        st.caption(f"⏱ Last updated: {time.strftime('%H:%M:%S')}")

    # Pause for 1 second between map updates
    time.sleep(1)
