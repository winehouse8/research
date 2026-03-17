"""Auto Research v2 Core - Database initialization and connection management."""

import os
import sqlite3
from pathlib import Path


def init_db(db_path: str) -> sqlite3.Connection:
    """Initialize the SQLite database with the v2 schema.

    Creates the database file and parent directories if they don't exist.
    Enables WAL mode and sets busy_timeout for write contention handling.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        A sqlite3.Connection instance configured for the session lifetime.
        The caller is responsible for closing this connection.
    """
    # Create parent directories
    db_dir = os.path.dirname(db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    # Create connection with row factory for dict-like access
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Enable WAL mode for concurrent read safety
    conn.execute("PRAGMA journal_mode=wal")

    # Set busy timeout for write contention (5 seconds)
    conn.execute("PRAGMA busy_timeout=5000")

    # Enable foreign keys
    conn.execute("PRAGMA foreign_keys=ON")

    # Run schema
    schema_path = Path(__file__).parent / "schema.sql"
    with open(schema_path, "r") as f:
        conn.executescript(f.read())

    conn.commit()
    return conn
