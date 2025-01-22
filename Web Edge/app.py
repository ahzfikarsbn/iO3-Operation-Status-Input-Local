from flask import Flask, render_template, request, jsonify  # type: ignore
import redis  # type: ignore
import json
from datetime import datetime, timedelta
import threading
import time
import requests  # For checking internet connectivity

app = Flask(__name__)

# Initialize Redis connection
redis_client = redis.StrictRedis(host="localhost", port=6379, decode_responses=True)

# Global variable to manage the latest thread
current_thread = None


# Function to check internet connectivity
def is_internet_available():
    try:
        requests.get("https://www.google.com", timeout=3)
        return True
    except requests.RequestException:
        return False


# Push data to the Redis queue at precise intervals
def push_data(interval, device_data, start_time):
    # Wait until the start_time
    while datetime.utcnow() < start_time:
        time.sleep(0.1)

    # Push data at the specified interval
    while True:
        timestamp = datetime.utcnow().isoformat()

        # Update the timestamp in the data
        device_data["time"] = timestamp

        # Store data locally in Redis queue
        redis_client.rpush("data_queue", json.dumps(device_data))  # Append to queue
        print(f"Data added to local queue at {timestamp}")

        time.sleep(interval)  # Wait for the specified interval


# Process the local queue and send to the remote database
def process_queue():
    while True:
        if is_internet_available():
            # Check if there's data in the queue
            while redis_client.llen("data_queue") > 0:
                # Get the oldest data (FIFO)
                data = redis_client.lpop("data_queue")
                if data:
                    # Simulate storing data in the database
                    print(f"Sending data to remote DB: {data}")
                    # Add your actual database insertion logic here
        else:
            print("No internet connection. Retrying...")
        time.sleep(5)  # Retry every 5 seconds


@app.route("/form")
def form():
    vessel_status = redis_client.get("vessel_status")
    current_value = 0
    if vessel_status:
        try:
            vessel_status_data = json.loads(vessel_status)
            tags = vessel_status_data.get("tags", [])
            for tag in tags:
                if "Operation Status Input" in tag:
                    current_value = tag["Operation Status Input"]
                    break
        except json.JSONDecodeError:
            pass

    return render_template("form.html", currentValue=current_value)


@app.route("/update_state", methods=["POST"])
def update_state():
    global current_thread

    data = request.get_json()
    interval = 10  # seconds

    # Calculate the next 10-second interval
    now = datetime.utcnow()
    seconds_to_next_interval = interval - (now.second % interval)
    start_time = now + timedelta(seconds=seconds_to_next_interval)

    # Create new device data
    device_data = {
        "time": datetime.utcnow().isoformat(),
        "name": "OPERATION_TEST",
        "address": "",
        "device_id": "b047a075-c542-41ca-ae5d-a85f53c068f6",
        "status": "Connected",
        "serial": "cfe95cc4-f34c-495f-b012-540fd661ccbe",
        "target": "M2C_DATA_MQTT.MQTT_TEST",
        "model": "NMEA_1",
        "alarm_status": "good",
        "high_alarm": [],
        "low_alarm": [],
        "tags": [
            {"Operation Status Input": data["value"]},
            {"Operation Status Input Description": data["description"]},
        ],
        "last_node": "WEB-EDGE",
    }

    # Stop the previous thread if running
    if current_thread and current_thread.is_alive():
        current_thread.do_run = False
        current_thread.join()

    # Start a new thread for pushing data
    current_thread = threading.Thread(
        target=push_data, args=(interval, device_data, start_time), daemon=True
    )
    current_thread.start()

    return jsonify({"message": "State updated successfully"}), 200


if __name__ == "__main__":
    # Suppress socket.io logging
    import logging

    log = logging.getLogger("werkzeug")
    log.setLevel(logging.ERROR)

    # Start the background thread to process the queue
    threading.Thread(target=process_queue, daemon=True).start()

    app.run(debug=True, host="0.0.0.0", port=5001)

