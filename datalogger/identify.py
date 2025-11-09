import uuid
import re

def get_station_id():
    """
    Retrieves the MAC address of the device to serve as a unique Station ID.
    """
    try:
        # getnode() usually returns the MAC as a 48-bit integer
        mac_int = uuid.getnode()
        mac_hex = "{:012x}".format(mac_int)
        # Format as human-readable MAC (e.g., 00:11:22:33:44:55)
        mac_formatted = ":".join(re.findall('..', mac_hex))
        return mac_formatted
    except Exception as e:
        return "UNKNOWN_STATION"

if __name__ == "__main__":
    print(f"Station ID: {get_station_id()}")