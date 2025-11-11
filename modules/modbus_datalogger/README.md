### Core Philosophy: "The Conveyor Belt"

We will treat your data like a physical production line.

1.  **Station 1 (Polling):** A fast worker (`Thread 1`) pulls raw material (Modbus data) and places it into an in-memory "bin" (`list`).
2.  **Station 2 (Storage):** When the bin is full, a second worker (`Thread 1` still) moves the *entire bin* to a massive, persistent warehouse (the SQLite database). This is done in one "trip" (a single transaction) to save energy (SD card writes).
3.  **Station 3 (Shipping):** A separate, slower worker (`Thread 2`) inspects the warehouse, finds items not yet "shipped" (`sent_flag = 0`), packs them up, and sends them to the customer (the API).
4.  **Station 4 (Maintenance):** The shipping worker (`Thread 2`) also checks if the warehouse is full. If it is, it discards the *oldest* items to make space, ensuring the factory never stops.

This "separation of concerns" ensures that a problem at one station (e.g., the API is down) does not stop the entire factory (Modbus polling continues).

### Project Structure (Separation of Concerns)

Here is the file/folder layout. This is a standard, testable Python package.

```
nix-datalogger/
│
├── datalogger/                 # The main Python package
│   ├── __init__.py
│   ├── main.py                 # Entry point: Loads config, starts threads
│   ├── config.py               # Loads and validates configuration
│   ├── core.py                 # The "main" logic: defines the two thread loops
│   ├── hardware.py             # Functional: Gets RPi CPU ID
│   ├── modbus_client.py        # Functional: All Modbus comms logic
│   ├── database.py             # Functional: All SQLite logic (setup, write, read, prune)
│   └── api_client.py           # Functional: All API publishing logic
│
├── tests/                      # Unit tests for each functional module
│   ├── test_database.py
│   ├── test_modbus_client.py
│   └── test_api_client.py
│
├── config.toml                 # All config (API keys, poll rates, DB path)
├── pyproject.toml              # Python project/dependency definition
├── prep_datalogger.sh          # Your existing setup script
└── README.md
```

-----

### Module-by-Module Functional Breakdown

#### 1\. `config.py` (The Blueprint)

  * **Purpose:** Load all external configuration from `config.toml`. Never hardcode.
  * **Functional Concept:** A single function `load_config(path)` reads the file and returns an **immutable** `dataclass` or `NamedTuple`. This `config` object is then passed *into* every other function that needs it.
  * **`config.toml` would contain:**
      * `[database]`
          * `path = "/home/datalogger/datalog.db"`
          * `storage_limit_gb = 1`
      * `[modbus]`
          * `port = "/dev/ttyUSB0"`
          * `poll_rate_hz = 10`
          * `batch_size = 100`  *(Key for SD card health\!)*
          * `registers_to_read = [...]`
      * `[api]`
          * `endpoint = "https://api.example.com/v1/data"`
          * `api_key = "..."`
          * `publish_interval_sec = 60`

#### 2\. `hardware.py` (The Identifier)

  * **Purpose:** Get the one thing that never changes.
  * **Functional Concept:** A pure, cached function.
      * `get_cpu_serial()`: Reads `/sys/firmware/devicetree/base/serial-number` (or `/proc/cpuinfo`) *once*, stores the result in a private variable, and returns it every time thereafter.

#### 3\. `modbus_client.py` (The Sensor)

  * **Purpose:** Handle all Modbus-specific communication.
  * **Functional Concept:** Pure I/O functions.
      * `create_client(config)`: A "factory function" that returns an initialized Modbus client instance.
      * `read_registers(client, register_list)`: Takes the client, reads the data, and returns a simple, "raw" Python `dict` or `list`. It does *not* know about the database or API.

