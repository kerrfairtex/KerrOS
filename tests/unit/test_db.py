import pytest
import sqlite3
import os
from data.db import get_connection

def test_db_wal_mode(tmp_path):
    db_file = tmp_path / "test.db"
    with get_connection(str(db_file)) as conn:
        # Check journal mode
        cursor = conn.execute("PRAGMA journal_mode")
        assert cursor.fetchone()[0].upper() == "WAL"
        
        # Check synchronous mode
        cursor = conn.execute("PRAGMA synchronous")
        assert cursor.fetchone()[0] == 1  # NORMAL is 1

def test_db_file_creation(tmp_path):
    db_file = tmp_path / "new.db"
    with get_connection(str(db_file)) as conn:
        assert db_file.exists()
        # Verify we can write and read
        conn.execute("CREATE TABLE IF NOT EXISTS test (id INTEGER PRIMARY KEY, val TEXT)")
        conn.execute("INSERT INTO test (val) VALUES ('hello')")
        cursor = conn.execute("SELECT val FROM test")
        assert cursor.fetchone()[0] == "hello"
