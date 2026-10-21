"""Four-level logger, the only place that decides what reaches the Domoticz log.

    0 Off      normal messages (Log) and errors only
    1 Basic    important diagnostic events
    2 Verbose  additional API and processing information
    3 Debug    detailed internal diagnostics (every request)

Debug lines are filtered here before they reach Domoticz. Every message passes ``_clean``, which replaces the
registered secrets (the Pi-hole password, the session id) by ``<masked>``: a secret can not reach the log by
accident, whatever a server or an exception puts into its text.
"""
from typing import Any, List

MASKED = "<masked>"
MIN_SECRET_LENGTH = 4

OFF, BASIC, VERBOSE, DEBUG = 0, 1, 2, 3
LEVEL_NAMES = {OFF: "Off", BASIC: "Basic", VERBOSE: "Verbose", DEBUG: "Debug"}


class Logger:
    def __init__(self, domoticz: Any, level: int = OFF) -> None:
        self.dz = domoticz
        self.level = OFF
        self._debugging = None
        self._secrets: List[str] = []
        self.set_level(level)

    # -- configuration --------------------------------------------------------------------------------------
    def set_level(self, level: int) -> None:
        try:
            self.level = max(OFF, min(DEBUG, int(level)))
        except (TypeError, ValueError):
            self.level = OFF
        enabled = self.level > OFF
        if self._debugging == enabled:
            return
        try:
            self.dz.Debugging(1 if enabled else 0)
            self._debugging = enabled
        except Exception as exc:                        # logging set-up must never prevent the plugin from starting
            self.dz.Error("Pi-hole Control: could not configure Domoticz debugging: %s" % exc)

    def add_secret(self, value: Any) -> None:
        text = "" if value is None else str(value)
        if len(text) >= MIN_SECRET_LENGTH and text not in self._secrets:
            self._secrets.append(text)

    def _clean(self, message: Any) -> str:
        text = str(message)
        for secret in self._secrets:
            if secret in text:
                text = text.replace(secret, MASKED)
        return text

    # -- output ---------------------------------------------------------------------------------------------
    def Basic(self, message: Any) -> None:
        if self.level >= BASIC:
            self.dz.Debug("[BASIC] %s" % self._clean(message))

    def Verbose(self, message: Any) -> None:
        if self.level >= VERBOSE:
            self.dz.Debug("[VERBOSE] %s" % self._clean(message))

    def Debug(self, message: Any) -> None:
        if self.level >= DEBUG:
            self.dz.Debug("[DEBUG] %s" % self._clean(message))

    def Log(self, message: Any) -> None:
        self.dz.Log(self._clean(message))

    def Error(self, message: Any) -> None:
        self.dz.Error(self._clean(message))
