"""The device model and the timings of the plugin.

The unit numbers below are the ones of the pre-0.1.0 plugin and must never change: they keep existing devices
(and their history, scenes, scripts and schedules) intact when upgrading.
"""
from typing import NamedTuple

from . import __version__

PLUGIN_KEY = "PiHole"                     # unchanged since the first version: Domoticz stores hardware by key
PLUGIN_NAME = "Pi-hole Monitor and Control - https Version"
PLUGIN_URL = "https://github.com/janreimen/Domoticz-PiHole-Control"
USER_AGENT = "Domoticz-PiHole-Control/%s" % __version__

# -- timings ------------------------------------------------------------------------------------------------
HEARTBEAT_SECONDS = 10        # Domoticz caps the heartbeat at 30 s; polling is scheduled by time, not by count
DEFAULT_INTERVAL = 60         # seconds between polls
MIN_INTERVAL = 10
MAX_INTERVAL = 3600
API_TIMEOUT = 10              # seconds per HTTP request
LOGOUT_TIMEOUT = 3            # the logout at shutdown must never hold Domoticz up
MAX_BACKOFF = 300             # longest wait between polls after failures
MAX_AUTH_BACKOFF = 900        # longest wait after a rejected login (do not hammer a wrong password)
MIN_AUTH_BACKOFF = 300
SESSION_RENEW_MARGIN = 30     # log in again this many seconds before the Pi-hole session expires
DEFAULT_SESSION_VALIDITY = 300
REMOVE_AFTER_MISSES = 3       # a list / group must be gone for this many polls in a row before its device is deleted
REFRESH_SECONDS = 300         # rewrite an unchanged sensor value this often, so Domoticz' sensor time-out never fires
CREATE_RETRY_SECONDS = 300    # after Domoticz refused to create a device, ask again no sooner than this

# -- device kinds -------------------------------------------------------------------------------------------
KIND_COUNT = "count"          # Custom Sensor with a unit label
KIND_PERCENT = "percentage"   # Percentage
KIND_STATUS = "status"        # On/Off switch that mirrors the connection to Pi-hole (read-only)

# Domoticz TypeName of each kind. TypeName is the documented way to create a device; raw Type / Subtype numbers are
# only for types TypeName does not offer. These are the TypeNames the pre-0.1.0 plugin used.
TYPENAME_COUNT = "Custom"
TYPENAME_PERCENT = "Percentage"
TYPENAME_SWITCH = "Switch"
SWITCHTYPE_ONOFF = 0
SUBTYPE_CUSTOM = 31           # what Domoticz makes of TypeName "Custom" (sTypeCustom, 0x1F in hardwaretypes.h)


class StatDevice(NamedTuple):
    unit: int
    key: str
    name: str
    kind: str
    label: str                # unit label of a Custom Sensor ("" for the others)


UNIT_DNS_QUERIES = 1
UNIT_ADS_BLOCKED = 2
UNIT_ADS_PERCENTAGE = 3
UNIT_DOMAINS_BLOCKED = 4
UNIT_QUERIES_FORWARDED = 5
UNIT_QUERIES_CACHED = 6
UNIT_CLIENTS_EVER = 7
UNIT_UNIQUE_CLIENTS = 8
UNIT_UNIQUE_DOMAINS = 9
UNIT_STATUS = 10

STAT_DEVICES = (
    StatDevice(UNIT_DNS_QUERIES, "dns_queries", "DNS Queries Today", KIND_COUNT, "queries"),
    StatDevice(UNIT_ADS_BLOCKED, "ads_blocked", "Ads Blocked Today", KIND_COUNT, "blocked"),
    StatDevice(UNIT_ADS_PERCENTAGE, "ads_percentage", "Ads Percentage", KIND_PERCENT, ""),
    StatDevice(UNIT_DOMAINS_BLOCKED, "domains_blocked", "Domains in Blocklist", KIND_COUNT, "domains"),
    StatDevice(UNIT_QUERIES_FORWARDED, "queries_forwarded", "Queries Forwarded", KIND_COUNT, "queries"),
    StatDevice(UNIT_QUERIES_CACHED, "queries_cached", "Queries Cached", KIND_COUNT, "queries"),
    StatDevice(UNIT_CLIENTS_EVER, "clients_ever", "Clients Ever Seen", KIND_COUNT, "clients"),
    StatDevice(UNIT_UNIQUE_CLIENTS, "unique_clients", "Unique Clients", KIND_COUNT, "clients"),
    StatDevice(UNIT_UNIQUE_DOMAINS, "unique_domains", "Unique Domains", KIND_COUNT, "domains"),
    StatDevice(UNIT_STATUS, "status", "Pi-hole Status", KIND_STATUS, ""),
)

# Block lists and groups become switches in their own unit ranges. The Pi-hole id is kept in the device
# description ("ListID:12"), so a device finds its list again whatever the order or the unit.
LIST_UNIT_FIRST = 100
LIST_UNIT_LAST = 199
GROUP_UNIT_FIRST = 200
GROUP_UNIT_LAST = 255         # Domoticz allows units 1..255 per hardware
LIST_PREFIX = "ListID:"
GROUP_PREFIX = "GroupID:"
LIST_NAME_PREFIX = "List: "
GROUP_NAME_PREFIX = "Group: "
MAX_NAME_LENGTH = 100
