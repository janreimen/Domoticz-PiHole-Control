"""The only module that talks to the Domoticz device API.

It is handed the ``Domoticz`` module and a callable returning the current ``Devices`` dict (Domoticz replaces
that dict before every callback, so it is never kept), and turns Pi-hole data into devices:

    * 10 fixed statistics devices (units 1-10), created when missing
    * one switch per Pi-hole list (units 100-199) and per group (units 200-255); the Pi-hole id sits in the
      device description ("ListID:12" / "GroupID:3"), so a device finds its list again after a restart
    * new lists / groups get a device; a device is deleted only after its list / group has been gone for
      REMOVE_AFTER_MISSES polls in a row (a glitch in one answer must not destroy a device and its history)
    * a device is renamed when its name changes *in the Pi-hole*; a name you chose in Domoticz is never
      overwritten at start-up
    * values are written when they change, sensors also every REFRESH_SECONDS so the "last seen" time stays fresh
"""
import re
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from .constants import (
    GROUP_NAME_PREFIX, GROUP_PREFIX, GROUP_UNIT_FIRST, GROUP_UNIT_LAST, KIND_COUNT, KIND_PERCENT, KIND_STATUS,
    LIST_NAME_PREFIX, LIST_PREFIX, LIST_UNIT_FIRST, LIST_UNIT_LAST, MAX_NAME_LENGTH, REFRESH_SECONDS,
    REMOVE_AFTER_MISSES, STAT_DEVICES, SWITCHTYPE_ONOFF, TYPENAME_COUNT, TYPENAME_PERCENT, TYPENAME_SWITCH,
    UNIT_STATUS, StatDevice,
)
from .model import BlockList, Group, Stats
from .util import shorten

# statistics device key -> field of Stats
STAT_FIELDS = {
    "dns_queries": "total_queries",
    "ads_blocked": "blocked_queries",
    "ads_percentage": "percent_blocked",
    "domains_blocked": "domains_blocked",
    "queries_forwarded": "forwarded",
    "queries_cached": "cached",
    "clients_ever": "clients_total",
    "unique_clients": "clients_active",
    "unique_domains": "unique_domains",
}


class _Mapping:
    """Pi-hole item (list or group) id -> Domoticz unit, for one kind of switch."""

    def __init__(self, kind: str, prefix: str, first: int, last: int) -> None:
        self.kind = kind
        self.prefix = prefix
        self.first = first
        self.last = last
        self.units: Dict[int, int] = {}
        self.names: Dict[int, str] = {}         # last name derived from the Pi-hole
        self.missing: Dict[int, int] = {}       # polls in a row the item was absent
        self.warned_full = False

    def id_of(self, description: str) -> Optional[int]:
        match = re.match(r"^%s(\d+)" % re.escape(self.prefix), description or "")
        return int(match.group(1)) if match else None


def list_device_name(item: BlockList, group_names: Dict[int, str]) -> str:
    label = item.comment.strip() or item.address.strip() or "Unnamed List"
    if item.groups:
        label += " (%s)" % ", ".join(group_names.get(g, "Group %d" % g) for g in item.groups)
    return shorten(LIST_NAME_PREFIX + label, MAX_NAME_LENGTH)


def group_device_name(item: Group) -> str:
    return shorten(GROUP_NAME_PREFIX + (item.name.strip() or "Unnamed Group"), MAX_NAME_LENGTH)


