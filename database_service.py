import sqlite3
import threading
import os
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone


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

    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    # ------------------------------------------------
    # INSERT DATA
    # ------------------------------------------------

    def insert_measurement(self, water_level,  liquid_level):
        cameroon_now = datetime.now(timezone(timedelta(hours=1))).isoformat()
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    INSERT INTO measurements
                    (timestamp, water_level,  liquid_level, synced)
                    VALUES (?, ?, ?, FALSE)
                """, (
                    cameroon_now,
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
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    DELETE FROM measurements
                    WHERE julianday(timestamp) < julianday(?) AND synced = TRUE
                """, (cutoff_date.isoformat(),))

                conn.commit()
                
    def get_today_measurements(self):
        cameroon_now = datetime.now(timezone(timedelta(hours=1)))
        today = cameroon_now.date().isoformat()

        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT timestamp, water_level, liquid_level
                    FROM measurements
                    WHERE date(timestamp) = ?
                    ORDER BY timestamp ASC
                """, (today,))

                return cursor.fetchall()

    def pending_stats(self):
        with self._lock:
            with self._get_connection() as conn:
                count, age = conn.execute("""
                    SELECT COUNT(*), MAX(0, (julianday('now') - julianday(MIN(timestamp))) * 86400)
                    FROM measurements WHERE synced = FALSE
                """).fetchone()
                return {"pending_count": count, "oldest_pending_age_seconds": int(age or 0)}
