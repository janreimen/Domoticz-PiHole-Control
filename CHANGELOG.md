# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions are plain numbers
(`MAJOR.MINOR.PATCH`, optionally a fourth `.N` for small fixes) so that release tags work with plugin managers
such as PyPluginStore.

## [0.1.1] - 2026-10-22

Found by reading the Pi-hole API specification (FTL 6.8) and the source of the Domoticz plugin framework against the
code of 0.1.0. No change to units, names or settings.

### Added
- **Units on the counters.** A counter that exists without a unit (created by an older version, or by hand) gets its
  unit (`queries`, `blocked`, `domains`, `clients`) at start. A unit you set yourself and a hidden device are never
  changed, and only the options of the device are written, no value and no trigger.
- **Devices Domoticz refused are created later.** While *Setup > Settings > System > Accept new Hardware Devices* is
  off, Domoticz refuses new devices. The plugin now explains that once in the log, asks again every five minutes (at
  most one refused request per round instead of one per device) and creates everything as soon as the setting is on,
  without restarting the hardware. A recovery line is logged once.
- `docs/PIHOLE-API.md`: coverage of the whole Pi-hole API (92 operations) with the candidates for further devices,
  ranked by value and cost; `ROADMAP.md` follows it.
- Tests: units, in-use state of every created device, refused creation (statistics, lists, groups, shared pause,
  recovery, no error per device), rename, plugin name handling. The Domoticz stub now models the refusal, the hardware
  name prefix and `SuppressTriggers`.

### Changed
- The statistics devices are checked at every poll, not only at start. A statistics device you delete in Domoticz
  comes back at the next poll (it came back at the next start before).
- `Cannot update Domoticz unit N` is not repeated per device while Domoticz refuses new devices; the one line about
  the refusal explains it.
- README: the verified section lists what was checked against the sources.

### Fixed
- Renaming a list or group device (after a rename in the Pi-hole) lost the `<hardware name> - ` prefix Domoticz puts
  in front of every plugin device name, and rewrote the device's value, which can fire notifications and scenes.
  The rename now keeps the prefix and changes only the name.
- With *Accept new Hardware Devices* off, every poll logged an error for every list and group and made Domoticz log
  its own refusal each time; the statistics devices were only retried after a restart.

## [0.1.0] - 2026-10-21

First numbered release: the single-file plugin (`plugin.py`, about 800 lines, no tests, no changelog) was rewritten
as a modular package. The plugin key (`PiHole`), the hardware type name, the settings fields and all device units
are unchanged, so an installation is upgraded by replacing the files (see the upgrade notes in the README).

### Added
- Package `pihole_control/`: `config` (settings), `api` (Pi-hole client), `controller` (polling and commands),
  `devices` (the only module that calls the Domoticz device API), `logger`, `model`, `constants`, `util`.
  `plugin.py` is Domoticz glue only.
- Four debug levels (Off / Basic / Verbose / Debug). Every log line passes a filter that masks the password and the
  session id, so a secret can not reach the log, whatever an error text contains. The legacy values `Normal`, `Debug`, `True` and `False` of the
  old setting are still understood.
- Settings are validated with clear messages: URL without scheme, with `/admin`, `/api` or a trailing `/`, with
  credentials or a bad port; empty password; update interval outside 10 - 3600 s; missing or unreadable certificate
  chain file; a chain file together with an `http://` URL.
- One login session, reused and extended by activity, renewed before it expires, and **logged out** when the
  hardware is stopped. Login problems (wrong password, two-factor authentication, rate limit) are reported
  distinctly; the app password is recommended in the README.
- TLS: certificates are always verified; a PEM chain for a private CA is loaded into the context and problems are
  reported with a hint. Environment proxies are ignored (the Pi-hole is a LAN device).
- Redirects are not followed (a password must not follow a redirect) and reported with the target address.
- Back-off after failed polls (up to 5 minutes; 15 for login / TLS / redirect problems), each problem logged once and
  its recovery once.
- The **Pi-hole Status** device (unit 10) now shows the connection: On while polls succeed, Off while they fail.
  Switching it by hand is refused and reset.
- Commands are verified by reading the state back from the Pi-hole; a change that did not take effect is reported.
- Devices of lists and groups removed from the Pi-hole are deleted after three polls in a row without them
  (grace period); a device deleted in Domoticz is created again; a list or group renamed in the Pi-hole renames its
  device (a name chosen in Domoticz is never overwritten at start-up).
- Unchanged statistics are rewritten every 300 s so Domoticz' sensor time-out does not mark them dead.
- Tests: unit and end-to-end tests with a fake Pi-hole v6 (real HTTP / TLS server) and a Domoticz stub, including
  the version agreement, repository hygiene and `deploy.sh` checks.
- `deploy.sh` (local or over SSH, `--dry-run`, syntax check before the copy, backup outside the plugins directory,
  `--rollback`, owner restore, Domoticz restart) and `Makefile` (`test`, `lint`, `compat`, `docs`, `check`,
  `package`, `deploy`, `deploy-dry`, `rollback`).
- Documentation: full `README.md`, `DEPLOY.md`, `docs/DEVICES.md` (generated by `tools/gen_device_catalog.py`),
  `docs/PIHOLE-API.md`, `ROADMAP.md`, `SECURITY.md`, `CONTRIBUTING.md`, `ACCESSIBILITY.md`, `checklist.md`,
  `NOTICE`.
- Repository files: `LICENSE` (Apache-2.0 text, as before), `.gitignore`, GitHub Actions workflow (tests on Python
  3.9 - 3.13, flake8, shellcheck, Python 3.7 compatibility), issue templates, pull request template, code of conduct.

### Changed
- The README is rewritten and now lists what is verified and what is not. The install directory is
  `Domoticz-PiHole-Control` (the old name `PiHole-HTTPS` keeps working).
- The Debug field offers Off / Basic / Verbose / Debug instead of False / True.
- A group's name in a list's device name comes from the Pi-hole instead of a built-in table; a list without a
  comment is named after its address.
- Lists and groups are read once per poll; groups are read before lists so a device name can contain the group name.
- Commands other than **On** and **Off** are refused with a log line.

### Fixed
- The heartbeat was set to the update interval (60 s by default). Domoticz treats a heartbeat above 30 seconds as
  "plugin not responding"; the heartbeat is now 10 s and polling is done by time.
- Every command except `On` was treated as `Off` (for example a dimmer level or a stray `Toggle`).
- Lists and groups were fetched twice per poll (once to synchronise devices, once to update them).
- The search for a free group unit had no upper bound and could create units above 255; both ranges now stop with
  one error when full (lists 100 - 199, groups 200 - 255).
- Group names were hard-coded (`0 = Default`, `1 = Kids`); other groups showed up as `Group <id>`.
- A leftover debug line (`NEW CODE VERSION 2023-11-23 v2 EXECUTING`) was written to the log each time a group was
  switched.
- A new login was made every 10 heartbeats without logging out, using up the Pi-hole's limited number of sessions.

[0.1.1]: https://github.com/janreimen/Domoticz-PiHole-Control/releases/tag/v0.1.1
[0.1.0]: https://github.com/janreimen/Domoticz-PiHole-Control/releases/tag/v0.1.0
