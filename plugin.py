"""
<plugin key="PiHole" name="Pi-hole Monitor and Control - https Version" author="Wojtek Sawasciuk, Jan Reimen" version="0.1.1" wikilink="https://github.com/janreimen/Domoticz-PiHole-Control" externallink="https://pi-hole.net/">
    <description>
        <h2>Pi-hole Monitor and Control</h2><br/>
        Monitors a <b>Pi-hole v6</b> and switches its block lists and groups from Domoticz, for example for
        parental-control schedules. Works over http and over https, also with a private certificate authority.<br/><br/>
        <h3>Features</h3>
        <ul style="list-style-type:square">
            <li>Statistics: DNS queries, blocked queries, percentage blocked, domains on the blocklists, forwarded and
                cached queries, clients and unique domains</li>
            <li>One switch per block list and per group; lists and groups you add or delete in the Pi-hole appear
                and disappear in Domoticz</li>
            <li>"Pi-hole Status" shows whether the Pi-hole answers</li>
            <li>No Python packages needed (standard library only)</li>
        </ul>
        <h3>Configuration</h3>
        Enter the Pi-hole URL (for example <tt>http://192.168.1.2</tt> or <tt>https://pi.hole</tt>) and the web
        interface password. Better: create an <b>app password</b> in the Pi-hole (Settings &gt; Web interface / API,
        expert mode) and use that; it also works when two-factor authentication is on.<br/>
        For https with a private CA, enter the path of a PEM file with the root and sub CA certificates. Certificates
        are always verified.<br/><br/>
        <h3>Documentation</h3>
        <a href="https://github.com/janreimen/Domoticz-PiHole-Control">https://github.com/janreimen/Domoticz-PiHole-Control</a><br/>
        Idea: abandoned plugin by Xorfor (<a href="https://forum.domoticz.com/viewtopic.php?t=20834">forum</a>),
        continued by Wojtek Sawasciuk (Voyo).
    </description>
    <params>
        <param field="Address" label="Pi-hole URL" width="300px" required="true" default="http://pi.hole"/>
        <param field="Password" label="Web Interface / App Password" width="300px" required="true" password="true" default=""/>
        <param field="Mode1" label="Update Interval (seconds)" width="75px" required="true" default="60"/>
        <param field="Mode2" label="Certificate Chain Path (https, private CA)" width="300px" required="false" default=""/>
        <param field="Mode6" label="Debug" width="120px">
            <options>
                <option label="Off" value="0" default="true"/>
                <option label="Basic" value="1"/>
                <option label="Verbose" value="2"/>
                <option label="Debug" value="3"/>
            </options>
        </param>
    </params>
</plugin>
"""
import os
import sys
import traceback

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import Domoticz  # noqa: E402  (provided by Domoticz)

# Domoticz injects the globals Parameters, Devices, Images and Settings into this module (and replaces them before
# every callback). Never bind one of those names here: the injected dict would silently shadow it (this once broke
# the Synology plugin). The modules are imported under other names.
from pihole_control import __version__  # noqa: E402
from pihole_control import config as ph_config  # noqa: E402
from pihole_control.api import PiHoleClient, PiHoleError, build_ssl_context  # noqa: E402
from pihole_control.constants import HEARTBEAT_SECONDS  # noqa: E402
from pihole_control.controller import Controller  # noqa: E402
from pihole_control.devices import DeviceManager  # noqa: E402
from pihole_control.logger import LEVEL_NAMES, Logger  # noqa: E402


class BasePlugin:
    def __init__(self):
        self.controller = None          # stays None until onStart completed: every other callback then does nothing
        self.log = Logger(Domoticz)

    # -- Domoticz callbacks ------------------------------------------------------------------------------
    def onStart(self):
        self.controller = None
        self.log = log = Logger(Domoticz)
        try:
            settings = ph_config.Settings.from_parameters(Parameters)
        except ph_config.SettingsError as exc:
            log.Error("Configuration error: %s" % exc)
            return
        log.set_level(settings.debug)
        log.add_secret(settings.password)
        log.Log("Pi-hole Control %s starting for %s (update every %d s, debug level %d: %s)" % (
            __version__, settings.base_url, settings.interval, settings.debug, LEVEL_NAMES[settings.debug]))
        for note in settings.notes:
            log.Log(note)

        try:
            ssl_context = build_ssl_context(settings.ca_file) if settings.ca_file else None
        except PiHoleError as exc:
            log.Error(str(exc))
            return
        if ssl_context is not None:
            log.Log("Trusting the certificates in %s" % settings.ca_file)

        client = PiHoleClient(settings.base_url, settings.password, log, ssl_context, settings.timeout)
        devices = DeviceManager(Domoticz, lambda: Devices, log, hardware_name=Parameters.get("Name", ""))
        controller = Controller(settings, client, devices, log)
        Domoticz.Heartbeat(HEARTBEAT_SECONDS)
        try:
            controller.start()
        except Exception as exc:
            self._unexpected("start-up", exc)
            return
        self.controller = controller

    def onStop(self):
        if self.controller is not None:
            try:
                self.controller.stop()
            except Exception as exc:
                self._unexpected("shutdown", exc)
            self.controller = None
        self.log.Log("Pi-hole Control stopped")

    def onHeartbeat(self):
        if self.controller is None:
            return
        try:
            self.controller.on_heartbeat()
        except Exception as exc:
            self._unexpected("heartbeat", exc)

    def onCommand(self, Unit, Command, Level, Hue):
        if self.controller is None:
            self.log.Error("Command for unit %s ignored: the plugin did not start, see the errors above" % Unit)
            return
        try:
            self.controller.on_command(Unit, Command)
        except Exception as exc:
            self._unexpected("command for unit %s" % Unit, exc)

    # -- helpers -----------------------------------------------------------------------------------------
    def _unexpected(self, where, exc):
        self.log.Error("Unexpected error in %s: %s: %s" % (where, type(exc).__name__, exc))
        self.log.Debug(traceback.format_exc())


_plugin = BasePlugin()


def onStart():
    _plugin.onStart()


def onStop():
    _plugin.onStop()


def onHeartbeat():
    _plugin.onHeartbeat()


def onCommand(Unit, Command, Level, Hue):
    _plugin.onCommand(Unit, Command, Level, Hue)
