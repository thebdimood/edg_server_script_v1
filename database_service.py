import sqlite3
import threading
import os
from datetime import datetime, timedelta


class DatabaseService:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._lock = threading.Lock()
        dirname = os.path.dirname(self.db_path)
        if dirname:
            os.makedirs(dirname, exist_ok=True)

        self._initialize_database()

    # ------------------------------------------------
    # INITIALISATION
    # ------------------------------------------------

    def _initialize_database(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS measurements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    water_level REAL,
                    liquid_level REAL,
                    synced BOOLEAN DEFAULT FALSE
                )
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_synced
                ON measurements (synced)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_timestamp
                ON measurements (timestamp)
            """)

            conn.commit()

    def _get_connection(self):
        return sqlite3.connect(self.db_path, check_same_thread=False)

    # ------------------------------------------------
    # INSERT DATA
    # ------------------------------------------------

    def insert_measurement(self, water_level,  liquid_level):
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    INSERT INTO measurements
                    (timestamp, water_level,  liquid_level, synced)
                    VALUES (?, ?, ?, FALSE)
                """, (
                    datetime.utcnow().isoformat(),
                    water_level,
                    liquid_level,
                ))

                conn.commit()

    # ------------------------------------------------
    # READ UNSYNCED DATA
    # ------------------------------------------------

    def get_unsynced(self,limit=50):
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT id, timestamp, water_level, liquid_level
                    FROM measurements
                    WHERE synced = FALSE
                    ORDER BY timestamp ASC
                    LIMIT ?
                """, (limit,))
                return cursor.fetchall()

    # ------------------------------------------------
    # MARK AS SYNCED
    # ------------------------------------------------

    def mark_as_synced(self, record_id):
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    UPDATE measurements
                    SET synced = TRUE
                    WHERE id = ?
                """, (record_id,))

                conn.commit()

    # ------------------------------------------------
    # RETENTION POLICY (30 jours)
    # ------------------------------------------------

    def cleanup_old_data(self, days=30):
        cutoff_date = datetime.utcnow() - timedelta(days=days)

        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    DELETE FROM measurements
                    WHERE timestamp < ?
                """, (cutoff_date.isoformat(),))

                conn.commit()