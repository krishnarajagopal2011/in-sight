// Shared kiosk helpers: live clock, resilient polling, freshness dot, daily reload.
// No frameworks — this runs on a Pi for weeks without a reload.

export function startClock(timeEl, dateEl) {
  const tick = () => {
    const now = new Date();
    timeEl.textContent = now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    dateEl.textContent = now.toLocaleDateString([], {
      weekday: "long", day: "numeric", month: "long",
    });
  };
  tick();
  setInterval(tick, 1000 * 15);
}

// Poll a JSON API forever. Calls render(data) on success. On failure it keeps
// the last screen (offline-first) and flips the freshness dot to "stale".
export async function poll(url, render, dot) {
  let refreshMs = 30000;
  const run = async () => {
    try {
      const res = await fetch(url, { cache: "no-store" });
      const body = await res.json();
      if (body.settings?.refresh_seconds) refreshMs = body.settings.refresh_seconds * 1000;
      if (body.ok) {
        render(body.data, body);
        setDot(dot, body.stale);
      } else {
        setDot(dot, true);
      }
    } catch (e) {
      setDot(dot, true); // network/server down — leave existing content on screen
    } finally {
      setTimeout(run, refreshMs);
    }
  };
  run();
}

function setDot(dot, stale) {
  if (!dot) return;
  dot.classList.toggle("stale", !!stale);
  dot.title = stale ? "Showing last saved data" : "Live";
}

// Reload the whole page once a day, just after the 3am sync, to pick up new
// markup and clear any month-long browser cruft. Runs at 03:05 local.
export function scheduleDailyReload(hour = 3, minute = 5) {
  const now = new Date();
  const next = new Date(now);
  next.setHours(hour, minute, 0, 0);
  if (next <= now) next.setDate(next.getDate() + 1);
  setTimeout(() => location.reload(), next - now);
}

// Register the service worker (installable PWA) and highlight the active
// bottom-nav tab on the phone. No-op visual impact on the wide kiosk.
export function initPWA() {
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  }
  const path = location.pathname;
  document.querySelectorAll(".phone-nav a").forEach((a) => {
    a.classList.toggle("active", a.getAttribute("data-path") === path);
  });
}

export function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text != null) n.textContent = text;
  return n;
}

export function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }
