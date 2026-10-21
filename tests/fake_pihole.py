"""A small fake Pi-hole v6 API on a real (optionally TLS) HTTP server, for tests.

It implements the endpoints the plugin uses with the reply shapes of the Pi-hole v6 API (login with a session id,
401 for unknown sessions, ``processed`` results for PUT). Behaviour can be bent per test:

    pihole.fail.append(("status", 500))            the next request answers HTTP 500
    pihole.fail.append(("drop",))                  the next request is cut off without an answer
    pihole.fail.append(("redirect", "https://x/")) the next request answers 301
    pihole.fail.append(("garbage",))               the next request answers 200 with text that is not JSON
    pihole.fail.append(("ok",))                    the next request is served normally (to fail a later one)
    pihole.sessions.clear()                        every session is suddenly unknown (the Pi-hole restarted)
    pihole.ignore_put = True                       PUT answers success but changes nothing
    pihole.put_errors = True                       PUT answers HTTP 200 with processed.errors
"""
import json
import socket
import ssl
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def default_lists():
    return [
        {"id": 1, "address": "https://example.org/ads.txt", "comment": "Ads", "groups": [0], "enabled": True,
         "type": "block"},
        {"id": 2, "address": "https://example.org/social media/list.txt", "comment": "Kids - Social Media",
         "groups": [1], "enabled": False, "type": "block"},
    ]


def default_groups():
    return [
        {"id": 0, "name": "Default", "comment": "The default group", "enabled": True},
        {"id": 1, "name": "Kids", "comment": None, "enabled": True},
    ]


class FakePiHole:
    def __init__(self, password="secret", validity=1800):
        self.password = password
        self.validity = validity
        self.sessions = {}
        self.lists = default_lists()
        self.groups = default_groups()
        self.stats = {
            "queries": {"total": 1234, "blocked": 234, "percent_blocked": 18.962, "unique_domains": 321,
                        "forwarded": 700, "cached": 300},
            "clients": {"active": 7, "total": 11},
            "gravity": {"domains_being_blocked": 99999, "last_update": 1700000000},
            "took": 0.001,
        }
        self.requests = []          # (method, path) of every request
        self.fail = []
        self.ignore_put = False
        self.put_errors = False
        self.logins = 0
        self.lock = threading.Lock()
        self.server = None
        self.thread = None
        self.scheme = "http"

    # -- control --------------------------------------------------------------------------------------------
    def start(self, certfile=None, keyfile=None):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self.server.daemon_threads = True
        self.server.state = self
        if certfile:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(certfile, keyfile)
            self.server.socket = context.wrap_socket(self.server.socket, server_side=True)
            self.scheme = "https"
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
        self.thread.start()
        return self

    def stop(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()

    @property
    def port(self):
        return self.server.server_address[1]

    @property
    def url(self):
        return "%s://127.0.0.1:%d" % (self.scheme, self.port)

    def count(self, method, prefix):
        return len([1 for m, p in self.requests if m == method and p.startswith(prefix)])

    def get_list(self, list_id):
        return next(item for item in self.lists if item["id"] == list_id)

    def get_group(self, group_id):
        return next(item for item in self.groups if item["id"] == group_id)


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):               # silence
        pass

    def do_GET(self):
        self._handle()

    def do_POST(self):
        self._handle()

    def do_PUT(self):
        self._handle()

    def do_DELETE(self):
        self._handle()

    # -- helpers --------------------------------------------------------------------------------------------
    def _send(self, status, payload=None, headers=None, raw=None):
        body = raw if raw is not None else (b"" if payload is None else json.dumps(payload).encode("utf-8"))
        self.send_response(status)
        if status != 204:
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if body and status != 204:
            self.wfile.write(body)

    def _error(self, status, key, message, hint=None):
        self._send(status, {"error": {"key": key, "message": message, "hint": hint}, "took": 0.001})

    def _handle(self):
        state = self.server.state
        parts = urllib.parse.urlsplit(self.path)
        path = parts.path
        query = urllib.parse.parse_qs(parts.query)
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        body = json.loads(raw.decode("utf-8")) if raw else None
        with state.lock:
            state.requests.append((self.command, path))
            if state.fail:
                behaviour = state.fail.pop(0)
                if behaviour[0] == "status":
                    return self._error(behaviour[1], "fake_failure", "Injected failure")
                if behaviour[0] == "drop":
                    self.close_connection = True
                    try:
                        self.connection.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass
                    return
                if behaviour[0] == "redirect":
                    return self._send(301, {"error": "moved"}, {"Location": behaviour[1]})
                if behaviour[0] == "garbage":
                    return self._send(200, raw=b"this is not json")
                # ("ok",) lets this request through: it only moves the failure to a later request
            self._route(state, path, query, body)

    def _session_ok(self, state):
        sid = self.headers.get("X-FTL-SID")
        return bool(sid) and state.sessions.get(sid, 0) > time.time()

    def _route(self, state, path, query, body):
        if path == "/api/auth":
            if self.command == "POST":
                if isinstance(body, dict) and body.get("password") == state.password:
                    state.logins += 1
                    sid = "SID-%d-%s" % (state.logins, "x" * 20)
                    state.sessions[sid] = time.time() + state.validity
                    return self._send(200, {"session": {"valid": True, "totp": False, "sid": sid, "csrf": "csrf",
                                                        "validity": state.validity, "message": "correct password"},
                                            "took": 0.001})
                return self._send(401, {"session": {"valid": False, "totp": False, "sid": None, "csrf": None,
                                                    "validity": -1, "message": "password incorrect"},
                                        "took": 0.001})
            if self.command == "DELETE":
                state.sessions.pop(self.headers.get("X-FTL-SID"), None)
                return self._send(204)
        if not self._session_ok(state):
            return self._error(401, "unauthorized", "Unauthorized", "No sid or an expired sid was sent")
        if self.command == "GET" and path == "/api/stats/summary":
            return self._send(200, state.stats)
        if self.command == "GET" and path == "/api/lists":
            return self._send(200, {"lists": state.lists, "took": 0.001})
        if self.command == "GET" and path == "/api/groups":
            return self._send(200, {"groups": state.groups, "took": 0.001})
        if self.command == "PUT" and path.startswith("/api/lists/"):
            address = urllib.parse.unquote(path[len("/api/lists/"):])
            kind = (query.get("type") or ["block"])[0]
            found = [i for i in state.lists if i["address"] == address and i["type"] == kind]
            return self._put(state, found, body, address)
        if self.command == "PUT" and path.startswith("/api/groups/"):
            name = urllib.parse.unquote(path[len("/api/groups/"):])
            found = [i for i in state.groups if i["name"] == name]
            return self._put(state, found, body, name)
        return self._error(404, "not_found", "Not found", path)

    def _put(self, state, found, body, label):
        if not found:
            return self._error(404, "not_found", "Item not found", label)
        if state.put_errors:
            return self._send(200, {"processed": {"success": [], "errors": [{"item": label, "error": "boom"}]},
                                    "took": 0.001})
        if not state.ignore_put:
            found[0].update({k: v for k, v in body.items() if k in ("enabled", "comment", "groups")})
        return self._send(200, {"processed": {"success": [{"item": label}], "errors": []}, "took": 0.001})
