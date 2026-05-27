import { useEffect, useState } from 'react'
import CampaignRow from './CampaignRow'
import { api } from './api'
import BackendError from './BackendError'

export default function MappingPanel() {
  const [campaigns, setCampaigns] = useState(null)
  const [options, setOptions] = useState({ qbo_accounts: [], qbo_classes: [] })
  const [error, setError] = useState(null)

  useEffect(() => {
    Promise.all([
      api('/mapping/unmapped').then(r => r.json()),
      api('/mapping/options').then(r => r.json()),
    ])
      .then(([unmapped, opts]) => {
        setCampaigns(unmapped.campaigns)
        setOptions(opts)
      })
      .catch(e => setError(e instanceof TypeError ? '__network__' : e.message))
  }, [])

  function handleSaved(campaign_id) {
    setCampaigns(prev => prev.filter(c => c.campaign_id !== campaign_id))
  }

  if (error) {
    if (error === '__network__') return <BackendError context="campaign mapping" />
    return (
      <div style={{ color: 'var(--danger)', padding: 12, fontSize: 12 }}>
        Error loading mapping data: {error}
      </div>
    )
  }

  if (!campaigns) return (
    <div style={{ color: 'var(--muted)', padding: 12, fontSize: 12 }}>
      Loading…
    </div>
  )

  return (
    <div>
      <div style={{
        display: 'flex',
        alignItems: 'baseline',
        gap: 10,
        marginBottom: 12,
      }}>
        <h2 style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)' }}>
          Needs Mapping
        </h2>
        {campaigns.length > 0 && (
          <span style={{
            fontSize: 11,
            background: '#f5e8e8',
            color: 'var(--danger)',
            border: '1px solid #e0c0c0',
            borderRadius: 3,
            padding: '1px 6px',
          }}>
            {campaigns.length} campaign{campaigns.length !== 1 ? 's' : ''}
          </span>
        )}
      </div>

      {campaigns.length === 0 ? (
        <div style={{
          padding: '12px 14px',
          background: 'var(--accent-dim)',
          border: '1px solid #c2d8c2',
          borderRadius: 4,
          color: 'var(--accent)',
          fontSize: 12,
        }}>
          All campaigns that move money are mapped.
        </div>
      ) : (
        <div style={{
          background: 'var(--surface)',
          border: '1px solid var(--border)',
          borderRadius: 4,
          overflow: 'hidden',
        }}>
          {/* header row */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: '1fr 80px 90px 200px 200px 90px 56px',
            gap: 8,
            padding: '6px 12px',
            borderBottom: '1px solid var(--border)',
            background: 'var(--bg)',
            fontSize: 11,
            color: 'var(--muted)',
            fontWeight: 500,
          }}>
            <span>Campaign</span>
            <span style={{ textAlign: 'right' }}>Txns</span>
            <span style={{ textAlign: 'right' }}>Gross</span>
            <span>QBO Account</span>
            <span>QBO Class</span>
            <span style={{ textAlign: 'center' }}>Donor Selects</span>
            <span />
          </div>

          {campaigns.map((c, i) => (
            <CampaignRow
              key={c.campaign_id}
              campaign={c}
              options={options}
              isLast={i === campaigns.length - 1}
              onSaved={handleSaved}
            />
          ))}
        </div>
      )}
    </div>
  )
}
