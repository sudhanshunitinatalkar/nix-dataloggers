import sqlite3
import time
import os

DB_PATH = os.path.expanduser("~/datalogger.db")

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    # OPTIMIZATION: Enable Write-Ahead Logging (WAL).
    # reduces write amplification on SD cards.
    conn.execute("PRAGMA journal_mode=WAL;")
    # OPTIMIZATION: Relax synchronization. 
    # 'NORMAL' is safe for WAL mode and reduces fsync() calls.
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn

def init_db():
    with get_connection() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL,
                modbus_data TEXT,
                published INTEGER DEFAULT 0
            )
        ''')

def save_reading(data_dict):
    """
    Stores a new reading. data_dict should be a JSON string or similar.
    """
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO readings (timestamp, modbus_data) VALUES (?, ?)",
            (time.time(), str(data_dict))
        )

def get_unpublished_readings(limit=100):
    """
    Fetch readings that haven't been sent to MQTT/API yet.
    """
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM readings WHERE published = 0 ORDER BY timestamp ASC LIMIT ?", 
        (limit,)
    )
    rows = cursor.fetchall()
    conn.close()
    return rows

def mark_as_published(reading_ids):
    """
    Update records to mark them as published.
    """
    if not reading_ids:
        return
    with get_connection() as conn:
        placeholders = ','.join(['?'] * len(reading_ids))
        conn.execute(
            f"UPDATE readings SET published = 1 WHERE id IN ({placeholders})",
            reading_ids
        )