import logging
from typing import Optional
from apscheduler.schedulers.background import BackgroundScheduler
from config import DEVICE_ID


class SyncService:
    """Service responsible for synchronizing unsent measurements from
    a local database to an MQTT broker using an MQTT client instance.

    The service schedules a periodic job that reads unsynced records from
    :class:`DatabaseService`, publishes them via :class:`Mqttlient`, and
    then marks them as synced if the publish succeeds.
    """

    def __init__(
        self,
        db_service,
        mqtt_client,
        topic_template: str = "devices/{device_id}/measurements",
        sync_interval: int = 60*5,
    ):
        """Initialize the synchronization service.

        Args:
            db_service: an instance of :class:`DatabaseService`.
            mqtt_client: an instance of :class:`Mqttlient` (from mqttClient.py).
            topic_template: format string for the MQTT topic. It will be
                formatted with ``device_id``.
            sync_interval: number of seconds between sync attempts.
        """
        self.db = db_service
        self.mqtt = mqtt_client
        self.topic_template = topic_template
        self.sync_interval = sync_interval

        self.logger = logging.getLogger()

        self._scheduler: Optional[BackgroundScheduler] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def start(self):
        """Start the MQTT client (if not connected) and the scheduler."""
        if not self.mqtt.is_connected():
            self.logger.info("Starting MQTT client connection")
            self.mqtt.connect()
        job_defaults = {
            'max_instances': 1,
            'coalesce': True,
            'misfire_grace_time': 30  # Donne 30s de marge si le Pi rame
        }
        self._scheduler = BackgroundScheduler(job_defaults=job_defaults)
        # schedule job
        
        self._scheduler.add_job(self._perform_sync, "interval", seconds=self.sync_interval)
        self._scheduler.start()
        self.logger.info("Synchronization scheduled every %ds", self.sync_interval)

    def stop(self):
        """Stop the scheduler and disconnect MQTT."""
        if self._scheduler:
            self._scheduler.shutdown(wait=False)
            self.logger.info("Scheduler stopped")
            self._scheduler = None
        if self.mqtt.is_connected():
            self.logger.info("Disconnecting MQTT client")
            self.mqtt.disconnect()

    def trigger_now(self):
        """Manually trigger a sync cycle outside of the schedule."""
        self._perform_sync()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _perform_sync(self):
        """Read unsynced rows and publish them one by one."""
        self.logger.info("Starting sync cycle")
        try:
            rows = self.db.get_unsynced()
        except (OSError, IOError, ValueError) as exc:
            self.logger.error("Failed to fetch unsynced data: %s", exc)
            return

        for row in rows:
            # row structure: (id, timestamp, water_level, water_temperature,
            # liquid_level, liquid_temperature)
            record_id , timestamp, water_level, water_temp, liq_level, liq_temp = row

            payload = {
                "id": record_id,
                "timestamp": timestamp,
                "water_level": water_level,
                "water_temperature": water_temp,
                "liquid_level": liq_level,
                "liquid_temperature": liq_temp,
            }
            topic = self.topic_template.format(device_id=DEVICE_ID)

            if not self.mqtt.is_connected():
                self.logger.warning("MQTT client disconnected during sync, stopping cycle")
                break

            success = self.mqtt.publish(topic, payload)
            if success:
                try:
                    self.db.mark_as_synced(record_id)
                    self.logger.info("Record %s synced to %s", record_id, topic)
                except (OSError, IOError, ValueError) as exc:
                    self.logger.error("Failed to mark record %s as synced: %s", record_id, exc)
                    # do not remove from list, next cycle will retry
            else:
                self.logger.error("Publish failed for record %s, aborting cycle", record_id)
                break

        self.logger.info("Sync cycle complete")
