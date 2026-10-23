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

## Coverage of the Pi-hole API

Compared with the OpenAPI specification in the FTL repository (`src/api/docs/content/specs`, master of 17 October
2026, FTL v6.8): **92 operations**. The plugin uses 7 of them (login, logout, statistics summary, lists and groups
read and write). Everything it calls and every field it reads matches the specification: `type` is a *required*
query parameter of `PUT /lists/{list}` (the plugin always sends it, so allow lists work), a group is renamed by
sending a different `name` in the body (the plugin never does that), and `queries.*`, `clients.*` and
`gravity.domains_being_blocked` are in the summary as the plugin reads them.

One nuance: the devices are named "... Today" (from the plugin before 0.1.0), but the PADD endpoint describes the
same counter as *"within the last 24 hours"*, so it is a rolling window rather than the calendar day. The names are
kept so that existing devices are not renamed.

### What could be added

Ranked by what it gives a Domoticz user, and by what it costs in requests. A feature is a new minor version (see
`checklist.md`); none of this is in 0.1.1.

| # | Candidate | API | Extra requests | Device |
|---|---|---|---|---|
| 1 | **Global blocking switch**, also "pause for N minutes" | `GET/POST /dns/blocking`: `blocking` is `enabled` / `disabled` / `failed` / `unknown`, `timer` the remaining seconds or `null` | one GET per poll | On/Off switch (+ the remaining time as text) |
| 2 | **Queries per second** | `queries.frequency` in `/stats/summary` | none | Custom Sensor `queries/s` |
| 3 | **Gravity last updated** (alert when stale) | `gravity.last_update` in `/stats/summary` (Unix time, `0` = unknown) | none | text, or "hours since" counter |
| 4 | **Query mix**: SERVFAIL / NXDOMAIN / REFUSED replies, blocked-by-regex / deny-list counts, A / AAAA / HTTPS types | `queries.types`, `queries.status`, `queries.replies` in `/stats/summary` | none | Custom Sensors (a SERVFAIL rise means DNS trouble) |
| 5 | **Diagnosis messages** (FTL warnings) | `GET /info/messages/count` | one GET | counter with alert colour when above 0 |
| 6 | **Update available** (core / web / FTL), version in the log | `GET /info/version` (`local` / `remote`; `remote` is `null` on a custom branch) | one GET, hourly is enough | text with alert colour; the version also helps bug reports |
| 7 | **Host health**: CPU, memory, temperature, FTL uptime | `GET /info/system`, `/info/ftl`, `/info/sensors`; `GET /padd` returns CPU, memory, temperature, blocking state, cache and DHCP state in **one** request | one GET | Percentage / Temperature sensors. Little value when Domoticz runs on the Pi-hole itself and already monitors its host |
| 8 | **Upstream health**: queries and response time per upstream DNS server | `GET /stats/upstreams` | one GET | text, or one sensor per upstream (detects a failing upstream) |
| 9 | **Domain rules** as switches: enable or disable an exact / regex allow or deny entry | `GET /domains`, `PUT /domains/{type}/{kind}/{domain}` | one GET | On/Off switches, like lists and groups |
| 10 | **Client groups**: move a client into or out of a group (for example a tablet into *Kids*) | `GET /clients`, `PUT /clients/{client}` (carries `groups`) | one GET | switch per client |
| 11 | **Actions**: update gravity, restart DNS, flush logs / network table | `POST /action/gravity`, `/action/restartdns`, `/action/flush/logs`, `/action/flush/network` | on demand | push buttons. Gravity takes long and a DNS restart interrupts the whole network: only as an explicit option |
| 12 | **What is blocked / who asks** | `GET /stats/recent_blocked`, `/stats/top_domains`, `/stats/top_clients` | one GET each | text. Domain and client names would end up in the Domoticz database and log: only as an explicit option |

Cheapest first: 2, 3 and 4 need no further request at all, because the summary the plugin already reads carries them.
Most useful: 1. Number 7 can be had with a single `GET /padd`.

### Not for a plugin

`/config` and `/teleporter` (settings, backup and restore), `/logs/*`, `/queries` (the query log), `/history*`
(graph data), `/network/*` and `/dhcp/*` (could drive presence detection, but are privacy-sensitive and cost a request
each), `/auth/*` management (`/auth/sessions` lists the sessions, `/auth/app` creates an app password), `/docs`,
`/endpoints`, `/search`.
