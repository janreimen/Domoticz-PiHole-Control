import os
import unittest
from unittest import mock

import domoticz_stub as dz
from fake_pihole import FakePiHole
from helpers import Clock, make_logger
from pihole_control import api
from pihole_control.api import PiHoleClient, PiHoleError


class ClientTests(unittest.TestCase):
    def setUp(self):
        dz.reset()
        self.ph = FakePiHole().start()
        self.addCleanup(self.ph.stop)
        self.clock = Clock()
        self.log = make_logger(3)
        self.client = PiHoleClient(self.ph.url, "secret", self.log, timeout=3, clock=self.clock)

    def fails(self, kind, call, *args):
        with self.assertRaises(PiHoleError) as ctx:
            call(*args)
        self.assertEqual(ctx.exception.kind, kind, str(ctx.exception))
        return ctx.exception

    # -- session --------------------------------------------------------------------------------------------
    def test_login_and_statistics(self):
        stats = self.client.get_stats()
        self.assertEqual((stats.total_queries, stats.blocked_queries, stats.unique_domains), (1234, 234, 321))
        self.assertAlmostEqual(stats.percent_blocked, 18.962)
        self.assertEqual((stats.forwarded, stats.cached, stats.clients_active, stats.clients_total, stats.domains_blocked),
                         (700, 300, 7, 11, 99999))
        self.assertEqual(self.ph.logins, 1)

    def test_one_session_serves_many_requests(self):
        for _ in range(3):
            self.client.get_stats()
            self.client.get_lists()
        self.assertEqual(self.ph.count("POST", "/api/auth"), 1)

    def test_session_is_renewed_before_it_expires(self):
        self.client.get_stats()
        self.clock.advance(self.ph.validity - 10)                       # inside the renewal margin
        self.client.get_stats()
        self.assertEqual(self.ph.logins, 2)

    def test_regular_use_keeps_one_session_alive(self):
        self.ph.validity = 300                                           # the Pi-hole default
        client = PiHoleClient(self.ph.url, "secret", self.log, timeout=3, clock=self.clock)
        for _ in range(12):                                              # one hour of polling every 5 minutes minus a bit
            client.get_stats()
            self.clock.advance(240)                                      # every request extends the session
        self.assertEqual(self.ph.logins, 1)

    def test_renewing_a_session_frees_the_old_seat(self):
        self.ph.validity = 300
        client = PiHoleClient(self.ph.url, "secret", self.log, timeout=3, clock=self.clock)
        client.get_stats()
        self.clock.advance(290)                                          # about to run out: renew
        client.get_stats()
        self.assertEqual(self.ph.logins, 2)
        self.assertEqual(self.ph.count("DELETE", "/api/auth"), 1)
        self.assertEqual(len(self.ph.sessions), 1)                       # the Pi-hole only has a limited number of seats

    def test_a_session_the_pihole_forgot_is_replaced_transparently(self):
        self.client.get_stats()
        self.ph.sessions.clear()                                        # the Pi-hole restarted
        self.assertEqual(len(self.client.get_lists()), 2)
        self.assertEqual(self.ph.logins, 2)

    def test_wrong_password(self):
        client = PiHoleClient(self.ph.url, "wrong", self.log, timeout=3, clock=self.clock)
        err = self.fails(api.AUTH, client.get_stats)
        self.assertIn("password incorrect", str(err))
        self.assertEqual(self.ph.count("POST", "/api/auth"), 1)         # no retry loop
        self.assertEqual(self.ph.count("GET", "/api"), 0)

    def test_logout_frees_the_session(self):
        self.client.get_stats()
        self.assertEqual(len(self.ph.sessions), 1)
        self.client.logout()
        self.assertEqual(self.ph.sessions, {})
        self.assertIsNone(self.client.sid)

    def test_logout_never_raises(self):
        self.client.get_stats()
        self.ph.stop()
        self.client.logout(timeout=1)
        self.assertIsNone(self.client.sid)
        PiHoleClient(self.ph.url, "x", self.log).logout()                # never logged in: nothing to do

    # -- reads ----------------------------------------------------------------------------------------------
    def test_lists_and_groups_are_parsed(self):
        lists = self.client.get_lists()
        self.assertEqual([(i.id, i.comment, i.groups, i.enabled, i.type) for i in lists],
                         [(1, "Ads", [0], True, "block"), (2, "Kids - Social Media", [1], False, "block")])
        groups = self.client.get_groups()
        self.assertEqual([(g.id, g.name, g.comment, g.enabled) for g in groups],
                         [(0, "Default", "The default group", True), (1, "Kids", "", True)])   # comment null -> ""

    def test_malformed_entries_are_skipped_not_fatal(self):
        self.ph.lists.append("not an object")
        self.ph.lists.append({"address": "no id"})
        self.assertEqual(len(self.client.get_lists()), 2)

    def test_unexpected_shapes_are_reported(self):
        self.ph.stats = {"nothing": 1}
        self.fails(api.INVALID, self.client.get_stats)
        self.assertEqual(api.parse_stats({"queries": {}}).total_queries, None)       # missing values stay None

    # -- writes ---------------------------------------------------------------------------------------------
    def test_enable_a_list_keeps_its_other_fields_and_quotes_the_address(self):
        item = self.client.get_lists()[1]
        self.client.set_list_enabled(item, True)
        stored = self.ph.get_list(2)
        self.assertTrue(stored["enabled"])
        self.assertEqual((stored["comment"], stored["groups"]), ("Kids - Social Media", [1]))
        put = [p for m, p in self.ph.requests if m == "PUT"][0]
        self.assertEqual(put, "/api/lists/https%3A%2F%2Fexample.org%2Fsocial%20media%2Flist.txt")

    def test_enable_a_group_is_addressed_by_name(self):
        self.client.set_group_enabled(self.client.get_groups()[1], False)
        self.assertFalse(self.ph.get_group(1)["enabled"])
        self.assertIn(("PUT", "/api/groups/Kids"), self.ph.requests)

    def test_errors_reported_in_a_200_answer_are_errors(self):
        self.ph.put_errors = True
        err = self.fails(api.HTTP, self.client.set_group_enabled, api.Group(1, "Kids", "", True), False)
        self.assertIn("boom", str(err))

    def test_unknown_item_is_a_404_with_the_message_of_the_pihole(self):
        err = self.fails(api.HTTP, self.client.set_group_enabled, api.Group(9, "Nobody", "", True), False)
        self.assertEqual(err.status, 404)
        self.assertIn("Item not found", str(err))

    # -- transport problems ---------------------------------------------------------------------------------
    def test_http_errors(self):
        self.ph.fail.append(("status", 500))
        err = self.fails(api.HTTP, self.client.get_stats)               # the login itself gets the 500
        self.assertEqual(err.status, 500)
        self.ph.fail.append(("ok",))
        self.ph.fail.append(("status", 429))
        self.fails(api.RATE, self.client.get_stats)

    def test_connection_refused_and_dropped_connections(self):
        self.ph.fail.append(("drop",))
        self.fails(api.CONNECTION, self.client.get_stats)
        port = self.ph.port
        self.ph.stop()
        dead = PiHoleClient("http://127.0.0.1:%d" % port, "secret", self.log, timeout=2, clock=self.clock)
        self.fails(api.CONNECTION, dead.get_stats)

    def test_a_redirect_is_reported_and_never_followed(self):
        self.ph.fail.append(("redirect", "https://pi.hole/api/auth"))
        err = self.fails(api.REDIRECT, self.client.get_stats)
        self.assertIn("https://pi.hole/api/auth", str(err))
        self.assertEqual(len(self.ph.requests), 1)

    def test_an_answer_that_is_not_json(self):
        self.ph.fail.append(("garbage",))
        self.fails(api.INVALID, self.client.get_stats)

    def test_environment_proxies_are_ignored(self):
        env = {"http_proxy": "http://127.0.0.1:9", "HTTP_PROXY": "http://127.0.0.1:9", "no_proxy": "", "NO_PROXY": ""}
        with mock.patch.dict(os.environ, env):
            client = PiHoleClient(self.ph.url, "secret", self.log, timeout=3, clock=self.clock)
            self.assertEqual(client.get_stats().total_queries, 1234)
            self.assertEqual(self.ph.count("GET", "/api/stats/summary"), 1)        # it came here, not via the proxy

    # -- secrets --------------------------------------------------------------------------------------------
    def test_the_password_never_reaches_the_log_or_an_error(self):
        password = "pw-S3cr3t-value"
        self.ph.password = password
        log = make_logger(3)                                             # note: the password is NOT registered here
        client = PiHoleClient(self.ph.url, password, log, timeout=3, clock=self.clock)
        client.get_stats()
        client.get_lists()
        self.ph.fail.append(("status", 500))
        self.ph.sessions.clear()
        try:
            client.get_groups()
        except PiHoleError as exc:
            self.assertNotIn(password, str(exc))
        wrong = PiHoleClient(self.ph.url, "another-wrong-pw", log, timeout=3, clock=self.clock)
        try:
            wrong.get_stats()
        except PiHoleError as exc:
            self.assertNotIn("another-wrong-pw", str(exc))
        everything = dz.all_text()
        self.assertNotIn(password, everything)
        self.assertNotIn("another-wrong-pw", everything)
        self.assertIn("GET /stats/summary", dz.all_text())      # debug output is there

    def test_the_session_id_is_masked_by_the_logger(self):
        self.client.get_stats()
        self.log.Log("header X-FTL-SID: %s" % self.client.sid)
        self.assertNotIn(self.client.sid, dz.all_text())
        self.assertIn("<masked>", dz.all_text())


if __name__ == "__main__":
    unittest.main()
