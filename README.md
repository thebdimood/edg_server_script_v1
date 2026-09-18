# Edge Modbus Server

Python edge application for collecting tank-level measurements from a
magnetostrictive gauge over Modbus RTU/RS-485. Measurements are buffered and
filtered locally, stored in SQLite, and synchronized with a remote HTTP API.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the component design and data flow.

## Main features

- Polls two gauge floats through a Modbus serial connection.
- Rejects measurements outside the configured gauge range.
- Adds a configurable gauge offset and calculates median values.
- Stores measurements locally before attempting network delivery.
- Retries unsynchronized measurements through the HTTP synchronization job.
- Recreates the serial client after Modbus or USB communication failures.
- Exits after repeated failures so systemd can restart the application.
- Includes optional hardware diagnostics and a local Flask dashboard.

## Requirements

- Python 3.10 or newer
- A Modbus RTU-compatible USB-to-RS-485 adapter
- A reachable remote HTTP API
- Linux/systemd for the production service configuration

Install the Python dependencies:

```bash
python3 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

The optional dashboard in `api/server.py` also requires Flask:

```bash
python -m pip install Flask
```

## Configuration

Runtime settings are defined in `config.py`.

Important settings include:

| Setting | Purpose |
|---|---|
| `DEVICE_ID` | Unique tank or gauge identifier |
| `DB_PATH` | SQLite database location |
| `LOG_FILE` | Application log location |
| `API_URL` | Destination for synchronized measurements |
| `SYNC_INTERVAL_SECONDS` | Interval between HTTP synchronization jobs |
| `MODBUS_SERIAL_PORT` | Serial device used by the RS-485 adapter |
| `MODBUS_POLL_INTERVAL` | Seconds between Modbus polling cycles |
| `GAUGE_MAX_MM` | Maximum accepted raw gauge value |
| `GAUGE_OFFSET_MM` | Calibration offset added to readings |
| `MODBUS_MAX_CONSECUTIVE_FAILURES` | Failures allowed before process restart |
| `MODBUS_RECONNECT_DELAY_SECONDS` | Delay before reopening the serial client |

For Raspberry Pi deployments, do not use a Windows port such as `COM5`. Prefer
the stable Linux device path shown by:

```bash
ls -l /dev/serial/by-id/
```

Example:

```python
MODBUS_SERIAL_PORT = "/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0"
```

Ensure the service account can access serial devices:

```bash
sudo usermod -aG dialout lightgroup
```

Log out and back in, or reboot, after changing group membership.

## Running locally

Run the production pipeline:

```bash
python main.py
```

The application starts two background jobs:

1. Modbus acquisition and local database insertion.
2. HTTP synchronization of unsent database records.

Stop it with `Ctrl+C`.

## Production deployment with systemd

The repository includes `edge.service`. Confirm that its user, working
directory, virtual environment, and script paths match the deployed location.

Install and start it with:

```bash
sudo cp edge.service /etc/systemd/system/edge.service
sudo systemctl daemon-reload
sudo systemctl enable --now edge.service
```

Check its status:

```bash
systemctl status edge.service
```

The unit uses `Restart=always`, so when the application exits after repeated
Modbus failures, systemd starts a fresh process and serial connection.

## Logs and troubleshooting

Follow the application file log:

```bash
sudo tail -F /var/log/edge/app.log
```

Follow the systemd service:

```bash
sudo journalctl -u edge.service -f
```

Follow relevant Raspberry Pi kernel events:

```bash
sudo journalctl -k -f | grep --line-buffered -Ei "usb|ch341|ttyUSB|voltage|under"
```

Check Raspberry Pi power history:

```bash
vcgencmd get_throttled
```

`throttled=0x0` means no under-voltage or throttling condition was recorded.

Recovery-related messages include:

```text
Modbus failure 1/5
Modbus serial port reopened
Modbus communication restored
Too many consecutive Modbus failures; requesting service restart
```

## Remote monitoring

Start with the [Raspberry Pi logging setup](deploy/raspberry-pi/README.md).
It covers rotating application logs and a local Alloy collection check.
The Loki connection and Grafana configuration will be completed separately.

For centralized log monitoring, install Grafana Alloy on the Raspberry Pi and
send these sources to Loki on the monitoring server:

- `app.log`
- the `edge.service` systemd journal
- kernel messages matching `ch341`, `ttyUSB`, USB, or under-voltage events

Grafana should query Loki and provide log panels and alerts. Loki port `3100`
should remain private; expose ingestion through an authenticated HTTPS reverse
proxy or a private VPN.

## Local dashboard

The optional Flask server displays the current day's measurements:

```bash
python api/server.py
```

Open `http://<device-address>:5000/`. This server is independent from
`main.py` and is not started by `edge.service`.

## Diagnostic scripts

- `scan_modbus.py`: scans Modbus unit addresses.
- `test_jauge.py`: reads gauge float registers asynchronously.
- `test_temp.py`: reads gauge temperature registers.
- `fake_modbus_service.py`: generates measurements without physical hardware.
- `test_subscriber.py`: listens for messages from the legacy MQTT pipeline.

These are hardware/integration utilities rather than an automated unit-test
suite. Confirm serial-port values before running them.

## Repository layout

```text
.
├── main.py                   Production entry point
├── config.py                 Runtime configuration
├── modbus_service_2.py       Active Modbus acquisition and recovery
├── database_service.py       SQLite persistence
├── SynchServiceHttp.py       Active HTTP synchronization
├── edge.service              systemd unit
├── api/                      Optional local dashboard
├── fake_modbus_service.py    Synthetic measurement source
├── modbus_service.py         Legacy Modbus implementation
├── Synch_service.py          Legacy MQTT synchronization
├── mqttClient.py             Legacy MQTT client
└── test_*.py / scan_modbus.py Hardware diagnostic scripts
```

## Known limitations

- Device identity and logging support environment overrides; other settings
  remain source-code constants.
- The active application does not start the MQTT path or Flask dashboard.
- Database cleanup exists but is not scheduled automatically.
- HTTP synchronization currently uses an unencrypted URL unless `API_URL` is
  changed to HTTPS.
- Logging tests run with `python -m unittest discover -s tests -v`;
  hardware acquisition is not covered by that suite.
