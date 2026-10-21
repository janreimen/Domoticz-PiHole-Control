import os
import tempfile
import unittest

import helpers  # noqa: F401  (sets sys.path)
from pihole_control.config import Settings, SettingsError, parse_debug


def params(**kw):
    base = {"Address": "http://192.168.1.2", "Password": "secret", "Mode1": "60", "Mode2": "", "Mode6": "0"}
    base.update(kw)
    return base


class UrlTests(unittest.TestCase):
    def check(self, given, expected, notes=0):
        settings = Settings.from_parameters(params(Address=given))
        self.assertEqual(settings.base_url, expected)
        self.assertEqual(len(settings.notes), notes, settings.notes)

    def test_plain_urls(self):
        self.check("http://192.168.1.2", "http://192.168.1.2")
        self.check("http://192.168.1.2/", "http://192.168.1.2")
        self.check("  https://pi.hole:8443  ", "https://pi.hole:8443")
        self.check("http://[::1]:8080", "http://[::1]:8080")
        self.check("http://pi.hole/pihole/", "http://pi.hole/pihole")

    def test_corrections_are_reported(self):
        self.check("192.168.1.2", "http://192.168.1.2", notes=1)                 # no scheme
        self.check("http://pi.hole/admin", "http://pi.hole", notes=1)            # the UI path
        self.check("HTTPS://Pi.Hole:8443/admin/", "https://Pi.Hole:8443", notes=1)
        self.check("http://pi.hole/api", "http://pi.hole", notes=1)

    def test_invalid_urls_are_refused(self):
        for bad in ("", "   ", "ftp://pi.hole", "http://", "http://user:pw@pi.hole", "http://pi.hole:99999",
                    "http://pi.hole:abc", "http://pi.hole/?a=1", "http://pi.hole/#x"):
            with self.assertRaises(SettingsError, msg=bad):
                Settings.from_parameters(params(Address=bad))

    def test_credentials_in_the_url_are_not_echoed(self):
        with self.assertRaises(SettingsError) as ctx:
            Settings.from_parameters(params(Address="http://admin:hunter2@pi.hole"))
        self.assertNotIn("hunter2", str(ctx.exception))


class FieldTests(unittest.TestCase):
    def test_defaults(self):
        s = Settings.from_parameters({"Address": "http://pi.hole", "Password": "pw"})
        self.assertEqual((s.interval, s.ca_file, s.debug, s.https), (60, "", 0, False))

    def test_password_is_required_and_never_trimmed(self):
        with self.assertRaises(SettingsError):
            Settings.from_parameters(params(Password=""))
        self.assertEqual(Settings.from_parameters(params(Password=" pw ")).password, " pw ")

    def test_interval(self):
        self.assertEqual(Settings.from_parameters(params(Mode1="")).interval, 60)
        self.assertEqual(Settings.from_parameters(params(Mode1="30")).interval, 30)
        self.assertEqual(Settings.from_parameters(params(Mode1="45.7")).interval, 45)
        low = Settings.from_parameters(params(Mode1="5"))
        self.assertEqual((low.interval, len(low.notes)), (10, 1))
        self.assertEqual(Settings.from_parameters(params(Mode1="99999")).interval, 3600)
        with self.assertRaises(SettingsError):
            Settings.from_parameters(params(Mode1="soon"))

    def test_debug_levels_and_the_values_of_the_old_plugin(self):
        for text, level in (("0", 0), ("1", 1), ("2", 2), ("3", 3), ("7", 3), ("-1", 0), ("junk", 0), ("", 0),
                            ("Normal", 0), ("Debug", 3), ("True", 3), ("False", 0)):
            self.assertEqual(parse_debug(text), level, text)

    def test_certificate_chain(self):
        with tempfile.NamedTemporaryFile(suffix=".pem") as pem:
            s = Settings.from_parameters(params(Address="https://pi.hole", Mode2=pem.name))
            self.assertEqual((s.ca_file, s.https), (pem.name, True))
            ignored = Settings.from_parameters(params(Address="http://pi.hole", Mode2=pem.name))
            self.assertEqual(ignored.ca_file, "")
            self.assertEqual(len(ignored.notes), 1)
        with self.assertRaises(SettingsError) as ctx:
            Settings.from_parameters(params(Address="https://pi.hole", Mode2="/does/not/exist.pem"))
        self.assertIn("/does/not/exist.pem", str(ctx.exception))
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(SettingsError):                        # a directory is not a chain file
                Settings.from_parameters(params(Address="https://pi.hole", Mode2=folder))

    @unittest.skipIf(os.name != "posix" or os.geteuid() == 0, "needs a non-root POSIX user")
    def test_unreadable_certificate_chain(self):
        with tempfile.NamedTemporaryFile(suffix=".pem") as pem:
            os.chmod(pem.name, 0)
            with self.assertRaises(SettingsError):
                Settings.from_parameters(params(Address="https://pi.hole", Mode2=pem.name))


if __name__ == "__main__":
    unittest.main()
