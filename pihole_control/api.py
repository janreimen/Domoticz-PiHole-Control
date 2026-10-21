"""Pi-hole v6 REST client. Standard library only; knows nothing about Domoticz.

Endpoints used (all below ``<url>/api``):

    POST   /auth                 log in; the reply carries the session id (sid) and its validity in seconds
    DELETE /auth                 log out (frees the session "seat" on the Pi-hole)
    GET    /stats/summary        statistics
    GET    /lists                block and allow lists
    GET    /groups               groups
    PUT    /lists/{address}      enable / disable a list  (?type=block|allow)
    PUT    /groups/{name}        enable / disable a group

Behaviour worth knowing:

    * One session is reused for as long as it is valid (the Pi-hole only has a limited number of seats); when
      the Pi-hole answers 401 the client logs in again once and repeats the request.
    * Redirects are never followed (a POST would silently turn into a GET); the error names the target instead.
    * Environment proxies are ignored: the Pi-hole is a LAN host.
    * Certificates are always verified. A private CA is given as a PEM file (``build_ssl_context``).
"""
import http.client
import json
import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Dict, List, Optional

from .constants import API_TIMEOUT, DEFAULT_SESSION_VALIDITY, SESSION_RENEW_MARGIN, USER_AGENT
from .model import BlockList, Group, Stats
from .util import safe_float, safe_int

# kinds of PiHoleError; the controller decides on retries from them
CONNECTION = "connection"   # no answer: refused, unreachable, timeout, reset
TLS = "tls"                 # certificate or handshake problem
AUTH = "auth"               # login rejected, or still 401 after logging in again
REDIRECT = "redirect"       # the Pi-hole answered with a redirect
RATE = "rate"               # HTTP 429
HTTP = "http"               # any other HTTP error status
INVALID = "invalid"         # an answer that is not what the Pi-hole API documents
CONFIG = "config"           # local configuration problem (certificate file)


class PiHoleError(Exception):
    def __init__(self, message: str, kind: str = HTTP, status: Optional[int] = None) -> None:
        Exception.__init__(self, message)
        self.kind = kind
        self.status = status


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):    # noqa: D401  (urllib hook)
        return None                                                      # urllib then raises HTTPError(3xx)


def build_ssl_context(ca_file: str) -> ssl.SSLContext:
    """Verifying context that trusts exactly the certificates in ``ca_file`` (RootCA and SubCAs in one PEM)."""
    try:
        return ssl.create_default_context(cafile=ca_file)
    except (OSError, ssl.SSLError) as exc:
        raise PiHoleError("Cannot load the certificate chain %s: %s" % (ca_file, exc), kind=CONFIG)


def _api_message(body: Any) -> str:
    """The human readable part of a Pi-hole error body ({"error": {...}} or {"session": {...}})."""
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict):
            text = str(error.get("message") or error.get("key") or "")
            if error.get("hint"):
                text += " (%s)" % error["hint"]
            if text:
                return text
        session = body.get("session")
        if isinstance(session, dict) and session.get("message"):
            return str(session["message"])
    return ""


