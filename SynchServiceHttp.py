import logging
import requests  # Importation pour l'API REST
from typing import Optional
from apscheduler.schedulers.background import BackgroundScheduler
from config import DEVICE_ID, API_URL, SYNC_INTERVAL_SECONDS

class SyncService:
    def __init__(
        self,
        db_service,
        api_url: str = API_URL,
        sync_interval: int =SYNC_INTERVAL_SECONDS,
    ):
        self.db = db_service
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

    def _perform_sync(self):
        """Lit la DB et envoie via POST HTTP."""
        self.logger.info("Starting HTTP sync cycle")
        try:
            rows = self.db.get_unsynced()
        except (OSError, IOError, ValueError) as exc:
            self.logger.error("Failed to fetch unsynced data: %s", exc)
            return

        for row in rows:
            # Structure : (id, timestamp, water_level, water_temp, liq_level, liq_temp)
            record_id, ts, w_lvl, w_temp, l_lvl, l_temp = row

            # --- CONSTRUCTION DU FORMAT SPECIFIQUE ---
            # Format "data" : date,ID,DeviceID&Niveau&0&0...
            data_string = f"{ts},-34,{DEVICE_ID}&{l_lvl}&0&0&0&1.0&0&0&0&{l_lvl}"

            payload = {
                "data": data_string,
                "water_level": w_lvl,
                "water_temperature": w_temp
            }

            if self._send_to_api(payload):
                try:
                    self.db.mark_as_synced(record_id)
                    self.logger.info("Record %s synced via HTTP", record_id)
                except (OSError, IOError, ValueError) as exc:
                    self.logger.error("Failed to mark record %s: %s", record_id, exc)
            else:
                self.logger.error("API sync failed for record %s, aborting cycle", record_id)
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
                self.logger.error("API Error %d: %s", response.status_code, response.text)
                return False
        except requests.exceptions.RequestException as e:
            self.logger.error("Connection to API failed: %s", e)
            return False