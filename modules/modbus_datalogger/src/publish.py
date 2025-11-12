# publish.py

import json
import sqlite3
import sys
import requests
import paho.mqtt.client as mqtt
from datetime import datetime


def api(db_path, config):
    """
    Publishes the oldest unpublished row to the API endpoint.
    
    Args:
        db_path (str): Path to the SQLite database file.
        config (dict): The API configuration from testid-publish.json
        
    Returns:
        bool: True if successfully published, False otherwise.
    """
    if not config.get("enabled", False):
        print("API publishing is disabled in config.")
        return False
    
    try:
        # Get the oldest unpublished row
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, timestamp, data 
                FROM readings 
                WHERE is_published = 0 
                ORDER BY timestamp ASC 
                LIMIT 1
            """)
            row = cursor.fetchone()
            
            if not row:
                print("No unpublished rows found for API.")
                return False
            
            row_id, timestamp, data = row
            
        # Parse the sensor data
        sensor_data = json.loads(data)
        
        # Prepare the payload based on payload_format in config
        payload_format = config.get("payload_format", "wrapped")
        
        if payload_format == "direct":
            # Send sensor data directly without wrapping
            payload = sensor_data
        else:
            # Default: wrap with timestamp and data
            payload = {
                "timestamp": timestamp,
                "data": sensor_data
            }
        
        # Build headers
        headers = {"Content-Type": "application/json"}
        
        # Add API key based on auth_type
        auth_type = config.get("auth_type", "bearer")
        api_key = config.get("api_key", "")
        
        if auth_type == "x-api-key":
            headers["X-API-KEY"] = api_key
        elif auth_type == "bearer":
            headers["Authorization"] = f"Bearer {api_key}"
        elif auth_type == "header":
            # Custom header name
            header_name = config.get("api_key_header", "X-API-KEY")
            headers[header_name] = api_key
        
        # Make the API request
        response = requests.post(
            config["url"],
            json=payload,
            headers=headers,
            timeout=config.get("timeout_seconds", 10)
        )
        
        if response.status_code in [200, 201, 204]:
            # Mark as published
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE readings SET is_published = 1 WHERE id = ?",
                    (row_id,)
                )
                conn.commit()
            
            print(f"Successfully published row {row_id} to API (Status: {response.status_code})")
            return True
        else:
            print(f"API request failed with status {response.status_code}: {response.text}")
            return False
            
    except requests.exceptions.Timeout:
        print("API request timed out.")
        return False
    except requests.exceptions.RequestException as e:
        print(f"API request error: {e}")
        return False
    except sqlite3.Error as e:
        print(f"Database error in API publish: {e}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"Unexpected error in API publish: {e}", file=sys.stderr)
        return False


def mqtt_publish(db_path, config):
    """
    Publishes the oldest unpublished row to the MQTT broker.
    
    Args:
        db_path (str): Path to the SQLite database file.
        config (dict): The MQTT configuration from testid-publish.json
        
    Returns:
        bool: True if successfully published, False otherwise.
    """
    if not config.get("enabled", False):
        print("MQTT publishing is disabled in config.")
        return False
    
    try:
        # Get the oldest unpublished row
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, timestamp, data 
                FROM readings 
                WHERE is_published = 0 
                ORDER BY timestamp ASC 
                LIMIT 1
            """)
            row = cursor.fetchone()
            
            if not row:
                print("No unpublished rows found for MQTT.")
                return False
            
            row_id, timestamp, data = row
        
        # Parse the sensor data
        sensor_data = json.loads(data)
        
        # Prepare the payload
        payload = {
            "timestamp": timestamp,
            "data": sensor_data
        }
        
        # Create MQTT client
        client = mqtt.Client()
        
        # Set username and password if provided
        if config.get("username") and config.get("password"):
            client.username_pw_set(config["username"], config["password"])
        
        # Configure TLS if enabled
        if config.get("tls_enabled", False):
            client.tls_set()  # Use default system CA certificates
            print(f"TLS enabled for MQTT connection")
        
        # Connection tracking
        connected = False
        published = False
        error_message = None
        
        def on_connect(client, userdata, flags, rc):
            nonlocal connected, error_message
            if rc == 0:
                connected = True
                print("Connected to MQTT broker")
            else:
                error_message = f"Connection failed with code {rc}"
        
        def on_publish(client, userdata, mid):
            nonlocal published
            published = True
            print(f"Message published with ID {mid}")
        
        client.on_connect = on_connect
        client.on_publish = on_publish
        
        # Extract host (remove http:// or https:// prefix if present)
        host = config["host"]
        if host.startswith("http://"):
            host = host[7:]
        elif host.startswith("https://"):
            host = host[8:]
        
        # Connect to broker
        port = config.get("port", 1883)
        client.connect(host, port, keepalive=60)
        
        # Start network loop
        client.loop_start()
        
        # Wait for connection (max 5 seconds)
        import time
        for _ in range(50):
            if connected:
                break
            time.sleep(0.1)
        
        if not connected:
            client.loop_stop()
            print(f"Failed to connect to MQTT broker: {error_message or 'Timeout'}")
            return False
        
        # Publish message
        topic = f"{config.get('topic_prefix', 'dataloggers')}/{row_id}"
        result = client.publish(topic, json.dumps(payload), qos=1)
        
        # Wait for publish confirmation (max 5 seconds)
        for _ in range(50):
            if published:
                break
            time.sleep(0.1)
        
        client.loop_stop()
        client.disconnect()
        
        if published:
            # Mark as published in database
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE readings SET is_published = 1 WHERE id = ?",
                    (row_id,)
                )
                conn.commit()
            
            print(f"Successfully published row {row_id} to MQTT topic: {topic}")
            return True
        else:
            print("MQTT publish confirmation not received")
            return False
            
    except Exception as e:
        print(f"Error in MQTT publish: {e}", file=sys.stderr)
        return False


