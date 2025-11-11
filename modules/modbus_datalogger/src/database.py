import sqlite3
import json
import logging
import os
import shutil
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

log = logging.getLogger(__name__)

@dataclass
class ReadingRow:
    """A strongly-typed object representing an unsent row from the DB."""
    id: int
    timestamp: str
    cpu_id: str
    data: Dict[str, Any] # Deserialized from data_json


def create_connection(db_path: str) -> Optional[sqlite3.Connection]:
    """
    Creates a database connection. Sets up WAL mode.
    
    Args:
        db_path: The file path to the SQLite database.

    Returns:
        A sqlite3.Connection object or None if connection fails.
    """
    conn = None
    try:
        # Get the directory for the DB file
        db_dir = os.path.dirname(os.path.abspath(db_path))
        # Ensure the directory exists
        os.makedirs(db_dir, exist_ok=True)
        
        conn = sqlite3.connect(db_path, timeout=10) # 10s timeout
        
        # --- CRITICAL PERFORMANCE TWEAKS ---
        # 1. Use Write-Ahead Logging (WAL) mode.
        #    This allows a reader (publisher) and writer (poller)
        #    to operate concurrently without locking.
        conn.execute("PRAGMA journal_mode=WAL;")
        
        # 2. Set synchronous mode to NORMAL.
        #    This is a safe trade-off for WAL mode, making
        #    writes much faster.
        conn.execute("PRAGMA synchronous=NORMAL;")
        
        log.info(f"Database connection established to {db_path} in WAL mode.")
        return conn
    except sqlite3.Error as e:
        log.critical(f"Failed to connect to database at {db_path}: {e}", exc_info=True)
        return None

def init_db(conn: sqlite3.Connection):
    """
    Initializes the database schema (table and indexes).
    Safe to run on every startup.
    """
    schema_sql = """
    BEGIN;

    CREATE TABLE IF NOT EXISTS readings (
        id INTEGER PRIMARY KEY,
        timestamp TEXT NOT NULL,
        cpu_id TEXT NOT NULL,
        data_json TEXT NOT NULL,
        sent_flag INTEGER NOT NULL DEFAULT 0
    );

    -- Create an index on sent_flag.
    -- This makes get_unsent_readings() and prune_sent_data()
    -- extremely fast, even on millions of rows.
    CREATE INDEX IF NOT EXISTS idx_sent_flag
    ON readings (sent_flag);

    COMMIT;
    """
    try:
        with conn:
            conn.executescript(schema_sql)
        log.info("Database schema initialized successfully.")
    except sqlite3.Error as e:
        log.error(f"Failed to initialize database schema: {e}", exc_info=True)

def batch_insert_readings(conn: sqlite3.Connection, 
                          readings: List[Dict[str, Any]]):
    """
    Inserts a batch of readings into the database in a single transaction.
    This is optimized for SD card health.
    
    Args:
        conn: The database connection.
        readings: A list of dicts, where each dict has
                  'timestamp', 'cpu_id', and 'data'.
    """
    
    # Convert data dicts to JSON strings for storage
    data_to_insert = []
    for r in readings:
        data_to_insert.append((
            r['timestamp'],
            r['cpu_id'],
            json.dumps(r['data']) # Serialize the data dict
        ))

    sql = """
    INSERT INTO readings (timestamp, cpu_id, data_json)
    VALUES (?, ?, ?)
    """
    
    try:
        # 'with conn:' automatically begins a transaction
        # and commits on success or rolls back on failure.
        with conn:
            conn.executemany(sql, data_to_insert)
        
        log.debug(f"Successfully inserted batch of {len(data_to_insert)} readings.")
        
    except sqlite3.Error as e:
        log.error(f"Failed to batch insert readings: {e}", exc_info=True)
        # The 'with conn:' context manager handles the rollback.

def get_unsent_readings(conn: sqlite3.Connection, batch_size: int) -> List[ReadingRow]:
    """
    Fetches a batch of unsent readings, ordered by ID (oldest first).
    
    Args:
        conn: The database connection.
        batch_size: The maximum number of rows to fetch.
    
    Returns:
        A list of ReadingRow objects, ready for processing.
    """
    sql = """
    SELECT id, timestamp, cpu_id, data_json
    FROM readings
    WHERE sent_flag = 0
    ORDER BY id ASC
    LIMIT ?
    """
    results = []
    try:
        cursor = conn.execute(sql, (batch_size,))
        rows = cursor.fetchall()
        
        for row in rows:
            results.append(ReadingRow(
                id=row[0],
                timestamp=row[1],
                cpu_id=row[2],
                data=json.loads(row[3]) # Deserialize the data
            ))
            
        return results
        
    except json.JSONDecodeError as e:
        log.error(f"Failed to decode corrupt data from DB: {e}", exc_info=True)
        # This could be a single corrupt row, try to recover
        # (A more robust system might flag/delete this row)
    except sqlite3.Error as e:
        log.error(f"Failed to get unsent readings: {e}", exc_info=True)
        
    return results # Return (possibly empty) list on failure

