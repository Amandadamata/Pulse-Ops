// Refreshes the dashboard summary every 15 s. The page works without this script.
// The request uses the session cookie (HttpOnly); no token is kept in this file.
(function () {
  "use strict";
  const section = document.querySelector("[data-summary-url]");
  if (!section) return;
  const status = section.querySelector("[data-summary-status]");
  const url = section.getAttribute("data-summary-url");

  function setValue(key, value) {
    const el = section.querySelector('[data-key="' + key + '"]');
    if (el) el.textContent = String(value);
  }

  async function refresh() {
    status.textContent = "Refreshing…";
    try {
      const response = await fetch(url, { credentials: "same-origin", headers: { Accept: "application/json" } });
      if (!response.ok) throw new Error("HTTP " + response.status);
      const data = await response.json();
      setValue("total", data.total);
      for (const key of ["healthy", "degraded", "down", "no_data", "paused"]) {
        setValue(key, data.by_health[key] || 0);
      }
      setValue("stale", data.stale);
      setValue("open_incidents", data.open_incidents);
      setValue("failed_deliveries", data.failed_deliveries);
      const when = new Date(data.generated_at).toLocaleTimeString("en-GB");
      status.textContent = "Summary updated at " + when + "." +
        (data.worker_alive ? "" : " Worker silent: stale data.");
    } catch (error) {
      status.textContent = "Could not refresh the summary (" + error.message + "). Reload the page.";
    }
  }

  setInterval(refresh, 15000);
})();
