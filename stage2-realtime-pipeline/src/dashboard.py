import streamlit as st
import json
import os
import threading
import time
from filelock import FileLock, Timeout
import folium
from streamlit_folium import st_folium
from streamlit_autorefresh import st_autorefresh
import paho.mqtt.client as mqtt
from dotenv import load_dotenv

load_dotenv()

# Constants for configuration (override via .env, see .env.example)
mqtt_broker = os.environ.get("MQTT_BROKER", "127.0.0.1")
mqtt_topic = os.environ.get("MQTT_TOPIC", "fuel/check")
data_file = "fuel_data.json"
lock_file = data_file + ".lock"
initial_record_threshold = 100

# Global variables
buffer = []
existing_keys = set()
data_initialized = False
lock = threading.Lock()

# Streamlit session state initialization
if "mqtt_loop_running" not in st.session_state:
    st.session_state["mqtt_loop_running"] = False

if "app_start_time" not in st.session_state:
    st.session_state["app_start_time"] = time.time()

if "app_initialized" not in st.session_state:
    with lock:
        buffer.clear()
        existing_keys.clear()
        data_initialized = False
    st.session_state["app_initialized"] = True

# Data loading and saving fuel data from JSON file
def loadExistingData():
    try:
        if os.path.exists(data_file):
            with open(data_file, "r") as f:
                return json.load(f)
    except Exception as e:
        print("Error loading data file:", e)
    return []

# Write data to the JSON file
def saveData(data):
    file_lock = FileLock(lock_file, timeout=2)
    try:
        with file_lock:
            with open(data_file, "w") as f:
                json.dump(data, f, indent=2)
    except Timeout:
        print("Timeout: could not acquire file lock to save data.")

# Saving initial buffer
def saveInitialData():
    global data_initialized
    with lock:
        saveData(buffer)
        data_initialized = True

# MQTT callbacks

# Handling incoming MQTT messages and saving unique records
def onMessage(client, userdata, msg):
    global buffer, existing_keys, data_initialized
    new_entry = json.loads(msg.payload.decode())
    key = (new_entry.get("stationid"), new_entry.get("fueltype"), new_entry.get("lastupdated"))
    with lock:
        if key in existing_keys:
            return
        existing_keys.add(key)
        if not data_initialized:
            buffer.append(new_entry)
            if len(buffer) >= initial_record_threshold:
                threading.Thread(target=saveInitialData, daemon=True).start()
        else:
            current_data = loadExistingData()
            existing_keys_file = {
                (e.get("stationid"), e.get("fueltype"), e.get("lastupdated")) for e in current_data
            }
            if key not in existing_keys_file:
                current_data.append(new_entry)
                saveData(current_data)

# Subscribing MQTT
def onConnect(client, userdata, flags, rc):
    if rc == 0:
        client.subscribe(mqtt_topic)

def onSubscribe(client, userdata, mid, granted_qos):
    pass

# Handling diconnection
def onDisconnect(client, userdata, rc):
    if rc != 0:
        try:
            client.reconnect()
        except Exception:
            pass

# Starting MQTT subscription loop
def mqttSubscriber():
    if st.session_state.get("mqtt_loop_running"):
        return
    st.session_state["mqtt_loop_running"] = True
    while True:
        try:
            client = mqtt.Client(protocol=mqtt.MQTTv311)
            client.on_connect = onConnect
            client.on_subscribe = onSubscribe
            client.on_message = onMessage
            client.on_disconnect = onDisconnect
            client.connect(mqtt_broker, 1883, 60)
            client.loop_forever()
        except Exception:
            time.sleep(5)

# Checking file changes
def fileHasChanged():
    try:
        mtime = os.path.getmtime(data_file)
        if mtime != st.session_state.get("last_mtime", 0):
            st.session_state["last_mtime"] = mtime
            return True
    except Exception:
        return False
    return False

# Loading file data with file lock
def loadDataForDisplay():
    file_lock = FileLock(lock_file, timeout=2)
    try:
        with file_lock:
            with open(data_file, "r") as f:
                return json.load(f)
    except Timeout:
        pass
    except Exception:
        pass
    return []

# Data grouping and filtering
def groupDataByStation(data):
    stations = {}
    for entry in data:
        sid = entry.get("stationid")
        if not sid:
            continue
        if sid not in stations:
            stations[sid] = {
                "stationname": entry.get("name", "Unknown"),
                "brand": entry.get("brand", "Unknown"),
                "address": entry.get("address", "No address"),
                "latitude": entry.get("latitude"),
                "longitude": entry.get("longitude"),
                "lastupdated": entry.get("lastupdated", ""),
                "fuels": {}
            }
        fueltype = entry.get("fueltype")
        price = entry.get("price")
        if fueltype and price is not None:
            stations[sid]["fuels"][fueltype] = price
        if entry.get("lastupdated") > stations[sid]["lastupdated"]:
            stations[sid]["lastupdated"] = entry.get("lastupdated")
    return stations

