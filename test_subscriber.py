import logging
import json
import paho.mqtt.client as mqtt
from config import MQTT_BROKER, MQTT_PORT, MQTT_TOPIC_TEMPLATE


class TestSubscriber:
    """Subscribe to the measurement topic and log incoming messages.

    Useful for verifying that the fake service → database → sync pipeline is
    working correctly.
    """

    def __init__(self, broker: str = MQTT_BROKER, port: int = MQTT_PORT):
        self.broker = broker
        self.port = port
        self.topic = MQTT_TOPIC_TEMPLATE.format(device_id="1")

        self.logger = logging.getLogger("TestSubscriber")
        self.logger.setLevel(logging.INFO)
        handler = logging.FileHandler("test_subscriber.log")
        fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
        handler.setFormatter(fmt)
        self.logger.addHandler(handler)

        self.client = mqtt.Client()
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message

    # ------------------------------------------------------------------
    # MQTT callbacks
    # ------------------------------------------------------------------
    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self.logger.info("Connected to broker %s:%d", self.broker, self.port)
            client.subscribe(self.topic)
            self.logger.info("Subscribed to topic: %s", self.topic)
        else:
            self.logger.error("Connection failed with code %d", rc)

    def _on_disconnect(self, client, userdata, rc):
        if rc != 0:
            self.logger.warning("Unexpected disconnection with code %d", rc)
        else:
            self.logger.info("Disconnected from broker")

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
            self.logger.info(
                "Received message on %s: %s",
                msg.topic,
                json.dumps(payload, indent=2),
            )
        except json.JSONDecodeError:
            self.logger.warning("Received non-JSON payload: %s", msg.payload)

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------
    def start(self):
        """Connect to the broker and start listening."""
        self.logger.info("Connecting to %s:%d", self.broker, self.port)
        self.client.connect(self.broker, self.port, keepalive=60)
        self.client.loop_start()

    def stop(self):
        """Disconnect from the broker."""
        self.client.loop_stop()
        self.client.disconnect()
        self.logger.info("Subscriber stopped")


if __name__ == "__main__":
    # simple CLI test runner
    import time
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    sub = TestSubscriber()
    sub.start()

    try:
        print("Listening for messages... (press Ctrl+C to stop)")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping...")
        sub.stop()
        sys.exit(0)