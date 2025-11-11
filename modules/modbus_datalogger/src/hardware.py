import logging
import re
from functools import lru_cache

# Configure a logger for this module
log = logging.getLogger(__name__)

# Pre-compile the regex for parsing /proc/cpuinfo
# This looks for a line starting with "Serial", followed by whitespace,
# a colon, more whitespace, and then captures the 16-hex-digit serial.
_SERIAL_RE = re.compile(r"^Serial\s*:\s*([0-9a-f]{16})$", re.MULTILINE)

@lru_cache(maxsize=1)
def get_cpu_serial() -> str:
    """
    Fetches the unique CPU serial number from the Raspberry Pi.

    This function is cached, so it only performs the file I/O
    on its very first call. It tries the devicetree first,
    then falls back to /proc/cpuinfo.

    Returns:
        A string of the 16-digit CPU serial, or a fallback
        string if it cannot be found.
    """
    
    # Method 1: Try the modern devicetree file first.
    # This is the most direct and reliable method.
    try:
        with open("/sys/firmware/devicetree/base/serial-number", "r") as f:
            serial = f.read().strip().strip('\x00') # Also strip null bytes
            if serial:
                log.info(f"Read CPU Serial from devicetree: {serial}")
                return serial
    except FileNotFoundError:
        log.warning("Could not find devicetree serial-number, falling back to /proc/cpuinfo.")
    except Exception as e:
        log.error(f"Error reading devicetree serial-number: {e}", exc_info=True)

    # Method 2: Fallback to parsing /proc/cpuinfo.
    # This is the classic method.
    try:
        with open("/proc/cpuinfo", "r") as f:
            cpuinfo_content = f.read()
            match = _SERIAL_RE.search(cpuinfo_content)
            if match:
                serial = match.group(1)
                log.info(f"Read CPU Serial from /proc/cpuinfo: {serial}")
                return serial
    except FileNotFoundError:
        log.error("Could not find /proc/cpuinfo.")
    except Exception as e:
        log.error(f"Error reading /proc/cpuinfo: {e}", exc_info=True)

    # Fallback: If both methods fail (e.g., running on non-RPi dev machine)
    log.critical("Failed to get a unique CPU serial number!")
    return "0000000000000000-DEV"

# This allows you to test the file directly by running:
# python -m datalogger.hardware
if __name__ == "__main__":
    # Basic logging setup for testing
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    
    print("--- Testing CPU Serial Fetch ---")
    
    # Call it once
    serial_1 = get_cpu_serial()
    print(f"First call:  {serial_1}")
    
    # Call it again to prove it's cached (will be much faster)
    serial_2 = get_cpu_serial()
    print(f"Second call: {serial_2}")
    
    if serial_1 == serial_2 and serial_1 != "0000000000000000-DEV":
        print("\nSuccess: Serial was fetched and cached.")
    elif serial_1 == "0000000000000000-DEV":
        print("\nWarning: Could not find serial. Using dev fallback.")
    else:
        print("\nError: Calls produced different serials (this shouldn't happen).")