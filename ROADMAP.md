# Roadmap

## Current state (0.1.1)

The original goal is reached: a Pi-hole v6 is monitored and its block lists and groups are switched from Domoticz,
with modular, documented and tested code that follows the same standards as the author's other Domoticz plugins.
Developed against a simulated Pi-hole and a simulated Domoticz, **not yet verified on a real installation**. That is
the main gap and the next milestone.

## 0.1.x - verify on real installations

Fix what a real Pi-hole or a real Domoticz does differently from the documentation and the test doubles. Open
points, in the order of how likely they are to matter:

- [ ] Domoticz: renaming a device with `Update(Name=...)` when the Pi-hole renames a list. The Domoticz
      documentation discourages it, the framework source supports it (0.1.1 keeps the hardware prefix and writes only
      the name); confirm it on a real system or replace it by "keep the old name, log once"
- [ ] Domoticz: unit label, in-use state and the "Accept new Hardware Devices" path (0.1.1) on a real system
- [ ] Domoticz: units above the ranges, many devices, the heartbeat of 10 s on a busy system
- [ ] Pi-hole: the reply of `GET /api/lists` / `GET /api/groups` on a real v6 (fields, `type` handling for allow
      lists), and `PUT /api/lists/{address}` for addresses with special characters
- [ ] Pi-hole: login with an app password and with two-factor authentication, the session limit and the 429 rate
      limit as the real server behaves
- [ ] Pi-hole: behaviour while FTL restarts (gravity update, upgrade): the back-off and the log once-rule
- [ ] https with a private CA and a self-signed certificate, `pi.hole` against the IP address
- [ ] Versions: record the Pi-hole and Domoticz versions that work in the README

## 0.2 - more of the Pi-hole API

The whole API was compared with the plugin in 0.1.1; the ranked candidates and their cost in requests are in
[docs/PIHOLE-API.md](docs/PIHOLE-API.md#what-could-be-added). Suggested order:

- [ ] **Global blocking switch** (`/dns/blocking`) including "pause for N minutes": the most useful missing piece
- [ ] Without any further request, from the summary the plugin already reads: **queries per second**,
      **gravity last updated**, and the **reply / status mix** (SERVFAIL, NXDOMAIN, deny-list and regex blocks)
- [ ] **Diagnosis messages** count and **update available** (`/info/messages/count`, `/info/version`); log the Pi-hole
      version at connect
- [ ] Host health through one `GET /padd` (CPU, memory, temperature, cache), for a Pi-hole on another host
- [ ] Upstream health (`/stats/upstreams`)
- [ ] Domain rules and client groups as switches (`/domains`, `/clients`)
- [ ] Optional, off by default: actions (gravity update, DNS restart) and the "what is blocked / who asks" texts
- [ ] Optional: delete a device immediately instead of after three polls (setting)
- [ ] A second poll interval for the lists and groups (they change rarely) if request volume matters

## Release and packaging

- [ ] Publish the GitHub releases (`v0.1.0`, `v0.1.1`) and check that the plugin manager sees them
      (release tags are plain numbers, see `checklist.md`)
- [ ] Verify the plugin on a second Domoticz host (the `deploy.sh --host` workflow)

## Ideas, not planned

- Pi-hole v5 support: it has a different API (`api.php`) and the plugin is deliberately v6-only
- Creating, editing or deleting lists, groups, clients or domains: the plugin only enables and disables
- Running gravity from Domoticz
- A Python HTTP library as a dependency: the point of this project is to have none
