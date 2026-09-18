"""
Central configuration for the edge‑server application.

Consumers import the constants they need. Device identity and logging settings
support environment overrides; other settings are edited in this module.
"""

import os
from typing import Optional

# database
DB_PATH: str = "edge.db"

#device settings
DEVICE_ID: str = os.getenv("DEVICE_ID", "TKS-111")
SITE_ID: str = os.getenv("SITE_ID", "default")
DEVICE_TYPE:str="magnetostrictive"
TANK_MINIMAL_HEIGHT_MM: int = 0
TANK_MAXIMAL_HEIGHT_MM: int =3300
GAUGE_MAX_MM: int =3150
GAUGE_OFFSET_MM: int =80


# logging
LOG_FILE: str = os.getenv("LOG_FILE", "app.log")
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_MAX_BYTES: int = int(os.getenv("LOG_MAX_BYTES", str(10 * 1024 * 1024)))
LOG_BACKUP_COUNT: int = int(os.getenv("LOG_BACKUP_COUNT", "5"))
LOG_TO_CONSOLE: bool = os.getenv("LOG_TO_CONSOLE", "true").lower() in ("1", "true", "yes")
LOG_HEARTBEAT_SECONDS: int = int(os.getenv("LOG_HEARTBEAT_SECONDS", "60"))

#API settings
API_URL: str = "http://192.168.1.151:8000/api/add-data"

# MQTT broker settings
MQTT_BROKER: str = "38.242.228.212"
MQTT_PORT: int = 1883
MQTT_CLIENT_ID: str = "edge-device-01"
MQTT_USERNAME: Optional[str] = None
MQTT_PASSWORD: Optional[str] = None
MQTT_TOPIC_TEMPLATE: str = "devices/{device_id}/measurements"

# synchronization
SYNC_INTERVAL_SECONDS: int = 60   # every five minutes

# Modbus/RS‑485
MODBUS_SERIAL_PORT: str = os.getenv("MODBUS_SERIAL_PORT", "COM5")
MODBUS_BAUDRATE: int = 9600
MODBUS_PARITY: str = "O"
MODBUS_STOPBITS: int = 1
MODBUS_UNIT_ID: int = 1
MODBUS_POLL_INTERVAL: int = 30       # every 30 seconds
MODBUS_TIMEOUT: float = 3.0
MODBUS_MAX_CONSECUTIVE_FAILURES: int = 5
MODBUS_RECONNECT_DELAY_SECONDS: float = 2.0
