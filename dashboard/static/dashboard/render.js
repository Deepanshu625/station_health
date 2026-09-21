// DOM rendering for both dashboard views. Never uses innerHTML: all API data
// (station_id, firmware_version, region, etc.) is untrusted device input and
// is rendered only via textContent / createElement.

import { formatLatency, formatNumber, formatRelativeTime, formatScore, scoreSeverity } from "./format.js";

function el(tag, options = {}, children = []) {
  const node = document.createElement(tag);
  if (options.className) node.className = options.className;
  if (options.text !== undefined) node.textContent = options.text;
  if (options.attrs) {
    for (const [key, value] of Object.entries(options.attrs)) node.setAttribute(key, value);
  }
  for (const child of children) node.appendChild(child);
  return node;
}

function scoreBar(score) {
  const track = el("div", { className: "score-bar" });
  const fill = el("div", { className: `score-bar__fill score-bar__fill--${scoreSeverity(score)}` });
  fill.style.width = `${Math.max(0, Math.min(100, score ?? 0))}%`;
  track.appendChild(fill);
  return track;
}

function relativeTimeEl(iso) {
  const span = el("span", { text: formatRelativeTime(iso) });
  if (iso) span.title = iso;
  return span;
}

function statusChip(status) {
  return el("span", {
    className: `chip ${status === "online" ? "chip--ok" : "chip--bad"}`,
    text: status || "unknown",
  });
}

// --- Overview -----------------------------------------------------------

function kpiTile(label, value, sub) {
  const tile = el("div", { className: "kpi-tile" }, [
    el("div", { className: "kpi-tile__label", text: label }),
    el("div", { className: "kpi-tile__value", text: value }),
  ]);
  if (sub) tile.appendChild(el("div", { className: "kpi-tile__sub", text: sub }));
  return tile;
}

function buildKpis(overall) {
  const grid = el("div", { className: "kpi-grid" });
  const onlinePct = overall.stations
    ? `${Math.round((overall.online / overall.stations) * 100)}% of fleet`
    : "\u2014";
  grid.appendChild(kpiTile("Stations", formatNumber(overall.stations)));
  grid.appendChild(kpiTile("Online", formatNumber(overall.online), onlinePct));
  grid.appendChild(kpiTile("Offline", formatNumber(overall.offline)));
  grid.appendChild(kpiTile("Poor hygiene", formatNumber(overall.poor)));
  grid.appendChild(kpiTile("Avg latency", formatLatency(overall.avg_latency_ms)));
  grid.appendChild(kpiTile("Avg score", formatScore(overall.avg_hygiene_score)));
  return grid;
}

function buildRegionPills(regions, activeRegion, onSelect) {
  const row = el("div", { className: "pill-row" }, [el("span", { className: "pill-row__label", text: "Region" })]);
  const options = [{ value: "all", label: "All" }, ...regions.map((r) => ({ value: r, label: r }))];
  for (const option of options) {
    const pressed = option.value === activeRegion;
    const button = el("button", {
      className: `pill${pressed ? " pill--active" : ""}`,
      text: option.label,
      attrs: { type: "button", "aria-pressed": String(pressed) },
    });
    button.addEventListener("click", () => onSelect(option.value));
    row.appendChild(button);
  }
  return row;
}

function buildProblemsTable(results, onNavigate) {
  const table = el("table", { className: "data-table" });
  const head = el("thead", {}, [
    el("tr", {}, ["Station", "Region", "Score", "Status", "Last report"].map((h) => el("th", { text: h }))),
  ]);
  const body = el("tbody");

  if (results.length === 0) {
    body.appendChild(
      el("tr", {}, [el("td", { text: "No poor-hygiene stations right now.", attrs: { colspan: "5" } })])
    );
  }

  for (const row of results) {
    const link = el("a", {
      text: row.station_id,
      attrs: { href: `#/stations/${encodeURIComponent(row.station_id)}` },
    });
    link.addEventListener("click", (event) => {
      event.preventDefault();
      onNavigate(row.station_id);
    });

    const scoreCell = el("td", {}, [
      el("span", { className: "score-cell__value", text: formatScore(row.hygiene_score) }),
      scoreBar(row.hygiene_score),
    ]);

    body.appendChild(
      el("tr", {}, [
        el("td", {}, [link]),
        el("td", { text: row.region }),
        scoreCell,
        el("td", {}, [statusChip(row.connectivity_status)]),
        el("td", {}, [relativeTimeEl(row.last_reported_at)]),
      ])
    );
  }

  table.appendChild(head);
  table.appendChild(body);
  return table;
}

function buildRegionCards(groups, onToggleRegion, activeRegion) {
  const list = el("div", { className: "region-list" });
  for (const group of groups) {
    const card = el("button", {
      className: `region-card${group.region === activeRegion ? " region-card--active" : ""}`,
      attrs: { type: "button" },
    });
    card.appendChild(el("div", { className: "region-card__name", text: group.region }));
    card.appendChild(el("div", { className: "region-card__score", text: formatScore(group.avg_hygiene_score) }));
    card.appendChild(scoreBar(group.avg_hygiene_score));
    card.appendChild(
      el("div", {
        className: "region-card__meta",
        text: `${formatNumber(group.poor)} poor \u00b7 ${formatLatency(group.avg_latency_ms)}`,
      })
    );
    card.addEventListener("click", () => onToggleRegion(group.region));
    list.appendChild(card);
  }
  return list;
}