#### 4\. `database.py` (The Warehouse)

  * **Purpose:** Abstract all SQL. No other module should ever write a SQL query.
  * **Functional Concept:** A set of pure functions that take a `db_connection` and `data` as arguments.
      * **Table Schema:**
          * `id` (INTEGER, PRIMARY KEY)
          * `timestamp` (TEXT, ISO8601)
          * `cpu_id` (TEXT)
          * `data` (TEXT - as a JSON blob. This is *crucial* for industrial use. If you add a new Modbus register, you don't need to change your database schema.)
          * `sent_flag` (INTEGER, 0 or 1, default 0)
      * **Functions:**
          * `init_db(conn)`: Creates the table if it doesn't exist.
          * `batch_insert_readings(conn, readings_list)`: The **SD card optimization**. Takes a *list* of readings and inserts all of them inside a single `BEGIN TRANSACTION...COMMIT`.
          * `get_unsent_readings(conn, limit)`: `SELECT id, timestamp, data FROM ... WHERE sent_flag = 0 LIMIT ...`
          * `mark_readings_as_sent(conn, list_of_ids)`: `UPDATE ... SET sent_flag = 1 WHERE id IN (...)` (also in a transaction). This is the "address" you mentioned.
          * `prune_database(conn, free_space_gb, limit_gb)`: This is the **circular buffer logic**.
            1.  Checks `free_space_gb` against `limit_gb`.
            2.  If space is low, it first tries to `DELETE FROM readings WHERE sent_flag = 1 ORDER BY timestamp ASC LIMIT 5000`.
            3.  If space is *still* low, it's forced to delete old, unsent data: `DELETE FROM readings ORDER BY timestamp ASC LIMIT 5000`. This prioritizes *new* data over *old*.

#### 5\. `api_client.py` (The Shipper)

  * **Purpose:** Format data and send it to the cloud.
  * **Functional Concept:** A pure function for transformation, and one for I/O.
      * `transform_for_api(cpu_id, db_rows)`: Takes the database rows and formats them into the exact JSON structure the API expects.
      * `publish_data(api_config, json_payload)`: Uses `httpx` or `requests` to `POST` the data. It handles timeouts and basic retries (e.t., 3 attempts). Returns `True` on success (HTTP 2xx) or `False` on failure.

-----

### `core.py` (The Factory Floor)

This is where the two threads are defined. They are just function loops that call the pure modules.

```python
# This is pseudocode to show the logic

# --- Thread 1: Priority 1 (Poll & Save) ---
def polling_loop(config, cpu_id, stop_event):
    modbus_client = modbus_client.create_client(config.modbus)
    db_conn = sqlite.connect(config.database.path)
    
    in_memory_batch = [] # The "bin"

    while not stop_event.is_set():
        # 1. Poll
        raw_data = modbus_client.read_registers(modbus_client, ...)
        
        # 2. Format
        reading = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "cpu_id": cpu_id,
            "data": raw_data,
            "sent_flag": 0
        }
        in_memory_batch.append(reading)

        # 3. Save (only when bin is full)
        if len(in_memory_batch) >= config.modbus.batch_size:
            database.batch_insert_readings(db_conn, in_memory_batch)
            in_memory_batch.clear() # Empty the bin
        
        time.sleep(1 / config.modbus.poll_rate_hz)

# --- Thread 2: Priority 2 (Publish & Maintain) ---
def publishing_loop(config, stop_event):
    db_conn = sqlite.connect(config.database.path)

    while not stop_event.is_set():
        # 1. Get Unsent Data
        unsent_rows = database.get_unsent_readings(db_conn, limit=500)
        
        if unsent_rows:
            # 2. Transform
            api_payload = api_client.transform_for_api(unsent_rows)
            
            # 3. Publish
            success = api_client.publish_data(config.api, api_payload)
            
            # 4. Mark as Sent (Update the "address")
            if success:
                sent_ids = [row.id for row in unsent_rows]
                database.mark_readings_as_sent(db_conn, sent_ids)

        # 5. Database Maintenance (The Circular Buffer)
        current_free_space = get_free_disk_space(config.database.path)
        if current_free_space < config.database.storage_limit_gb:
            database.prune_database(...)
            
        # 6. Sleep
        # This loop runs much slower, e.g., once a minute
        time.sleep(config.api.publish_interval_sec)
```

### `main.py` (The On/Off Switch)

  * **Purpose:** Start and gracefully stop the factory.
  * **Logic:**
    1.  `config = config.load_config("config.toml")`
    2.  `cpu_id = hardware.get_cpu_serial()`
    3.  `stop_event = threading.Event()`
    4.  Create `polling_thread` (target `core.polling_loop`) and `publishing_thread` (target `core.publishing_loop`).
    5.  Start both threads.
    6.  Listen for `SIGTERM` / `KeyboardInterrupt`.
    7.  On shutdown signal:
          * `stop_event.set()`
          * `polling_thread.join()`
          * `publishing_thread.join()`
          * This ensures a clean shutdown, no data is corrupted. This is non-negotiable for industrial use.