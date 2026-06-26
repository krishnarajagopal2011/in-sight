#!/usr/bin/env bash
# Launch Chromium fullscreen kiosk on the LIFE view.
# Use this on the second HDMI output, or on a second Raspberry Pi.
# To pin it to HDMI-2 on a dual-display Pi, set INSIGHT_WINDOW_POS (see install.sh notes).
set -euo pipefail

URL="${INSIGHT_URL:-http://localhost:8137/life}"

for i in $(seq 1 30); do
  curl -fsS "http://localhost:8137/api/health" >/dev/null 2>&1 && break
  sleep 1
done

unclutter -idle 0.5 -root &>/dev/null &

# A separate user-data-dir lets two Chromium kiosks run side by side.
exec chromium-browser \
  --kiosk "$URL" \
  --user-data-dir="$HOME/.config/insight-chromium-life" \
  --window-position="${INSIGHT_WINDOW_POS:-1920,0}" \
  --noerrdialogs \
  --disable-infobars \
  --incognito \
  --check-for-update-interval=31536000 \
  --disable-session-crashed-bubble \
  --disable-features=Translate \
  --ozone-platform=wayland
