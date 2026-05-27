/**
 * api.js — centralised API URL helper.
 *
 * In local dev (Vite proxy): VITE_API_BASE_URL is empty → relative URLs,
 * proxied by vite.config.js to http://127.0.0.1:8000.
 *
 * In the GitHub Pages build: VITE_API_BASE_URL points to the Render-hosted
 * backend (https://reserva-reconciler-backend.onrender.com). Free tier sleeps
 * after 15 min idle; first request after sleep takes ~30s to wake.
 */
export const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '')

/**
 * True when the app is running as a static GitHub Pages build with no backend
 * URL configured. Components can use this to show a "not connected" screen
 * instead of a confusing 404 error.
 */
export const NO_BACKEND =
  API_BASE === '' && !window.location.hostname.includes('localhost')

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

/**
 * Ping the backend /health endpoint with retries.
 * Used to wake up a sleeping Render free-tier instance before the user
 * sees a stack of failed fetches in the UI.
 *
 * Calls onTick(attempt, elapsedMs) on every retry so the UI can show
 * "still waking up, please wait" feedback.
 *
 * Resolves true once /health returns 200.
 * Resolves false if maxAttempts is exhausted without success.
 */
export async function waitForBackend({
  maxAttempts = 30,
  intervalMs = 2000,
  onTick = () => {},
} = {}) {
  const started = Date.now()
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    onTick(attempt, Date.now() - started)
    try {
      const ctrl = new AbortController()
      const t = setTimeout(() => ctrl.abort(), 8000)
      const r = await fetch(API_BASE + '/health', { signal: ctrl.signal })
      clearTimeout(t)
      if (r.ok) return true
    } catch (_) {
      // network error → backend still asleep, keep retrying
    }
    await new Promise(res => setTimeout(res, intervalMs))
  }
  return false
}
