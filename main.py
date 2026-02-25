import time
import logging
from database_service import DatabaseService
from fake_modbus_service import FakeModbusService
from fake_modbus_service import FakeModbusService
from modbus_service import ModbusService
from mqttClient import MqttClient
from Synch_service import SyncService
from config import (
    DB_PATH, LOG_FILE,
    MQTT_BROKER,
    SYNC_INTERVAL_SECONDS,
    MODBUS_SERIAL_PORT, MODBUS_BAUDRATE, MODBUS_POLL_INTERVAL,
)


def setup_root_logger(log_file: str = LOG_FILE):
    logger = logging.getLogger()
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
    mqtt = MqttClient(MQTT_BROKER, log_file=LOG_FILE)
    modbus = FakeModbusService(
        db,
        poll_interval=MODBUS_POLL_INTERVAL,
    )

    # create and start sync service
    sync = SyncService(db, mqtt, sync_interval=SYNC_INTERVAL_SECONDS)
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
