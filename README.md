# Domoticz-PiHole-Control

A [Domoticz](https://www.domoticz.com) plugin that **monitors a Pi-hole v6** and lets Domoticz **switch its block
lists and groups** on and off, for example for parental-control schedules ("Kids" group off at 20:00).

* **Statistics.** DNS queries, blocked queries, percentage blocked, domains on the blocklists, forwarded and cached
  queries, clients, unique domains, and a "Pi-hole Status" switch that shows whether the Pi-hole answers.
* **One switch per block list and per group.** Lists and groups you add, rename or delete in the Pi-hole appear,
  change and disappear in Domoticz by themselves.
* **No Python packages at all.** Standard library only, Python 3.7 or newer.
* **http and https**, also with a private certificate authority. Certificates are always verified.
* **Quiet and careful.** A problem is logged once and its recovery once; a Pi-hole that is down is asked less and
  less often; a command is checked by reading the state back from the Pi-hole; passwords and session ids never
  reach the log.
* **Modular.** API client, settings, device layer and polling logic are separate modules; only `plugin.py` touches
  Domoticz.

> **Status:** version 0.1.0. Developed and tested against a simulated Pi-hole v6 (a real HTTP / TLS server inside
> the test suite) and a simulated Domoticz, **not yet against a real Domoticz and a real Pi-hole**. Please read
> [what is verified and what is not](#what-is-verified-and-what-is-not) and watch the log during your first run.

Contents: [Requirements](#requirements) · [App password](#create-an-app-password-recommended) · [Install](#install) ·
[Settings](#settings) · [Devices](#devices) · [Scheduling](#scheduling-a-group-or-a-list) ·
[How it works](#how-it-works) · [Troubleshooting](#troubleshooting) · [FAQ](#faq) ·
[Upgrading](#upgrading-from-the-plugin-before-010) · [Verified](#what-is-verified-and-what-is-not) ·
[Development](#development) · [Credits](#credits) · [License](#license)

## Requirements

| Where | What |
|---|---|
| Domoticz host | Domoticz with Python plugin support, **Python 3.7+** |
| Pi-hole | **Pi-hole v6** (FTL 6.x with the REST API). Pi-hole v5 and older have no such API and do not work |
| Network | Domoticz host can reach the Pi-hole's web interface (port 80 / 443) |

Tested with the Pi-hole versions Core 6.1.2, FTL 6.2.3 and Web 6.2.1 by the original author of the plugin; see
[what is verified](#what-is-verified-and-what-is-not).

## Create an app password (recommended)

The plugin logs in to the Pi-hole with a password and keeps one session open. You can use the password of the web
interface, but an **app password** is better: it is made for exactly this, it works when two-factor authentication
is switched on, and you can revoke it without changing your own password.

In the Pi-hole web interface: *Settings > Web interface / API*, switch to **Expert** mode, press **Configure app
password**, copy the generated password (it is shown once) and enter it in the plugin's *Password* field.

## Install

```sh
cd /srv/domoticz/plugins                  # your Domoticz plugin directory, e.g. ~/domoticz/plugins
git clone https://github.com/janreimen/Domoticz-PiHole-Control.git
sudo systemctl restart domoticz
```

`plugin.py` and the `pihole_control/` directory must stay together. The directory name does not matter to Domoticz
(the plugin is identified by its `key`, `PiHole`). Use one directory per plugin; do not leave an old copy next to it.

Or use the bundled [`deploy.sh`](DEPLOY.md), which installs locally or over SSH, checks the syntax of the new files,
makes a backup, restores ownership and restarts Domoticz:

```sh
./deploy.sh --host jan@rpi4office
```

Then *Setup > Hardware*, type **Pi-hole Monitor and Control - https Version**, fill in the [settings](#settings),
*Add*. Full instructions, updates, rollback and removal: **[DEPLOY.md](DEPLOY.md)**.

## Settings

| Field | Meaning |
|---|---|
| Pi-hole URL | Address of the web interface, for example `http://192.168.1.2` or `https://pi.hole`. `http://` is assumed when the scheme is missing. A trailing `/admin` or `/api` and a trailing `/` are removed. Credentials, a query or a fragment in the URL are refused (use the Password field) |
| Web Interface / App Password | The password or, better, an [app password](#create-an-app-password-recommended). Required. It is never trimmed, never written to the log and never sent anywhere but to the Pi-hole |
| Update Interval (seconds) | Seconds between polls. Default 60, allowed 10 to 3600; other values are corrected and the log says so |
| Certificate Chain Path | **https with a private CA only:** a PEM file with the root and sub CA certificates, for example `/srv/domoticz/chain.pem`. It must exist and be readable by the Domoticz user. Empty = the system's CA store. Ignored (with a log line) for `http://` |
| Debug | `Off` (default), `Basic` (what happens when), `Verbose` (adds logins and skipped items), `Debug` (every request and the plugin's Domoticz updates). Debug lines never contain the password or the session id |

Several Pi-holes: add the hardware once per Pi-hole. Each gets its own set of devices.

## Devices

| Units | Devices | Created when |
|---|---|---|
| 1 - 9 | **Statistics**: DNS Queries Today, Ads Blocked Today, Ads Percentage, Domains in Blocklist, Queries Forwarded, Queries Cached, Clients Ever Seen, Unique Clients, Unique Domains (read-only) | missing at start |
| 10 | **Pi-hole Status**: On while the Pi-hole answers, Off while it does not (read-only; switching it is refused and reset) | missing at start |
| 100 - 199 | **Block lists**: one On/Off switch per list, named `List: <comment> (<groups>)` | the list exists in the Pi-hole |
| 200 - 255 | **Groups**: one On/Off switch per group, named `Group: <name>` | the group exists in the Pi-hole |

On = the list or group is **enabled** in the Pi-hole. Switching a device Off disables the list (it stops blocking) or
the group (the Pi-hole stops applying that group's lists to its clients), exactly as the toggle in the Pi-hole web
interface does.

The full list with types, unit labels and API sources is generated from the code into
**[docs/DEVICES.md](docs/DEVICES.md)**; the API calls the plugin uses are in **[docs/PIHOLE-API.md](docs/PIHOLE-API.md)**.

**Devices are matched by what they stand for, never by their name.** A list or group device carries the Pi-hole's id
in its *Description* (`ListID:12`, `GroupID:3`); do not edit that field. You may rename a device in Domoticz: the
plugin only changes a name when the *Pi-hole's* name changes, never at start-up. A list or group that is gone from
the Pi-hole loses its device after it was missing for three polls in a row, so one odd answer can not delete a device
and its history.

## Scheduling a group or a list

Use Domoticz' timers or `dzVents` like for any switch. Example for a parental-control schedule: enable the *Kids*
group (or the list `List: Kids - Social Media (Kids)`) at 06:00 and disable it at 20:00.

```lua
-- dzVents: the Kids group (and with it its block lists) is on from 06:00 to 20:00 on school days
return {
    on = { timer = { "at 06:00 on mon, tue, wed, thu, fri", "at 20:00 on mon, tue, wed, thu, fri" } },
    execute = function(domoticz, timer)
        local kids = domoticz.devices("Group: Kids")
        if timer.trigger == "at 06:00 on mon, tue, wed, thu, fri" then kids.switchOn() else kids.switchOff() end
    end
}
```

After a command the plugin asks the Pi-hole for the new state and reports it (`Group 3 (Group: Kids) is now
enabled`). If the Pi-hole does not take the change, the device is put back and the log says so.

## How it works

```
plugin.py               Domoticz glue only: manifest, callbacks, wiring
pihole_control/
    constants.py        names, unit ranges, limits, the statistics device table
    config.py           Settings: validation of the hardware page
    api.py              PiHoleClient: login / session, GET and PUT, error classification, TLS context
    controller.py       polling, back-off, problem log-once, commands with read-back
    devices.py          DeviceManager: the only module that calls the Domoticz device API
    logger.py           four log levels, secrets masked
    model.py, util.py   small data types and helpers
docs/                   DEVICES.md (generated), PIHOLE-API.md
tests/                  unit tests, a fake Pi-hole (HTTP and TLS), a Domoticz stub
tools/                  gen_device_catalog.py
```

* **Heartbeat 10 s, polling by time.** Domoticz logs a plugin as "not responding" when its heartbeat is longer than
  30 seconds, so the heartbeat stays at 10 s and the plugin polls when the interval has elapsed. A poll takes up to three requests (statistics,
  groups, lists), each with a 10 s time-out.
* **One session.** The plugin logs in once, reuses the session (the Pi-hole extends it with every request) and logs
  out when Domoticz stops the hardware. When the session expires or is rejected it logs in again; it never piles up
  sessions, which the Pi-hole limits.
* **Back-off.** After a failed poll the next attempt is delayed (twice the interval, then four times, up to five
  minutes; for login, TLS and redirect problems at least five minutes, up to fifteen, because retrying a wrong
  password quickly only trips the Pi-hole's login rate limit). The first successful poll resets it.
* **Log once.** A problem is an *Error* in the log once, repeats appear only with Debug *Verbose*, and the recovery
  is one line.
* **Commands are verified.** A switch change is sent, then the Pi-hole is read again; a command that did not take
  effect is reported and the Domoticz device shows the truth again.
* **Never blocks, never crashes Domoticz.** Every callback is wrapped; an unexpected exception is logged once with
  its name, details at Debug level.

## Troubleshooting

Set *Debug* to **Basic** first; **Debug** shows every request. The messages below are the ones the plugin writes.

| Log message | Cause / fix |
|---|---|
| `Configuration error: No Pi-hole password configured ...` | the password field is empty |
| `Configuration error: The Pi-hole URL must start with http:// or https://` (or has no host, contains credentials ...) | fix the *Pi-hole URL* field |
| `Configuration error: Certificate chain file not found: ...` | the path in *Certificate Chain Path* is wrong or not readable by the Domoticz user |
| `Pi-hole poll failed: ... Login rejected: ...` | wrong password, or two-factor authentication is on: create an [app password](#create-an-app-password-recommended). The plugin waits at least 5 minutes before the next login |
| `... HTTP 429 ...` | the Pi-hole's login rate limit: do not restart the hardware (that logs in again and makes it worse), wait a few minutes |
| `... TLS error: ... Check the certificate chain file` | the certificate is not trusted (set *Certificate Chain Path* to a PEM with root *and* sub CAs), expired, or the URL does not use the host name in the certificate (use `https://pi.hole`, not the IP address) |
| `... the Pi-hole redirects to <address> - use that address as Pi-hole URL` | the URL redirects, for example http to https or to another host name; use the target address. The plugin never follows redirects, because a password must not be sent to a place you did not configure |
| `... no answer within 10 s` or `Connection refused` | the Pi-hole or its web server is down, the address or port is wrong, or a firewall blocks it |
| `Could not create the device of list N` / `No free Domoticz unit left for more lists` | more than 100 lists (or 56 groups): delete devices you do not need, or disable lists in the Pi-hole you do not control from Domoticz |
| `Cannot update Domoticz unit N: no such device` | the device was deleted in Domoticz; it is created again on the next poll while the list or group exists |
| `The Pi-hole accepted the request but still reports list N (...) as enabled` | the Pi-hole did not apply the change (a gravity update in progress, or a second admin changed it back). Try again |
| `Unexpected error in ...` | a bug: please open an issue with the line and, with Debug on, the lines after it |

## FAQ

**Which Pi-hole versions work?** Pi-hole v6 and newer. Version 5 has no REST API.

**Can I use the web password although I have two-factor authentication?** No, the login needs the second factor. Use
an app password.

**The plugin is on https and the log says TLS error.** Python verifies certificates and checks the host name. Use
the name from the certificate in the URL and, for a private CA, put the root and sub CA certificates in one PEM file
and enter its path. See the table above.

**Group switch or list switch?** A *group* switch enables or disables a whole group, a *list* switch a single list.
Use whichever matches how you set up the Pi-hole.

**Does the plugin change anything in the Pi-hole besides lists and groups?** No. It enables and disables lists and
groups, it does not create, edit or delete anything, and it does not run gravity.

**Can I disable "Pi-hole Status"?** Delete the device in Domoticz; it comes back at the next start of the hardware.
The plugin needs it to show that the Pi-hole is unreachable.

## Upgrading from the plugin before 0.1.0

Replace the files, restart Domoticz. Nothing else is needed:

* The **plugin key (`PiHole`) and the hardware type name are unchanged**, so the existing hardware keeps working.
  The directory name (for example `PiHole-HTTPS`) may stay.
* **All devices are kept**: the statistics devices still use units 1 - 10, block lists start at unit 100 and groups at
  unit 200 as before, and their `ListID:` / `GroupID:` descriptions are recognised. History, scenes, scripts and
  schedules stay.
* The old **Debug** values `Normal` / `Debug` (shown as *False* / *True*) are understood; the page now offers
  *Off / Basic / Verbose / Debug*.
* **Behaviour changes** you may notice: any command other than *On* used to be treated as *Off* and is now refused
  with a log line; an unreachable Pi-hole is retried with a back-off instead of every interval; the Pi-hole Status
  device now reflects the connection; redirects are not followed; the Pi-hole's group names come from the Pi-hole
  (the old code had `Default` and `Kids` built in); the session is reused and logged out at stop.
* Please look at the log of the first start; if a device behaves differently from before, open an issue.

See the [CHANGELOG](CHANGELOG.md) for the complete list.

## What is verified and what is not

**Verified (by the test suite and by reading the Domoticz and Pi-hole documentation):**

* settings parsing and URL normalisation, including the odd inputs people type;
* the login, session reuse, renewal, rejection and logout against a fake Pi-hole v6 that is a real HTTP and TLS
  server (including a CA you create yourself, a wrong host name, an expired session, a rate limit, redirects,
  garbage replies and dropped connections);
* that the password and the session id never reach the log, at any level, including in error texts;
* the device logic against a stub of the Domoticz API: creation, matching, renaming, removal grace, a full unit
  range, deleted devices, commands, read-back, refused commands;
* that `plugin.py` binds none of the names Domoticz injects, imports only the standard library and is the only
  module that imports `Domoticz`; Python 3.7 compatibility (`vermin`).

**Not verified:**

* **a real Domoticz.** The stub follows the documentation, but Domoticz has details of its own. In particular the
  plugin renames a device with `Update(Name=...)` when the Pi-hole renames a list, which the Domoticz documentation
  discourages; it is guarded and logged, and the old name stays when it fails.
* **a real Pi-hole.** The fake server follows the Pi-hole API documentation; real replies may carry fields or
  differences it does not know. Fields the plugin does not understand are ignored, and a missing value leaves its
  device untouched.
* **Pi-hole versions other than** the ones listed above, and Domoticz versions other than 2025.2.

Reports from real installations, also "it works on my setup", are very welcome: [open an issue](https://github.com/janreimen/Domoticz-PiHole-Control/issues).

## Development

```sh
git clone https://github.com/janreimen/Domoticz-PiHole-Control.git
cd Domoticz-PiHole-Control
make test            # python3 -m unittest discover -s tests
make check           # tests + flake8 + shellcheck + Python 3.7 compatibility (vermin) + generated docs up to date
make package         # dist/Domoticz-PiHole-Control-<version>.tar.gz
```

Rules, how to add a device and how to prepare a release: [CONTRIBUTING.md](CONTRIBUTING.md) and
[checklist.md](checklist.md). Planned work: [ROADMAP.md](ROADMAP.md). Security notes: [SECURITY.md](SECURITY.md).
Accessibility: [ACCESSIBILITY.md](ACCESSIBILITY.md). Code of conduct: [.github/CODE_OF_CONDUCT.md](.github/CODE_OF_CONDUCT.md).

## Credits

* Idea: the abandoned plugin by [Xorfor](https://forum.domoticz.com/viewtopic.php?t=20834).
* Continued for Pi-hole v6 by Wojtek Sawasciuk ([Voyo](https://github.com/voyo/Domoticz_PiHole-Control/)).
* Modular rewrite, tests and tooling: Jan Reimen.

## License

[Apache License 2.0](LICENSE) (see also [NOTICE](NOTICE)). The Apache licence of the predecessor is kept, so this
project is not relicensed to MIT like the author's other plugins.
