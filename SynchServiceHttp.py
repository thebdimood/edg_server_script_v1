import logging
import sqlite3
import time
import shutil
from pathlib import Path
from health import WorkerHealth, monitored_cycle
import requests  # Importation pour l'API REST
from typing import Optional
from apscheduler.schedulers.background import BackgroundScheduler
from config import DEVICE_ID, API_URL, DEVICE_TYPE, SYNC_INTERVAL_SECONDS

class SyncService:
    def __init__(
        self,
        db_service,
        api_url: str = API_URL,
        sync_interval: int =SYNC_INTERVAL_SECONDS,
    ):
        self.db = db_service
        self.health = WorkerHealth()
        self.api_url = api_url
        self.sync_interval = sync_interval
        self.logger = logging.getLogger("SyncService")
        self._scheduler: Optional[BackgroundScheduler] = None

    def start(self):
        """Démarre le scheduler pour l'envoi HTTP."""
        job_defaults = {
            'max_instances': 1,
            'coalesce': True,
            'misfire_grace_time': 30
        }
        self._scheduler = BackgroundScheduler(job_defaults=job_defaults)
        self._scheduler.add_job(self._perform_sync, "interval", seconds=self.sync_interval)
        self._scheduler.start()
        self.logger.info("HTTP Sync scheduled every %ds to %s", self.sync_interval, self.api_url)

    def stop(self):
        if self._scheduler:
            self._scheduler.shutdown(wait=False)
            self.logger.info("Scheduler stopped")

    @monitored_cycle
    def _perform_sync(self):
        """Lit la DB et envoie via POST HTTP."""
        self.logger.info("Starting HTTP sync cycle")
        try:
            stats = self.db.pending_stats()
            usage = shutil.disk_usage(Path(self.db.db_path).resolve().parent)
            self.logger.info("Storage health", extra={"event": "storage_health", **stats,
                             "disk_used_percent": round(100 * usage.used / usage.total, 1)})
            rows = self.db.get_unsynced()
        except (OSError, ValueError, sqlite3.Error):
            self.logger.exception("Failed to fetch unsynced data", extra={"event": "sync_failure"})
            return

        batch_started = time.monotonic()
        for row in rows:
            if time.monotonic() - batch_started >= 45:
                break
            self.health.progress()
            # Structure : (id, timestamp, water_level, water_temp, liq_level, liq_temp)
            record_id, ts, w_lvl, l_lvl  = row

            # Format "data" : date,ID,DeviceID&Niveau&0&0...
            data_string = f"{ts},-34,{DEVICE_ID}&{l_lvl}&0&0&0&1.0&0&0&0&{l_lvl}"

            payload = {
                "data": data_string,
                "water_level": w_lvl,
                "source": DEVICE_TYPE
            }

            if self._send_to_api(payload):
                try:
                    self.db.mark_as_synced(record_id)
                    self.logger.info("Record %s synced via HTTP", record_id,
                                     extra={"event": "sync_success", "record_id": record_id})
                except (OSError, ValueError, sqlite3.Error):
                    self.logger.exception("Failed to mark record %s", record_id,
                                          extra={"event": "sync_failure", "record_id": record_id})
                    break
            else:
                self.logger.error("API sync failed for record %s, aborting cycle", record_id,
                                  extra={"event": "sync_failure", "record_id": record_id})
                break

        self.logger.info("Sync cycle complete")

    def _send_to_api(self, payload: dict) -> bool:
        """Helper pour effectuer la requête POST."""
        try:
            # Envoi avec un timeout pour ne pas bloquer le script si le serveur est down
            response = requests.post(self.api_url, json=payload, timeout=10)
            
            if response.status_code in [200, 201]:
                return True
            else:
                self.logger.error("API returned HTTP %d", response.status_code,
                                  extra={"status_code": response.status_code})
                return False
        except requests.exceptions.RequestException as e:
            self.logger.error("Connection to API failed: %s", e)
            return False
