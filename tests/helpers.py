import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [ROOT, os.path.join(ROOT, "tests"), os.path.join(ROOT, "tools")]

import domoticz_stub as dz  # noqa: E402
from fake_pihole import FakePiHole  # noqa: E402,F401  (re-exported for the test modules)
from pihole_control.api import PiHoleClient  # noqa: E402
from pihole_control.config import Settings  # noqa: E402
from pihole_control.controller import Controller  # noqa: E402
from pihole_control.devices import DeviceManager  # noqa: E402
from pihole_control.logger import Logger  # noqa: E402


class Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds


def make_logger(level=0):
    return Logger(dz, level)


def make_stack(pihole, interval=60, level=0, password=None, clock=None, **settings_kw):
    """Client + device manager + controller against a fake Pi-hole, with a controllable clock."""
    dz.reset()
    clock = clock or Clock()
    log = make_logger(level)
    password = pihole.password if password is None else password
    log.add_secret(password)
    settings = Settings(pihole.url, password, interval=interval, **settings_kw)
    client = PiHoleClient(pihole.url, password, log, timeout=3, clock=clock)
    devices = DeviceManager(dz, lambda: dz.Devices, log, clock=clock)
    controller = Controller(settings, client, devices, log, clock=clock)
    return controller, client, devices, clock


def by_name(prefix):
    return [d for d in dz.Devices.values() if d.Name.startswith(prefix)]
