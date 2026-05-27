import { useState } from 'react'
import { api } from './api'

const NEW_SENTINEL = '__new__'

function SelectOrNew({ value, onChange, options, placeholder }) {
  const [adding, setAdding] = useState(false)
  const [custom, setCustom] = useState('')

  if (adding) {
    return (
      <div style={{ display: 'flex', gap: 4 }}>
        <input
          autoFocus
          value={custom}
          onChange={e => setCustom(e.target.value)}
          onKeyDown={e => {
            if (e.key === 'Enter' && custom.trim()) { onChange(custom.trim()); setAdding(false) }
            if (e.key === 'Escape') { setAdding(false) }
          }}
          placeholder="Type new value…"
          style={inputStyle}
        />
        <button
          type="button"
          onClick={() => { if (custom.trim()) { onChange(custom.trim()); setAdding(false) } }}
          style={btnSmallStyle}
        >✓</button>
        <button
          type="button"
          onClick={() => setAdding(false)}
          style={{ ...btnSmallStyle, background: 'none', border: '1px solid var(--border)', color: 'var(--muted)' }}
        >✕</button>
      </div>
    )
  }

  return (
    <select
      value={value}
      onChange={e => {
        if (e.target.value === NEW_SENTINEL) { setAdding(true); onChange('') }
        else onChange(e.target.value)
      }}
      style={selectStyle}
    >
      <option value="">{placeholder}</option>
      {options.map(o => <option key={o} value={o}>{o}</option>)}
      <option value={NEW_SENTINEL}>+ add new…</option>
    </select>
  )
}

export default function CampaignRow({ campaign, options, isLast, onSaved }) {
  const [account, setAccount] = useState('')
  const [cls, setCls] = useState('')
  const [donorSelects, setDonorSelects] = useState(false)
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState(null)

  const canSave = donorSelects || (account.trim() && cls.trim())

  async function handleSave() {
    setSaving(true)
    setErr(null)
    try {
      const res = await api('/mapping/assign', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          campaign_id:   campaign.campaign_id,
          qbo_account:   donorSelects ? '' : account,
          qbo_class:     donorSelects ? '' : cls,
          donor_selects: donorSelects,
        }),
      })
      if (!res.ok) {
        const body = await res.json()
        throw new Error(body.detail || res.statusText)
      }
      onSaved(campaign.campaign_id)
    } catch (e) {
      setErr(e.message)
      setSaving(false)
    }
  }

  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: '1fr 80px 90px 200px 200px 90px 56px',
      gap: 8,
      padding: '8px 12px',
      borderBottom: isLast ? 'none' : '1px solid var(--border-soft)',
      alignItems: 'center',
      background: err ? '#fdf5f5' : undefined,
    }}>
      {/* campaign name + id */}
      <div>
        <div style={{ fontWeight: 500, fontSize: 12, color: 'var(--text)', lineHeight: 1.3 }}>
          {campaign.campaign_name}
        </div>
        <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 1 }}>
          #{campaign.campaign_id}
        </div>
        {err && <div style={{ fontSize: 11, color: 'var(--danger)', marginTop: 2 }}>{err}</div>}
      </div>

      {/* txn count */}
      <div style={{ textAlign: 'right', fontSize: 12, color: 'var(--muted)' }}>
        {campaign.txn_count}
      </div>

      {/* gross */}
      <div style={{ textAlign: 'right', fontSize: 12, fontVariantNumeric: 'tabular-nums' }}>
        ${campaign.total_gross.toLocaleString('en-US', { minimumFractionDigits: 2 })}
      </div>

      {/* account dropdown */}
      <div style={{ opacity: donorSelects ? 0.35 : 1, pointerEvents: donorSelects ? 'none' : 'auto' }}>
        <SelectOrNew
          value={account}
          onChange={setAccount}
          options={options.qbo_accounts}
          placeholder="Select account…"
        />
      </div>

      {/* class dropdown */}
      <div style={{ opacity: donorSelects ? 0.35 : 1, pointerEvents: donorSelects ? 'none' : 'auto' }}>
        <SelectOrNew
          value={cls}
          onChange={setCls}
          options={options.qbo_classes}
          placeholder="Select class…"
        />
      </div>

      {/* donor selects checkbox */}
      <div style={{ textAlign: 'center' }}>
        <input
          type="checkbox"
          checked={donorSelects}
          onChange={e => setDonorSelects(e.target.checked)}
          style={{ accentColor: 'var(--accent)', cursor: 'pointer' }}
        />
      </div>

      {/* save button */}
      <div>
        <button
          type="button"
          disabled={!canSave || saving}
          onClick={handleSave}
          style={{
            width: '100%',
            padding: '4px 0',
            background: canSave && !saving ? 'var(--accent)' : 'var(--border)',
            color: canSave && !saving ? '#fff' : 'var(--muted)',
            border: 'none',
            borderRadius: 3,
            fontWeight: 500,
            fontSize: 12,
          }}
        >
          {saving ? '…' : 'Save'}
        </button>
      </div>
    </div>
  )
}

const selectStyle = {
  width: '100%',
  padding: '4px 6px',
  border: '1px solid var(--border)',
  borderRadius: 3,
  background: 'var(--surface)',
  color: 'var(--text)',
  fontSize: 12,
}

const inputStyle = {
  flex: 1,
  padding: '4px 6px',
  border: '1px solid var(--accent)',
  borderRadius: 3,
  background: 'var(--surface)',
  color: 'var(--text)',
  fontSize: 12,
  outline: 'none',
}

const btnSmallStyle = {
  padding: '4px 7px',
  background: 'var(--accent)',
  color: '#fff',
  border: 'none',
  borderRadius: 3,
  fontSize: 12,
}