# Dashboard layout
def main():
    st.markdown("""
        <style>
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        header {visibility: hidden;}
        .block-container {padding-top: 1.5rem; padding-bottom: 0rem;}
        .stMultiSelect .css-12jo7m5, .stMultiSelect .css-1rhbuit-multiValue {
            background-color: #e74c3c !important;
            color: #fff !important;
            border-radius: 4px;
            font-weight: 600;
        }
        .stMultiSelect .css-xb97g8 {
            color: #fff !important;
        }
        .stMultiSelect .css-1hb7zxy-IndicatorsContainer {
            color: #222 !important;
        }
        .stSelectbox > div, .stMultiSelect > div {
            background: #e3eaf2 !important;
        }
        </style>
        """, unsafe_allow_html=True)

    # Dashboard title and subtitle
    st.markdown(
        "<h1 style='text-align: center; margin-bottom: 0.2em; font-size: 2.8em;'>Fuel Prices Dashboard</h1>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<div style='text-align: center; color: #888; margin-bottom: 1.5em;'>Live fuel prices on map. Data automatically updates every 10 seconds.</div>",
        unsafe_allow_html=True,
    )

    # Starting MQTT subscriber thread only once
    if "mqtt_thread_started" not in st.session_state:
        threading.Thread(target=mqttSubscriber, daemon=True).start()
        st.session_state["mqtt_thread_started"] = True
        st.session_state["last_mtime"] = 0
        st.session_state["data"] = []

    # Refreshing the dashboard in 10 seconds
    st_autorefresh(interval=10000, limit=None, key="fuel_autorefresh")

    now = time.time()
    last_reload = st.session_state.get("last_data_reload", 0)

    # Reloading data from file 
    if not st.session_state["data"] or (now - last_reload) > 10:
        st.session_state["data"] = loadDataForDisplay()
        st.session_state["last_data_reload"] = now

    data = st.session_state["data"]
    stations = groupDataByStation(data)

    if not data:
        st.warning("Waiting for live fuel data to be received...")
        st.stop()

    # Filters for all unique fuel types and brands
    fuel_types = set()
    brands = set()
    for info in stations.values():
        fuel_types.update(info.get("fuels", {}).keys())
        brands.add(info.get("brand", "Unknown"))
    fuel_types = sorted(fuel_types)
    brands = sorted(brands)

    # Filter widgets
    filter_col1, filter_col2 = st.columns([1, 2], gap="medium")

    with filter_col1:
        if not fuel_types:
            fuel_types = ["Regular"]
        default_fuel = "U91" if "U91" in fuel_types else fuel_types[0]
        selected_fuel = st.selectbox("Select fuel type", fuel_types, index=fuel_types.index(default_fuel), key="fuel_type")

    with filter_col2:
        selected_brands = st.multiselect(
            "Select brands",
            options=brands,
            default=[],
            key="brand_multiselect",
            placeholder="All Brands"
        )

    # Filter stations by selected fuel and brands
    filtered_stations = {
        sid: info for sid, info in stations.items()
        if selected_fuel in info.get("fuels", {}) and
           (info.get("brand", "Unknown") in selected_brands if selected_brands else True)
    }

    # Count of data displayed
    st.markdown(
        f"""
        <div style='padding: 8px 0 12px 0; font-size:1.15em;'>
            <b>Displaying {len(filtered_stations)} stations</b> with fuel type <b>'{selected_fuel}'</b>
            {"for selected brands" if selected_brands else ""}
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.write(f"Total records received: {len(data)}")

    # Centering and zooming the map
    if filtered_stations:
        lats = [s["latitude"] for s in filtered_stations.values() if s["latitude"] is not None]
        lons = [s["longitude"] for s in filtered_stations.values() if s["longitude"] is not None]
        if lats and lons:
            center_lat = sum(lats) / len(lats)
            center_lon = sum(lons) / len(lons)
        else:
            center_lat, center_lon = -33.8688, 151.2093
    else:
        center_lat, center_lon = -33.8688, 151.2093

    # Map changes
    m = folium.Map(location=[-33.8688, 151.2093], zoom_start=12, control_scale=True)

    # Marker for each station
    for sid, info in filtered_stations.items():
        lat = info["latitude"]
        lon = info["longitude"]
        if lat is None or lon is None:
            continue
        price = info["fuels"].get(selected_fuel)
        popup_html = (
            f"<b>{info['stationname']}</b> ({info['brand']})<br>"
            f"{info['address']}<br><br>"
            f"<b>{selected_fuel}:</b> <span style='color:#0072ce;'>${price}</span><br>"
            f"<i>Last updated: {info['lastupdated']}</i>"
        )
        folium.Marker(
            [lat, lon],
            popup=folium.Popup(popup_html, max_width=350),
            icon=folium.Icon(color="darkblue", icon="gas-pump", prefix='fa')
        ).add_to(m)

    # Displaying map
    st_folium(m, width=1500, height=600)

# Entry point
if __name__ == "__main__":
    main()
