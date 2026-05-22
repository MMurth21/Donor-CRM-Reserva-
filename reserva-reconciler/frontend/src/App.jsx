import MappingPanel from './MappingPanel'

export default function App() {
  return (
    <div>
      <header style={{
        borderBottom: '1px solid var(--border)',
        padding: '10px 0 8px',
        marginBottom: 20,
        display: 'flex',
        alignItems: 'baseline',
        gap: 12,
      }}>
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
      </header>
      <MappingPanel />
    </div>
  )
}
