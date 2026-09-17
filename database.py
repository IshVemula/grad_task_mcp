import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "tasks.db"


def get_connection():
    """Create and return a connection to the SQLite database."""
    return sqlite3.connect(DB_PATH)


def initialize_database():
    """Create the tasks table if it does not already exist."""
    connection = get_connection()

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            category TEXT NOT NULL,
            due_date TEXT,
            completed INTEGER DEFAULT 0
        )
        """
    )

    connection.commit()
    connection.close()