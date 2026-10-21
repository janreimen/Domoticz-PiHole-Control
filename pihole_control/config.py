"""Plugin settings, parsed and validated from the Domoticz ``Parameters`` dict.

Hardware-page fields (see the manifest in plugin.py):

    Address   Pi-hole URL, e.g. http://192.168.1.2 or https://pi.hole
    Password  Pi-hole web interface password or app password (never trimmed, never logged)
    Mode1     poll interval in seconds
    Mode2     certificate chain file (PEM) for HTTPS with a private CA; empty = system trust store
    Mode6     debug level: 0 Off | 1 Basic | 2 Verbose | 3 Debug
              (the values "Normal" and "Debug" of the pre-0.1.0 plugin are still understood)
"""
import os
from typing import Any, List, Mapping
from urllib.parse import urlsplit

from .constants import DEFAULT_INTERVAL, MAX_INTERVAL, MIN_INTERVAL, API_TIMEOUT
from .util import clamp, safe_int

_LEGACY_DEBUG = {"normal": 0, "false": 0, "off": 0, "true": 3, "debug": 3}
_STRIP_SUFFIXES = ("/admin", "/api")


class SettingsError(ValueError):
    """Raised for an invalid hardware configuration."""


class Settings:
    def __init__(self, base_url: str, password: str, interval: int = DEFAULT_INTERVAL, ca_file: str = "",
                 debug: int = 0, timeout: int = API_TIMEOUT, notes: List[str] = None) -> None:
        self.base_url = base_url
        self.password = password
        self.interval = interval
        self.ca_file = ca_file
        self.debug = debug
        self.timeout = timeout
        self.notes = list(notes or [])         # things worth a log line at start-up (corrections made, ignored fields)

    @property
    def https(self) -> bool:
        return self.base_url.lower().startswith("https://")

    @classmethod
    def from_parameters(cls, params: Mapping[str, Any]) -> "Settings":
        def get(name: str, default: str = "") -> str:
            value = params.get(name, default)
            return default if value is None else str(value)

        notes: List[str] = []
        base_url = normalise_url(get("Address"), notes)

        password = get("Password")              # an opaque credential: no trimming
        if not password:
            raise SettingsError("No Pi-hole password configured (use the web interface password or an app password)")

        interval_text = get("Mode1").strip()
        interval = DEFAULT_INTERVAL
        if interval_text:
            number = safe_int(interval_text)
            if number is None:
                raise SettingsError("Update interval must be a number of seconds, got %r" % interval_text)
            interval = clamp(number, MIN_INTERVAL, MAX_INTERVAL)
            if interval != number:
                notes.append("Update interval %d s is outside %d-%d s, using %d s"
                             % (number, MIN_INTERVAL, MAX_INTERVAL, interval))

        ca_file = get("Mode2").strip()
        if ca_file:
            if not base_url.lower().startswith("https://"):
                notes.append("Certificate chain path is ignored: the Pi-hole URL is not https")
                ca_file = ""
            else:
                ca_file = os.path.expanduser(ca_file)
                if not os.path.isfile(ca_file):
                    raise SettingsError("Certificate chain file not found: %s" % ca_file)
                if not os.access(ca_file, os.R_OK):
                    raise SettingsError("Certificate chain file is not readable for Domoticz: %s" % ca_file)

        return cls(base_url, password, interval, ca_file, parse_debug(get("Mode6")), notes=notes)


def parse_debug(text: str) -> int:
    text = str(text).strip().lower()
    if text in _LEGACY_DEBUG:
        return _LEGACY_DEBUG[text]
    return clamp(safe_int(text, 0) or 0, 0, 3)


def normalise_url(text: str, notes: List[str]) -> str:
    """Return scheme://host[:port][/prefix] without a trailing slash, /admin or /api; raise SettingsError."""
    text = text.strip()
    if not text:
        raise SettingsError("No Pi-hole URL configured")
    if "://" not in text:
        text = "http://" + text
        notes.append("The Pi-hole URL has no scheme, assuming http://")
    try:
        parts = urlsplit(text)
        parts.port                                      # raises ValueError for an invalid port
    except ValueError as exc:
        raise SettingsError("Invalid Pi-hole URL: %s" % exc)
    if parts.scheme.lower() not in ("http", "https"):
        raise SettingsError("The Pi-hole URL must start with http:// or https://")
    if not parts.hostname:
        raise SettingsError("The Pi-hole URL has no host name")
    if parts.username is not None or parts.password is not None:
        raise SettingsError("The Pi-hole URL must not contain credentials; use the password field")
    if parts.query or parts.fragment:
        raise SettingsError("The Pi-hole URL must not contain a query or fragment")
    path = parts.path.rstrip("/")
    for suffix in _STRIP_SUFFIXES:
        if path.lower().endswith(suffix):
            path = path[: -len(suffix)]
            notes.append("Removed '%s' from the Pi-hole URL (the plugin adds /api itself)" % suffix)
    return "%s://%s%s" % (parts.scheme.lower(), parts.netloc, path)
