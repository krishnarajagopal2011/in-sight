#!/usr/bin/env bash
# Launch Chromium fullscreen kiosk on the PROJECTS view (HDMI-1 / primary).
# Wayland (labwc/wayfire) is the default on Pi OS Bookworm for Pi 5.
set -euo pipefail

URL="${INSIGHT_URL:-http://localhost:8137/projects}"

# Wait for the local server to answer before opening the browser.
for i in $(seq 1 30); do
  curl -fsS "http://localhost:8137/api/health" >/dev/null 2>&1 && break
  sleep 1
done

# Hide the cursor and stop the screen from blanking.
unclutter -idle 0.5 -root &>/dev/null &

exec chromium-browser \
  --kiosk "$URL" \
  --noerrdialogs \
  --disable-infobars \
  --incognito \
  --check-for-update-interval=31536000 \
  --disable-session-crashed-bubble \
  --disable-features=Translate \
  --autoplay-policy=no-user-gesture-required \
  --ozone-platform=wayland
