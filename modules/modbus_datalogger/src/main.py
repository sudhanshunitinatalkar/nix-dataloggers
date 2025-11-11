import requests
import random
import time
import json
import copy

# --- Configuration ---
API_URL = "https://api.saicloud.in/api/device_data/site_NSA/SNHS2B09"
API_KEY = "4xCOWlaAAGwa8uBEwIhMfcKnqSrxFPiz"
STATION_ID = "NSA_ETP"
SEND_INTERVAL_SEC = 10 # Send data every 10 seconds

# This is the "base" data. We will randomize the values from this.
BASE_PARAMETERS = [
    {"parameter_key": "cod", "parameter_value": "250"},
    {"parameter_key": "bod", "parameter_value": "100"},
    {"parameter_key": "tss", "parameter_value": "100"},
    {"parameter_key": "wind_spe", "parameter_value": "100"},
    # Note: You had two "wind_spe" entries. I kept them as-is.
    {"parameter_key": "wind_spe", "parameter_value": "100"}
]

# --- Helper Function ---

def get_randomized_value(base_value_str: str) -> str:
    """
    Takes a string value (e.g., "250"), calculates a +/- 10%
    fluctuation, and returns the new value as a string.
    """
    try:
        base_value = int(base_value_str)
    except ValueError:
        # If it's not a number, just return the original string
        return base_value_str
    
    # Calculate 10% margin
    margin = base_value * 0.10
    
    # Calculate a random fluctuation between -margin and +margin
    fluctuation = random.uniform(-margin, margin)
    
    # Apply fluctuation and cast back to an integer, then to a string
    new_value = base_value + fluctuation
    return str(int(new_value))

# --- Main Function ---

def main():
    """
    Main loop for the data logger.
    """
    print("Starting simple data logger...")
    print(f"Sending data to: {API_URL}")
    print(f"Sending interval: {SEND_INTERVAL_SEC} seconds")

    headers = {
        "Content-Type": "application/json",
        "X-API-KEY": API_KEY
    }

    while True:
        try:
            # 1. Create a new list for this loop's parameters
            current_parameters = []
            
            # 2. Apply randomization
            for base_param in BASE_PARAMETERS:
                # Create a copy to avoid changing the original
                new_param = base_param.copy()
                
                # Get the randomized value
                random_val = get_randomized_value(new_param["parameter_value"])
                
                # Update the new parameter
                new_param["parameter_value"] = random_val
                
                # Add the station_identifier
                new_param["station_identifier"] = STATION_ID
                
                current_parameters.append(new_param)

            # 3. Build the final payload
            payload = {
                "parameters": current_parameters
            }

            print(f"\nSending data at {time.ctime()}:")
            # Use json.dumps for a nicely formatted print
            print(json.dumps(payload, indent=4))

            # 4. Send the POST request
            response = requests.post(
                API_URL, 
                headers=headers, 
                json=payload,
                timeout=10 # 10 second timeout
            )

            # 5. Print the response from the server
            print(f"Response Status: {response.status_code}")
            print(f"Response Body: {response.text}")

        except requests.exceptions.RequestException as e:
            # Handle network errors, timeouts, etc.
            print(f"Error: Could not send data. {e}")
        except Exception as e:
            # Handle other unexpected errors
            print(f"An unexpected error occurred: {e}")

        # 6. Wait for the next interval
        print(f"Waiting {SEND_INTERVAL_SEC} seconds...")
        time.sleep(SEND_INTERVAL_SEC)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopping data logger.")