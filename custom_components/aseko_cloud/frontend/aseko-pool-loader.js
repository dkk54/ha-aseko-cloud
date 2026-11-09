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

      // Rebuilt for new devices and entities, and for another language, which
      // names the views. Home Assistant before 2026.6 does not ask and rebuilds
      // on registry changes only.
      static shouldRegenerate(config, oldHass, newHass) {
        return (
          oldHass.entities !== newHass.entities ||
          oldHass.devices !== newHass.devices ||
          oldHass.locale?.language !== newHass.locale?.language
        );
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

// If this file still arrived too late, Home Assistant shows an error view and
// does not try again on its own, so it is asked to reload the dashboard once.
const recover = setInterval(() => {
  const panel = document
    .querySelector("home-assistant")
    ?.shadowRoot?.querySelector("home-assistant-main")
    ?.shadowRoot?.querySelector("partial-panel-resolver ha-panel-lovelace");
  const failed = panel?.lovelace?.config?.views?.[0]?.cards?.some((card) =>
    String(card.content ?? "").includes("ll-strategy-dashboard-aseko-pool"),
  );
  if (!failed) {
    return;
  }
  clearInterval(recover);
  panel.shadowRoot
    ?.querySelector("hui-root")
    ?.dispatchEvent(new Event("config-refresh", { bubbles: true, composed: true }));
}, 1000);
setTimeout(() => clearInterval(recover), 30 * 1000);
