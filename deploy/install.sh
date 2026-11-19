#!/usr/bin/env bash
# One-shot, repeatable setup of ptt-agent on a Debian VM. Run as root: sudo ./install.sh
# Needs the VM packages from gcp-free-agents scripts/startup.sh (dbus, gnome-keyring, WARP).
# Does NOT: write secrets, log agy in, or enable the timer (that posts to the live board).
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/scottxxx666/ptt-agent.git}"
APP_USER="ptt-agent"
APP_HOME="/opt/ptt-agent"
APP_DIR="$APP_HOME/app"

log() { echo "[install] $*"; }
die() { echo "[install] ERROR: $*" >&2; exit 1; }
as_app() { sudo -H -u "$APP_USER" "$@"; }

[ "$(id -u)" = 0 ] || die "run as root"
dpkg -s dbus gnome-keyring libsecret-1-0 >/dev/null 2>&1 ||
  die "keyring packages missing: sudo apt-get install -y dbus gnome-keyring libsecret-1-0"

if [ ! -x /usr/local/bin/uv ]; then
  log "installing uv"
  curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin UV_NO_MODIFY_PATH=1 sh
fi

if ! id "$APP_USER" >/dev/null 2>&1; then
  log "creating user $APP_USER"
  useradd --system --create-home --home-dir "$APP_HOME" --shell /bin/bash "$APP_USER"
fi

if [ -d "$APP_DIR/.git" ]; then
  log "updating $APP_DIR"
  as_app git -C "$APP_DIR" pull --ff-only
else
  log "cloning $REPO_URL"
  as_app git clone "$REPO_URL" "$APP_DIR" || die "clone failed (private repo needs credentials)"
fi

log "syncing dependencies"
as_app bash -c "cd '$APP_DIR' && uv sync --frozen --python 3.13"

if [ ! -x "$APP_HOME/.local/bin/agy" ]; then
  log "installing agy"
  as_app bash -c 'curl -fsSL https://antigravity.google/cli/install.sh | bash'
fi
[ -x "$APP_HOME/.local/bin/agy" ] || die "agy not found after install"

log "installing systemd units (timer NOT enabled)"
install -m 0644 "$APP_DIR"/deploy/ptt-agent.service "$APP_DIR"/deploy/ptt-agent.timer /etc/systemd/system/
systemctl daemon-reload

if [ ! -e /etc/ptt-agent.env ]; then
  install -m 0600 -o root -g root "$APP_DIR/deploy/ptt-agent.env.example" /etc/ptt-agent.env
  log "created /etc/ptt-agent.env: fill in PTT_ID, PTT_PW, TELEGRAM_*"
fi

cat <<NEXT
[install] done. Next, by hand:
  1. sudoedit /etc/ptt-agent.env
  2. log agy in (README: Linux, test a), then test b, c, d
  3. only when ready for the live board: sudo systemctl enable --now ptt-agent.timer
NEXT