class PiHoleClient:
    def __init__(self, base_url: str, password: str, logger: Any, ssl_context: Optional[ssl.SSLContext] = None,
                 timeout: int = API_TIMEOUT, clock: Callable[[], float] = time.monotonic) -> None:
        self.base_url = base_url.rstrip("/")
        self._password = password
        self.log = logger
        self.timeout = timeout
        self.clock = clock
        self.sid: Optional[str] = None
        self._sid_expires = 0.0         # when the session runs out if nothing is sent (every request extends it)
        self._validity = DEFAULT_SESSION_VALIDITY
        handlers = [urllib.request.ProxyHandler({}), _NoRedirect()]
        if ssl_context is not None:
            handlers.append(urllib.request.HTTPSHandler(context=ssl_context))
        self._opener = urllib.request.build_opener(*handlers)
        self.requests = 0               # number of HTTP requests sent (diagnostics, tests)

    # -- session --------------------------------------------------------------------------------------------
    def authenticate(self) -> None:
        self.sid = None
        body = self._request("POST", "/auth", "/auth", {"password": self._password}, auth=False)
        session = body.get("session") if isinstance(body, dict) else None
        if not isinstance(session, dict):
            raise PiHoleError("Unexpected login reply (no session object)", kind=INVALID)
        if not session.get("valid"):
            reason = str(session.get("message") or "login rejected")
            if session.get("totp"):
                reason += " (two-factor authentication is on: use an app password)"
            raise PiHoleError("Login rejected: %s" % reason, kind=AUTH, status=401)
        sid = session.get("sid")
        if not sid:
            raise PiHoleError("Login accepted but the Pi-hole sent no session id", kind=INVALID)
        self.sid = str(sid)
        self.log.add_secret(self.sid)
        validity = safe_int(session.get("validity"), DEFAULT_SESSION_VALIDITY) or DEFAULT_SESSION_VALIDITY
        self._validity = max(validity, 2 * SESSION_RENEW_MARGIN)
        self._sid_expires = self.clock() + self._validity
        self.log.Verbose("Logged in to the Pi-hole (session valid for %d s)" % validity)

    def logout(self, timeout: Optional[int] = None) -> None:
        """Free the session seat. Best effort: never raises."""
        if not self.sid:
            return
        try:
            self._request("DELETE", "/auth", "/auth", timeout=timeout)
            self.log.Verbose("Logged out of the Pi-hole")
        except PiHoleError as exc:
            self.log.Verbose("Logout failed (ignored): %s" % exc)
        finally:
            self.sid = None

    def _session_current(self) -> bool:
        return self.sid is not None and self.clock() < self._sid_expires - SESSION_RENEW_MARGIN

    # -- reads ----------------------------------------------------------------------------------------------
    def get_stats(self) -> Stats:
        return parse_stats(self._call("GET", "/stats/summary", "/stats/summary"))

    def get_lists(self) -> List[BlockList]:
        return parse_lists(self._call("GET", "/lists", "/lists"))

    def get_groups(self) -> List[Group]:
        return parse_groups(self._call("GET", "/groups", "/groups"))

    # -- writes ---------------------------------------------------------------------------------------------
    def set_list_enabled(self, item: BlockList, enabled: bool) -> None:
        """Enable or disable a list. All other fields are sent unchanged so that comment and groups survive."""
        if not item.address:
            raise PiHoleError("List %d has no address" % item.id, kind=INVALID)
        body = {"enabled": bool(enabled), "comment": item.comment, "groups": list(item.groups),
                "address": item.address, "type": item.type}
        path = "/lists/%s" % urllib.parse.quote(item.address, safe="")
        result = self._call("PUT", path, "/lists/<address>", body, query="type=%s" % urllib.parse.quote(item.type))
        _check_processed(result, "list %d" % item.id)

    def set_group_enabled(self, item: Group, enabled: bool) -> None:
        """Enable or disable a group (the Pi-hole addresses groups by name, not by id)."""
        body = {"name": item.name, "comment": item.comment, "enabled": bool(enabled)}
        path = "/groups/%s" % urllib.parse.quote(item.name, safe="")
        result = self._call("PUT", path, "/groups/<name>", body)
        _check_processed(result, "group %d" % item.id)

    # -- transport ------------------------------------------------------------------------------------------
    def _call(self, method: str, path: str, label: str, body: Any = None, query: str = "") -> Any:
        """An authenticated request: logs in when needed, and once more when the Pi-hole says 401."""
        if self.sid is not None and not self._session_current():
            self.logout()                           # free the seat of a session that is about to run out
        if self.sid is None:
            self.authenticate()
        try:
            return self._request(method, path, label, body, query=query)
        except PiHoleError as exc:
            if exc.status != 401:
                raise
            self.log.Verbose("Session rejected by the Pi-hole, logging in again")
            self.authenticate()
            try:
                return self._request(method, path, label, body, query=query)
            except PiHoleError as again:
                if again.status == 401:
                    raise PiHoleError("Pi-hole keeps answering 401 after logging in: %s" % again, kind=AUTH, status=401)
                raise

    def _request(self, method: str, path: str, label: str, body: Any = None, auth: bool = True,
                 query: str = "", timeout: Optional[int] = None) -> Any:
        url = "%s/api%s%s" % (self.base_url, path, "?" + query if query else "")
        headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if auth and self.sid:
            headers["X-FTL-SID"] = self.sid
        request = urllib.request.Request(url, data=data, method=method, headers=headers)
        self.requests += 1
        try:
            with self._opener.open(request, timeout=timeout or self.timeout) as response:
                raw = response.read()
                status = response.status
        except urllib.error.HTTPError as exc:
            raise self._http_error(exc, method, label)
        except urllib.error.URLError as exc:
            raise self._transport_error(exc.reason if exc.reason is not None else exc, method, label)
        except (OSError, http.client.HTTPException) as exc:
            raise self._transport_error(exc, method, label)
        self.log.Debug("%s %s -> HTTP %s (%d bytes)" % (method, label, status, len(raw)))
        if auth and self.sid:
            self._sid_expires = self.clock() + self._validity      # the Pi-hole extends a session on every request
        if not raw.strip():
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except ValueError:
            raise PiHoleError("%s %s: the reply is not valid JSON" % (method, label), kind=INVALID, status=status)

    def _http_error(self, exc: urllib.error.HTTPError, method: str, label: str) -> PiHoleError:
        try:
            raw = exc.read()
            body = json.loads(raw.decode("utf-8")) if raw.strip() else None
        except (OSError, ValueError):
            body = None
        finally:
            exc.close()
        text = _api_message(body)
        status = exc.code
        self.log.Debug("%s %s -> HTTP %s %s" % (method, label, status, text))
        if 300 <= status < 400:
            target = exc.headers.get("Location", "") if exc.headers else ""
            return PiHoleError("%s %s: the Pi-hole redirects to %s - use that address as Pi-hole URL"
                               % (method, label, target or "another address"), kind=REDIRECT, status=status)
        message = "%s %s: HTTP %d %s%s" % (method, label, status, exc.reason or "", " - " + text if text else "")
        if status == 401:
            return PiHoleError(message, kind=AUTH, status=status)
        if status == 429:
            return PiHoleError(message, kind=RATE, status=status)
        return PiHoleError(message, kind=HTTP, status=status)

    def _transport_error(self, reason: Any, method: str, label: str) -> PiHoleError:
        if isinstance(reason, ssl.SSLError):
            return PiHoleError("%s %s: TLS error: %s. Check the certificate chain file (RootCA and SubCAs, PEM) "
                               "and that the URL uses the certificate's host name" % (method, label, reason), kind=TLS)
        if isinstance(reason, socket.timeout):
            return PiHoleError("%s %s: no answer within %d s" % (method, label, self.timeout), kind=CONNECTION)
        return PiHoleError("%s %s: %s" % (method, label, reason), kind=CONNECTION)


