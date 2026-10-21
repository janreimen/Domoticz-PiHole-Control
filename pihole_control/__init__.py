"""Domoticz-PiHole-Control: monitor a Pi-hole v6 and switch its block lists and groups from Domoticz.

Package layout (each module has exactly one job):

    config.py       plugin settings (parsed and validated from the Domoticz ``Parameters``)
    constants.py    device model (unit numbers, types), defaults, timings
    logger.py       four-level logger; the only place that decides what reaches the Domoticz log
    util.py         small helpers
    model.py        plain data objects handed between the layers (Stats, BlockList, Group)
    api.py          Pi-hole v6 REST client (standard library only, no Domoticz)
    devices.py      the ONLY module that talks to the Domoticz device API
    controller.py   poll scheduling, error policy, command handling (no Domoticz import)

``plugin.py`` is thin glue and the only module that imports ``Domoticz``.
"""

__version__ = "0.1.0"
