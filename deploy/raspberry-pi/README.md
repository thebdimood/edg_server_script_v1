# Raspberry Pi logging setup

For service watchdog/recovery and remote alert activation, follow
[RECOVERY_SETUP.md](RECOVERY_SETUP.md). The local-only Alloy checks below remain
useful before configuring the remote endpoint.

This phase configures and checks collection on the Pi. The application keeps
rotating JSON logs and emits a heartbeat every minute. Alloy collects the log,
systemd events, and relevant USB/kernel events, then prints them to its own
journal for local verification. No Loki endpoint or server credentials are needed.

These instructions target Raspberry Pi OS with systemd and the existing
`lightgroup` account and `/home/lightgroup/edg_server_script_v1` project path.
Adjust `edge.service` and the Alloy drop-in if those differ on your device.
Run the commands on the Pi from the project root. Files have been prepared in
the repository; they have not been installed on your Pi remotely.

## 1. Enable application logging

Confirm the Modbus serial port in `config.py` is a Linux device path, preferably
`/dev/serial/by-id/...`, rather than `COM5`. Inspect available ports with:

```bash
ls -l /dev/serial/by-id/
```

Install the application dependencies in its existing virtual environment if
needed, then configure the service:

```bash
venv/bin/python -m pip install -r requirements.txt
sudo install -d -m 0755 /etc/edge
if ! sudo test -e /etc/edge/edge.env; then
  sudo install -m 0640 deploy/raspberry-pi/edge.env.example /etc/edge/edge.env
fi
sudoedit /etc/edge/edge.env
sudo usermod -aG dialout lightgroup
sudo install -m 0644 edge.service /etc/systemd/system/edge.service
sudo systemctl daemon-reload
sudo systemctl enable edge
sudo systemctl restart edge
```

Set a unique `DEVICE_ID` and the correct `SITE_ID` in `edge.env`. Both Python
and Alloy load this file, avoiding identity/path mismatches. Keep `LOG_FILE`
absolute. It contains configuration only, not credentials.

The systemd unit creates `/var/log/edge`, owned by the service account.
Default log retention is five backups of approximately 10 MiB each plus the
active file, or about 60 MiB. Individual oversized records can exceed that
threshold. Do not configure logrotate on the same file or run multiple Python
processes against it. `LOG_LEVEL` controls verbosity; heartbeats still emit at
INFO when application verbosity is WARNING or higher.

Verify locally after about one minute:

```bash
sudo systemctl status edge --no-pager
sudo tail -n 10 /var/log/edge/app.log
sudo journalctl -u edge --since '2 minutes ago' --no-pager
```

Look for `"event":"heartbeat"`, your device/site, and a UTC timestamp.
The heartbeat reports process liveness, not successful sensor readings or HTTP
delivery. Modbus and sync failures have separate event fields.

## 2. Install Alloy and configure local collection

Install the packaged Alloy service using Grafana's official
[Linux installation instructions](https://grafana.com/docs/alloy/latest/set-up/install/linux/)
for Debian/Ubuntu. Use the package matching the Pi's OS architecture; check it
with `dpkg --print-architecture`. After installation, `alloy --version` should
work and the `alloy` system user/service should exist.

If Alloy already collects other applications, merge this configuration into
the existing one instead of replacing it. For a new installation:

```bash
sudo usermod -aG lightgroup,adm,systemd-journal alloy
sudo install -d -m 0755 /etc/alloy /etc/systemd/system/alloy.service.d
sudo install -m 0644 deploy/raspberry-pi/config.alloy /etc/alloy/config.alloy
sudo install -m 0644 deploy/raspberry-pi/alloy-override.conf /etc/systemd/system/alloy.service.d/edge.conf
sudo -u alloy test -r /var/log/edge/app.log
sudo -u alloy journalctl -u edge -n 1 --no-pager
sudo bash -c 'set -a; . /etc/edge/edge.env; set +a; runuser -u alloy --preserve-environment -- alloy validate /etc/alloy/config.alloy'
sudo systemctl daemon-reload
sudo systemctl enable alloy
sudo systemctl restart alloy
```

The validation command assumes shell-compatible assignments as in the provided
environment file. Stop and fix any validation/permission failure before starting
Alloy. The file is read by systemd as root; the Alloy user only needs access to
the log and journal. Keep the packaged service's persistent storage path
(normally `/var/lib/alloy`) so collection offsets survive restarts.

The temporary output uses
[`loki.echo`](https://grafana.com/docs/alloy/latest/reference/components/loki/loki.echo/),
which prints received records to Alloy stdout. This lets us prove collection
without configuring the server. It is not a queue for later remote delivery.

## 3. Check the complete local collection path

```bash
sudo systemctl status alloy --no-pager
sudo journalctl -u alloy --since '2 minutes ago' --no-pager
sudo journalctl -k --since '1 hour ago' --no-pager
```

Wait for the next application heartbeat and confirm it appears in the Alloy
journal with `job=edge-app` and your device/site labels. Kernel records use
`job=edge-kernel`; service records use `job=edge-service`. Kernel output may be
empty if there have been no matching USB or power events.

The collector reads only `edge.service`, its systemd lifecycle messages, and
selected kernel events. It does not collect its own journal, preventing a log
feedback loop. Application JSON duplicated in the edge journal is filtered
because its file copy is collected separately. If file logging fails, inspect
the edge journal directly for the error.

After confirming collection, stop the temporary echo collector until the
server connection is configured to avoid continuously duplicating logs:

```bash
sudo systemctl disable --now alloy
```

Python continues collecting measurements and writing rotating logs. Journald
retention is controlled by the host's existing policy; inspect disk use with
`journalctl --disk-usage`. We do not change retention for the whole host here.

## Next phase

Once the local checks pass, we will replace the echo output with an authenticated
`loki.write` endpoint, validate it, and enable Alloy again. Only the active file
is tailed; old rotations are not automatically replayed after Alloy downtime.
Remote delivery remains separate from SQLite measurement storage.

Hardware-independent logging tests can run on either the Pi or the development
machine:

```bash
venv/bin/python -m unittest discover -s tests -v
```

Native Alloy validation and the systemd checks must run on the Pi. The Python
tests do not validate Alloy syntax, hardware access, or Linux permissions.
