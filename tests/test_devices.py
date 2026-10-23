import unittest

import domoticz_stub as dz
from helpers import Clock, make_logger
from pihole_control.constants import CREATE_RETRY_SECONDS, KIND_COUNT, REFRESH_SECONDS, REMOVE_AFTER_MISSES, STAT_DEVICES
from pihole_control.devices import DeviceManager, group_device_name, list_device_name
from pihole_control.model import BlockList, Group, Stats


def lst(i, comment="List", groups=(), enabled=True, address=None):
    return BlockList(i, "https://example.org/%d.txt" % i if address is None else address, comment, list(groups), enabled, "block")


def grp(i, name="Group", enabled=True):
    return Group(i, name, "", enabled)


class DeviceTests(unittest.TestCase):
    def setUp(self):
        dz.reset()
        self.clock = Clock()
        self.log = make_logger()
        self.dm = self.manager()

    def manager(self):
        return DeviceManager(dz, lambda: dz.Devices, self.log, clock=self.clock)

    def errors(self):
        return dz.messages("error")

    # -- statistics devices ---------------------------------------------------------------------------------
    def test_statistics_devices_keep_the_units_names_and_types_of_the_old_plugin(self):
        self.dm.ensure_stat_devices()
        self.assertEqual(sorted(dz.Devices), list(range(1, 11)))
        self.assertEqual([dz.Devices[u].Name for u in range(1, 11)], [
            "DNS Queries Today", "Ads Blocked Today", "Ads Percentage", "Domains in Blocklist", "Queries Forwarded",
            "Queries Cached", "Clients Ever Seen", "Unique Clients", "Unique Domains", "Pi-hole Status"])
        custom = dz.Devices[1]
        self.assertEqual((custom.TypeName, custom.Options), ("Custom", {"Custom": "1;queries"}))
        self.assertEqual(dz.Devices[2].Options, {"Custom": "1;blocked"})
        self.assertEqual(dz.Devices[3].TypeName, "Percentage")
        self.assertEqual((dz.Devices[10].TypeName, dz.Devices[10].SwitchType), ("Switch", 0))
        self.assertEqual([(d.Type, d.SubType) for d in (custom, dz.Devices[3], dz.Devices[10])],
                         [(243, 31), (243, 6), (244, 73)])                  # what Domoticz makes of those names
        self.assertTrue(all(d.Used == 1 for d in dz.Devices.values()))

    def test_existing_devices_are_left_alone(self):
        self.dm.ensure_stat_devices()
        before = dict(dz.Devices)
        dz.Devices[1].Name = "My own name"
        self.manager().ensure_stat_devices()
        self.assertEqual(dz.Devices, before)
        self.assertEqual(dz.Devices[1].Name, "My own name")

    def test_statistics_values(self):
        self.dm.ensure_stat_devices()
        self.dm.update_stats(Stats(1234, 234, 18.962, 321, 700, 300, 7, 11, 99999))
        got = {u: dz.Devices[u].sValue for u in range(1, 10)}
        self.assertEqual(got, {1: "1234", 2: "234", 3: "18.96", 4: "99999", 5: "700", 6: "300", 7: "11", 8: "7", 9: "321"})

    def test_a_value_the_pihole_did_not_report_leaves_the_device_alone(self):
        self.dm.ensure_stat_devices()
        self.dm.update_stats(Stats(5, None, None, None, None, None, None, None, None))
        self.assertEqual((dz.Devices[1].sValue, dz.Devices[2].sValue), ("5", ""))

    def test_unchanged_values_are_rewritten_only_every_refresh_interval(self):
        self.dm.ensure_stat_devices()
        stats = Stats(1, 1, 1.0, 1, 1, 1, 1, 1, 1)
        self.dm.update_stats(stats)
        self.dm.update_stats(stats)
        self.assertEqual(dz.Devices[4].updates, 1)
        self.clock.advance(REFRESH_SECONDS + 1)
        self.dm.update_stats(stats)
        self.assertEqual(dz.Devices[4].updates, 2)

    def test_status_switch(self):
        self.dm.ensure_stat_devices()
        self.dm.set_status(True)
        self.assertEqual((dz.Devices[10].nValue, dz.Devices[10].sValue), (1, "On"))
        self.dm.set_status(False)
        self.assertEqual((dz.Devices[10].nValue, dz.Devices[10].sValue), (0, "Off"))

    def test_a_deleted_device_is_reported_once(self):
        self.dm.ensure_stat_devices()
        del dz.Devices[1]
        stats = Stats(1, 1, 1.0, 1, 1, 1, 1, 1, 1)
        self.dm.update_stats(stats)
        self.dm.update_stats(stats)
        self.assertEqual(len(self.errors()), 1)
        self.assertIn("unit 1", self.errors()[0])

    def test_every_statistics_device_has_a_source(self):
        from pihole_control.devices import STAT_FIELDS
        for spec in STAT_DEVICES:
            if spec.kind != "status":
                self.assertIn(spec.key, STAT_FIELDS)
                self.assertIn(STAT_FIELDS[spec.key], Stats._fields)

    # -- lists and groups -----------------------------------------------------------------------------------
    def test_list_devices(self):
        self.dm.sync_lists([lst(1, "Ads", [0], True), lst(7, "Kids - Social", [1], False)], {0: "Default", 1: "Kids"})
        self.assertEqual(sorted(dz.Devices), [100, 101])
        first, second = dz.Devices[100], dz.Devices[101]
        self.assertEqual((first.Name, first.Description, first.nValue, first.sValue),
                         ("List: Ads (Default)", "ListID:1", 1, "On"))
        self.assertEqual((second.Name, second.Description, second.nValue, second.sValue),
                         ("List: Kids - Social (Kids)", "ListID:7", 0, "Off"))
        self.assertEqual((first.TypeName, first.SwitchType, first.Used), ("Switch", 0, 1))

    def test_group_devices_start_at_200(self):
        self.dm.sync_groups([grp(0, "Default"), grp(1, "Kids", False)])
        self.assertEqual(sorted(dz.Devices), [200, 201])
        self.assertEqual((dz.Devices[201].Name, dz.Devices[201].Description, dz.Devices[201].sValue),
                         ("Group: Kids", "GroupID:1", "Off"))

    def test_device_names(self):
        names = {0: "Default"}
        self.assertEqual(list_device_name(lst(1, "Ads"), names), "List: Ads")
        self.assertEqual(list_device_name(lst(1, "", address="https://x.org/a.txt"), names), "List: https://x.org/a.txt")
        self.assertEqual(list_device_name(lst(1, "Ads", [0, 5]), names), "List: Ads (Default, Group 5)")
        self.assertEqual(list_device_name(lst(1, "  ", address=""), names), "List: Unnamed List")
        self.assertEqual(group_device_name(grp(1, "")), "Group: Unnamed Group")
        self.assertLessEqual(len(list_device_name(lst(1, "x" * 500), names)), 100)

    def test_restart_finds_the_devices_again_without_creating_or_renaming(self):
        items = [lst(1, "Ads", [0]), lst(2, "Kids", [1])]
        names = {0: "Default", 1: "Kids"}
        self.dm.sync_lists(items, names)
        created = dict(dz.Devices)
        dz.Devices[101].Name = "My kids list"                       # a name chosen in Domoticz
        fresh = self.manager()                                       # = after a Domoticz restart
        fresh.load_mappings()
        fresh.sync_lists(items, names)
        self.assertEqual(dz.Devices, created)
        self.assertEqual(dz.Devices[101].Name, "My kids list")      # never overwritten at start-up
        self.assertEqual(self.errors(), [])

    def test_a_rename_in_the_pihole_renames_the_device(self):
        self.dm.sync_lists([lst(1, "Ads")], {})
        self.dm.sync_lists([lst(1, "Advertising")], {})
        self.assertEqual(dz.Devices[100].Name, "List: Advertising")
        self.assertTrue(any("renamed" in text for text in dz.messages("log")))

    def test_one_missing_answer_never_deletes_a_device(self):
        self.assertGreaterEqual(REMOVE_AFTER_MISSES, 2)                # the grace period is a policy, not a detail
        self.dm.sync_lists([lst(1), lst(2)], {})
        self.dm.sync_lists([lst(2)], {})                               # one answer without list 1
        self.assertIn(100, dz.Devices)
        self.assertEqual(dz.Devices[100].Description, "ListID:1")

    def test_a_list_is_removed_only_after_it_was_gone_for_several_polls(self):
        self.dm.sync_lists([lst(1), lst(2)], {})
        for _ in range(REMOVE_AFTER_MISSES - 1):
            self.dm.sync_lists([lst(2)], {})
        self.assertIn(100, dz.Devices)                               # still there
        self.dm.sync_lists([lst(1), lst(2)], {})                    # it came back: the counter starts again
        for _ in range(REMOVE_AFTER_MISSES - 1):
            self.dm.sync_lists([lst(2)], {})
        self.assertIn(100, dz.Devices)
        self.dm.sync_lists([lst(2)], {})
        self.assertNotIn(100, dz.Devices)
        self.assertIn(101, dz.Devices)
        self.assertTrue(any("Removing" in text for text in dz.messages("log")))

    def test_a_device_deleted_in_domoticz_is_created_again(self):
        self.dm.sync_groups([grp(3, "Kids")])
        del dz.Devices[200]
        self.dm.sync_groups([grp(3, "Kids")])
        self.assertEqual(dz.Devices[200].Description, "GroupID:3")

    def test_new_lists_take_the_next_free_unit(self):
        self.dm.sync_lists([lst(1)], {})
        self.dm.sync_lists([lst(1), lst(2), lst(3)], {})
        self.assertEqual([(u, dz.Devices[u].Description) for u in sorted(dz.Devices)],
                         [(100, "ListID:1"), (101, "ListID:2"), (102, "ListID:3")])

    def test_running_out_of_units_is_reported_once_and_does_not_break_the_rest(self):
        items = [lst(i) for i in range(1, 102)]                      # 101 lists, 100 units
        self.dm.sync_lists(items, {})
        self.dm.sync_lists(items, {})
        self.assertEqual(len(dz.Devices), 100)
        self.assertEqual(len(self.errors()), 1)
        self.assertIn("100-199", self.errors()[0])

    def test_state_follows_the_pihole(self):
        self.dm.sync_lists([lst(1, enabled=True)], {})
        self.dm.sync_lists([lst(1, enabled=False)], {})
        self.assertEqual((dz.Devices[100].nValue, dz.Devices[100].sValue), (0, "Off"))
        self.assertFalse(self.dm.state_of(100))

    def test_resolve_and_restore(self):
        self.dm.sync_lists([lst(4)], {})
        self.dm.sync_groups([grp(2)])
        self.assertEqual(self.dm.resolve(100), ("list", 4))
        self.assertEqual(self.dm.resolve(200), ("group", 2))
        self.assertEqual(self.dm.resolve(10), ("status", None))
        self.assertEqual(self.dm.resolve(5), (None, None))
        before = dz.Devices[100].updates
        self.dm.restore(100)
        self.assertEqual(dz.Devices[100].updates, before + 1)
        self.assertEqual(self.dm.name_of(100), "List: List")



