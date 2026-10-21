# Pi-hole API used by the plugin

The plugin talks to the **Pi-hole v6** REST API (`<url>/api`). It only uses the calls below; the client is
[`pihole_control/api.py`](../pihole_control/api.py). Official reference: <https://docs.pi-hole.net/api/>, and the
interactive documentation of your own Pi-hole at `<url>/api/docs`.

| Call | Used for | Notes |
|---|---|---|
| `POST /api/auth` `{"password": "..."}` | log in | the reply carries `session.sid` and `session.validity` (seconds, 300 by default). An invalid password is HTTP 401 with `session.message` |
| `DELETE /api/auth` | log out | frees the session; done when the hardware is stopped and before a session is renewed. Answer: 204 |
| `GET /api/stats/summary` | statistics devices | `queries.*`, `clients.*`, `gravity.domains_being_blocked` |
| `GET /api/lists` | list switches | `id`, `address`, `comment`, `groups`, `enabled`, `type` |
| `GET /api/groups` | group switches | `id`, `name`, `comment`, `enabled` |
| `PUT /api/lists/{address}?type=block` | switch a list | `{"enabled", "comment", "groups", "address", "type"}`; the address is URL-encoded in the path. All other fields are sent unchanged so the comment and the groups survive |
| `PUT /api/groups/{name}` | switch a group | `{"name", "comment", "enabled"}`; groups are addressed by **name**, not by id |

## Authentication

* The session id is sent in the `X-FTL-SID` header. The plugin never uses the cookie variant (which would need the
  CSRF token as well).
* **One session is reused.** The Pi-hole extends a session with every request and only has a limited number of
  concurrent sessions, so the plugin logs in once, keeps the session alive by polling, logs in again only when the
  Pi-hole answers 401 (or the session is about to run out because polling was paused), and logs out at shutdown.
* Use an **app password** (Pi-hole: Settings > Web interface / API, expert mode). It works with two-factor
  authentication switched on; the plugin does not ask for a TOTP code.
* A rejected login is retried only after 5 minutes (and then 10 and 15), so a wrong password does not run into the
  Pi-hole's limit for login attempts (HTTP 429).

## What a change request looks like

A switch in Domoticz is never reported as done because a request was sent: after the `PUT` the plugin reads the lists
and groups back and compares. If the Pi-hole reports another state, the switch shows the real state and an error is
logged.

## Not used (yet)

* `GET/POST /api/dns/blocking` (the global blocking switch with a timer): see the [roadmap](../ROADMAP.md).
* Query log, top domains, top clients, per-client groups.
