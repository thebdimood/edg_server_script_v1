import logging
import random
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler

from database_service import DatabaseService


class FakeModbusService:
    """Simulate a Modbus device by generating synthetic sensor readings and
    storing them in the database.

    Useful for testing the pipeline without a real physical device.
    """

    def __init__(
        self,
        db_service: DatabaseService,
        unit_id: int = 1,
        poll_interval: int = 60 * 5,
    ):
        self.db = db_service
        self.unit_id = unit_id
        self.poll_interval = poll_interval

        self.logger = logging.getLogger("FakeModbusService")
        self.logger.setLevel(logging.INFO)
        handler = logging.FileHandler("fake_modbus.log")
        fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
        handler.setFormatter(fmt)
        self.logger.addHandler(handler)

        self._scheduler: Optional[BackgroundScheduler] = None

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------
    def start(self):
        """Start the synthetic data generation job."""
        self._scheduler = BackgroundScheduler()
        self._scheduler.add_job(self._poll, "interval", seconds=self.poll_interval)
        self._scheduler.start()
        self.logger.info("Fake Modbus polling scheduled every %ds", self.poll_interval)

    def stop(self):
        """Stop the synthetic data generation."""
        if self._scheduler:
            self._scheduler.shutdown(wait=False)
            self.logger.info("Fake Modbus scheduler stopped")
            self._scheduler = None

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------
    def _poll(self):
        """Generate synthetic readings and insert them into the database."""
        try:
            # generate random values within reasonable ranges
            water_level = round(random.uniform(10.0, 50.0), 2)
            water_temperature = round(random.uniform(15.0, 30.0), 2)
            liquid_level = round(random.uniform(20.0, 80.0), 2)
            liquid_temperature = round(random.uniform(10.0, 25.0), 2)

            self.db.insert_measurement(
                device_id=str(self.unit_id),
                water_level=water_level,
                water_temperature=water_temperature,
                liquid_level=liquid_level,
                liquid_temperature=liquid_temperature,
            )
            self.logger.info(
                "Inserted fake measurement: water_level=%.2f, water_temp=%.2f, "
                "liquid_level=%.2f, liquid_temp=%.2f",
                water_level,
                water_temperature,
                liquid_level,
                liquid_temperature,
            )
        except (OSError, ValueError) as exc:
            self.logger.error("Fake poll failed: %s", exc)