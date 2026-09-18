import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from database_service import DatabaseService
from health import WorkerHealth, monitored_cycle, notify_systemd, watchdog_interval
from modbus_service_2 import ModbusService
from SynchServiceHttp import SyncService
import main as entrypoint


class RecoveryTests(unittest.TestCase):
    def test_main_detects_stall_and_cleans_up_both_services(self):
        modbus = Mock(fatal_error=False)
        modbus.health.stalled.return_value = True
        sync = Mock()
        with patch.object(entrypoint, "setup_root_logger"), patch.object(entrypoint, "DatabaseService"), patch.object(entrypoint, "ModbusService", return_value=modbus), patch.object(entrypoint, "SyncService", return_value=sync), patch.object(entrypoint, "notify_systemd") as notify, patch.object(entrypoint, "watchdog_interval", return_value=60):
            with self.assertRaisesRegex(RuntimeError, "Worker stalled: modbus"):
                entrypoint.main()
        modbus.stop.assert_called_once()
        sync.stop.assert_called_once()
        self.assertEqual([call.args[0] for call in notify.call_args_list], ["READY=1", "STOPPING=1"])

    def test_partial_startup_is_cleaned_up(self):
        modbus = Mock()
        sync = Mock()
        sync.start.side_effect = RuntimeError("scheduler failed")
        with patch.object(entrypoint, "setup_root_logger"), patch.object(entrypoint, "DatabaseService"), patch.object(entrypoint, "ModbusService", return_value=modbus), patch.object(entrypoint, "SyncService", return_value=sync), patch.object(entrypoint, "notify_systemd") as notify:
            with self.assertRaisesRegex(RuntimeError, "scheduler failed"):
                entrypoint.main()
        modbus.stop.assert_called_once()
        sync.stop.assert_called_once()
        self.assertNotIn("READY=1", [call.args[0] for call in notify.call_args_list])

    def test_http_batch_yields_after_budget(self):
        db = Mock(db_path="edge.db")
        db.pending_stats.return_value = {}
        db.get_unsynced.return_value = [(1, "timestamp", 1, 2), (2, "timestamp", 1, 2)]
        sync = SyncService(db)
        # Cycle entry, batch start, first check, progress, next check, cycle exit.
        with patch("health.time.monotonic", side_effect=[0, 0, 0, 0, 46, 46]), patch.object(sync, "_send_to_api", return_value=True) as send:
            sync._perform_sync()
        send.assert_called_once()
        db.mark_as_synced.assert_called_once_with(1)

    def test_stalled_worker_and_progress(self):
        with patch("health.time.monotonic", return_value=100):
            health = WorkerHealth()
        self.assertFalse(health.stalled(190, 90))
        self.assertTrue(health.stalled(191, 90))
        with patch("health.time.monotonic", return_value=191):
            health.progress()
        self.assertFalse(health.stalled(200, 90))

    def test_failed_cycle_still_reports_progress(self):
        class Worker:
            health = Mock()

            @monitored_cycle
            def run(self):
                raise ValueError("handled by scheduler")

        worker = Worker()
        with self.assertRaises(ValueError):
            worker.run()
        self.assertEqual(worker.health.progress.call_count, 2)

    def test_notify_handles_abstract_socket_and_no_systemd(self):
        with patch.dict(os.environ, {}, clear=True), patch("health.socket.socket") as factory:
            notify_systemd("READY=1")
            factory.assert_not_called()
        with patch.dict(os.environ, {"NOTIFY_SOCKET": "@edge"}), patch("health.socket.AF_UNIX", 1, create=True), patch("health.socket.socket") as factory:
            notify_systemd("WATCHDOG=1")
            sock = factory.return_value.__enter__.return_value
            sock.connect.assert_called_once_with("\0edge")
            sock.sendall.assert_called_once_with(b"WATCHDOG=1")

    def test_watchdog_honors_pid_and_timeout(self):
        with patch.dict(os.environ, {"WATCHDOG_USEC": "120000000", "WATCHDOG_PID": str(os.getpid())}):
            self.assertEqual(watchdog_interval(), 60)
        with patch.dict(os.environ, {"WATCHDOG_USEC": "120000000", "WATCHDOG_PID": "-1"}):
            self.assertIsNone(watchdog_interval())

    def test_modbus_threshold_and_recovery(self):
        service = ModbusService(Mock(), max_consecutive_failures=2)
        service._client = Mock(connected=True)
        with patch.object(service, "_reset_connection", return_value=True):
            service._record_failure(ConnectionError("USB"))
        self.assertFalse(service.fatal_error)
        with patch.object(service, "_read_float_register", return_value=100):
            service._poll()
        self.assertEqual(service._consecutive_failures, 0)
        self.assertIsNotNone(service.last_valid_read)
        with patch.object(service, "_reset_connection", return_value=False):
            service._record_failure(ConnectionError("USB"))
            service._record_failure(ConnectionError("USB"))
        self.assertTrue(service.fatal_error)

    def test_invalid_readings_do_not_refresh_valid_read_age(self):
        service = ModbusService(Mock())
        service._client = Mock(connected=True)
        with patch.object(service, "_read_float_register", return_value=-1):
            service._poll()
        self.assertIsNone(service.last_valid_read)

    def test_sqlite_failure_is_not_serial_failure(self):
        db = Mock()
        db.insert_measurement.side_effect = sqlite3.OperationalError("disk full")
        service = ModbusService(db)
        service._client = Mock(connected=True)
        service._window_start = 0
        with patch.object(service, "_read_float_register", return_value=100), patch.object(service, "_reset_connection") as reconnect:
            service._poll()
        reconnect.assert_not_called()
        self.assertFalse(service.fatal_error)
        self.assertIsNone(service.last_insert)

    def test_retention_preserves_pending_and_reports_age(self):
        with tempfile.TemporaryDirectory() as directory:
            db = DatabaseService(str(Path(directory) / "edge.db"))
            with db._get_connection() as conn:
                conn.executemany("INSERT INTO measurements(timestamp, synced) VALUES (?, ?)",
                                 [("2000-01-01T00:00:00+01:00", 0), ("2000-01-01T00:00:00+01:00", 1)])
            db.cleanup_old_data()
            self.assertEqual(len(db.get_unsynced()), 1)
            stats = db.pending_stats()
            self.assertEqual(stats["pending_count"], 1)
            self.assertGreater(stats["oldest_pending_age_seconds"], 86400)
            with db._get_connection() as conn:
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM measurements").fetchone()[0], 1)

    def test_http_outage_retains_measurements_and_worker_progress(self):
        with tempfile.TemporaryDirectory() as directory:
            db = DatabaseService(str(Path(directory) / "edge.db"))
            db.insert_measurement(100, 200)
            sync = SyncService(db)
            with patch.object(sync, "_send_to_api", return_value=False):
                sync._perform_sync()
            self.assertEqual(len(db.get_unsynced()), 1)
            with patch.object(sync, "_send_to_api", return_value=True):
                sync._perform_sync()
            self.assertEqual(db.pending_stats()["pending_count"], 0)


if __name__ == "__main__":
    unittest.main()
