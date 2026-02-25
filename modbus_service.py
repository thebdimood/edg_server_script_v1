import logging
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from pymodbus.client import ModbusSerialClient
from pymodbus.exceptions import ModbusException

from database_service import DatabaseService


class ModbusService:
    """Poll a Modbus/RTU device over an RS‑485 serial link and store the
    readings in the database."""
    def __init__(
        self,
        db_service: DatabaseService,
        serial_port: str,
        baudrate: int = 19200,
        parity: str = "N",
        stopbits: int = 1,
        unit_id: int = 1,
        poll_interval: int = 60 * 5,
        timeout: float = 3.0,
    ):
        self.db = db_service
        self.serial_port = serial_port
        self.baudrate = baudrate
        self.parity = parity
        self.stopbits = stopbits
        self.unit_id = unit_id
        self.poll_interval = poll_interval
        self.timeout = timeout

        self.logger = logging.getLogger("ModbusService")
        self.logger.setLevel(logging.INFO)
        handler = logging.FileHandler("modbus.log")
        fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
        handler.setFormatter(fmt)
        self.logger.addHandler(handler)

        self._client: Optional[ModbusSerialClient] = None
        self._scheduler: Optional[BackgroundScheduler] = None

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------
    def start(self):
        """Open the serial port and start the polling job."""
        self._client = ModbusSerialClient(
            port=self.serial_port,
            baudrate=self.baudrate,
            parity=self.parity,
            stopbits=self.stopbits,
            timeout=self.timeout,
        )

        if not self._client.connect():
            self.logger.error("Failed to open serial port %s", self.serial_port)
            return

        self.logger.info("Connected to Modbus RTU %s", self.serial_port)
        self._scheduler = BackgroundScheduler()
        self._scheduler.add_job(self._poll, "interval", seconds=self.poll_interval)
        self._scheduler.start()
        self.logger.info("Polling scheduled every %ds", self.poll_interval)

    def stop(self):
        if self._scheduler:
            self._scheduler.shutdown(wait=False)
            self.logger.info("Scheduler stopped")
            self._scheduler = None
        if self._client:
            self._client.close()
            self.logger.info("Modbus client disconnected")
            self._client = None

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------
    def _poll(self):
        if not self._client:
            return

        try:
            resp = self._client.read_holding_registers(address=0, count=4, slave=self.unit_id)
            if resp.isError():
                raise ModbusException(resp)
            regs = resp.registers
            water_level = regs[0] / 100.0
            water_temperature = regs[1] / 100.0
            liquid_level = regs[2] / 100.0
            liquid_temperature = regs[3] / 100.0

            self.db.insert_measurement(
                device_id=str(self.unit_id),
                water_level=water_level,
                water_temperature=water_temperature,
                liquid_level=liquid_level,
                liquid_temperature=liquid_temperature,
            )
            self.logger.info("Inserted measurement from unit %d", self.unit_id)
        except ModbusException as exc:
            self.logger.error("Modbus poll failed: %s", exc)