def mark_readings_as_sent(conn: sqlite3.Connection, ids: List[int]):
    """
    Updates a list of readings to sent_flag = 1 in a single transaction.
    
    Args:
        conn: The database connection.
        ids: A list of primary key IDs to mark as sent.
    """
    if not ids:
        return

    # Prepare data for executemany (must be a list of tuples)
    data_to_update = [(id,) for id in ids]
    
    sql = "UPDATE readings SET sent_flag = 1 WHERE id = ?"
    
    try:
        with conn:
            conn.executemany(sql, data_to_update)
        log.debug(f"Marked {len(data_to_update)} readings as sent.")
    except sqlite3.Error as e:
        log.error(f"Failed to mark readings as sent: {e}", exc_info=True)

def prune_sent_data(conn: sqlite3.Connection) -> int:
    """
    Deletes a batch of *already sent* data (sent_flag = 1).
    This reclaims disk space.
    
    Returns:
        The number of rows deleted.
    """
    # We delete in batches to avoid locking the database
    # for too long if millions of rows need to be deleted.
    sql = "DELETE FROM readings WHERE sent_flag = 1 LIMIT 5000"
    
    try:
        with conn:
            cursor = conn.execute(sql)
            deleted_count = cursor.rowcount
            if deleted_count > 0:
                log.info(f"Pruned {deleted_count} sent readings from database.")
            return deleted_count
    except sqlite3.Error as e:
        log.error(f"Failed to prune sent data: {e}", exc_info=True)
    return 0

def get_free_disk_space(db_path: str) -> Optional[float]:
    """
    Checks the free disk space *for the drive the DB is on*.
    This is the core of the back-pressure system.
    
    Args:
        db_path: The file path to the SQLite database.
    
    Returns:
        Free space in Gigabytes (GB), or None on failure.
    """
    try:
        db_dir = os.path.dirname(os.path.abspath(db_path))
        total, used, free = shutil.disk_usage(db_dir)
        free_gb = free / (1024**3)
        return free_gb
    except FileNotFoundError:
        log.error(f"Cannot get disk space: Directory for {db_path} not found.")
    except Exception as e:
        log.error(f"Failed to get free disk space: {e}", exc_info=True)
    return None

# --- Test Block ---
# This allows you to test the file directly by running:
# python -m datalogger.database
if __name__ == "__main__":
    
    logging.basicConfig(level=logging.DEBUG, 
                        format="%(asctime)s %(levelname)s: %(message)s")
    
    TEST_DB = ":memory:" # Use an in-memory DB for testing
    
    log.info(f"--- Testing Database Module (in-memory) ---")
    
    conn = create_connection(TEST_DB)
    
    if conn:
        init_db(conn)
        
        # 1. Test Batch Insert
        log.info("Testing batch insert...")
        mock_readings = [
            {'timestamp': '2025-11-11T12:00:00Z', 'cpu_id': 'test_cpu', 'data': {'temp': 25.5}},
            {'timestamp': '2025-11-11T12:00:01Z', 'cpu_id': 'test_cpu', 'data': {'temp': 25.6}}
        ]
        batch_insert_readings(conn, mock_readings)
        
        # 2. Test Get Unsent
        log.info("Testing get unsent readings...")
        unsent = get_unsent_readings(conn, 100)
        assert len(unsent) == 2
        assert unsent[0].id == 1
        assert unsent[1].data['temp'] == 25.6
        log.info(f"Got {len(unsent)} unsent readings. OK.")
        
        # 3. Test Mark as Sent
        log.info("Testing mark as sent...")
        ids_to_mark = [r.id for r in unsent]
        mark_readings_as_sent(conn, ids_to_mark)
        
        # 4. Verify Get Unsent is now empty
        log.info("Verifying no unsent readings remain...")
        unsent_after = get_unsent_readings(conn, 100)
        assert len(unsent_after) == 0
        log.info("No unsent readings. OK.")
        
        # 5. Test Pruning
        log.info("Testing prune sent data...")
        deleted = prune_sent_data(conn)
        assert deleted == 2
        log.info(f"Pruned {deleted} rows. OK.")
        
        # 6. Verify table is empty
        rows = conn.execute("SELECT COUNT(*) FROM readings").fetchone()[0]
        assert rows == 0
        log.info("Table is empty. OK.")
        
        conn.close()
        
        log.info("\n--- Database Module Test Succeeded! ---")
    
    else:
        log.error("Failed to create in-memory connection for testing.")