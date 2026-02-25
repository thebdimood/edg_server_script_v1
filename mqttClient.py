import json
import ssl
import threading
import logging
import uuid
import paho.mqtt.client as mqtt
from config import LOG_FILE, DEVICE_ID

class MqttClient:
    def __init__(
        self,
        broker,
        port=1883,
        client_id=None,
        username=None,
        password=None,
        use_tls=False,
        ca_cert=None,
        log_file: str = LOG_FILE
    ):
        if client_id is None:
            client_id = DEVICE_ID
        self.broker = broker
        self.port = port
        self.client_id = client_id
        self.username = username
        self.password = password
        self.use_tls = use_tls
        self.ca_cert = ca_cert

        self._connected = False
        self._lock = threading.Lock()

        # logging setup
        self.logger = logging.getLogger(self.client_id)

        # Création client
        self.client = mqtt.Client(client_id=self.client_id, clean_session=True)

        # Auth
        if self.username and self.password:
            self.client.username_pw_set(self.username, self.password)

        # TLS
        if self.use_tls:
            self.client.tls_set(
                ca_certs=self.ca_cert,
                certfile=None,
                keyfile=None,
                tls_version=ssl.PROTOCOL_TLS,
            )

        # Last Will (si crash)
        self.client.will_set(
            topic=f"devices/{self.client_id}/status",
            payload="offline",
            qos=1,
            retain=True,
        )

        # Callbacks
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message

        # Reconnexion automatique
        self.client.reconnect_delay_set(min_delay=5, max_delay=60)

    # ------------------------------------------------
    # Callbacks internes
    # ------------------------------------------------

    def _on_connect(self, client, userdata, flags, rc):
        with self._lock:
            if rc == 0:
                self._connected = True
                self.logger.info("client MQTT connecté")

            else:
                self._connected = False
                self.logger.error("Erreur de reconnexion MQTT: %s", rc)

    def _on_disconnect(self, client, userdata, rc):
        with self._lock:
            self._connected = False
        self.logger.info("Client MQTT déconnecté")

    def _on_message(self, client, userdata, msg):
        self.logger.info("Nouvelle commande reçue")

 
# ------------------------------------------------   
# Méthodes publiques
# ------------------------------------------------
    def connect(self):
        """Connexion au broker"""
        self.logger.info("Connecting to broker %s:%s", self.broker, self.port)
        self.client.connect(self.broker, self.port, keepalive=60)
        self.client.loop_start()

    def disconnect(self):
        self.logger.info("Disconnecting from broker")
        self.client.loop_stop()
        self.client.disconnect()

    def is_connected(self):
        """Retourne état connexion"""
        with self._lock:
            return self._connected

    def publish(self, topic, payload, qos=1, retain=False):
        """
        Publish message
        payload peut être dict ou string
        Retourne True si succès
        """
        if not self.is_connected():
            self.logger.warning("Publish attempted while not connected")
            return False

        if isinstance(payload, dict):
            payload = json.dumps(payload)

        result = self.client.publish(topic, payload, qos=qos, retain=retain)
        success = result.rc == mqtt.MQTT_ERR_SUCCESS
        if success:
            self.logger.info("Published to %s qos=%s retain=%s", topic, qos, retain)
        else:
            self.logger.error("Failed to publish to %s: rc=%s", topic, result.rc)

        return success

    def subscribe(self, topic, qos=1):
        """S'abonner à un topic"""
        if self.is_connected():
            self.logger.info("Subscribing to %s qos=%s", topic, qos)
            self.client.subscribe(topic, qos=qos)
