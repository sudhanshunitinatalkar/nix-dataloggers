# modbus.py

import random
import json
import sys



def readsens(slave_id, function_code, mem_address, number_of_bytes, data_type, scaling_factor):
    
    dt_lower = data_type.lower()

    if 'int' in dt_lower:
        max_raw_value = (2 ** (number_of_bytes * 8)) - 1
        
        if max_raw_value <= 0:
            raw_value = 0
        else:
            raw_value = random.randint(0, max_raw_value)
        
        scaled_value = raw_value * scaling_factor
        return int(scaled_value)

    elif 'float' in dt_lower:
        max_raw_value = (2 ** (number_of_bytes * 8)) - 1

        if max_raw_value <= 0:
            raw_value = 0.0
        else:
            raw_value = random.randint(0, max_raw_value)
        
        scaled_value = raw_value * scaling_factor
        return scaled_value

    elif 'bool' in dt_lower:
        return random.choice([True, False])

    else:
        return None
    

def readsens_all(filename):
    """
    Reads sensor configuration from a JSON file, calls readsens for each,
    and prints the results as a dictionary.
    
    --- [UPDATED] ---
    This function now reads the *entire* config file but only processes
    the dictionary found under the "sensor_config" key.
    """
    try:
        with open(filename, 'r') as f:
            full_config = json.load(f)
    except FileNotFoundError:
        print(f"Error: Configuration file '{filename}' not found.", file=sys.stderr)
        return None # Return None on error
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from '{filename}'. Check file format.", file=sys.stderr)
        return None # Return None on error
    except Exception as e:
        print(f"An error occurred opening or reading '{filename}': {e}", file=sys.stderr)
        return None # Return None on error

    sensor_readings = {}
    
    # --- [NEW] Check for the "sensor_config" key ---
    if "sensor_config" not in full_config or not isinstance(full_config["sensor_config"], dict):
        print(f"Error: JSON file '{filename}' is missing a 'sensor_config' dictionary.", file=sys.stderr)
        return None

    # --- [UPDATED] Iterate over the "sensor_config" key, not the whole file ---
    sensor_config = full_config["sensor_config"]
    for sensor_name, params in sensor_config.items():
        try:
            # Use keyword argument unpacking (**) to pass the dictionary
            # of parameters directly to the readsens function.
            value = readsens(**params)
            sensor_readings[sensor_name] = value
        except TypeError:
            # This will catch errors if 'params' is missing a required
            # argument for readsens (e.g., "slave_id" is missing)
            print(f"Error: Invalid or missing parameters for '{sensor_name}' in {filename}.", file=sys.stderr)
        except Exception as e:
            # Catch any other errors during the read
            print(f"Error reading sensor '{sensor_name}': {e}", file=sys.stderr)

    # Return the final dictionary of readings
    return sensor_readings



if __name__ == "__main__":
    # Update the test to use the new config file name
    print(readsens_all("testid-modbus.json"))