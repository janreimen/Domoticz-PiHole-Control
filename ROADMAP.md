# Roadmap

## Current state (0.1.0)

The original goal is reached: a Pi-hole v6 is monitored and its block lists and groups are switched from Domoticz,
with modular, documented and tested code that follows the same standards as the author's other Domoticz plugins.
Developed against a simulated Pi-hole and a simulated Domoticz, **not yet verified on a real installation**. That is
the main gap and the next milestone.

## 0.1.x - verify on real installations

Fix what a real Pi-hole or a real Domoticz does differently from the documentation and the test doubles. Open
points, in the order of how likely they are to matter:

- [ ] Domoticz: renaming a device with `Update(Name=...)` when the Pi-hole renames a list (the Domoticz
      documentation discourages it); confirm it works or replace it by "keep the old name, log once"
- [ ] Domoticz: units above the ranges, many devices, the heartbeat of 10 s on a busy system
- [ ] Pi-hole: the reply of `GET /api/lists` / `GET /api/groups` on a real v6 (fields, `type` handling for allow
      lists), and `PUT /api/lists/{address}` for addresses with special characters
- [ ] Pi-hole: login with an app password and with two-factor authentication, the session limit and the 429 rate
      limit as the real server behaves
- [ ] Pi-hole: behaviour while FTL restarts (gravity update, upgrade): the back-off and the log once-rule
- [ ] https with a private CA and a self-signed certificate, `pi.hole` against the IP address
- [ ] Versions: record the Pi-hole and Domoticz versions that work in the README

## 0.2 - ideas for the next features

- [ ] Optional: a switch for the Pi-hole's **global blocking** (`/api/dns/blocking`), including the timer
- [ ] Optional per-client or per-domain statistics (top blocked domain / top client as text devices)
- [ ] Gravity status and last update, and "update available" for core / FTL / web, as text devices
- [ ] Optional: delete a device immediately instead of after three polls (setting)
- [ ] A second poll interval for the lists and groups (they change rarely) if request volume matters

## Release and packaging

- [ ] Publish the first GitHub release (`v0.1.0`) and check that the plugin manager sees it
      (release tags are plain numbers, see `checklist.md`)
- [ ] Verify the plugin on a second Domoticz host (the `deploy.sh --host` workflow)

## Ideas, not planned

- Pi-hole v5 support: it has a different API (`api.php`) and the plugin is deliberately v6-only
- Creating, editing or deleting lists, groups, clients or domains: the plugin only enables and disables
- Running gravity from Domoticz
- A Python HTTP library as a dependency: the point of this project is to have none
