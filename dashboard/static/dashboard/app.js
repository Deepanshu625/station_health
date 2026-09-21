// Bootstrap, hash routing, and the polling loop.

import { ApiError, getJSON } from "./api.js";
import { renderOverview, renderStation, renderStationNotFound } from "./render.js";

const body = document.body;
const refreshSeconds = Number(body.dataset.refreshSeconds || 30);
const overviewSection = document.getElementById("view-overview");
const stationSection = document.getElementById("view-station");
const updatedLabel = document.getElementById("updated-label");
const errorBanner = document.getElementById("error-banner");
const refreshButton = document.getElementById("refresh-button");

const DEFAULT_LIMIT = 20;

const state = {
  route: { view: "overview", stationId: null },
  filters: { region: "all" },
  overview: { metrics: null, problems: null, limit: DEFAULT_LIMIT },
  station: { health: null, notFound: false },
  lastUpdated: null,
  inFlight: false,
  error: null,
};

function parseHash() {
  const hash = window.location.hash.replace(/^#/, "") || "/";
  const [path, query] = hash.split("?");
  const params = new URLSearchParams(query || "");
  const stationMatch = path.match(/^\/stations\/([^/]+)$/);

  return {
    view: stationMatch ? "station" : "overview",
    stationId: stationMatch ? decodeURIComponent(stationMatch[1]) : null,
    filters: { region: params.get("region") || "all" },
  };
}

function writeHash(view, stationId, filters) {
  if (view === "station") {
    window.location.hash = `#/stations/${encodeURIComponent(stationId)}`;
    return;
  }
  const params = new URLSearchParams();
  if (filters.region !== "all") params.set("region", filters.region);
  const query = params.toString();
  window.location.hash = query ? `#/?${query}` : "#/";
}

function setUpdatedLabel() {
  if (!state.lastUpdated) {
    updatedLabel.textContent = "Loading\u2026";
    return;
  }
  const seconds = Math.round((Date.now() - state.lastUpdated) / 1000);
  updatedLabel.textContent = `Updated ${seconds}s ago \u00b7 refreshes every ${refreshSeconds}s`;
}

function showError(message) {
  state.error = message;
  errorBanner.textContent = message;
  errorBanner.hidden = false;
}

function clearError() {
  state.error = null;
  errorBanner.hidden = true;
}

async function loadOverview() {
  const [metrics, problems] = await Promise.all([
    getJSON("/metrics", { group_by: "region" }),
    getJSON("/stations/poor-hygiene", {
      region: state.filters.region === "all" ? "" : state.filters.region,
      limit: state.overview.limit,
    }),
  ]);
  state.overview.metrics = metrics;
  state.overview.problems = problems;
}

async function loadStation(stationId) {
  try {
    const health = await getJSON(`/stations/${encodeURIComponent(stationId)}/health`);
    state.station = { health, notFound: false };
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      state.station = { health: null, notFound: true };
      return;
    }
    throw error;
  }
}

function overviewHandlers() {
  return {
    poorThreshold: 60,
    onRegionChange(region) {
      const next = state.filters.region === region ? "all" : region;
      state.filters.region = next;
      state.overview.limit = DEFAULT_LIMIT;
      writeHash("overview", null, state.filters);
      refresh(true);
    },
    onNavigateStation(stationId) {
      window.location.hash = `#/stations/${encodeURIComponent(stationId)}`;
    },
    onShowMore() {
      state.overview.limit += DEFAULT_LIMIT;
      refresh(true);
    },
  };
}

function render() {
  const isOverview = state.route.view === "overview";
  overviewSection.hidden = !isOverview;
  stationSection.hidden = isOverview;

  if (isOverview) {
    renderOverview(overviewSection, state, overviewHandlers());
  } else if (state.station.notFound) {
    renderStationNotFound(stationSection, state.route.stationId, () => {
      window.location.hash = "#/";
    });
  } else {
    renderStation(stationSection, state, {
      onBack: () => {
        window.location.hash = "#/";
      },
    });
  }
  setUpdatedLabel();
}

async function refresh(force = false) {
  if (state.inFlight && !force) return;
  if (document.hidden && !force) return;
  state.inFlight = true;
  try {
    if (state.route.view === "overview") {
      await loadOverview();
    } else {
      await loadStation(state.route.stationId);
    }
    state.lastUpdated = Date.now();
    clearError();
  } catch (error) {
    const message = error instanceof ApiError ? `Refresh failed: ${error.message}` : "Refresh failed.";
    showError(message);
  } finally {
    state.inFlight = false;
    render();
  }
}

function route() {
  const parsed = parseHash();
  state.route = { view: parsed.view, stationId: parsed.stationId };
  if (parsed.view === "overview") {
    state.filters = parsed.filters;
  }
  refresh(true);
}

window.addEventListener("hashchange", route);
refreshButton.addEventListener("click", () => refresh(true));
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) refresh(true);
});

setInterval(() => refresh(false), refreshSeconds * 1000);
setInterval(setUpdatedLabel, 1000);

route();
