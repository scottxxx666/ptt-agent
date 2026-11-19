#!/usr/bin/env bash
# Run a command inside a private D-Bus session with an unlocked gnome-keyring.
# agy keeps its Google login in the Secret Service keyring, which a headless VM lacks.
# The keyring file lives in $HOME/.local/share/keyrings and has an EMPTY password, so
# anyone who can read that user's home can read the token. Keep the user dedicated.
# Leftover keyring daemons are killed with the systemd unit's cgroup, so always run this
# under a unit (ptt-agent.service or systemd-run), not from a login shell.
set -euo pipefail

if [ -z "${WITH_KEYRING_INNER:-}" ]; then
  WITH_KEYRING_INNER=1 exec dbus-run-session -- "$0" "$@"
fi

while IFS= read -r line; do
  case "$line" in *=*) export "$line" ;; esac
done < <(gnome-keyring-daemon --unlock --components=secrets <<<"")

exec "$@"