class UnitTests(unittest.TestCase):
    """Counters show their unit; a counter that was created without one gets it."""

    def setUp(self):
        dz.reset()
        self.clock = Clock()
        self.log = make_logger()
        self.dm = DeviceManager(dz, lambda: dz.Devices, self.log, clock=self.clock)
        self.dm.ensure_stat_devices()

    def fresh(self):
        return DeviceManager(dz, lambda: dz.Devices, self.log, clock=self.clock)       # = after a restart

    def counters(self):
        return [spec for spec in STAT_DEVICES if spec.kind == KIND_COUNT]

    def test_every_counter_is_created_with_its_unit(self):
        self.assertEqual(len(self.counters()), 8)
        for spec in self.counters():
            self.assertEqual(dz.Devices[spec.unit].Options, {"Custom": "1;%s" % spec.label}, spec.name)
            self.assertTrue(spec.label, spec.name)

    def test_a_counter_without_a_unit_gets_its_unit_and_keeps_its_value(self):
        device = dz.Devices[1]
        device.Options, device.nValue, device.sValue = {}, 0, "42"
        self.fresh().ensure_stat_devices()
        self.assertEqual(device.Options, {"Custom": "1;queries"})
        self.assertEqual((device.nValue, device.sValue, device.Used), (0, "42", 1))
        self.assertEqual(len(device.update_calls), 1)
        self.assertTrue(device.update_calls[0]["SuppressTriggers"])       # only the options change, no triggers fire
        self.assertIsNone(device.update_calls[0]["Used"])
        self.assertTrue(any("Added the unit 'queries'" in t for t in dz.messages("log")))

    def test_every_counter_gets_its_own_unit(self):
        for spec in self.counters():
            dz.Devices[spec.unit].Options = {"Custom": "1"}                # an axis, but no unit
        self.fresh().ensure_stat_devices()
        for spec in self.counters():
            self.assertEqual(dz.Devices[spec.unit].Options, {"Custom": "1;%s" % spec.label}, spec.name)

    def test_percentage_and_status_devices_are_never_touched(self):
        self.fresh().ensure_stat_devices()
        self.assertEqual(dz.Devices[3].update_calls, [])
        self.assertEqual(dz.Devices[10].update_calls, [])

    def test_a_unit_you_chose_stays(self):
        dz.Devices[1].Options = {"Custom": "1;requests"}
        self.fresh().ensure_stat_devices()
        self.assertEqual(dz.Devices[1].Options, {"Custom": "1;requests"})
        self.assertEqual(dz.Devices[1].update_calls, [])

    def test_a_device_that_is_no_longer_a_custom_sensor_is_left_alone(self):
        dz.Devices[1].SubType, dz.Devices[1].Options = 6, {}
        self.fresh().ensure_stat_devices()
        self.assertEqual(dz.Devices[1].update_calls, [])

    def test_a_device_is_looked_at_once_per_start(self):
        device = dz.Devices[1]
        device.Options = {}
        calls = []
        device.Update = lambda **kw: calls.append(kw)                      # Domoticz that ignores the change
        manager = self.fresh()
        for _ in range(3):
            manager.ensure_stat_devices()
        self.assertEqual(len(calls), 1)

    def test_a_failing_update_is_reported_and_does_not_break_the_start(self):
        device = dz.Devices[1]
        device.Options = {}

        def boom(**_):
            raise RuntimeError("no way")
        device.Update = boom
        self.fresh().ensure_stat_devices()
        self.assertTrue(any("Could not add the unit 'queries'" in t and "no way" in t for t in dz.messages("error")))

    def test_the_used_state_of_an_existing_device_is_the_users_choice(self):
        dz.Devices[2].Used = 0                                             # hidden on purpose
        dz.Devices[2].Options = {}
        self.fresh().ensure_stat_devices()
        self.assertEqual(dz.Devices[2].Used, 0)
        self.assertIsNone(dz.Devices[2].update_calls[-1]["Used"])