# -- parsing ------------------------------------------------------------------------------------------------
def parse_stats(data: Any) -> Stats:
    queries = data.get("queries") if isinstance(data, dict) else None
    if not isinstance(queries, dict):
        raise PiHoleError("Unexpected statistics reply (no 'queries' object)", kind=INVALID)
    clients = data.get("clients") if isinstance(data.get("clients"), dict) else {}
    gravity = data.get("gravity") if isinstance(data.get("gravity"), dict) else {}
    return Stats(
        total_queries=safe_int(queries.get("total")),
        blocked_queries=safe_int(queries.get("blocked")),
        percent_blocked=safe_float(queries.get("percent_blocked")),
        unique_domains=safe_int(queries.get("unique_domains")),
        forwarded=safe_int(queries.get("forwarded")),
        cached=safe_int(queries.get("cached")),
        clients_active=safe_int(clients.get("active")),
        clients_total=safe_int(clients.get("total")),
        domains_blocked=safe_int(gravity.get("domains_being_blocked")),
    )


def _items(data: Any, key: str) -> List[Dict[str, Any]]:
    items = data.get(key) if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise PiHoleError("Unexpected reply (no '%s' array)" % key, kind=INVALID)
    return [item for item in items if isinstance(item, dict) and safe_int(item.get("id")) is not None]


def parse_lists(data: Any) -> List[BlockList]:
    result = []
    for item in _items(data, "lists"):
        groups = [g for g in (safe_int(x) for x in (item.get("groups") or [])) if g is not None]
        result.append(BlockList(id=safe_int(item["id"]), address=str(item.get("address") or ""),
                                comment=str(item.get("comment") or ""), groups=groups,
                                enabled=bool(item.get("enabled", False)), type=str(item.get("type") or "block")))
    return result


def parse_groups(data: Any) -> List[Group]:
    return [Group(id=safe_int(item["id"]), name=str(item.get("name") or ""), comment=str(item.get("comment") or ""),
                  enabled=bool(item.get("enabled", True))) for item in _items(data, "groups")]


def _check_processed(result: Any, what: str) -> None:
    """A PUT is only a success when the Pi-hole reports no error for the item."""
    if not isinstance(result, dict):
        return
    if result.get("error"):
        raise PiHoleError("Pi-hole refused the change of %s: %s" % (what, _api_message(result) or result["error"]))
    processed = result.get("processed")
    if isinstance(processed, dict) and processed.get("errors"):
        raise PiHoleError("Pi-hole reported errors changing %s: %s" % (what, processed["errors"]))
