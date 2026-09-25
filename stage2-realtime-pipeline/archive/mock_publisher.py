
import time
import json
import paho.mqtt.client as mqtt

MQTT_BROKER = "172.17.34.107"
MQTT_PORT = 1883
MQTT_TOPIC = "fuelcheck"

stations = [
    {
        "stationid": "TEST-001",
        "brandid": "B-001",
        "brand": "Shell",
        "name": "Shell Test Station",
        "address": "123 Test Road, Sydney NSW",
        "latitude": -33.870,
        "longitude": 151.210,
        "fueltype": "U91",
        "price": 180.9,
        "lastupdated": "29/05/2025 10:00:00"
    },
    {
        "stationid": "TEST-002",
        "brandid": "B-002",
        "brand": "BP",
        "name": "BP Test Station",
        "address": "456 Mock St, Sydney NSW",
        "latitude": -33.873,
        "longitude": 151.215,
        "fueltype": "Diesel",
        "price": 199.5,
        "lastupdated": "29/05/2025 10:00:00"
    }
]

client = mqtt.Client()
client.connect(MQTT_BROKER, MQTT_PORT, 60)

for record in stations:
    client.publish(MQTT_TOPIC, json.dumps(record))
    print(f"Published mock message: {record}")
    time.sleep(1)

client.disconnect()
