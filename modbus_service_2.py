import logging
import statistics
from collections import deque
import time
import sqlite3
from health import WorkerHealth, monitored_cycle
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from pymodbus.client import ModbusSerialClient
from pymodbus.exceptions import ModbusException

from database_service import DatabaseService

from config import (
    GAUGE_MAX_MM,
    GAUGE_OFFSET_MM,
    MODBUS_MAX_CONSECUTIVE_FAILURES,
    MODBUS_POLL_INTERVAL,
    MODBUS_RECONNECT_DELAY_SECONDS,
    MODBUS_SERIAL_PORT,
    TANK_MINIMAL_HEIGHT_MM,
)


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
        max_consecutive_failures: int = MODBUS_MAX_CONSECUTIVE_FAILURES,
        reconnect_delay: float = MODBUS_RECONNECT_DELAY_SECONDS,
    ):
        self.db = db_service
        self.health = WorkerHealth()
        self.last_valid_read = None
        self.last_insert = None
        self.serial_port = serial_port
        self.baudrate = baudrate
        self.parity = parity
        self.stopbits = stopbits
        self.unit_id = unit_id
        self.poll_interval = poll_interval
        self.timeout = timeout
        self.max_consecutive_failures = max_consecutive_failures
        self.reconnect_delay = reconnect_delay

        self.logger = logging.getLogger("ModbusService")

        self._client: Optional[ModbusSerialClient] = None
        self._scheduler: Optional[BackgroundScheduler] = None
        self._window_start = time.time()
        self._window_duration = 300  # 5 minutes en secondes
        self._consecutive_failures = 0
        self._fatal_error = False

        # Buffer circulaire de 10 valeurs (5 min / 30s)
        self._buffers = {
            flott_id: deque(maxlen=10)
            for flott_id in self.REGISTRE_FLOTTEUR.keys()
        }

    # ------------------------------------------------------------------
    # PUBLIC API
    # ------------------------------------------------------------------
    @property
    def fatal_error(self):
        """Whether the process should exit and let systemd restart it."""
        return self._fatal_error

    def _reset_connection(self):
        if self._client:
            try:
                self._client.close()
            except Exception as exc:
                self.logger.warning("Failed to close Modbus client: %s", exc)

        self._client = ModbusSerialClient(
            port=self.serial_port,
            baudrate=self.baudrate,
            parity=self.parity,
            stopbits=self.stopbits,
            timeout=self.timeout,
            handle_local_echo=False,
            reconnect_delay=1,
            reconnect_delay_max=10,
        )
        time.sleep(self.reconnect_delay)
        return self._client.connect()

    def _record_failure(self, exc):
        self._consecutive_failures += 1
        self.logger.error(
            "Modbus failure %d/%d: %s",
            self._consecutive_failures,
            self.max_consecutive_failures,
            exc,
            extra={"event": "modbus_failure", "failure_count": self._consecutive_failures,
                   "failure_limit": self.max_consecutive_failures},
        )

        if self._consecutive_failures >= self.max_consecutive_failures:
            self._fatal_error = True
            self.logger.critical(
                "Too many consecutive Modbus failures; requesting service restart",
                extra={"event": "modbus_fatal"},
            )
            return

        try:
            if self._reset_connection():
                self.logger.info("Modbus serial port reopened", extra={"event": "modbus_reconnected"})
            else:
                self.logger.warning("Modbus serial port could not be reopened")
        except Exception as reconnect_exc:
            # Keep the scheduler alive; the next poll counts another failure.
            self.logger.error("Modbus reconnect failed: %s", reconnect_exc)

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

        if self._client.connect():
            self.logger.info("Connecté au Modbus RTU %s", self.serial_port)
        else:
            # Keep the scheduler alive so later polling cycles can retry.
            self.logger.error("Impossible d’ouvrir le port série %s", self.serial_port)

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

    @monitored_cycle
    def _poll(self):
        if self._fatal_error:
            return

        if not self._client or not self._client.connected:
            self._record_failure(
                ConnectionError(f"Modbus port {self.serial_port} is disconnected")
            )
            return

        try:
            #self.logger.info("Lecture Modbus...")

            # Lecture des flotteurs
            if hasattr(self._client,'socket') and self._client.socket:
                self._client.socket.reset_input_buffer()  # vider le buffer pour éviter les données obsolètes
            now = time.time()
            valid_read = True
            for flott_id, reg_addr in self.REGISTRE_FLOTTEUR.items():
                value = self._read_float_register(reg_addr)
                if value < TANK_MINIMAL_HEIGHT_MM or value > GAUGE_MAX_MM:  # filtrage de valeurs aberrantes
                    self.logger.warning("Valeur aberrante pour flotteur %d: %.2f mm", flott_id, value)
                    valid_read = False
                    self.logger.warning("Gauge value rejected", extra={"event": "modbus_invalid_value"})
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
            if valid_read:
                self.last_valid_read = time.monotonic()
            time_elapsed = now - self._window_start
            buffers_full = all(len(buf) == 3 for buf in self._buffers.values())

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
                if all(value is not None for value in median_values.values()):
                    self.last_insert = time.monotonic()

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

            # Both registers were read without an exception.
            if self._consecutive_failures:
                self.logger.info("Modbus communication restored", extra={"event": "modbus_recovered"})
            self._consecutive_failures = 0

        except (sqlite3.Error, OSError) as exc:
            # Serial OSErrors still need reconnection; SQLite errors do not.
            if isinstance(exc, sqlite3.Error):
                self.logger.exception("Measurement storage failed", extra={"event": "database_failure"})
            else:
                self._record_failure(exc)
        except ModbusException as exc:
            self._record_failure(exc)
        except Exception as e:
            # Includes pyserial USB errors such as CH341 EPIPE/stalled URBs.
            self._record_failure(e)