def publish(modbus_config_path, publish_config_path):
    """
    Main publish function that reads configs and publishes to enabled endpoints.
    
    Publishes the oldest unpublished row from the database to all enabled
    endpoints (API and/or MQTT).
    
    Args:
        modbus_config_path (str): Path to testid-modbus.json
        publish_config_path (str): Path to testid-publish.json
        
    Returns:
        dict: Status of each publishing method {"api": bool, "mqtt": bool}
    """
    results = {"api": False, "mqtt": False}
    
    try:
        # Load modbus config to get database path and publish rate
        with open(modbus_config_path, 'r') as f:
            modbus_config = json.load(f)
        
        db_path = modbus_config["database"]["db_path"]
        publish_rate = modbus_config.get("datalogger_settings", {}).get("publish_interval_seconds", 60)
        
        # Load publish config
        with open(publish_config_path, 'r') as f:
            publish_config = json.load(f)
        
        # Check if there are any unpublished rows
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM readings WHERE is_published = 0")
            unpublished_count = cursor.fetchone()[0]
            
        if unpublished_count == 0:
            print("No unpublished rows in database.")
            return results
        
        print(f"Found {unpublished_count} unpublished row(s).")
        print(f"Publish interval: {publish_rate} seconds")
        
        # Publish to API if enabled
        if "api_endpoints" in publish_config:
            for endpoint_name, endpoint_config in publish_config["api_endpoints"].items():
                print(f"\n--- Publishing to API: {endpoint_name} ---")
                results["api"] = api(db_path, endpoint_config)
        
        # Publish to MQTT if enabled
        if "mqtt_brokers" in publish_config:
            for broker_name, broker_config in publish_config["mqtt_brokers"].items():
                print(f"\n--- Publishing to MQTT: {broker_name} ---")
                results["mqtt"] = mqtt_publish(db_path, broker_config)
        
        return results
        
    except FileNotFoundError as e:
        print(f"Config file not found: {e}", file=sys.stderr)
        return results
    except json.JSONDecodeError as e:
        print(f"Invalid JSON in config file: {e}", file=sys.stderr)
        return results
    except KeyError as e:
        print(f"Missing required config key: {e}", file=sys.stderr)
        return results
    except Exception as e:
        print(f"Unexpected error in publish: {e}", file=sys.stderr)
        return results


# --- Example Usage and Testing ---
if __name__ == "__main__":
    import database
    import modbus
    import time
    
    print("=== Testing publish.py ===\n")
    
    # Configuration
    modbus_config = "testid-modbus.json"
    publish_config = "testid-publish.json"
    
    # Load the database path from modbus config
    with open(modbus_config, 'r') as f:
        config = json.load(f)
    db_path = config["database"]["db_path"]
    
    # Initialize database and add test data
    print("1. Initializing test database...")
    database.initDB(db_path)
    
    print("\n2. Adding 3 test readings...")
    for i in range(3):
        ts = datetime.now().isoformat()
        sensor_data = modbus.readsens_all(modbus_config)
        if sensor_data:
            json_data = json.dumps(sensor_data)
            database.insertReading(db_path, ts, json_data)
            print(f"   Added reading {i+1}/3")
        time.sleep(0.5)
    
    print("\n3. Current database contents:")
    database.printAllReadings(db_path)
    
    # Test publishing
    print("\n4. Testing publish function...")
    results = publish(modbus_config, publish_config)
    
    print("\n5. Publishing results:")
    print(f"   API: {'Success' if results['api'] else 'Failed/Disabled'}")
    print(f"   MQTT: {'Success' if results['mqtt'] else 'Failed/Disabled'}")
    
    print("\n6. Database after publishing:")
    database.printAllReadings(db_path)
    
    print("\n=== Test complete ===")
    print("Note: Check if rows were marked as published (is_published = 1)")