import time
import random
# from pymodbus.client import ModbusSerialClient 
# from pymodbus.exceptions import ModbusException

# Mocking Modbus for demonstration. 
# Uncomment imports above and implement actual client for real use.

def read_data():
    """
    Connects to Modbus and reads registers.
    Returns a dictionary of data.
    """
    # EXAMPLE REAL IMPLEMENTATION:
    # client = ModbusSerialClient(port='/dev/ttyUSB0', baudrate=9600, timeout=1)
    # client.connect()
    # result = client.read_holding_registers(address=0, count=10, slave=1)
    # data = result.registers
    # client.close()
    
    # MOCK DATA:
    data = {
        "temperature": round(20 + (random.random() * 5), 2),
        "humidity": round(50 + (random.random() * 10), 1),
        "voltage": round(230 + (random.random() * 20 - 10), 1)
    }
    
    return data

if __name__ == "__main__":
    print(read_data())