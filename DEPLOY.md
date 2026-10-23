# Deploying Domoticz-PiHole-Control

The plugin is a plain directory (`plugin.py` + the `pihole_control/` package) that has to sit in Domoticz' `plugins/`
directory. Nothing is compiled and no Python package is installed. This page covers the ways to get it there, how
to verify the result, and how to update, roll back and remove it.

## 0. Prerequisites

| Where | What |
|---|---|
| Domoticz host | Domoticz with Python plugin support, Python 3.7 or newer |
| Pi-hole | Pi-hole **v6**, web interface reachable from the Domoticz host |
| Pi-hole | an **app password**: *Settings > Web interface / API* (Expert mode) > *Configure app password* |

Quick check from the Domoticz host (should print a JSON object with a `session`; replace the password, and note that
the password is visible in your shell history and the process list while the command runs, so use a throw-away app
password):

```sh
curl -sS -X POST http://pi.hole/api/auth -H 'Content-Type: application/json' -d '{"password":"APP-PASSWORD"}'
```

If Domoticz runs in a **container**, the container must be able to reach the Pi-hole; a host-side test does not prove
that.

## 1. `deploy.sh` (recommended)

Run it from a checkout (or unpacked archive) of this repository.

```sh
./deploy.sh --dry-run                               # show what would happen on this machine
./deploy.sh                                         # install on this machine
./deploy.sh --host jan@rpi4office                   # install on another machine over SSH
./deploy.sh --host jan@rpi4office --rollback        # back to the previous version
```

Or through make: `make deploy HOST=jan@rpi4office`, `make deploy-dry`, `make rollback HOST=...`.

What it does on the target:

1. checks that `python3` is 3.7 or newer
2. **parses the new files before anything is touched**: a copy that does not compile on the target's Python never
   replaces the working installation
3. picks `sudo` only if the plugin directory is not writable for the SSH user (needs **passwordless** sudo then;
   otherwise log in as the Domoticz user or root)
4. backs up the installed copy to `~/domoticz-plugin-backups/Domoticz-PiHole-Control-<version>-<time>.tar.gz`
   and keeps the newest 3. The backup is deliberately **outside** the plugins directory: a second copy of `plugin.py`
   in there would be loaded by Domoticz as a duplicate plugin
5. replaces `plugin.py`, `pihole_control/` and the documentation files. Other files you put in that directory are
   left alone
6. gives the directory back to its previous owner (for example `domoticz:domoticz`)
7. restarts the `domoticz` systemd service

Nothing is changed when a step before the copy fails (for instance when the backup directory is not writable).

| Option | Default | Meaning |
|---|---|---|
| `--host [USER@]HOST` | this machine | deploy over SSH |
| `--ssh-opts "OPTS"` | | extra `ssh` options, e.g. `"-p 2222 -i ~/.ssh/id_ed25519"` |
| `--dir PATH` | `/srv/domoticz/plugins/Domoticz-PiHole-Control` | target directory |
| `--dry-run`, `-n` | | report only; the target is not changed |
| `--rollback` | | restore the newest backup |
| `--service NAME` | `domoticz` | systemd service to restart |
| `--restart-cmd CMD` | | run CMD on the target instead (init.d, docker restart, ...) |
| `--no-restart` | | do not restart Domoticz |
| `--backup-dir PATH` | `$HOME/domoticz-plugin-backups` | backup location on the target |
| `--keep N` | `3` | backups to keep |
| `-V`, `--version` | | print the version of this source tree |

Exit status: `0` success, `1` error (nothing was changed if it happened before the copy).

The script opens two SSH connections (upload, then run). Use key authentication, or `ControlMaster auto` in
`~/.ssh/config`, to avoid being asked twice.

## 2. By hand

```sh
cd /srv/domoticz/plugins
sudo cp -r /path/to/Domoticz-PiHole-Control .             # plugin.py and pihole_control/ must stay together
sudo chown -R domoticz:domoticz Domoticz-PiHole-Control   # whatever user runs Domoticz
sudo systemctl restart domoticz
```

Or with git, which makes updates a `git pull`:

