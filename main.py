import time
import logging
from database_service import DatabaseService
from mqttClient import MqttClient
from Synch_service import SyncService


def setup_root_logger(log_file: str = "app.log"):
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
    db = DatabaseService(db_path="edge.db")
    mqtt = MqttClient("38.242.228.212", log_file="app.log")

    # create and start sync service
    sync = SyncService(db, mqtt, sync_interval=30)
    sync.start()

    try:
        # keep the main thread alive while background scheduler works
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("Shutdown requested by user")
    finally:
        sync.stop()
        logging.info("Application stopped")


if __name__ == "__main__":
    main()
