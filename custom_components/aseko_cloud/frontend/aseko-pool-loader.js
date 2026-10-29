// Entry point for the Aseko pool dashboard, loaded on every Home Assistant page.
// It carries the integration version in its URL (?v=), passed on to the
// dashboard code so a browser fetches it afresh after an update.
// The strategy is registered right away, because Home Assistant gives up if it
// does not appear within a few seconds, and slow devices fetch the code later.
const dashboard = import(new URL(`./aseko-pool.js${new URL(import.meta.url).search}`, import.meta.url).href);

if (!customElements.get("ll-strategy-dashboard-aseko-pool")) {
  customElements.define(
    "ll-strategy-dashboard-aseko-pool",
    class extends HTMLElement {
      static async generate(config, hass) {
        const { AsekoPoolDashboardStrategy } = await dashboard;
        return AsekoPoolDashboardStrategy.generate(config, hass);
      }
    },
  );
}

// Offered under Settings → Dashboards → Add dashboard.
window.customStrategies = window.customStrategies || [];
if (!window.customStrategies.some((strategy) => strategy.type === "aseko-pool")) {
  window.customStrategies.push({
    type: "aseko-pool",
    strategyType: "dashboard",
    name: "Aseko Pool",
    description: "Every Aseko pool unit with water quality, filtration and a showcase for a wall tablet.",
    documentationURL: "https://github.com/dkk54/ha-aseko-cloud#pool-dashboard",
  });
}

// If this file still arrived too late, Home Assistant shows a timeout error and
// never retries, so the page is reloaded once to recover.
const RELOAD_KEY = "aseko-pool-reloaded-at";
const recover = setInterval(() => {
  const panel = document
    .querySelector("home-assistant")
    ?.shadowRoot?.querySelector("home-assistant-main")
    ?.shadowRoot?.querySelector("partial-panel-resolver ha-panel-lovelace");
  const error = panel?.shadowRoot?.querySelector("hass-error-screen")?.error || "";
  if (!error.includes("ll-strategy-dashboard-aseko-pool")) {
    return;
  }
  clearInterval(recover);
  let last = 0;
  try {
    last = Number(sessionStorage.getItem(RELOAD_KEY)) || 0;
    sessionStorage.setItem(RELOAD_KEY, String(Date.now()));
  } catch (err) {
    return;
  }
  if (Date.now() - last > 60 * 1000) {
    window.location.reload();
  }
}, 1000);
setTimeout(() => clearInterval(recover), 30 * 1000);
