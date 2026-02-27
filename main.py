import time
import logging
from database_service import DatabaseService
from fake_modbus_service import FakeModbusService
from SynchServiceHttp import SyncService
from config import (
    DB_PATH, LOG_FILE,
    MODBUS_POLL_INTERVAL,
)


def setup_root_logger(log_file: str = LOG_FILE):
    logger = logging.getLogger()
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        handler = logging.FileHandler(log_file)
        fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
        handler.setFormatter(fmt)
        logger.addHandler(handler)
    return logger


def main():
    # initialize global logging
    setup_root_logger()
    logging.info("Application starting")

    # create services
    db = DatabaseService(db_path=DB_PATH)
   # mqtt = MqttClient(MQTT_BROKER, log_file=LOG_FILE)
    modbus = FakeModbusService(
        db,
        poll_interval=MODBUS_POLL_INTERVAL,
    )

    # create and start sync service
    sync = SyncService(db)
    modbus.start()
    sync.start()

    try:
        # keep the main thread alive while background scheduler works
        while True:
            time.sleep(30)
    except KeyboardInterrupt:
        logging.info("Shutdown requested by user")
    finally:
        sync.stop()
        logging.info("Application stopped")


if __name__ == "__main__":
    main()