class DeviceManager:
    def __init__(self, domoticz: Any, get_devices: Callable[[], Dict[int, Any]], logger: Any,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.dz = domoticz
        self.get_devices = get_devices
        self.log = logger
        self.clock = clock
        self.lists = _Mapping("list", LIST_PREFIX, LIST_UNIT_FIRST, LIST_UNIT_LAST)
        self.groups = _Mapping("group", GROUP_PREFIX, GROUP_UNIT_FIRST, GROUP_UNIT_LAST)
        self._written: Dict[int, float] = {}    # unit -> time of the last write (sensors)
        self._warned: set = set()               # problems reported once

    # -- start-up -------------------------------------------------------------------------------------------
    def ensure_stat_devices(self) -> None:
        for spec in STAT_DEVICES:
            if spec.unit in self.get_devices():
                continue
            self.dz.Device(**self._stat_kwargs(spec)).Create()
            if spec.unit not in self.get_devices():
                self.log.Error("Could not create device '%s' (unit %d)" % (spec.name, spec.unit))
            else:
                self.log.Basic("Created device '%s' (unit %d)" % (spec.name, spec.unit))

    @staticmethod
    def _stat_kwargs(spec: StatDevice) -> Dict[str, Any]:
        kwargs: Dict[str, Any] = dict(Name=spec.name, Unit=spec.unit, Used=1)
        if spec.kind == KIND_COUNT:
            kwargs.update(TypeName=TYPENAME_COUNT, Options={"Custom": "1;%s" % spec.label})
        elif spec.kind == KIND_PERCENT:
            kwargs.update(TypeName=TYPENAME_PERCENT)
        else:
            kwargs.update(TypeName=TYPENAME_SWITCH, Switchtype=SWITCHTYPE_ONOFF)
        return kwargs

    def load_mappings(self) -> None:
        """Learn which list / group devices already exist (after a Domoticz restart) from their descriptions."""
        for mapping in (self.lists, self.groups):
            mapping.units.clear()
        for unit, device in sorted(self.get_devices().items()):
            for mapping in (self.lists, self.groups):
                if mapping.first <= unit <= mapping.last:
                    item_id = mapping.id_of(getattr(device, "Description", ""))
                    if item_id is not None:
                        mapping.units[item_id] = unit
                        self.log.Debug("Found %s %d -> unit %d" % (mapping.kind, item_id, unit))

    # -- statistics -----------------------------------------------------------------------------------------
    def update_stats(self, stats: Stats) -> None:
        now = self.clock()
        for spec in STAT_DEVICES:
            field = STAT_FIELDS.get(spec.key)
            value = getattr(stats, field) if field else None
            if value is None:
                continue
            text = "%.2f" % value if spec.kind == KIND_PERCENT else str(int(value))
            self._write(spec.unit, 0, text, now=now)

    def set_status(self, online: bool) -> None:
        self._set_switch(UNIT_STATUS, online)

    # -- lists and groups -----------------------------------------------------------------------------------
    def sync_lists(self, lists: List[BlockList], group_names: Dict[int, str]) -> None:
        self._sync(self.lists, {item.id: (list_device_name(item, group_names), item.enabled) for item in lists})

    def sync_groups(self, groups: List[Group]) -> None:
        self._sync(self.groups, {item.id: (group_device_name(item), item.enabled) for item in groups})

    def _sync(self, mapping: _Mapping, items: Dict[int, Tuple[str, bool]]) -> None:
        devices = self.get_devices()
        for item_id in sorted(mapping.units):                    # 1. items that disappeared from the Pi-hole
            if item_id in items:
                mapping.missing.pop(item_id, None)
                continue
            misses = mapping.missing.get(item_id, 0) + 1
            if misses < REMOVE_AFTER_MISSES:
                mapping.missing[item_id] = misses
                self.log.Verbose("%s %d is not reported by the Pi-hole (%d of %d)"
                                 % (mapping.kind.capitalize(), item_id, misses, REMOVE_AFTER_MISSES))
                continue
            unit = mapping.units.pop(item_id)
            mapping.names.pop(item_id, None)
            mapping.missing.pop(item_id, None)
            device = devices.get(unit)
            if device is not None:
                self.log.Log("Removing the device of the deleted %s %d: %s (unit %d)"
                             % (mapping.kind, item_id, device.Name, unit))
                device.Delete()
        for item_id in sorted(items):                            # 2. new items, renames, states
            name, enabled = items[item_id]
            unit = mapping.units.get(item_id)
            if unit is not None and unit not in self.get_devices():
                self.log.Log("The device of %s %d (unit %d) was deleted in Domoticz, creating it again"
                             % (mapping.kind, item_id, unit))
                del mapping.units[item_id]
                mapping.names.pop(item_id, None)
                unit = None
            if unit is None:
                unit = self._create_switch(mapping, item_id, name)
                if unit is None:
                    continue
            else:
                self._rename_if_changed(mapping, item_id, unit, name)
            self._set_switch(unit, enabled)

    def _free_unit(self, mapping: _Mapping) -> Optional[int]:
        taken = set(self.get_devices()) | set(mapping.units.values())
        for unit in range(mapping.first, mapping.last + 1):
            if unit not in taken:
                return unit
        return None

    def _create_switch(self, mapping: _Mapping, item_id: int, name: str) -> Optional[int]:
        unit = self._free_unit(mapping)
        if unit is None:
            if not mapping.warned_full:
                mapping.warned_full = True
                self.log.Error("No free Domoticz unit left for more %ss (units %d-%d are in use): "
                               "delete devices you do not need" % (mapping.kind, mapping.first, mapping.last))
            return None
        self.dz.Device(Name=name, Unit=unit, TypeName=TYPENAME_SWITCH, Switchtype=SWITCHTYPE_ONOFF,
                       Description="%s%d" % (mapping.prefix, item_id), Used=1).Create()
        if unit not in self.get_devices():
            self.log.Error("Could not create the device of %s %d (unit %d)" % (mapping.kind, item_id, unit))
            return None
        mapping.units[item_id] = unit
        mapping.names[item_id] = name
        self.log.Log("Created device for %s %d: %s (unit %d)" % (mapping.kind, item_id, name, unit))
        return unit

    def _rename_if_changed(self, mapping: _Mapping, item_id: int, unit: int, name: str) -> None:
        known = mapping.names.get(item_id)
        if known is None:
            mapping.names[item_id] = name        # first sight since start: adopt, never overwrite a name you chose
            return
        if known == name:
            return
        device = self.get_devices().get(unit)
        try:
            device.Update(nValue=device.nValue, sValue=device.sValue, Name=name)
        except Exception as exc:                  # renaming is a convenience: never let it break the sync
            if "rename" not in self._warned:
                self._warned.add("rename")
                self.log.Error("Could not rename the device '%s' to '%s': %s. It keeps its old name; "
                               "this is reported once" % (known, name, exc))
            mapping.names[item_id] = name
            return
        mapping.names[item_id] = name
        self.log.Log("The Pi-hole renamed %s %d: device is now '%s' (unit %d)" % (mapping.kind, item_id, name, unit))

    # -- commands -------------------------------------------------------------------------------------------
    def resolve(self, unit: int) -> Tuple[Optional[str], Optional[int]]:
        """Which Pi-hole item a unit belongs to: ("list", id), ("group", id), ("status", None) or (None, None)."""
        if unit == UNIT_STATUS:
            return KIND_STATUS, None
        for mapping in (self.lists, self.groups):
            for item_id, mapped in mapping.units.items():
                if mapped == unit:
                    return mapping.kind, item_id
        return None, None

    def state_of(self, unit: int) -> Optional[bool]:
        device = self.get_devices().get(unit)
        return None if device is None else bool(device.nValue)

    def set_switch(self, unit: int, enabled: bool) -> None:
        self._set_switch(unit, enabled)

    def restore(self, unit: int) -> None:
        """Put a device back to its real value after a command that was not carried out."""
        device = self.get_devices().get(unit)
        if device is not None:
            device.Update(nValue=device.nValue, sValue=device.sValue, SuppressTriggers=True)

    def name_of(self, unit: int) -> str:
        device = self.get_devices().get(unit)
        return "" if device is None else str(device.Name)

    # -- writing --------------------------------------------------------------------------------------------
    def _set_switch(self, unit: int, enabled: bool) -> None:
        self._write(unit, 1 if enabled else 0, "On" if enabled else "Off")

    def _write(self, unit: int, nvalue: int, svalue: str, now: Optional[float] = None) -> None:
        device = self.get_devices().get(unit)
        if device is None:
            if ("missing", unit) not in self._warned:
                self._warned.add(("missing", unit))
                self.log.Error("Cannot update Domoticz unit %d: no such device. It was deleted or never created; "
                               "restarting the hardware creates the statistics devices again" % unit)
            return
        self._warned.discard(("missing", unit))
        changed = device.nValue != nvalue or device.sValue != svalue
        stale = now is not None and now - self._written.get(unit, 0.0) >= REFRESH_SECONDS
        if not (changed or stale):
            return
        device.Update(nValue=nvalue, sValue=svalue)
        if now is not None:
            self._written[unit] = now
        if changed:
            self.log.Debug("Update unit %d: %d '%s'" % (unit, nvalue, svalue))
