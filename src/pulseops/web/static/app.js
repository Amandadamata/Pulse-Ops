// Atualiza o resumo do painel a cada 15 s. A página funciona sem este script.
// A requisição usa o cookie de sessão (HttpOnly); nenhum token fica neste arquivo.
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
    status.textContent = "Atualizando…";
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
      const when = new Date(data.generated_at).toLocaleTimeString("pt-BR");
      status.textContent = "Resumo atualizado às " + when + "." +
        (data.worker_alive ? "" : " Worker sem sinal: dados desatualizados.");
    } catch (error) {
      status.textContent = "Falha ao atualizar o resumo (" + error.message + "). Recarregue a página.";
    }
  }

  setInterval(refresh, 15000);
})();
