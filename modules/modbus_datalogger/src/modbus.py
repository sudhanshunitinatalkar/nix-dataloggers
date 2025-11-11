import logging
from dataclasses import dataclass
from typing import Any, Dict, List

from pymodbus.client import ModbusSerialClient
from pymodbus.exceptions import ModbusIOException, ConnectionException
from pymodbus.payload import BinaryPayloadDecoder
from pymodbus.constants import Endian

# Configure a logger for this module
log = logging.getLogger(__name__)

# --- Configuration Dataclasses ---
# These classes are used by config.py to load settings.
# We define them here so they are tightly coupled to the module that uses them.

@dataclass
class ModbusRegister:
    """Configuration for a single register to read."""
    name: str       # e.g., "sensor_temp"
    address: int    # e.g., 100
    dtype: str      # e.g., "float32", "uint16"

@dataclass
class ModbusConfig:
    """Full Modbus client configuration."""
    port: str
    baudrate: int
    stopbits: int = 1
    bytesize: int = 8
    parity: str = "N"
    timeout: int = 3
    # A list of holding registers to read
    holding_registers: List[ModbusRegister] = None 
    # A list of input registers to read
    input_registers: List[ModbusRegister] = None

# --- Client Functions ---

def create_client(config: ModbusConfig) -> ModbusSerialClient:
    """
    Factory function to create an configure a Pymodbus client.
    
    Args:
        config: A ModbusConfig object with all connection settings.
    
    Returns:
        An un-connected ModbusSerialClient instance.
    """
    client = ModbusSerialClient(
        port=config.port,
        baudrate=config.baudrate,
        stopbits=config.stopbits,
        bytesize=config.bytesize,
        parity=config.parity,
        timeout=config.timeout,
    )
    return client

def read_modbus_data(client: ModbusSerialClient, config: ModbusConfig) -> Dict[str, Any]:
    """
    Connects, reads all configured registers, and closes.
    
    This is the main functional entry point for this module.
    It orchestrates the connection, data reading, and disconnection.

    Args:
        client: A Pymodbus client instance from create_client.
        config: The ModbusConfig object containing register lists.
    
    Returns:
        A dictionary of {register_name: value} or None if the
        entire read fails.
    """
    
    results = {}
    
    try:
        if not client.connect():
            log.error(f"Failed to connect to Modbus client at {client.port}")
            return None
        
        # 1. Read Holding Registers
        if config.holding_registers:
            _read_register_group(
                client.read_holding_registers,
                config.holding_registers,
                results
            )
            
        # 2. Read Input Registers
        if config.input_registers:
            _read_register_group(
                client.read_input_registers,
                config.input_registers,
                results
            )
        
        return results
        
    except ConnectionException as e:
        log.error(f"Modbus connection exception on {client.port}: {e}", exc_info=True)
        return None
    except Exception as e:
        log.error(f"Unexpected error during Modbus read: {e}", exc_info=True)
        return None
    finally:
        if client.is_open:
            client.close()
            log.debug("Modbus connection closed.")

def _read_register_group(read_function, registers: List[ModbusRegister], results: Dict):
    """
    Internal helper to read a list of registers of the same type (e.g., all holding).
    It tries to optimize reads by grouping contiguous registers.
    
    Note: This is a simplified implementation. A more advanced one would
    group non-contiguous reads, but for many dataloggers, registers
    are read one by one.
    
    Args:
        read_function: The client method to call (e.g., client.read_holding_registers).
        registers: The list of ModbusRegister objects to read.
        results: The results dictionary to populate.
    """
    for reg in registers:
        try:
            # Determine how many registers to read based on data type
            # uint16 = 1 register, float32 = 2 registers, etc.
            count = 1
            if "32" in reg.dtype:
                count = 2
            elif "64" in reg.dtype:
                count = 4

            # Perform the Modbus read
            read_result = read_function(address=reg.address, count=count, slave=1)
            
            if read_result.isError():
                raise ModbusIOException(f"Error reading register {reg.name} at {reg.address}")
            
            # Decode the result
            value = _decode_payload(read_result, reg.dtype)
            if value is not None:
                results[reg.name] = value
                log.debug(f"Read Modbus {reg.name}: {value}")
            
        except ModbusIOException as e:
            log.warning(f"Modbus read failed for {reg.name}: {e}")
        except Exception as e:
            log.error(f"Unexpected error decoding {reg.name}: {e}", exc_info=True)

def _decode_payload(payload, dtype: str) -> Any:
    """Decodes a Pymodbus payload based on a data type string."""
    
    # We use BIG endian (WORD_ENDIAN) by default for floats/32-bit.
    # This is a common default but may need to be configurable.
    decoder = BinaryPayloadDecoder.fromRegisters(
        payload.registers,
        byteorder=Endian.BIG,
        wordorder=Endian.BIG
    )
    
    dtype = dtype.lower()
    
    if dtype == "float32":
        return decoder.decode_32bit_float()
    elif dtype == "uint32":
        return decoder.decode_32bit_uint()
    elif dtype == "int32":
        return decoder.decode_32bit_int()
    elif dtype == "uint16":
        return decoder.decode_16bit_uint()
    elif dtype == "int16":
        return decoder.decode_16bit_int()
    else:
        log.warning(f"Unsupported data type for decoding: {dtype}")
        return None

# This allows you to test the file directly by running:
# python -m datalogger.modbus_client
if __name__ == "__main__":
    # Basic logging setup for testing
    logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(levelname)s: %(message)s")
    
    log.info("--- Testing Modbus Client ---")
    
    # --- MOCK CONFIG ---
    # This is what your config.py module will create
    mock_config = ModbusConfig(
        port="/dev/ttyUSB0",  # Change this to your actual port
        baudrate=9600,
        holding_registers=[
            ModbusRegister(name="sensor_temp_c", address=100, dtype="float32"),
            ModbusRegister(name="valve_status", address=102, dtype="uint16")
        ],
        input_registers=[
            ModbusRegister(name="flow_rate", address=200, dtype="float32")
        ]
    )
    
    log.debug(f"Mock Config: {mock_config}")

    # --- TEST ---
    # This test will likely fail unless a device is connected,
    # but it proves the code structure works.
    try:
        client = create_client(mock_config)
        log.info(f"Client created for {mock_config.port}. Attempting to read...")
        
        data = read_modbus_data(client, mock_config)
        
        if data is None:
            log.warning("Read failed (this is expected if no device is connected).")
        else:
            log.info(f"\n--- SUCCESSFUL READ ---")
            import json
            print(json.dumps(data, indent=2))
            log.info("--------------------------")
            
    except Exception as e:
        log.error(f"Test failed with unexpected error: {e}", exc_info=True)