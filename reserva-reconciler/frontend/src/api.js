/**
 * api.js — centralised API URL helper.
 *
 * In local dev (Vite proxy): VITE_API_BASE_URL is empty → relative URLs,
 * proxied by vite.config.js to http://127.0.0.1:8000.
 *
 * In the GitHub Pages build: set VITE_API_BASE_URL to the publicly-accessible
 * backend URL (e.g. https://your-ngrok-tunnel.ngrok.io) via a GitHub Actions
 * repo variable (Settings → Variables → Actions → VITE_API_BASE_URL).
 */
export const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '')

/**
 * fetch() wrapper that prepends API_BASE.
 * Usage: api('/classy/transactions/all').then(r => r.json())
 */
export function api(path, init) {
  return fetch(API_BASE + path, init)
}

/** Absolute URL string for use in <a href> or window.location */
export function apiUrl(path) {
  return API_BASE + path
}
