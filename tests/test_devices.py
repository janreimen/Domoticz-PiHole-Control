import unittest

import domoticz_stub as dz
from helpers import Clock, make_logger
from pihole_control.constants import REFRESH_SECONDS, REMOVE_AFTER_MISSES, STAT_DEVICES
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


if __name__ == "__main__":
    unittest.main()