export function renderOverview(container, state, handlers) {
  container.textContent = "";

  if (!state.overview.metrics || !state.overview.problems) {
    container.appendChild(el("div", { className: "skeleton", text: "Loading fleet overview\u2026" }));
    return;
  }

  const { metrics, problems } = state.overview;
  const { region } = state.filters;

  container.appendChild(buildKpis(metrics.overall));

  const panels = el("div", { className: "overview-panels" });

  const problemsPanel = el("div", { className: "panel panel--problems" }, [
    el("h2", { text: "Problem stations" }),
    el("p", {
      className: "panel-explainer",
      text: `"Poor" means a hygiene score below ${formatScore(handlers.poorThreshold)}.`,
    }),
  ]);

  const regions = metrics.groups.map((g) => g.region);
  problemsPanel.appendChild(buildRegionPills(regions, region, handlers.onRegionChange));
  problemsPanel.appendChild(buildProblemsTable(problems.results, handlers.onNavigateStation));

  const footer = el("div", { className: "panel-footer" });
  const shown = problems.results.length;
  const total = problems.count ?? shown;
  footer.appendChild(el("span", { text: `Showing ${shown} of ${total} problem stations` }));
  const moreButton = el("button", { className: "button", text: "Show more", attrs: { type: "button" } });
  moreButton.disabled = shown >= total;
  moreButton.addEventListener("click", handlers.onShowMore);
  footer.appendChild(moreButton);
  problemsPanel.appendChild(footer);

  const regionsPanel = el("div", { className: "panel panel--regions" }, [el("h2", { text: "By region" })]);
  regionsPanel.appendChild(buildRegionCards(metrics.groups, handlers.onRegionChange, region));
  regionsPanel.appendChild(
    el("p", {
      className: "panel-footnote",
      text: "Weights: availability 40 \u00b7 latency 25 \u00b7 errors 25 \u00b7 firmware 10",
    })
  );

  panels.appendChild(problemsPanel);
  panels.appendChild(regionsPanel);
  container.appendChild(panels);
}

// --- Station drill-down ---------------------------------------------------

const COMPONENT_LABELS = { availability: "Availability", latency: "Latency", errors: "Errors", firmware: "Firmware" };

function componentDetail(name, component) {
  if (name === "availability") return component.connectivity_status;
  if (name === "latency") return component.latency_ms === null ? "Offline" : formatLatency(component.latency_ms);
  if (name === "errors") return `${formatNumber(component.error_count)} errors on this report`;
  if (name === "firmware") return `${component.version} (minimum ${component.minimum}, ${component.status})`;
  return "";
}

function componentRow(name, component) {
  return el("div", { className: "component-row" }, [
    el("div", { className: "component-row__label", text: COMPONENT_LABELS[name] }),
    el("div", { className: "component-row__points", text: `${formatScore(component.points)} / ${component.max}` }),
    scoreBar((component.points / component.max) * 100),
    el("div", { className: "component-row__detail", text: componentDetail(name, component) }),
  ]);
}

function buildScoreCard(health) {
  const card = el("div", { className: "panel score-card" });
  card.appendChild(el("div", { className: "score-card__big", text: formatScore(health.hygiene_score) }));

  const rows = el("div", { className: "component-rows" });
  for (const name of ["availability", "latency", "errors", "firmware"]) {
    const component = health.score_components && health.score_components[name];
    if (component) rows.appendChild(componentRow(name, component));
  }
  card.appendChild(rows);
  return card;
}

export function renderStationNotFound(container, stationId, onBack) {
  container.textContent = "";
  const backLink = el("a", { text: "\u2190 Back to overview", attrs: { href: "#/" } });
  backLink.addEventListener("click", (event) => {
    event.preventDefault();
    onBack();
  });
  container.appendChild(
    el("div", { className: "panel" }, [backLink, el("p", { text: `Station "${stationId}" not found.` })])
  );
}

export function renderStation(container, state, handlers) {
  container.textContent = "";
  const { health } = state.station;

  if (!health) {
    container.appendChild(el("div", { className: "skeleton", text: "Loading station\u2026" }));
    return;
  }

  const backLink = el("a", { text: "\u2190 Back to overview", attrs: { href: "#/" } });
  backLink.addEventListener("click", (event) => {
    event.preventDefault();
    handlers.onBack();
  });

  const headerRow = el("div", { className: "station-header" }, [
    backLink,
    el("h1", { className: "station-header__id", text: health.station_id }),
    el("span", { text: health.region }),
    el("span", { text: health.firmware_version || "\u2014" }),
    relativeTimeEl(health.last_reported_at),
    statusChip(health.connectivity_status),
  ]);
  container.appendChild(headerRow);

  if (health.is_poor) {
    container.appendChild(el("div", { className: "banner banner--poor", text: "Poor hygiene" }));
  }

  container.appendChild(buildScoreCard(health));
}
