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

        self.logger = logging.getLogger()

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
            water_level = round(random.uniform(100.0, 200.0), 2)
            liquid_level = round(random.uniform(3000.0, 2000.0), 2)

            self.db.insert_measurement(
                water_level=water_level,
                liquid_level=liquid_level,

            )
            self.logger.info(
                "Fake Modbus poll: water_level=%.2f, liquid_level=%.2f",
                water_level,
                liquid_level,
            )
        except (OSError, ValueError) as exc:
            self.logger.error("Fake poll failed: %s", exc)