import streamlit as st
import json
import os
import threading
import paho.mqtt.client as mqtt
import folium
from streamlit_folium import st_folium
from streamlit_autorefresh import st_autorefresh
import time
from filelock import FileLock, Timeout

# CONSTANTS
MQTT_BROKER = "172.17.34.107"
MQTT_TOPIC = "fuel/check"
DATA_FILE = "fuel_data.json"
INITIAL_RECORD_THRESHOLD = 100
SAVE_INTERVAL = 10  # seconds between file saves
DATA_FILE = "fuel_data.json"
LOCK_FILE = DATA_FILE + ".lock"

# SHARED GLOBAL VARIABLES
buffer = []
existing_keys = set()
data_initialized = False
lock = threading.Lock()
save_in_progress = False

if "mqtt_loop_running" not in st.session_state:
    st.session_state["mqtt_loop_running"] = False


if "app_start_time" not in st.session_state:
    st.session_state["app_start_time"] = time.time()
    print("🔄 App is starting fresh (Streamlit re-run detected)")

if "app_initialized" not in st.session_state:
    with lock:
        buffer.clear()
        existing_keys.clear()
        data_initialized = False

        if not os.path.exists(DATA_FILE):
            print(f"{DATA_FILE} not found. Starting with empty dataset.")
        else:
            print(f"{DATA_FILE} found. Loading existing data.")
    st.session_state["app_initialized"] = True





# LOADING ANY EXISTING DATA
def load_existing_data():

    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "r") as f:
                return json.load(f)
    except Exception as e:
        print("Error loading data file: " , e)
    return []
    



# SAVING DATA TO JSON
# def save_data(data):

#     global save_in_progress

#     if save_in_progress:
#         return  # Skip if save ongoing
#     save_in_progress = True

#     try:
#         with open(DATA_FILE, "w") as f:
#             json.dump(data, f, indent=2)
#     except Exception as e:
#         print("Error saving data file: " , e)
#     save_in_progress = False


def save_data(data):
    lock = FileLock(LOCK_FILE, timeout=2)
    try:
        with lock:
            with open(DATA_FILE, "w") as f:
                json.dump(data, f, indent=2)
    except Timeout:
        print("Timeout: could not acquire file lock to save data.")




# SAVING THE INITIAL DATA 
def save_initial_data():

    global data_initialized

    with lock:
        save_data(buffer)
        data_initialized = True

    print(DATA_FILE , " created with " , str(len(buffer))," records.")




# ACTION AFTER MQTT RECIEVES A MSG
def on_message(client, userdata, msg):

    global buffer, existing_keys, data_initialized

    new_entry = json.loads(msg.payload.decode())
    key = (new_entry.get("stationid"), new_entry.get("fueltype"), new_entry.get("lastupdated"))

    with lock:
        if key in existing_keys:
            return
        existing_keys.add(key)

        if not data_initialized:
            buffer.append(new_entry)
            print("Buffered record" , str(len(buffer)), ":", key)

            if len(buffer) >= INITIAL_RECORD_THRESHOLD:
                threading.Thread(target=save_initial_data, daemon=True).start()
        else:
            current_data = load_existing_data()
            existing_keys_file = {
                (e.get("stationid"), e.get("fueltype"), e.get("lastupdated")) for e in current_data
            }

            if key not in existing_keys_file:
                current_data.append(new_entry)
                save_data(current_data)
                print("Appended new record:", key, "(total: ", len(current_data))
            else:
                print("Duplicate record skipped:", key)




# 
def on_connect(client, userdata, flags, rc):

    if rc == 0:
        print("MQTT connected successfully")
        client.subscribe(MQTT_TOPIC)
    else:
        print("ERROR: MQTT failed to connect")




# MQTT SUBSCRIBER VERIFICATION
def on_subscribe(client, userdata, mid, granted_qos):
    print("Subscribed to topic ", MQTT_TOPIC," with QoS ", granted_qos)




# MQTT SUBSCRIBER 
def mqtt_subscriber():
    
    if st.session_state.get("mqtt_loop_running"):
        print("⚠️ MQTT loop already running! Exiting duplicate thread.")
        return
    st.session_state["mqtt_loop_running"] = True

    while True:
        try:
            client = mqtt.Client(protocol=mqtt.MQTTv311)
            client.on_connect = on_connect
            client.on_subscribe = on_subscribe
            client.on_message = on_message
            client.on_disconnect = on_disconnect

            client.connect(MQTT_BROKER, 1883, 60)
            client.loop_forever()
        except Exception as e:
            print("MQTT subscriber crashed:", e)
            time.sleep(5)  # Backoff before retry




def on_disconnect(client, userdata, rc):
    if rc != 0:
        print(f"Unexpected MQTT disconnect (rc={rc}). Reconnecting...")
        try:
            client.reconnect()
        except Exception as e:
            print("Reconnect failed:", e)
    else:
        print("MQTT disconnected cleanly.")