class UsedTests(unittest.TestCase):
    def setUp(self):
        dz.reset()
        self.dm = DeviceManager(dz, lambda: dz.Devices, make_logger(), clock=Clock())

    def test_every_device_the_plugin_creates_is_in_use_from_the_start(self):
        self.dm.ensure_stat_devices()
        self.dm.sync_lists([lst(1), lst(2, enabled=False)], {})
        self.dm.sync_groups([grp(0, "Default"), grp(1, "Kids", False)])
        self.assertEqual(len(dz.Devices), 14)
        self.assertEqual([unit for unit, d in dz.Devices.items() if d.Used != 1], [])
        for device in dz.Devices.values():
            self.assertEqual(device.kw.get("Used"), 1)                     # asked for explicitly, not left to a default


class CreationRefusedTests(unittest.TestCase):
    """Domoticz refuses new devices while "Accept new Hardware Devices" is off. The plugin says so once, does not
    nag Domoticz, and creates everything as soon as the setting is on - without restarting the hardware."""

    def setUp(self):
        dz.reset()
        self.clock = Clock()
        self.dm = DeviceManager(dz, lambda: dz.Devices, make_logger(), clock=self.clock)
        dz.accept_new_devices = False

    def ours(self):
        return [t for t in dz.messages("error") if t.startswith("Domoticz did not create")]

    def test_statistics_devices_ask_domoticz_once_and_explain_once(self):
        self.dm.ensure_stat_devices()
        self.assertEqual(dz.create_attempts, [1])                          # not ten refusals from Domoticz
        self.assertEqual(len(self.ours()), 1)
        self.assertIn("Accept new Hardware Devices", self.ours()[0])
        self.clock.advance(60)
        self.dm.ensure_stat_devices()
        self.assertEqual(dz.create_attempts, [1])                          # inside the retry window: no new attempt
        self.clock.advance(CREATE_RETRY_SECONDS)
        self.dm.ensure_stat_devices()
        self.assertEqual(dz.create_attempts, [1, 1])                       # asked again ...
        self.assertEqual(len(self.ours()), 1)                              # ... but the explanation is not repeated

    def test_the_devices_appear_when_the_setting_is_switched_on(self):
        self.dm.ensure_stat_devices()
        self.assertEqual(dz.Devices, {})
        dz.accept_new_devices = True
        self.clock.advance(CREATE_RETRY_SECONDS + 1)
        self.dm.ensure_stat_devices()
        self.assertEqual(sorted(dz.Devices), list(range(1, 11)))
        self.assertEqual(len([t for t in dz.messages("log") if "creates the devices of the Pi-hole now" in t]), 1)
        self.dm.ensure_stat_devices()
        self.assertEqual(len([t for t in dz.messages("log") if "creates the devices of the Pi-hole now" in t]), 1)

    def test_list_and_group_switches_ask_once_per_window(self):
        items = [lst(i) for i in range(1, 6)]
        self.dm.sync_lists(items, {})
        self.dm.sync_groups([grp(1, "Kids")])
        self.assertEqual(dz.create_attempts, [100])                        # one attempt covers lists and groups
        self.assertEqual(len(self.ours()), 1)
        self.assertIn("list 1", self.ours()[0])
        dz.accept_new_devices = True
        self.clock.advance(CREATE_RETRY_SECONDS + 1)
        self.dm.sync_lists(items, {})
        self.dm.sync_groups([grp(1, "Kids")])
        self.assertEqual(sorted(dz.Devices), [100, 101, 102, 103, 104, 200])
        self.assertEqual(self.dm.resolve(104), ("list", 5))

    def test_statistics_and_switches_share_the_pause(self):
        self.dm.ensure_stat_devices()
        self.dm.sync_lists([lst(1)], {})
        self.assertEqual(dz.create_attempts, [1])

    def test_updating_a_device_that_was_refused_does_not_add_error_lines(self):
        self.dm.ensure_stat_devices()
        self.dm.update_stats(Stats(1, 2, 3.0, 4, 5, 6, 7, 8, 9))
        self.dm.set_status(True)
        self.assertEqual([t for t in dz.messages("error") if "Cannot update" in t], [])

    def test_a_device_that_is_missing_while_creation_works_is_still_reported_once(self):
        dz.accept_new_devices = True
        self.dm.ensure_stat_devices()
        del dz.Devices[1]
        self.dm.update_stats(Stats(1, 2, 3.0, 4, 5, 6, 7, 8, 9))
        self.dm.update_stats(Stats(1, 2, 3.0, 4, 5, 6, 7, 8, 9))
        self.assertEqual(len([t for t in dz.messages("error") if "Cannot update Domoticz unit 1" in t]), 1)


