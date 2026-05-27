import { useState, useEffect } from 'react'
import DonorCRM from './DonorCRM'
import MappingPanel from './MappingPanel'
import TransactionTable from './TransactionTable'
import { NO_BACKEND, waitForBackend } from './api'

const TABS = [
  { id: 'donors',       label: 'Donors' },
  { id: 'transactions', label: 'Transactions' },
  { id: 'mapping',      label: 'Campaign Mapping' },
]

function NoBackendScreen() {
  return (
    <div style={{
      minHeight: '60vh',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      gap: 20,
      padding: '40px 16px',
      textAlign: 'center',
    }}>
      <div style={{
        fontSize: 32,
        lineHeight: 1,
      }}>🌿</div>

      <div>
        <div style={{ fontWeight: 600, fontSize: 15, color: 'var(--text)', marginBottom: 6 }}>
          Reserva Reconciler
        </div>
        <div style={{ fontSize: 12, color: 'var(--muted)', maxWidth: 400 }}>
          This app needs a running backend to load donor and transaction data.
          The backend is a local FastAPI server — it's not included in this static deployment.
        </div>
      </div>

      <div style={{
        background: 'var(--surface)',
        border: '1px solid var(--border)',
        borderRadius: 6,
        padding: '20px 28px',
        maxWidth: 480,
        textAlign: 'left',
        fontSize: 12,
        color: 'var(--text)',
      }}>
        <div style={{ fontWeight: 600, marginBottom: 12, color: 'var(--text)' }}>
          To connect the backend:
        </div>

        <ol style={{ paddingLeft: 18, lineHeight: 2.2, color: 'var(--muted)' }}>
          <li>
            Start the backend locally:&nbsp;
            <code style={{ background: '#e8e2db', padding: '1px 5px', borderRadius: 3, fontFamily: 'monospace', fontSize: 11 }}>
              uvicorn main:app --reload
            </code>
          </li>
          <li>
            Start an ngrok tunnel:&nbsp;
            <code style={{ background: '#e8e2db', padding: '1px 5px', borderRadius: 3, fontFamily: 'monospace', fontSize: 11 }}>
              ngrok http 8000
            </code>
          </li>
          <li>
            In the repo, go to&nbsp;
            <strong>Settings → Secrets and variables → Actions → Variables</strong>
          </li>
          <li>
            Set&nbsp;
            <code style={{ background: '#e8e2db', padding: '1px 5px', borderRadius: 3, fontFamily: 'monospace', fontSize: 11 }}>
              VITE_API_BASE_URL
            </code>
            &nbsp;to your ngrok URL (e.g.&nbsp;
            <code style={{ background: '#e8e2db', padding: '1px 5px', borderRadius: 3, fontFamily: 'monospace', fontSize: 11 }}>
              https://xxxx.ngrok-free.app
            </code>
            )
          </li>
          <li>
            Trigger a redeploy:&nbsp;
            <strong>Actions → Deploy Frontend → Run workflow</strong>
          </li>
        </ol>

        <div style={{
          marginTop: 14,
          paddingTop: 14,
          borderTop: '1px solid var(--border)',
          color: 'var(--muted)',
          fontSize: 11,
        }}>
          For day-to-day use, run the frontend locally at&nbsp;
          <code style={{ background: '#e8e2db', padding: '1px 5px', borderRadius: 3, fontFamily: 'monospace' }}>
            http://localhost:5173
          </code>
          &nbsp;— no tunnel needed.
        </div>
      </div>
    </div>
  )
}

function WakingUpScreen({ seconds }) {
  return (
    <div style={{
      minHeight: '60vh',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      gap: 18,
      padding: '40px 16px',
      textAlign: 'center',
    }}>
      <div style={{ fontSize: 30 }}>🌿</div>
      <div style={{ fontWeight: 600, fontSize: 15, color: 'var(--text)' }}>
        Waking up the backend…
      </div>
      <div style={{ fontSize: 12, color: 'var(--muted)', maxWidth: 380 }}>
        The Render free-tier backend sleeps after 15 minutes of inactivity.
        First load takes ~30 seconds. Elapsed: {seconds}s.
      </div>
      <div style={{
        width: 200, height: 3, background: 'var(--border)', borderRadius: 2, overflow: 'hidden',
      }}>
        <div style={{
          width: `${Math.min(100, (seconds / 45) * 100)}%`,
          height: '100%',
          background: 'var(--platform)',
          transition: 'width 0.5s linear',
        }} />
      </div>
    </div>
  )
}

export default function App() {
  const [tab, setTab] = useState('donors')
  // 'waking' | 'ready' | 'failed' (or 'waking' permanently if NO_BACKEND, since
  // the NO_BACKEND branch renders before this state matters)
  const [backendStatus, setBackendStatus] = useState('waking')
  const [wakeSeconds, setWakeSeconds] = useState(0)

  useEffect(() => {
    if (NO_BACKEND) return
    let cancelled = false
    waitForBackend({
      maxAttempts: 30,
      intervalMs: 2000,
      onTick: (_attempt, elapsedMs) => {
        if (!cancelled) setWakeSeconds(Math.round(elapsedMs / 1000))
      },
    }).then(ok => {
      if (!cancelled) setBackendStatus(ok ? 'ready' : 'failed')
    })
    return () => { cancelled = true }
  }, [])

  return (
    <div>
      <header style={{
        borderBottom: '1px solid var(--border)',
        padding: '10px 0 0',
        marginBottom: 0,
        display: 'flex',
        alignItems: 'flex-end',
        gap: 12,
      }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, paddingBottom: 10 }}>
          <span style={{ fontWeight: 600, fontSize: 14, color: 'var(--text)' }}>
            Reserva Reconciler
          </span>
          <span style={{
            fontSize: 11,
            background: 'var(--platform-bg)',
            color: 'var(--platform)',
            border: '1px solid #b2d0ca',
            borderRadius: 3,
            padding: '1px 6px',
            letterSpacing: '0.02em',
          }}>
            GoFundMe Pro
          </span>
        </div>

        {!NO_BACKEND && backendStatus === 'ready' && (
          <nav style={{ display: 'flex', gap: 2, marginLeft: 12 }}>
            {TABS.map(t => (
              <button
                key={t.id}
                type="button"
                onClick={() => setTab(t.id)}
                style={{
                  padding: '5px 14px',
                  fontSize: 12,
                  fontWeight: tab === t.id ? 600 : 400,
                  background: tab === t.id ? 'var(--surface)' : 'transparent',
                  color: tab === t.id ? 'var(--text)' : 'var(--muted)',
                  border: '1px solid var(--border)',
                  borderBottom: tab === t.id ? '1px solid var(--surface)' : '1px solid var(--border)',
                  borderRadius: '3px 3px 0 0',
                  cursor: 'pointer',
                  position: 'relative',
                  bottom: -1,
                }}
              >
                {t.label}
              </button>
            ))}
          </nav>
        )}
      </header>

      <div style={{ padding: '16px 0' }}>
        {NO_BACKEND ? (
          <NoBackendScreen />
        ) : backendStatus === 'waking' ? (
          <WakingUpScreen seconds={wakeSeconds} />
        ) : backendStatus === 'failed' ? (
          <NoBackendScreen />
        ) : (
          <>
            {tab === 'donors'       && <DonorCRM />}
            {tab === 'transactions' && <TransactionTable />}
            {tab === 'mapping'      && <MappingPanel />}
          </>
        )}
      </div>
    </div>
  )
}
