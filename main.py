import logging
import signal
import threading
import time

from config import DB_PATH, MODBUS_POLL_INTERVAL, LOG_HEARTBEAT_SECONDS, SYNC_INTERVAL_SECONDS
from database_service import DatabaseService
from SynchServiceHttp import SyncService
from modbus_service_2 import ModbusService
from logging_config import setup_root_logger
from health import notify_systemd, watchdog_interval


def main():
    setup_root_logger()
    if LOG_HEARTBEAT_SECONDS <= 0:
        raise ValueError("LOG_HEARTBEAT_SECONDS must be positive")
    stop = threading.Event()
    previous = {}
    services = []
    for sig in (signal.SIGTERM, signal.SIGINT):
        previous[sig] = signal.signal(sig, lambda *_: stop.set())
    started_at = time.monotonic()
    next_heartbeat = started_at
    next_watchdog = started_at
    interval = watchdog_interval()
    logging.info("Application starting", extra={"event": "application_start"})
    try:
        db = DatabaseService(db_path=DB_PATH)
        modbus = ModbusService(db, poll_interval=MODBUS_POLL_INTERVAL)
        sync = SyncService(db)
        for service in (modbus, sync):
            services.append(service)
            service.start()
        notify_systemd("READY=1")
        while not stop.is_set():
            now = time.monotonic()
            if modbus.fatal_error:
                raise RuntimeError("Modbus failure threshold reached")
            for name, service, timeout in (
                ("modbus", modbus, max(90, MODBUS_POLL_INTERVAL + 60)),
                ("sync", sync, max(90, SYNC_INTERVAL_SECONDS + 60)),
            ):
                if service.health.stalled(now, timeout):
                    logging.critical("Worker stalled: %s", name,
                                     extra={"event": "worker_stalled", "worker": name})
                    raise RuntimeError(f"Worker stalled: {name}")
            if interval is not None and now >= next_watchdog:
                notify_systemd("WATCHDOG=1")
                next_watchdog = now + interval
            if now >= next_heartbeat:
                # Never query SQLite here: its lock may be the source of a stall.
                logging.getLogger("edge.heartbeat").info(
                    "Application heartbeat",
                    extra={"event": "heartbeat", "uptime_seconds": int(now - started_at),
                           "modbus_fatal": modbus.fatal_error,
                           "read_age_seconds": int(now - (modbus.last_valid_read if modbus.last_valid_read is not None else started_at)),
                           "insert_age_seconds": int(now - (modbus.last_insert if modbus.last_insert is not None else started_at))},
                )
                next_heartbeat = now + LOG_HEARTBEAT_SECONDS
            stop.wait(min(1, interval) if interval else 1)
    finally:
        try:
            notify_systemd("STOPPING=1")
        finally:
            for service in reversed(services):
                try:
                    service.stop()
                except Exception:
                    logging.exception("Service cleanup failed")
            for sig, handler in previous.items():
                signal.signal(sig, handler)
            logging.info("Application stopped", extra={"event": "application_stop"})


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logging.exception("Application crashed", extra={"event": "application_crash"})
        raise
