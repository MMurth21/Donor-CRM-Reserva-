/**
 * BackendError.jsx
 *
 * Shown when the frontend has a backend URL configured (VITE_API_BASE_URL is
 * set in the build) but cannot actually reach it — e.g. the ngrok tunnel
 * expired or the local uvicorn server isn't running.
 *
 * This is distinct from the NO_BACKEND state (no URL configured at all),
 * which App.jsx handles before rendering any panels.
 */

const code = s => (
  <code style={{
    background: '#e8e2db',
    padding: '1px 5px',
    borderRadius: 3,
    fontFamily: 'ui-monospace, "Cascadia Code", Menlo, monospace',
    fontSize: 11,
  }}>
    {s}
  </code>
)

export default function BackendError({ context = 'data' }) {
  return (
    <div style={{
      minHeight: '40vh',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      gap: 16,
      padding: '32px 16px',
      textAlign: 'center',
    }}>
      <div style={{ fontSize: 28, lineHeight: 1 }}>⚠️</div>

      <div>
        <div style={{ fontWeight: 600, fontSize: 14, color: 'var(--text)', marginBottom: 6 }}>
          Can't reach the backend
        </div>
        <div style={{ fontSize: 12, color: 'var(--muted)', maxWidth: 420 }}>
          The app is configured to connect to a backend, but the request for{' '}
          <strong>{context}</strong> failed at the network level. The backend
          server is probably not running, or the tunnel URL has expired.
        </div>
      </div>

      <div style={{
        background: 'var(--surface)',
        border: '1px solid var(--border)',
        borderRadius: 6,
        padding: '16px 24px',
        maxWidth: 480,
        textAlign: 'left',
        fontSize: 12,
        color: 'var(--text)',
      }}>
        <div style={{ fontWeight: 600, marginBottom: 10, color: 'var(--text)' }}>
          To reconnect:
        </div>
        <ol style={{ paddingLeft: 18, lineHeight: 2.2, color: 'var(--muted)', margin: 0 }}>
          <li>
            Start the backend:{' '}
            {code('uvicorn main:app --reload')}
          </li>
          <li>
            Start an ngrok tunnel:{' '}
            {code('ngrok http 8000')}
          </li>
          <li>
            In the repo go to{' '}
            <strong>Settings → Variables → Actions</strong>
          </li>
          <li>
            Update {code('VITE_API_BASE_URL')} to the new ngrok URL
          </li>
          <li>
            Retrigger:{' '}
            <strong>Actions → Deploy Frontend → Run workflow</strong>
          </li>
        </ol>
        <div style={{
          marginTop: 12,
          paddingTop: 12,
          borderTop: '1px solid var(--border)',
          fontSize: 11,
          color: 'var(--muted)',
        }}>
          For day-to-day use, run the frontend locally at{' '}
          {code('http://localhost:5173')} — no tunnel needed.
        </div>
      </div>
    </div>
  )
}
