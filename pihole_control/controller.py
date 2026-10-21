"""Poll scheduling, error policy and command handling. Knows neither Domoticz nor HTTP details.

Error policy:

    * every problem is logged ONCE as an error, repeats go to the verbose log, and recovery is logged once
    * after a failed poll the next attempt waits longer (backoff, capped); a rejected login, a TLS problem or a
      redirect (all need a change of settings, not patience) wait much longer, so a wrong password is not
      hammered into the Pi-hole's login rate limit
    * the "Pi-hole Status" switch follows the connection: On while polls succeed, Off while they fail
    * a failing list / group request does not mark the Pi-hole as offline, statistics keep flowing

Commands are never reported as done because a request was sent: the state is read back from the Pi-hole.
"""
import time
from typing import Any, Callable, Dict, Optional

from .api import AUTH, REDIRECT, TLS, PiHoleError
from .constants import (
    KIND_STATUS, LOGOUT_TIMEOUT, MAX_AUTH_BACKOFF, MAX_BACKOFF, MIN_AUTH_BACKOFF,
)


class Controller:
    def __init__(self, settings: Any, client: Any, devices: Any, logger: Any,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.settings = settings
        self.client = client
        self.devices = devices
        self.log = logger
        self.clock = clock
        self.next_poll_at = 0.0
        self.failures = 0
        self.connected = False
        self.group_names: Dict[int, str] = {}
        self._problems: Dict[str, str] = {}      # problem key -> kind of the last one logged

    # -- life cycle -----------------------------------------------------------------------------------------
    def start(self) -> None:
        self.devices.ensure_stat_devices()
        self.devices.load_mappings()
        self.poll()

    def stop(self) -> None:
        self.client.logout(timeout=LOGOUT_TIMEOUT)

    def on_heartbeat(self) -> None:
        if self.clock() >= self.next_poll_at:
            self.poll()

    # -- polling --------------------------------------------------------------------------------------------
    def poll(self) -> bool:
        """One poll: statistics, groups, lists. True when everything could be read."""
        now = self.clock()
        self.next_poll_at = now + self.settings.interval        # an unexpected exception must not cause a retry storm
        self.log.Basic("Polling the Pi-hole")
        try:
            stats = self.client.get_stats()
        except PiHoleError as exc:
            self._poll_failed(exc, now)
            return False
        self.failures = 0
        if not self.connected:
            self.connected = True
            self.log.Log("Connected to the Pi-hole at %s" % self.settings.base_url)
        self._recovered("pihole", "The Pi-hole answers again")
        self.devices.update_stats(stats)
        self.devices.set_status(True)

        complete = True
        groups = self._fetch("groups", self.client.get_groups)
        if groups is not None:
            self.group_names = {item.id: item.name for item in groups}
            self.devices.sync_groups(groups)
        else:
            complete = False
        lists = self._fetch("lists", self.client.get_lists)
        if lists is not None:
            self.devices.sync_lists(lists, self.group_names)
        else:
            complete = False
        return complete

    def _fetch(self, what: str, fetch: Callable[[], Any]) -> Optional[Any]:
        try:
            result = fetch()
        except PiHoleError as exc:
            self._report(what, "Could not read the %s from the Pi-hole: %s" % (what, exc), exc.kind)
            return None
        self._recovered(what, "The %s can be read from the Pi-hole again" % what)
        return result

    def _poll_failed(self, exc: PiHoleError, now: float) -> None:
        self.failures += 1
        self.connected = False
        self.devices.set_status(False)
        self._report("pihole", "Pi-hole poll failed: %s" % exc, exc.kind)
        interval = self.settings.interval
        if exc.kind in (AUTH, TLS, REDIRECT):
            delay = min(max(interval, MIN_AUTH_BACKOFF) * 2 ** min(self.failures - 1, 4), MAX_AUTH_BACKOFF)
        else:
            delay = max(interval, min(interval * 2 ** min(self.failures - 1, 6), MAX_BACKOFF))
        self.next_poll_at = now + delay
        self.log.Basic("Failure %d, next attempt in %d s" % (self.failures, delay))

    def _report(self, key: str, message: str, kind: str) -> None:
        if self._problems.get(key) == kind:
            self.log.Verbose(message)                           # same problem as before: not an error again
            return
        self._problems[key] = kind
        self.log.Error(message)

    def _recovered(self, key: str, message: str) -> None:
        if self._problems.pop(key, None) is not None:
            self.log.Log(message)

    # -- commands -------------------------------------------------------------------------------------------
    def on_command(self, unit: int, command: Any) -> None:
        kind, item_id = self.devices.resolve(unit)
        name = self.devices.name_of(unit)
        action = str(command).strip().lower()
        self.log.Log("Command received: unit %d (%s) %s" % (unit, name or "unknown", command))

        if kind == KIND_STATUS:
            self.log.Log("'Pi-hole Status' only shows whether the Pi-hole answers; it cannot be switched")
            self.devices.restore(unit)
            return
        if kind is None:
            self.log.Log("Unit %d is not a Pi-hole list or group, the command is ignored" % unit)
            self.devices.restore(unit)
            return
        if action not in ("on", "off"):
            self.log.Error("Unsupported command '%s' for %s %d (%s): only On and Off are understood"
                           % (command, kind, item_id, name))
            self.devices.restore(unit)
            return

        enabled = action == "on"
        verb = "enable" if enabled else "disable"
        try:
            self._send(kind, item_id, enabled)
        except PiHoleError as exc:
            self.log.Error("Could not %s %s %d (%s): %s" % (verb, kind, item_id, name, exc))
            self.devices.restore(unit)
            return

        self.devices.set_switch(unit, enabled)
        if not self.poll():
            self.log.Log("Asked the Pi-hole to %s %s %d (%s); the new state could not be read back yet"
                         % (verb, kind, item_id, name))
        elif self.devices.state_of(unit) == enabled:
            self.log.Log("%s %d (%s) is now %s" % (kind.capitalize(), item_id, name, "enabled" if enabled else "disabled"))
        else:
            self.log.Error("The Pi-hole accepted the request but still reports %s %d (%s) as %s"
                           % (kind, item_id, name, "disabled" if enabled else "enabled"))

    def _send(self, kind: str, item_id: int, enabled: bool) -> None:
        """Fetch the item fresh (the PUT must carry its current comment and groups) and change it."""
        if kind == "list":
            lst = next((i for i in self.client.get_lists() if i.id == item_id), None)
            if lst is None:
                raise PiHoleError("the Pi-hole has no list %d any more" % item_id)
            self.client.set_list_enabled(lst, enabled)
        else:
            grp = next((i for i in self.client.get_groups() if i.id == item_id), None)
            if grp is None:
                raise PiHoleError("the Pi-hole has no group %d any more" % item_id)
            self.client.set_group_enabled(grp, enabled)
