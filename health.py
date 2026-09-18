"""Worker progress independent of database and serial locks."""

import os
import socket
import time
from functools import wraps


class WorkerHealth:
    def __init__(self):
        self.progress_at = time.monotonic()

    def progress(self):
        self.progress_at = time.monotonic()

    def stalled(self, now, timeout):
        return now - self.progress_at > timeout


def monitored_cycle(method):
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        self.health.progress()
        try:
            return method(self, *args, **kwargs)
        finally:
            self.health.progress()
    return wrapped


def notify_systemd(message):
    address = os.environ.get("NOTIFY_SOCKET")
    if not address:
        return
    if address.startswith("@"):
        address = "\0" + address[1:]
    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
        sock.settimeout(1)
        sock.connect(address)
        sock.sendall(message.encode("utf-8"))


def watchdog_interval():
    pid = os.environ.get("WATCHDOG_PID")
    if pid and int(pid) != os.getpid():
        return None
    usec = int(os.environ.get("WATCHDOG_USEC", "0"))
    return usec / 2_000_000 if usec > 0 else None
