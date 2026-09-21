// Thin fetch wrapper for the public REST API.

const API_BASE = "/api/v1";

export class ApiError extends Error {
  constructor(status, code, message) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

export async function getJSON(path, params = {}, { timeoutMs = 10000 } = {}) {
  const url = new URL(API_BASE + path, window.location.origin);
  for (const [key, value] of Object.entries(params)) {
    if (value !== null && value !== undefined && value !== "") {
      url.searchParams.set(key, value);
    }
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url.toString(), { signal: controller.signal });
    let body = null;
    try {
      body = await response.json();
    } catch {
      body = null;
    }
    if (!response.ok) {
      const error = body && body.error ? body.error : {};
      throw new ApiError(response.status, error.code || "internal_error", error.message || "Request failed.");
    }
    return body;
  } finally {
    clearTimeout(timeout);
  }
}
