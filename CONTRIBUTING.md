# Contributing

Bug reports, reports from real installations (also "it works on my setup...") and pull requests are welcome. The most
valuable contribution right now is **a report from a real Domoticz with a real Pi-hole v6**: install the plugin, set
*Debug* to *Basic*, and open an issue with the Pi-hole and Domoticz versions and what the log shows. Remove
passwords, host names and the names of your block lists first.

## Set up

```sh
git clone https://github.com/janreimen/Domoticz-PiHole-Control.git
cd Domoticz-PiHole-Control
make test            # python3 -m unittest discover -s tests
make check           # tests + flake8 (pyflakes checks) + shellcheck + Python 3.7 compatibility (vermin) + generated docs
```

The tests need only Python 3 (and the `openssl` command for the TLS tests, which skip themselves without it). They
talk to their own fake Pi-hole on `127.0.0.1`; never point them at a real one.

## Rules

- **No third-party Python packages**, and nothing that needs a newer Python than 3.7 (`make compat`).
- **Only `plugin.py` imports `Domoticz`**; only `devices.py` calls the Domoticz device API (through the object it is
  given). `api.py`, `controller.py` and `config.py` never see Domoticz and are tested without it.
- **`plugin.py` must not bind the names Domoticz injects** (`Parameters`, `Devices`, `Images`, `Settings`): the
  injected globals would silently shadow them. A test enforces this. Import modules under another name
  (`from pihole_control import config as ph_config`). `Devices` is replaced by Domoticz before every callback, so
  the device manager reads it through a function (`lambda: Devices`), never through a reference taken at start.
- **Never log secrets.** The password and the session id are registered with the logger, which masks them in every
  message. New code must not build log lines that bypass the logger.
- **The device model is frozen.** Units 1 - 10 (statistics and status), 100 - 199 (lists), 200 - 255 (groups) and
  the `ListID:` / `GroupID:` descriptions are what an installation in the field uses; changing them breaks
  upgrades. A new device gets a new unit and a line in `constants.py`.
- **Match devices by what they stand for**, never by name. Do not overwrite a name the user may have chosen.
- **A problem is logged once, and its recovery once.** Use `Controller._report` / `_recovered`; repeats go to
  Verbose.
- **Never delete on one odd answer.** Removal goes through the grace period (`REMOVE_AFTER_MISSES`).
- **Domoticz callbacks must return quickly** and must not raise: wrap new callback code like the existing ones.
- Only enable and disable. The plugin does not create, edit or delete anything in the Pi-hole.

## Adding a statistics device

1. Add a `StatDevice` row to `STAT_DEVICES` in `pihole_control/constants.py` (next free unit below 100) and the field
   it reads in `devices.py` (`STAT_FIELDS`) and `api.parse_stats` / `model.Stats`.
2. Add the source to `SOURCES` in `tools/gen_device_catalog.py`, run `python3 tools/gen_device_catalog.py` to
   regenerate `docs/DEVICES.md` (a test fails if you forget).
3. Add tests in `tests/test_api.py` (parsing, missing value) and `tests/test_devices.py` (creation, update).
4. Update the README device table and `CHANGELOG.md`.

## Adding an API call

Add it to `PiHoleClient` and `docs/PIHOLE-API.md`, give it a fake endpoint in `tests/fake_pihole.py` and tests for
success, an error reply and a reply the plugin does not understand. The reply of an unknown shape must produce a
`PiHoleError` of kind `INVALID`, not an exception from deep inside the parser.

## Pull requests

- One topic per pull request; keep it small enough to review. Target the `development` branch.
- Add or update tests; `make check` must pass.
- Update `CHANGELOG.md` under an `Unreleased` heading. The maintainer sets the version (see `checklist.md`).
- Describe what you tested and with which Pi-hole and Domoticz versions, if any.

By contributing you agree that your contribution is licensed under the [Apache License 2.0](LICENSE).
