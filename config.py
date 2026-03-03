"""
Central configuration for the edge‑server application.

Consumers import the constants they need; the defaults here may be overridden
by setting environment variables before starting the program, or by editing the
module.
"""

from typing import Optional

# database
DB_PATH: str = "edge.db"

#device settings
DEVICE_ID:str="1"
DEVICE_TYPE:str="magnetostrictive"
TANK_MINIMAL_HEIGHT_MM: int = 0
TANK_MAXIMAL_HEIGHT_MM: int =3300
GAUGE_MAX_MM: int =3150
GAUGE_OFFSET_MM: int =50


# logging
LOG_FILE: str = "app.log"

#API settings
API_URL: str = "http://38.242.228.212:8000/api/add-data"

# MQTT broker settings
MQTT_BROKER: str = "38.242.228.212"
MQTT_PORT: int = 1883
MQTT_CLIENT_ID: str = "edge-device-01"
MQTT_USERNAME: Optional[str] = None
MQTT_PASSWORD: Optional[str] = None
MQTT_TOPIC_TEMPLATE: str = "devices/{device_id}/measurements"

# synchronization
SYNC_INTERVAL_SECONDS: int = 60 * 5   # every five minutes

# Modbus/RS‑485
MODBUS_SERIAL_PORT: str = "/dev/ttyUSB0"       
MODBUS_BAUDRATE: int = 9600
MODBUS_PARITY: str = "O"
MODBUS_STOPBITS: int = 1
MODBUS_UNIT_ID: int = 1
MODBUS_POLL_INTERVAL: int = 30        # every 30 seconds
MODBUS_TIMEOUT: float = 3.0