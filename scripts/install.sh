#!/usr/bin/env bash
# One-shot installer for Raspberry Pi 5 (Pi OS Bookworm, 64-bit).
#
#   sudo ./scripts/install.sh                 # server + projects kiosk + 3am cron
#   sudo INSTALL_LIFE=1 ./scripts/install.sh   # also install the life kiosk (2nd display)
#
# Idempotent: safe to re-run after editing config.yaml.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_USER="${SUDO_USER:-$USER}"
RUN_UID="$(id -u "$RUN_USER")"

echo "==> in_sight install"
echo "    dir:  $ROOT"
echo "    user: $RUN_USER (uid $RUN_UID)"

if [ "$ROOT" != "/opt/in_sight" ]; then
  echo "!!  The systemd units expect /opt/in_sight."
  echo "    Move the project there, or edit the unit files' paths, then re-run."
fi

# 1. System packages -------------------------------------------------------
echo "==> apt packages"
apt-get update -y
apt-get install -y python3 python3-venv python3-pip chromium-browser unclutter curl

# 2. Python venv -----------------------------------------------------------
echo "==> python venv + deps"
sudo -u "$RUN_USER" python3 -m venv "$ROOT/.venv"
sudo -u "$RUN_USER" "$ROOT/.venv/bin/pip" install --upgrade pip
sudo -u "$RUN_USER" "$ROOT/.venv/bin/pip" install -r "$ROOT/requirements.txt"

# 3. Config ----------------------------------------------------------------
if [ ! -f "$ROOT/config/config.yaml" ]; then
  echo "==> creating config/config.yaml from example (EDIT IT for your password/schedules)"
  sudo -u "$RUN_USER" cp "$ROOT/config/config.example.yaml" "$ROOT/config/config.yaml"
fi
chmod 600 "$ROOT/config/config.yaml" || true     # holds the dVerse password
chmod +x "$ROOT/scripts/"*.sh

# 4. First snapshot --------------------------------------------------------
echo "==> building first snapshot"
sudo -u "$RUN_USER" "$ROOT/scripts/refresh.sh" || echo "   (sync failed — will retry at 3am; check data/refresh.log)"

# 5. systemd services ------------------------------------------------------
echo "==> installing systemd units"
sed "s/User=%i/User=$RUN_USER/" "$ROOT/systemd/insight-server.service" \
  > /etc/systemd/system/insight-server.service

install_kiosk() {  # $1 = unit filename
  sed -e "s#XDG_RUNTIME_DIR=/run/user/1000#XDG_RUNTIME_DIR=/run/user/$RUN_UID#" \
      "$ROOT/systemd/$1" > "/etc/systemd/system/$1"
}

# Kiosk units run inside the user's graphical session.
mkdir -p "/home/$RUN_USER/.config/systemd/user"
install_kiosk insight-kiosk-projects.service
cp /etc/systemd/system/insight-kiosk-projects.service \
   "/home/$RUN_USER/.config/systemd/user/insight-kiosk-projects.service"
if [ "${INSTALL_LIFE:-0}" = "1" ]; then
  install_kiosk insight-kiosk-life.service
  cp /etc/systemd/system/insight-kiosk-life.service \
     "/home/$RUN_USER/.config/systemd/user/insight-kiosk-life.service"
fi
chown -R "$RUN_USER":"$RUN_USER" "/home/$RUN_USER/.config/systemd"

systemctl daemon-reload
systemctl enable --now insight-server.service

# Enable user services + linger so the kiosk starts at boot without a login.
loginctl enable-linger "$RUN_USER"
sudo -u "$RUN_USER" XDG_RUNTIME_DIR="/run/user/$RUN_UID" \
  systemctl --user daemon-reload || true
sudo -u "$RUN_USER" XDG_RUNTIME_DIR="/run/user/$RUN_UID" \
  systemctl --user enable --now insight-kiosk-projects.service || \
  echo "   (start the projects kiosk from a desktop session: systemctl --user start insight-kiosk-projects)"
if [ "${INSTALL_LIFE:-0}" = "1" ]; then
  sudo -u "$RUN_USER" XDG_RUNTIME_DIR="/run/user/$RUN_UID" \
    systemctl --user enable --now insight-kiosk-life.service || true
fi

# 6. Cron — full rebuild at 03:00, plus a light life refresh every 15 min ------
#    (the 15-min pass keeps Google Calendar appointments current during the day).
echo "==> installing refresh cron (3am full + 15-min life)"
CRON_FULL="0 3 * * * $ROOT/scripts/refresh.sh"
CRON_LIFE="*/15 * * * * $ROOT/scripts/refresh.sh life"
( sudo -u "$RUN_USER" crontab -l 2>/dev/null | grep -v 'in_sight/scripts/refresh.sh' ; \
  echo "$CRON_FULL"; echo "$CRON_LIFE" ) \
  | sudo -u "$RUN_USER" crontab -

cat <<EOF

==> Done.
    Server:   http://localhost:8137/projects  and  /life
    Service:  systemctl status insight-server
    Kiosk:    systemctl --user status insight-kiosk-projects
    Refresh:  runs daily at 03:00 (cron) and on boot; logs in data/refresh.log

    Next: edit $ROOT/config/config.yaml
          - set your dVerse password (or export INSIGHT_DVERSE_PASSWORD)
          - tune fitness / meals / travel / house
    Then: $ROOT/scripts/refresh.sh && sudo systemctl restart insight-server
EOF
