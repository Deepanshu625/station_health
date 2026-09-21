// Number and time formatting helpers used across the dashboard.

const numberFormatter = new Intl.NumberFormat("en-US");
const integerFormatter = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
const scoreFormatter = new Intl.NumberFormat("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 });

export function formatNumber(value) {
  if (value === null || value === undefined) return "\u2014";
  return numberFormatter.format(value);
}

export function formatLatency(ms) {
  if (ms === null || ms === undefined) return "\u2014";
  return `${integerFormatter.format(ms)} ms`;
}

export function formatScore(score) {
  if (score === null || score === undefined) return "\u2014";
  return scoreFormatter.format(score);
}

export function scoreSeverity(score) {
  if (score === null || score === undefined) return "neutral";
  if (score < 40) return "bad";
  if (score < 60) return "warn";
  return "ok";
}

export function formatRelativeTime(isoString) {
  if (!isoString) return "never";
  const then = new Date(isoString).getTime();
  const now = Date.now();
  const seconds = Math.max(0, Math.round((now - then) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  const days = Math.round(hours / 24);
  return `${days} d ago`;
}
