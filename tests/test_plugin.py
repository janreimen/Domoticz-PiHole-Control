"""The real plugin.py (manifest, glue, callbacks) against the fake Pi-hole, with a Domoticz stub."""
import ast
import importlib
import os
import re
import sys
import unittest

import domoticz_stub as dz
from fake_pihole import FakePiHole
from helpers import ROOT

RESERVED = {"Parameters", "Devices", "Images", "Settings"}          # injected into plugin.py by Domoticz


class PluginTests(unittest.TestCase):
    def setUp(self):
        self.ph = FakePiHole().start()
        self.addCleanup(self.ph.stop)
        self.saved = sys.modules.get("Domoticz")
        sys.modules["Domoticz"] = dz
        self.addCleanup(self.restore)

    def restore(self):
        if self.saved is None:
            sys.modules.pop("Domoticz", None)
        else:
            sys.modules["Domoticz"] = self.saved

    def load(self, **params):
        dz.reset()
        sys.modules.pop("plugin", None)
        plugin = importlib.import_module("plugin")
        plugin.Parameters = {"Address": self.ph.url, "Password": "secret", "Mode1": "60", "Mode2": "", "Mode6": "0"}
        plugin.Parameters.update(params)
        plugin.Devices = dz.Devices
        plugin.Settings = {"Language": "en"}        # injected by Domoticz like these
        plugin.Images = {}
        return plugin

    def errors(self):
        return dz.messages("error")

    def test_start_creates_the_devices_and_stop_logs_out(self):
        plugin = self.load()
        plugin.onStart()
        self.assertEqual(self.errors(), [])
        self.assertEqual(sorted(dz.Devices), list(range(1, 11)) + [100, 101, 200, 201])
        self.assertIn(("heartbeat", 10), dz.logs)
        self.assertTrue(any("Pi-hole Control 0.1.0 starting for" in t for t in dz.messages("log")))
        plugin.onHeartbeat()
        plugin.onStop()
        self.assertEqual(self.ph.sessions, {})
        self.assertTrue(any("stopped" in t for t in dz.messages("log")))
        self.assertNotIn("secret", dz.all_text())

    def test_commands_go_through_the_callback(self):
        plugin = self.load()
        plugin.onStart()
        plugin.onCommand(101, "On", 0, "")
        self.assertTrue(self.ph.get_list(2)["enabled"])
        self.assertEqual(dz.Devices[101].sValue, "On")

    def test_a_bad_configuration_is_reported_and_the_plugin_stays_idle(self):
        plugin = self.load(Address="")
        plugin.onStart()
        self.assertTrue(any("Configuration error: No Pi-hole URL" in t for t in self.errors()))
        plugin.onHeartbeat()
        plugin.onCommand(100, "Off", 0, "")
        plugin.onStop()
        self.assertTrue(any("did not start" in t for t in self.errors()))
        self.assertEqual(dz.Devices, {})
        self.assertEqual(len(self.ph.requests), 0)

    def test_an_unreachable_pihole_is_one_error_and_the_devices_exist(self):
        port = self.ph.port
        self.ph.stop()
        plugin = self.load(Address="http://127.0.0.1:%d" % port)
        plugin.onStart()
        self.assertEqual(len(self.errors()), 1)
        self.assertEqual(sorted(dz.Devices), list(range(1, 11)))
        self.assertEqual(dz.Devices[10].sValue, "Off")
        plugin.onHeartbeat()
        self.assertEqual(len(self.errors()), 1)

    def test_an_unexpected_exception_does_not_escape_a_callback(self):
        plugin = self.load()
        plugin.onStart()

        def boom(*args):
            raise RuntimeError("boom")
        plugin._plugin.controller.on_heartbeat = boom
        plugin._plugin.controller.on_command = boom
        plugin.onHeartbeat()
        plugin.onCommand(100, "Off", 0, "")
        self.assertEqual(len([t for t in self.errors() if "RuntimeError: boom" in t]), 2)

    def test_debug_levels_wire_up_domoticz_debugging(self):
        plugin = self.load(Mode6="3")
        plugin.onStart()
        self.assertIn(("debugging", 1), dz.logs)
        self.assertTrue(any(t.startswith("[DEBUG]") for t in dz.messages("debug")))
        plugin = self.load(Mode6="Debug")                              # the value the old plugin stored
        plugin.onStart()
        self.assertIn(("debugging", 1), dz.logs)
        plugin = self.load(Mode6="Normal")
        plugin.onStart()
        self.assertNotIn(("debugging", 1), dz.logs)
        self.assertEqual(dz.messages("debug"), [])

    def test_corrections_to_the_url_are_logged(self):
        plugin = self.load(Address=self.ph.url + "/admin/")
        plugin.onStart()
        self.assertTrue(any("Removed '/admin'" in t for t in dz.messages("log")))
        self.assertEqual(self.errors(), [])


class ManifestTests(unittest.TestCase):
    def source(self):
        with open(os.path.join(ROOT, "plugin.py"), encoding="utf-8") as fh:
            return fh.read()

    def test_the_manifest_keeps_the_key_and_the_parameter_fields_of_the_old_plugin(self):
        manifest = self.source().split('"""')[1]
        self.assertIn('key="PiHole"', manifest)                         # Domoticz stores the hardware by this key
        for field in ("Address", "Password", "Mode1", "Mode2", "Mode6"):
            self.assertIn('field="%s"' % field, manifest)
        self.assertNotIn('field="Mode3"', manifest)

    def test_plugin_py_never_binds_a_name_domoticz_injects(self):
        tree = ast.parse(self.source())
        bound = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                bound |= {(a.asname or a.name).split(".")[0] for a in node.names}
            elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                bound.add(node.name)
            elif isinstance(node, ast.Assign):
                bound |= {t.id for t in node.targets if isinstance(t, ast.Name)}
        self.assertEqual(bound & RESERVED, set(), "plugin.py would be shadowed by Domoticz' injected globals")

    def test_only_plugin_py_imports_domoticz(self):
        package = os.path.join(ROOT, "pihole_control")
        for name in sorted(os.listdir(package)):
            if name.endswith(".py"):
                with open(os.path.join(package, name), encoding="utf-8") as fh:
                    self.assertIsNone(re.search(r"^\s*(import|from)\s+Domoticz\b", fh.read(), re.M), name)

    def test_the_callbacks_domoticz_calls_exist(self):
        tree = ast.parse(self.source())
        top = {n.name: [a.arg for a in n.args.args] for n in tree.body if isinstance(n, ast.FunctionDef)}
        self.assertEqual(top["onCommand"], ["Unit", "Command", "Level", "Hue"])      # Domoticz calls it positionally
        for name in ("onStart", "onStop", "onHeartbeat"):
            self.assertIn(name, top)

    def test_the_standard_library_is_all_that_is_needed(self):
        stdlib = set(sys.stdlib_module_names) if hasattr(sys, "stdlib_module_names") else None
        package = os.path.join(ROOT, "pihole_control")
        for name in sorted(os.listdir(package)):
            if not name.endswith(".py"):
                continue
            with open(os.path.join(package, name), encoding="utf-8") as fh:
                tree = ast.parse(fh.read())
            for node in ast.walk(tree):
                modules = []
                if isinstance(node, ast.Import):
                    modules = [a.name.split(".")[0] for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0:
                    modules = [node.module.split(".")[0]]
                for module in modules:
                    if stdlib is not None:
                        self.assertIn(module, stdlib, "%s imports the third-party module %s" % (name, module))


if __name__ == "__main__":
    unittest.main()
