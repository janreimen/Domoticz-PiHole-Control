"""https with a private certificate authority, against a real TLS server (certificates made with openssl)."""
import importlib
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

import domoticz_stub as dz
from fake_pihole import FakePiHole
from helpers import Clock, make_logger
from pihole_control import api
from pihole_control.api import PiHoleClient, PiHoleError, build_ssl_context

EXTENSIONS = (
    "subjectAltName=DNS:localhost,IP:127.0.0.1\n"
    "basicConstraints=critical,CA:FALSE\n"
    "keyUsage=critical,digitalSignature,keyEncipherment\n"
    "extendedKeyUsage=serverAuth\n"
    "subjectKeyIdentifier=hash\n"
    "authorityKeyIdentifier=keyid\n"
)


def openssl(*args, cwd):
    subprocess.run(("openssl",) + args, cwd=cwd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def make_ca(folder, name):
    openssl("req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", name + ".key", "-out", name + ".pem",
            "-days", "2", "-subj", "/CN=Test Root CA " + name, "-addext", "basicConstraints=critical,CA:TRUE",
            "-addext", "keyUsage=critical,keyCertSign,cRLSign", "-addext", "subjectKeyIdentifier=hash", cwd=folder)


def make_server_cert(folder, ca):
    with open(os.path.join(folder, "ext.cnf"), "w") as fh:
        fh.write(EXTENSIONS)
    openssl("req", "-newkey", "rsa:2048", "-nodes", "-keyout", "srv.key", "-out", "srv.csr", "-subj", "/CN=localhost",
            cwd=folder)
    openssl("x509", "-req", "-in", "srv.csr", "-CA", ca + ".pem", "-CAkey", ca + ".key", "-CAcreateserial",
            "-out", "srv.pem", "-days", "2", "-extfile", "ext.cnf", cwd=folder)


@unittest.skipUnless(shutil.which("openssl"), "openssl not installed")
class TlsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.mkdtemp(prefix="pihole-tls-")
        make_ca(cls.folder, "ca")
        make_ca(cls.folder, "other")
        make_server_cert(cls.folder, "ca")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.folder, ignore_errors=True)

    def path(self, name):
        return os.path.join(self.folder, name)

    def setUp(self):
        dz.reset()
        self.ph = FakePiHole().start(self.path("srv.pem"), self.path("srv.key"))
        self.addCleanup(self.ph.stop)
        self.log = make_logger()

    def client(self, ca=None):
        context = build_ssl_context(self.path(ca)) if ca else None
        return PiHoleClient(self.ph.url, "secret", self.log, context, timeout=3, clock=Clock())

    def test_the_private_ca_is_trusted_when_configured(self):
        self.assertTrue(self.ph.url.startswith("https://"))
        self.assertEqual(self.client("ca.pem").get_stats().total_queries, 1234)

    def test_without_the_ca_the_certificate_is_refused(self):
        with self.assertRaises(PiHoleError) as ctx:
            self.client().get_stats()
        self.assertEqual(ctx.exception.kind, api.TLS)
        self.assertIn("certificate chain", str(ctx.exception))
        self.assertEqual(self.ph.logins, 0)                              # no password was sent to an untrusted server

    def test_a_different_ca_is_refused_too(self):
        with self.assertRaises(PiHoleError) as ctx:
            self.client("other.pem").get_stats()
        self.assertEqual(ctx.exception.kind, api.TLS)
        self.assertEqual(self.ph.logins, 0)

    def test_a_broken_chain_file(self):
        broken = self.path("broken.pem")
        with open(broken, "w") as fh:
            fh.write("this is not a certificate")
        with self.assertRaises(PiHoleError) as ctx:
            build_ssl_context(broken)
        self.assertEqual(ctx.exception.kind, api.CONFIG)

    def test_the_whole_plugin_over_https(self):
        sys.modules["Domoticz"] = dz
        self.addCleanup(sys.modules.pop, "Domoticz", None)
        sys.modules.pop("plugin", None)
        plugin = importlib.import_module("plugin")
        plugin.Parameters = {"Address": self.ph.url, "Password": "secret", "Mode1": "60", "Mode6": "0",
                             "Mode2": self.path("ca.pem")}
        plugin.Devices = dz.Devices
        plugin.onStart()
        self.assertEqual(dz.messages("error"), [])
        self.assertEqual(sorted(dz.Devices), list(range(1, 11)) + [100, 101, 200, 201])
        plugin.onStop()
        plugin.Parameters["Mode2"] = ""                                  # the same server without its CA
        dz.reset()
        plugin.onStart()
        self.assertEqual(len(dz.messages("error")), 1)
        self.assertIn("TLS error", dz.messages("error")[0])


if __name__ == "__main__":
    unittest.main()
