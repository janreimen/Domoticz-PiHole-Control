# Security

## Scope

The plugin **reads** statistics, lists and groups from a Pi-hole v6 and **enables or disables** lists and groups
through the Pi-hole's REST API. It never creates, edits or deletes lists, groups, clients or domains, and it does not
change the Pi-hole's settings. It runs inside Domoticz, as the Domoticz user, and makes HTTP(S) requests to the one
address you configure. It starts no processes and uses only the Python standard library.

## Things to know

| Topic | Details | What to do |
|---|---|---|
| **The password** | The Pi-hole's web password (or an app password) is stored in Domoticz' hardware settings like any other plugin parameter and is sent to the Pi-hole to log in. The plugin never writes it to the log: every log line passes a filter that replaces it (and the session id) by `<masked>`, at every debug level, also in error texts | Use an **app password** (it can be revoked without changing your own password and works with two-factor authentication). Protect the Domoticz database and its backups |
| **http is not encrypted** | With `http://` the password and the session id travel in clear text over your network | Use `https://` when the Pi-hole offers it, or keep Domoticz and the Pi-hole on a trusted network segment |
| **Certificates are always verified** | There is no setting to switch verification off. For a private CA, give the PEM file with the root and sub CA certificates (*Certificate Chain Path*). The host name in the URL must match the certificate | Do not work around a TLS error by switching to http; fix the chain or the host name |
| **No redirects** | A redirect is never followed, so the password is never sent to a place you did not configure (for example when something on the network answers with a redirect to another host) | Use the final address as *Pi-hole URL* when the log reports a redirect |
| **No environment proxies** | The plugin ignores `http_proxy` / `https_proxy` and talks to the Pi-hole directly | Nothing to do |
| **Session** | The plugin keeps one session, reuses it and logs it out when the hardware is stopped. The Pi-hole limits the number of sessions; a failed login is retried at most every five minutes to stay below its login rate limit | Do not restart the hardware repeatedly while a login fails |
| **Debug log** | With *Debug* the log contains the Pi-hole's host name or address, the names and comments of your block lists and groups (which can reveal who is blocked from what, for example `Kids - Social Media`) and request paths | Review a log before you post it in an issue |
| **Authority of the plugin** | The password gives the plugin everything the Pi-hole's API allows, not only what the plugin uses | An app password does not limit this; keep the Domoticz host trusted |
| **`deploy.sh`** | Runs commands on the target through SSH (`bash -s`), uses `sudo -n` only if the plugin directory is not writable, and never changes anything outside the plugin directory, the backup directory and (restart) the Domoticz service | Review the script before running it; use SSH keys |

## Hardening checklist

1. Create an **app password** in the Pi-hole (*Settings > Web interface / API*, Expert mode) and use that.
2. Prefer `https://`, with a certificate chain you control, and use the host name of the certificate in the URL.
3. Allow access to the Pi-hole's web port only from the hosts that need it (Domoticz, your admin machine).
4. Keep the plugin directory writable only for the user that deploys it.
5. Revoke the app password when you remove the plugin.

## Supported versions

Only the latest release receives fixes.

## Reporting a vulnerability

Please do **not** open a public issue for a security problem. Use GitHub's private vulnerability reporting
(*Security* tab of the repository > *Report a vulnerability*). Include the plugin version, what you observed and, if
possible, how to reproduce it. Do not include real passwords, session ids or private list contents.
