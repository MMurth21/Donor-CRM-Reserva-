import { useState } from 'react'
import MappingPanel from './MappingPanel'
import TransactionTable from './TransactionTable'

const TABS = [
  { id: 'transactions', label: 'Transactions' },
  { id: 'mapping',      label: 'Campaign Mapping' },
]

export default function App() {
  const [tab, setTab] = useState('transactions')

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
      </header>

      <div style={{ padding: '16px 0' }}>
        {tab === 'transactions' ? <TransactionTable /> : <MappingPanel />}
      </div>
    </div>
  )
}
