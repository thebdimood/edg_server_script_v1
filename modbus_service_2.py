import logging
import statistics
from collections import deque
import time
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from pymodbus.client import ModbusSerialClient
from pymodbus.exceptions import ModbusException

from database_service import DatabaseService

from config import GAUGE_MAX_MM, GAUGE_OFFSET_MM, MODBUS_POLL_INTERVAL, MODBUS_SERIAL_PORT, TANK_MINIMAL_HEIGHT_MM


class ModbusService:
    """
    Service Modbus RTU :
    - Lecture toutes les 30s
    - Stockage en mémoire
    - Calcul médiane sur 5 minutes
    - Insertion en base
    """

    # Mapping des flotteurs vers registres
    REGISTRE_FLOTTEUR = {
        1: 0x0002, #flotteur 1(carburant)
        2: 0x0004 # flotteur 2 (flotteur eau)
    }

    def __init__(
        self,
        db_service: DatabaseService,
        serial_port: str=MODBUS_SERIAL_PORT,
        baudrate: int = 9600,
        parity: str = "O",
        stopbits: int = 1,
        unit_id: int = 1,
        poll_interval: int = MODBUS_POLL_INTERVAL,  # lecture toutes les 30s
        timeout: float = 1.0,
    ):
        self.db = db_service
        self.serial_port = serial_port
        self.baudrate = baudrate
        self.parity = parity
        self.stopbits = stopbits
        self.unit_id = unit_id
        self.poll_interval = poll_interval
        self.timeout = timeout

        self.logger = logging.getLogger()

        self._client: Optional[ModbusSerialClient] = None
        self._scheduler: Optional[BackgroundScheduler] = None
        self._window_start = time.time()
        self._window_duration = 300  # 5 minutes en secondes

        # Buffer circulaire de 10 valeurs (5 min / 30s)
        self._buffers = {
            flott_id: deque(maxlen=10)
            for flott_id in self.REGISTRE_FLOTTEUR.keys()
        }

    # ------------------------------------------------------------------
    # PUBLIC API
    # ------------------------------------------------------------------
    def start(self):
        self._client = ModbusSerialClient(
            port=self.serial_port,
            baudrate=self.baudrate,
            parity=self.parity,
            stopbits=self.stopbits,
            timeout=self.timeout,
            handle_local_echo=False,
            reconnect_delay=1,
            reconnect_delay_max=10
        )

        if not self._client.connect():
            self.logger.error("Impossible d’ouvrir le port série %s", self.serial_port)
            return

        self.logger.info("Connecté au Modbus RTU %s", self.serial_port)

        self._scheduler = BackgroundScheduler()
        self._scheduler.add_job(self._poll, "interval", seconds=self.poll_interval,misfire_grace_time=15)
        self._scheduler.start()

        self.logger.info("Polling démarré toutes les %ds", self.poll_interval)

    def stop(self):
        if self._scheduler:
            self._scheduler.shutdown(wait=False)
            self.logger.info("Scheduler arrêté")

        if self._client:
            self._client.close()
            self.logger.info("Connexion Modbus fermée")

    # ------------------------------------------------------------------
    # LOGIQUE INTERNE
    # ------------------------------------------------------------------
    def _read_float_register(self, address):
        """Lire 2 registres et reconstruire la valeur"""
        resp = self._client.read_input_registers(
            address=address,
            count=2,
            slave=self.unit_id,
        )

        if resp.isError():
            raise ModbusException(resp)

        raw = (resp.registers[0] << 16) + resp.registers[1]
        return raw / 65536.0

    def _poll(self):
        if not self._client or not self._client.connected:
            self.logger.warning("Client Modbus non connecté")
            if self._client: self._client.connect()  # tentative de reconnexion
            return

        try:
            #self.logger.info("Lecture Modbus...")

            # Lecture des flotteurs
            if hasattr(self._client,'socket') and self._client.socket:
                self._client.socket.reset_input_buffer()  # vider le buffer pour éviter les données obsolètes
            now = time.time()
            for flott_id, reg_addr in self.REGISTRE_FLOTTEUR.items():
                value = self._read_float_register(reg_addr)
                if value < TANK_MINIMAL_HEIGHT_MM or value > GAUGE_MAX_MM:  # filtrage de valeurs aberrantes
                    self.logger.warning("Valeur aberrante pour flotteur %d: %.2f mm", flott_id, value)
                    value=None
                    continue
                self._buffers[flott_id].append(value+GAUGE_OFFSET_MM)  # on ajoute l'offset de jauge pour avoir la hauteur réelle

               # self.logger.info(
               #     "Flotteur %d -> %.2f mm (buffer size=%d)",
               #     flott_id,
               #    value+GAUGE_OFFSET_MM,
               #   len(self._buffers[flott_id]),
               #)
                

            # Vérifier si on a 10 valeurs 
           # --------------------------------------------------
            # Vérification fenêtre 5 minutes
            # --------------------------------------------------
            time_elapsed = now - self._window_start
            buffers_full = all(len(buf) == 10 for buf in self._buffers.values())

            if time_elapsed >= self._window_duration or buffers_full:

                median_values = {}

                for flott_id, buf in self._buffers.items():
                    if len(buf) > 0:
                        median_values[flott_id] = statistics.median(buf)
                    else:
                        median_values[flott_id] = None

                self.db.insert_measurement(
                    water_level=median_values.get(1),
                    liquid_level=median_values.get(2),
                )

                #self.logger.info(
                #    "Fenêtre clôturée. Eau=%s Carburant=%s",
                #    median_values.get(2),
                #    median_values.get(1),
                #)

                # Reset buffers
                for buf in self._buffers.values():
                    buf.clear()

                # Reset timer
                self._window_start = time.time()

        except ModbusException as exc:
            self.logger.error("Erreur Modbus: %s", exc)
        except Exception as e:
            self.logger.error("Erreur générale: %s", e)