import unittest

import domoticz_stub as dz
from fake_pihole import FakePiHole
from helpers import make_stack


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.ph = FakePiHole().start()
        self.addCleanup(self.ph.stop)
        self.controller, self.client, self.devices, self.clock = make_stack(self.ph)

    def errors(self):
        return dz.messages("error")

    def start(self):
        self.controller.start()

    # -- start and polling ----------------------------------------------------------------------------------
    def test_start_creates_every_device_and_connects(self):
        self.start()
        self.assertEqual(self.errors(), [])
        self.assertEqual(sorted(dz.Devices), list(range(1, 11)) + [100, 101, 200, 201])
        self.assertEqual(dz.Devices[1].sValue, "1234")
        self.assertEqual((dz.Devices[10].nValue, dz.Devices[10].sValue), (1, "On"))
        self.assertEqual(dz.Devices[100].Name, "List: Ads (Default)")
        self.assertEqual(dz.Devices[101].sValue, "Off")
        self.assertEqual(dz.Devices[201].Name, "Group: Kids")
        self.assertTrue(any("Connected to the Pi-hole" in text for text in dz.messages("log")))
        # one login and three reads per poll - the old plugin read lists and groups twice
        self.assertEqual([m for m, _ in self.ph.requests], ["POST", "GET", "GET", "GET"])

    def test_polling_follows_the_interval_not_the_heartbeat(self):
        self.start()
        sent = len(self.ph.requests)
        self.clock.advance(59)
        self.controller.on_heartbeat()
        self.assertEqual(len(self.ph.requests), sent)
        self.clock.advance(2)
        self.controller.on_heartbeat()
        self.assertEqual(len(self.ph.requests), sent + 3)               # session reused: no new login

    def test_changes_in_the_pihole_arrive(self):
        self.start()
        self.ph.stats["queries"]["total"] = 2000
        self.ph.get_list(1)["enabled"] = False                           # someone used the Pi-hole web interface
        self.ph.groups.append({"id": 2, "name": "Guests", "comment": "", "enabled": True})
        self.clock.advance(61)
        self.controller.on_heartbeat()
        self.assertEqual(dz.Devices[1].sValue, "2000")
        self.assertEqual(dz.Devices[100].sValue, "Off")
        self.assertEqual(dz.Devices[202].Name, "Group: Guests")

    # -- failures -------------------------------------------------------------------------------------------
    def test_a_failure_is_one_error_then_quiet_and_recovery_is_announced(self):
        self.start()
        self.ph.fail.extend([("status", 500)] * 2)
        for expected_delay in (60, 120):
            self.clock.advance(self.controller.next_poll_at - self.clock() + 0.1)
            before = self.clock()
            self.controller.on_heartbeat()
            self.assertEqual(round(self.controller.next_poll_at - before), expected_delay)
        self.assertEqual(len(self.errors()), 1, self.errors())           # logged once, not twice
        self.assertEqual((dz.Devices[10].nValue, dz.Devices[10].sValue), (0, "Off"))
        self.clock.advance(self.controller.next_poll_at - self.clock() + 0.1)
        self.controller.on_heartbeat()
        self.assertEqual((dz.Devices[10].nValue, dz.Devices[10].sValue), (1, "On"))
        self.assertTrue(any("answers again" in text for text in dz.messages("log")))
        self.assertEqual(self.controller.failures, 0)
        self.assertEqual(len(self.errors()), 1)

    def test_backoff_is_capped(self):
        self.start()
        self.ph.stop()
        delays = []
        for _ in range(9):
            self.clock.advance(self.controller.next_poll_at - self.clock() + 0.1)
            before = self.clock()
            self.controller.on_heartbeat()
            delays.append(round(self.controller.next_poll_at - before))
        self.assertEqual(delays, [60, 120, 240, 300, 300, 300, 300, 300, 300])

    def test_a_rejected_login_waits_long_and_says_why(self):
        controller, _, _, clock = make_stack(self.ph, password="wrong")
        controller.start()
        self.assertEqual(len(self.errors()), 1)
        self.assertIn("password incorrect", self.errors()[0])
        delays = []
        for _ in range(4):
            before = clock()
            delays.append(round(controller.next_poll_at - before))
            clock.advance(controller.next_poll_at - before + 0.1)
            controller.on_heartbeat()
        self.assertEqual(delays, [300, 600, 900, 900])
        self.assertEqual(len(self.errors()), 1)                          # still one error, not one per attempt

    def test_unreachable_at_start_still_creates_the_devices(self):
        self.ph.stop()
        self.start()
        self.assertEqual(sorted(dz.Devices), list(range(1, 11)))
        self.assertEqual(dz.Devices[10].sValue, "Off")
        self.assertEqual(len(self.errors()), 1)

    def test_a_failing_lists_request_does_not_mark_the_pihole_offline(self):
        self.ph.fail.extend([("ok",), ("ok",), ("ok",), ("status", 500)])          # login, stats, groups, then lists
        self.start()
        self.assertEqual(dz.Devices[10].sValue, "On")
        self.assertEqual(sorted(u for u in dz.Devices if u >= 100), [200, 201])      # groups arrived, lists did not
        self.assertEqual(len(self.errors()), 1)
        self.assertIn("lists", self.errors()[0])
        self.clock.advance(61)
        self.controller.on_heartbeat()                                   # next poll: everything works again
        self.assertEqual(sorted(u for u in dz.Devices if u >= 100), [100, 101, 200, 201])
        self.assertTrue(any("lists can be read" in text for text in dz.messages("log")))

    def test_stop_logs_out(self):
        self.start()
        self.assertEqual(len(self.ph.sessions), 1)
        self.controller.stop()
        self.assertEqual(self.ph.sessions, {})

    # -- commands -------------------------------------------------------------------------------------------
    def test_switching_a_list_off_and_on(self):
        self.start()
        self.controller.on_command(100, "Off")
        self.assertFalse(self.ph.get_list(1)["enabled"])
        self.assertEqual((self.ph.get_list(1)["comment"], self.ph.get_list(1)["groups"]), ("Ads", [0]))
        self.assertEqual((dz.Devices[100].nValue, dz.Devices[100].sValue), (0, "Off"))
        self.assertTrue(any("is now disabled" in text for text in dz.messages("log")))
        self.controller.on_command(100, "On")
        self.assertTrue(self.ph.get_list(1)["enabled"])
        self.assertEqual(dz.Devices[100].sValue, "On")
        self.assertEqual(self.errors(), [])

    def test_switching_a_group(self):
        self.start()
        self.controller.on_command(201, "Off")
        self.assertFalse(self.ph.get_group(1)["enabled"])
        self.assertEqual(dz.Devices[201].sValue, "Off")
        self.assertIn(("PUT", "/api/groups/Kids"), self.ph.requests)

    def test_only_on_and_off_are_understood(self):
        self.start()
        for command in ("Toggle", "Set Level", "", "On Please"):
            self.controller.on_command(100, command)
        self.assertEqual(self.ph.count("PUT", "/api"), 0)                # the old plugin treated everything but "On" as Off
        self.assertTrue(self.ph.get_list(1)["enabled"])
        self.assertEqual(len(self.errors()), 4)

    def test_commands_are_case_insensitive(self):
        self.start()
        self.controller.on_command(100, "OFF")
        self.assertFalse(self.ph.get_list(1)["enabled"])

    def test_the_status_switch_and_foreign_units_cannot_be_operated(self):
        self.start()
        before = dz.Devices[10].updates
        self.controller.on_command(10, "Off")
        self.controller.on_command(5, "Off")
        self.controller.on_command(150, "Off")                           # no device behind it
        self.assertEqual(self.ph.count("PUT", "/api"), 0)
        self.assertEqual(dz.Devices[10].sValue, "On")
        self.assertGreater(dz.Devices[10].updates, before)               # restored, so the UI shows the truth
        self.assertEqual(self.errors(), [])

    def test_a_refused_change_restores_the_switch(self):
        self.start()
        self.ph.put_errors = True
        before = dz.Devices[100].updates
        self.controller.on_command(100, "Off")
        self.assertEqual(dz.Devices[100].sValue, "On")
        self.assertGreater(dz.Devices[100].updates, before)
        self.assertEqual(len(self.errors()), 1)
        self.assertIn("Could not disable list 1", self.errors()[0])

    def test_an_accepted_but_not_applied_change_is_not_reported_as_success(self):
        self.start()
        self.ph.ignore_put = True
        self.controller.on_command(100, "Off")
        self.assertEqual(dz.Devices[100].sValue, "On")                   # read back from the Pi-hole
        self.assertIn("still reports", self.errors()[-1])
        self.assertFalse(any("is now disabled" in text for text in dz.messages("log")))

    def test_a_list_that_vanished_from_the_pihole(self):
        self.start()
        self.ph.lists.pop(0)
        self.controller.on_command(100, "Off")
        self.assertIn("no list 1 any more", self.errors()[0])
        self.assertEqual(self.ph.count("PUT", "/api"), 0)

    def test_the_pihole_goes_away_during_a_command(self):
        self.start()
        self.ph.stop()
        self.controller.on_command(100, "Off")
        self.assertEqual(dz.Devices[100].sValue, "On")
        self.assertEqual(len(self.errors()), 1)


if __name__ == "__main__":
    unittest.main()