```sh
cd /srv/domoticz/plugins
git clone https://github.com/janreimen/Domoticz-PiHole-Control.git
# later:
cd Domoticz-PiHole-Control && git pull && sudo systemctl restart domoticz
```

The directory name does not matter to Domoticz; the plugin is identified by the `key` in the manifest (`PiHole`).
Use one directory per plugin: do not leave an old copy, a `.bak` folder or an unpacked archive next to it (Domoticz
loads every `plugin.py` it finds one level below `plugins/`). **If you had the old single-file plugin in another
directory (for example `PiHole-HTTPS`), update that directory instead of adding a second one**, otherwise two
plugins with the same key compete.

## 3. Add the hardware

1. *Setup > Hardware*, type **Pi-hole Monitor and Control - https Version**, name it (for example `Pi-hole`).
2. *Pi-hole URL* (for example `https://pi.hole`), the app password, and for a private CA the path of the certificate
   chain. Leave the rest at the defaults.
3. *Add*. The log shows `Pi-hole Control <version> starting for ...` and, after the first poll, `Connected to the Pi-hole
   at ...` and the created devices.

All fields are explained in the [README](README.md#settings).

**No devices appear?** Domoticz only accepts new devices from plugins while *Setup > Settings > System > Accept new
Hardware Devices* is on. The plugin says so once in the log (`Domoticz did not create the device ...`) and asks again
every five minutes: switch the setting on and the devices appear without a restart.

## 4. Verify

In the Domoticz log (*Setup > Log*), with *Debug* at *Basic* for the first run:

* `Pi-hole Control X.Y.Z starting for <url> (...)`: the plugin started with the settings you expect
* `Connected to the Pi-hole at <url>`: login and the first poll worked
* the statistics devices (*Setup > Devices*) have values, `Pi-hole Status` is On
* a switch for each list and group exists; switching one writes `Command received: ...` and
  `... is now enabled` / `... is now disabled`, and the Pi-hole's web interface shows the same

If something is wrong, set *Debug* to *Debug*, reload the hardware and read the log; the
[README troubleshooting table](README.md#troubleshooting) explains the messages. Passwords and session ids are masked
in the log, but check the text before you post it.

## 5. Update, roll back, remove

* **Update:** run `deploy.sh` again (or `git pull`) and restart Domoticz. Devices are matched by their unit and their
  `ListID:` / `GroupID:` description, so existing devices, their names, history, scenes and schedules are kept.
* **Roll back:** `./deploy.sh [--host ...] --rollback`, or unpack the newest archive from the backup directory
  over the plugin directory.
* **Remove:** delete the hardware in *Setup > Hardware* (this removes its devices), delete the plugin directory,
  restart Domoticz, and revoke the app password in the Pi-hole.
* **Upgrading from the single-file plugin before 0.1.0:** replace the files in the existing directory and restart;
  see the [upgrade notes](README.md#upgrading-from-the-plugin-before-010).

## 6. Troubleshooting a deployment

| Symptom | Cause / fix |
|---|---|
| Hardware type "Pi-hole Monitor and Control - https Version" is not in the list | Domoticz was not restarted, the directory is not directly below `plugins/`, or `plugin.py` is not readable by the Domoticz user. See the Domoticz log at start-up |
| `ModuleNotFoundError: No module named 'pihole_control'` | the `pihole_control/` directory is missing or not next to `plugin.py` (copied only `plugin.py`) |
| Hardware added, but no devices | *Setup > Settings > System > Accept new Hardware Devices* is off (see the log line `Domoticz did not create the device ...`). Switch it on, wait up to five minutes |
| Two hardware types / duplicate plugin errors | a second copy of the plugin sits in `plugins/` (backup folder, old version): remove it |
| The old behaviour is still there after an update | Domoticz keeps the old modules in memory: restart Domoticz, a hardware reload is not enough when a module was added or renamed |
| `deploy.sh`: `not writable ... sudo needs a password` | log in as the Domoticz user or root, or allow passwordless sudo for the SSH user |
| `deploy.sh`: `the new files do not parse` | the target's Python is older than the code needs; the installation was not touched |
