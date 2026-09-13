import sqlite3
from pathlib import Path
from contextlib import contextmanager

@contextmanager
def get_connection(db_path: str = "data/session_store.db"):
    """
    Provides a context-managed SQLite connection with WAL mode enabled.
    """
    db_file = Path(db_path).resolve()
    # Ensure parent directory exists for new DBs
    db_file.parent.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(db_file, timeout=30, isolation_level=None)
    try:
        # Enable WAL for concurrent reads/writes
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        yield conn
    finally:
        conn.close()

def verify_wal_mode(db_path: str = "data/session_store.db"):
    """Verify if the database is in WAL mode."""
    with get_connection(db_path) as conn:
        cursor = conn.execute("PRAGMA journal_mode;")
        mode = cursor.fetchone()[0]
        return mode.upper() == "WAL"
