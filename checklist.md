# Release checklist

Version numbers are **plain digits** (`0.2.0`, or `0.2.0.1` for a small fix): plugin managers such as PyPluginStore
only recognise plain numeric tags, so no `-alpha`, `-rc` or other suffix, neither in the tag nor in the version.

## 1. Prepare (on the development machine, branch `development`)

- [ ] Decide the version. Bug fix = third segment, new feature = second, a fourth `.N` for a tiny follow-up fix
- [ ] Set it in **all three places** (a test fails when they differ):
  - [ ] `plugin.py`: `version="X.Y.Z"` in the manifest
  - [ ] `pihole_control/__init__.py`: `__version__ = "X.Y.Z"`
  - [ ] `CHANGELOG.md`: top entry `## [X.Y.Z] - YYYY-MM-DD` (rename `Unreleased`), link at the bottom
- [ ] `CHANGELOG.md` lists every user-visible change (Added / Changed / Fixed)
- [ ] `README.md` still true: settings table, device table, troubleshooting messages, "verified / not verified",
      the Pi-hole and Domoticz versions it was tried with
- [ ] `ROADMAP.md`: tick what shipped, move what slipped
- [ ] `SECURITY.md` updated if credentials handling, TLS or deployment changed
- [ ] New or changed devices: `python3 tools/gen_device_catalog.py` (commit `docs/DEVICES.md`) and `docs/PIHOLE-API.md`
- [ ] Changed or added a log message that the README troubleshooting table quotes: update the table

## 2. Verify

- [ ] `make check`: tests, flake8, shellcheck, Python 3.7 compatibility, generated docs up to date
- [ ] `make package`, unpack the archive in an empty directory and run `python3 -m unittest discover -s tests` there
      (catches files that are missing from the package)
- [ ] `./deploy.sh --dry-run`, then `./deploy.sh --host <test host>` on a test Domoticz host
- [ ] In Domoticz: add the hardware, check the log (`Pi-hole Control X.Y.Z starting ...`,
      `Connected to the Pi-hole at ...`, no errors), check that the statistics change, switch one list and one group
      on and off and watch the Pi-hole's web interface follow (`... is now enabled / disabled` in the log)
- [ ] Stop the Pi-hole (or block its port): one error line, `Pi-hole Status` goes Off; start it again: one recovery
      line, values resume
- [ ] Enter a wrong password: one error line (`Login rejected`), no retry storm, nothing secret in the log at
      Debug level
- [ ] Delete a list device in Domoticz: it comes back at the next poll
- [ ] If the plugin directory is now different from before (new module, renamed file): restart Domoticz, not just a
      hardware reload, so Python re-imports everything

## 3. Release (two-machine workflow)

- [ ] On the development machine (rpi4office): commit on `development`
      (`git commit -am "Release X.Y.Z"`)
- [ ] On the production machine (rpi4dmz): merge into `main` and push (`git merge development && git push`)
- [ ] Tag `vX.Y.Z` on `main` (digits only) and push the tag; create the GitHub release with the CHANGELOG entry
- [ ] Check that the plugin manager lists the new version

## 4. After the release

- [ ] `./deploy.sh --host <production host>`; keep the previous backup until the new version has run for a day
      (`./deploy.sh --host ... --rollback` restores it)
- [ ] Answer open issues; add reports from real installations to the verified section of the README
