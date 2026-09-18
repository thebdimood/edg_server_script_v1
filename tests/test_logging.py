import io
import json
import logging
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from logging_config import setup_root_logger
from SynchServiceHttp import SyncService


class LoggingTests(unittest.TestCase):
    def setUp(self):
        self.root = logging.getLogger()
        self.old_level = self.root.level
        self.old_heartbeat_level = logging.getLogger("edge.heartbeat").level
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "nested" / "app.log"

    def tearDown(self):
        for handler in list(self.root.handlers):
            if getattr(handler, "_edge_owned", False):
                self.root.removeHandler(handler)
                handler.close()
        self.root.setLevel(self.old_level)
        logging.getLogger("edge.heartbeat").setLevel(self.old_heartbeat_level)
        self.temp.cleanup()

    def test_json_exception_is_one_line_with_context(self):
        setup_root_logger(self.path, console=False, device="tank-1", site="depot")
        try:
            raise ValueError("bad\nreading")
        except ValueError:
            logging.exception("Gauge échec", extra={"event": "test_error"})
        lines = self.path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)
        entry = json.loads(lines[0])
        self.assertEqual(entry["device"], "tank-1")
        self.assertEqual(entry["site"], "depot")
        self.assertEqual(entry["event"], "test_error")
        self.assertTrue(entry["timestamp"].endswith("+00:00"))
        self.assertIn("ValueError", entry["exception"])

    def test_rotation_bounds_history_and_keeps_recent_record(self):
        setup_root_logger(self.path, console=False, max_bytes=600, backup_count=2)
        for index in range(30):
            logging.info("record %s %s", index, "x" * 80)
        files = list(self.path.parent.glob("app.log*"))
        self.assertEqual(len(files), 3)
        self.assertIn("record 29", self.path.read_text(encoding="utf-8"))
        for file in files:
            for line in file.read_text(encoding="utf-8").splitlines():
                json.loads(line)

    def test_setup_replaces_owned_handlers_without_duplicate_records(self):
        for _ in range(2):
            setup_root_logger(self.path, console=False)
        logging.info("once")
        self.assertEqual(len(self.path.read_text(encoding="utf-8").splitlines()), 1)

    def test_console_and_file_share_structured_record(self):
        stream = io.StringIO()
        with patch("sys.stdout", stream):
            setup_root_logger(self.path, console=True)
            logging.warning("both destinations")
        self.assertEqual(stream.getvalue(), self.path.read_text(encoding="utf-8"))

    def test_heartbeat_survives_warning_log_level(self):
        setup_root_logger(self.path, console=False, level="WARNING")
        logging.info("filtered")
        logging.getLogger("edge.heartbeat").info("alive", extra={"event": "heartbeat"})
        lines = self.path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(json.loads(lines[0])["event"], "heartbeat")

    def test_existing_host_handler_is_preserved(self):
        host_handler = logging.NullHandler()
        self.root.addHandler(host_handler)
        try:
            setup_root_logger(self.path, console=False)
            self.assertIn(host_handler, self.root.handlers)
        finally:
            self.root.removeHandler(host_handler)

    def test_rotation_cannot_be_accidentally_disabled(self):
        for args in ({"max_bytes": 0}, {"backup_count": 0}):
            with self.assertRaises(ValueError):
                setup_root_logger(self.path, console=False, **args)

    def test_sync_database_failure_has_alertable_event(self):
        setup_root_logger(self.path, console=False)
        db = Mock()
        db.pending_stats.return_value = {}
        db.db_path = str(self.path.parent / "edge.db")
        db.get_unsynced.side_effect = sqlite3.OperationalError("database locked")
        SyncService(db)._perform_sync()
        entries = [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines()]
        failure = next(entry for entry in entries if entry.get("event") == "sync_failure")
        self.assertIn("OperationalError", failure["exception"])

    def test_http_rejection_logs_one_failure_without_response_body(self):
        setup_root_logger(self.path, console=False)
        db = Mock()
        db.pending_stats.return_value = {}
        db.db_path = str(self.path.parent / "edge.db")
        db.get_unsynced.return_value = [(1, "2026-01-01T00:00:00+00:00", 1, 2)]
        with patch("SynchServiceHttp.requests.post", return_value=Mock(status_code=403, text="sensitive-response")):
            SyncService(db)._perform_sync()
        content = self.path.read_text(encoding="utf-8")
        entries = [json.loads(line) for line in content.splitlines()]
        self.assertEqual(sum(entry.get("event") == "sync_failure" for entry in entries), 1)
        self.assertNotIn("sensitive-response", content)
        db.mark_as_synced.assert_not_called()


if __name__ == "__main__":
    unittest.main()
