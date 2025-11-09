import time
import json
import os
import paho.mqtt.client as mqtt
from identify import get_station_id
import store

MQTT_BROKER = os.environ.get("MQTT_HOST", "localhost")
MQTT_PORT = 8883
MQTT_USER = os.environ.get("MQTT_USER")
MQTT_PASS = os.environ.get("MQTT_PASS")
TOPIC = os.environ.get("MQTT_TOPIC_PUB", "datalogger/readings")

STATION_ID = get_station_id()

def publish_pending():
    readings = store.get_unpublished_readings(limit=50)
    if not readings:
        return

    # Setup MQTT Client
    client = mqtt.Client(client_id=f"pub_{STATION_ID}")
    if MQTT_USER and MQTT_PASS:
        client.username_pw_set(MQTT_USER, MQTT_PASS)
        client.tls_set(ca_certs="/etc/ssl/certs/ca-certificates.crt")
    
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_start()

        published_ids = []
        for row in readings:
            payload = {
                "station_id": STATION_ID,
                "timestamp": row['timestamp'],
                "data": eval(row['modbus_data']) # safely convert stored string back to dict
            }
            
            # Publish with QoS 1 to ensure delivery
            info = client.publish(TOPIC, json.dumps(payload), qos=1)
            info.wait_for_publish()
            
            if info.is_published():
                published_ids.append(row['id'])
                print(f"Published reading {row['id']}")

        client.loop_stop()
        client.disconnect()

        # Mark successful publishes in DB
        if published_ids:
             store.mark_as_published(published_ids)

    except Exception as e:
        print(f"Publish failed: {e}")

if __name__ == "__main__":
    publish_pending()