class RenameTests(unittest.TestCase):
    """Domoticz stores a plugin device as "<hardware name> - <name>" and Update(Name=...) stores the name as given."""

    def setUp(self):
        dz.reset()
        dz.hardware_name = "Pi-hole"
        self.dm = DeviceManager(dz, lambda: dz.Devices, make_logger(), clock=Clock(), hardware_name="Pi-hole")

    def test_a_rename_keeps_the_hardware_prefix(self):
        self.dm.sync_lists([lst(1, "Ads")], {})
        self.assertEqual(dz.Devices[100].Name, "Pi-hole - List: Ads")
        self.dm.sync_lists([lst(1, "Advertising")], {})
        self.assertEqual(dz.Devices[100].Name, "Pi-hole - List: Advertising")

    def test_a_rename_changes_the_name_only(self):
        self.dm.sync_groups([grp(3, "Kids")])
        device = dz.Devices[200]
        before = (device.nValue, device.sValue, device.updates)
        self.dm.sync_groups([grp(3, "Children")])
        self.assertEqual(device.Name, "Pi-hole - Group: Children")
        self.assertEqual((device.nValue, device.sValue), before[:2])
        self.assertEqual(device.updates, before[2] + 1)                    # exactly the rename
        self.assertTrue(device.update_calls[-1]["SuppressTriggers"])       # no notification, no scene

    def test_without_a_hardware_name_the_plain_name_is_used(self):
        dz.hardware_name = ""
        dm = DeviceManager(dz, lambda: dz.Devices, make_logger(), clock=Clock())
        dm.sync_groups([grp(3, "Kids")])
        dm.sync_groups([grp(3, "Children")])
        self.assertEqual(dz.Devices[200].Name, "Group: Children")


if __name__ == "__main__":
    unittest.main()