# TRIGGER FOR FILE UPDATE
def file_has_changed():

    try:
        mtime = os.path.getmtime(DATA_FILE)
        if mtime != st.session_state.get("last_mtime", 0):
            st.session_state["last_mtime"] = mtime
            return True
    except Exception:
        return False
    return False




# LOADING DATA FOR DISPLAY ON MAP
import json

# def load_data_for_display():
#     if not os.path.exists(DATA_FILE):
#         return []
#     try:
#         with open(DATA_FILE, "r") as f:
#             return json.load(f)
#     except json.JSONDecodeError as e:
#         print(f"JSON decode error loading {DATA_FILE}: {e}")
#         return []
#     except Exception as e:
#         print("Error loading data file for display: ", e)
#         return []

def load_data_for_display():
    lock = FileLock(LOCK_FILE, timeout=2)
    try:
        with lock:
            with open(DATA_FILE, "r") as f:
                return json.load(f)
    except Timeout:
        print("Timeout: could not acquire file lock to read data.")
    
    except Exception as e:
        print(f"Error loading data file: {e}")
    return []





# FILTERING DATA BY STATIONS
def group_data_by_station(data):

    stations = {}
    for entry in data:
        sid = entry.get("stationid")
        if not sid:
            continue
        if sid not in stations:
            stations[sid] = {
                "stationname": entry.get("name", "Unknown"),
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




# PERIODICALLY SAVING DATA EVERY SAVE_INTERVAL SECS 
# def periodic_save():

#     while True:
#         time.sleep(SAVE_INTERVAL)
#         if "data" in st.session_state:
#             with lock:
#                 save_data(st.session_state["data"])
#                 print("Periodic save: ", len(st.session_state['data']), " records saved.")





# MAIN DRIVER CODE
def main():
    st.title("Live Fuel Prices Map")

    # Delete data file once only at app start (optional)
    if "app_initialized" not in st.session_state:
        try:
            if os.path.exists(DATA_FILE):
                os.remove(DATA_FILE)
                print(f"{DATA_FILE} removed to start fresh.")
        except Exception as e:
            print("Error deleting existing data file at startup:", e)

        st.session_state["app_initialized"] = True

    # Start MQTT subscriber thread once
    if "mqtt_thread_started" not in st.session_state:
        threading.Thread(target=mqtt_subscriber, daemon=True).start()
        st.session_state["mqtt_thread_started"] = True
        st.session_state["last_mtime"] = 0
        st.session_state["data"] = []


    # Auto-refresh every 5 seconds
    st_autorefresh(interval=10000, limit=10000, key="fuel_autorefresh")

    now = time.time()
    last_reload = st.session_state.get("last_data_reload", 0)

    # Only reload from file every 10 seconds
    if not st.session_state["data"] or (now - last_reload) > 10:
        st.session_state["data"] = load_data_for_display()
        st.session_state["last_data_reload"] = now
        print("Reloaded data from file: ", len(st.session_state['data']), " records.")

    data = st.session_state["data"]
    stations = group_data_by_station(data)
    
    if not data:
        st.warning("Waiting for live fuel data to be received...")
        st.stop()

    # Getting all unique fuel types from stations dict
    fuel_types = set()
    for info in stations.values():
        fuel_types.update(info.get("fuels", {}).keys())
    fuel_types = sorted(fuel_types)

    if not fuel_types:
        fuel_types = ["Regular"]

    # Setting default fuel selection
    default_fuel = st.selectbox("Select fuel type to display", fuel_types, index=fuel_types.index('U91') if 'U91' in fuel_types else 0)
    selected_fuel = default_fuel


    displayed_station_count = sum(
        1 for info in stations.values()
        if selected_fuel in info.get("fuels", {})
    )
    st.write(f"Displaying {displayed_station_count} stations with fuel type '{selected_fuel}'")
    st.write(f"Total records received: {len(data)}")

    # Computing map center
    if stations:
        lats = [s["latitude"] for s in stations.values() if s["latitude"] is not None]
        lons = [s["longitude"] for s in stations.values() if s["longitude"] is not None]
        if lats and lons:
            center_lat = sum(lats) / len(lats)
            center_lon = sum(lons) / len(lons)
        else:
            center_lat, center_lon = -33.8688, 151.2093
    else:
        center_lat, center_lon = -33.8688, 151.2093

    m = folium.Map(location=[center_lat, center_lon], zoom_start=5)

    for sid, info in stations.items():
        lat = info["latitude"]
        lon = info["longitude"]
        if lat is None or lon is None:
            continue

        fuels = info.get("fuels", {})

        if selected_fuel not in fuels:
            continue

        price = fuels.get(selected_fuel)
        fuels_html = f"{selected_fuel}: ${price}" if price else "N/A"

        popup_html = (
            f"<b>{info['stationname']}</b><br>"
            f"{info['address']}<br><br>"
            f"<b>Fuel Prices:</b><br>{fuels_html}<br><br>"
            f"<i>Last updated: {info['lastupdated']}</i>"
        )
        folium.Marker([lat, lon], popup=popup_html).add_to(m)

    st_folium(m, width=1500, height=500)





# TRIGGER
if __name__ == "__main__":
    main()