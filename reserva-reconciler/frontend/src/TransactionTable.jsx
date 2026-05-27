import { useEffect, useState, useMemo } from 'react'
import { api, apiUrl } from './api'
import BackendError from './BackendError'

const fmt$ = v =>
  v == null ? '—' : '$' + Number(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

const fmtDate = s => {
  if (!s) return '—'
  const d = new Date(s)
  if (isNaN(d.getTime())) return s.slice(0, 10)
  return `${d.getMonth() + 1}/${d.getDate()}/${d.getFullYear()}`
}

const STATUS_CFG = {
  mapped:        { label: 'mapped',        bg: '#e8eee8', color: '#3a5a3a', border: '#b8d0b8' },
  needs_mapping: { label: 'needs mapping', bg: '#fef3cd', color: '#7a5200', border: '#d4ac20' },
  donor_selects: { label: 'donor selects', bg: '#efefef', color: '#666',    border: '#d0d0d0' },
}

const COLS = [
  { key: 'transaction_date', label: 'Date',        w: 90,  align: 'left'   },
  { key: 'donor_name',       label: 'Donor',       w: 160, align: 'left'   },
  { key: 'campaign_name',    label: 'Campaign',    w: 190, align: 'left'   },
  { key: 'platform',         label: 'Platform',    w: 110, align: 'left'   },
  { key: 'gross_amount',     label: 'Gross',       w: 88,  align: 'right', money: true },
  { key: 'platform_fee',     label: 'Plat. Fee',   w: 76,  align: 'right', money: true },
  { key: 'processing_fee',   label: 'Proc. Fee',   w: 80,  align: 'right', money: true },
  { key: 'net_amount',       label: 'Net',         w: 88,  align: 'right', money: true },
  { key: 'qbo_account',      label: 'QBO Account', w: 210, align: 'left'   },
  { key: 'qbo_class',        label: 'QBO Class',   w: 150, align: 'left'   },
  { key: 'mapping_status',   label: 'Status',      w: 100, align: 'center' },
]

function SortIcon({ active, dir }) {
  if (!active) return <span style={{ opacity: 0.25, marginLeft: 3, fontSize: 10 }}>↕</span>
  return <span style={{ marginLeft: 3, fontSize: 10 }}>{dir === 'asc' ? '↑' : '↓'}</span>
}

function StatusBadge({ status }) {
  const cfg = STATUS_CFG[status] || { label: status, bg: '#eee', color: '#555', border: '#ccc' }
  return (
    <span style={{
      fontSize: 10,
      padding: '1px 5px',
      borderRadius: 3,
      background: cfg.bg,
      color: cfg.color,
      border: `1px solid ${cfg.border}`,
      whiteSpace: 'nowrap',
      fontWeight: 500,
    }}>
      {cfg.label}
    </span>
  )
}

function SummaryBar({ summary, filteredCount, filteredTotals }) {
  const s = summary
  const isFiltered = filteredCount !== s.total_rows

  const cells = [
    { label: 'Gross',        full: s.total_gross,          filtered: filteredTotals.gross },
    { label: 'Platform Fee', full: s.total_platform_fee,   filtered: filteredTotals.platform_fee },
    { label: 'Proc. Fee',    full: s.total_processing_fee, filtered: filteredTotals.processing_fee },
    { label: 'Net',          full: s.total_net,            filtered: filteredTotals.net },
  ]

  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      flexWrap: 'wrap',
      gap: 16,
      padding: '8px 14px',
      background: 'var(--surface)',
      border: '1px solid var(--border)',
      borderRadius: 4,
      marginBottom: 10,
      fontSize: 12,
    }}>
      <span style={{ color: 'var(--muted)', fontWeight: 500 }}>
        {isFiltered
          ? <><strong style={{ color: 'var(--text)' }}>{filteredCount.toLocaleString()}</strong> of {s.total_rows.toLocaleString()} transactions</>
          : <><strong style={{ color: 'var(--text)' }}>{s.total_rows.toLocaleString()}</strong> transactions</>
        }
      </span>

      <span style={{ color: 'var(--border)', userSelect: 'none' }}>|</span>

      {cells.map(c => (
        <span key={c.label} style={{ color: 'var(--muted)' }}>
          {c.label}:{' '}
          <span style={{ fontVariantNumeric: 'tabular-nums', color: 'var(--text)', fontWeight: 500 }}>
            {fmt$(isFiltered ? c.filtered : c.full)}
          </span>
          {isFiltered && c.full !== c.filtered && (
            <span style={{ color: 'var(--muted)', fontWeight: 400 }}> / {fmt$(c.full)}</span>
          )}
        </span>
      ))}

      {s.unmapped_count > 0 && (
        <>
          <span style={{ color: 'var(--border)', userSelect: 'none' }}>|</span>
          <span style={{
            fontSize: 11,
            background: '#fef3cd',
            color: '#7a5200',
            border: '1px solid #d4ac20',
            borderRadius: 3,
            padding: '1px 6px',
          }}>
            {s.unmapped_count} needs mapping
          </span>
        </>
      )}
    </div>
  )
}

function ExportReport({ report }) {
  const t = report.totals
  const hasConfigWarning = (
    report.config?.platform_fee_account?.startsWith('<<') ||
    report.config?.processing_fee_account?.startsWith('<<')
  )

  return (
    <div style={{
      marginTop: 8,
      padding: '10px 14px',
      background: 'var(--surface)',
      border: '1px solid var(--border)',
      borderRadius: 4,
      fontSize: 11,
    }}>
      {hasConfigWarning && (
        <div style={{
          marginBottom: 8,
          padding: '5px 8px',
          background: '#fef3cd',
          border: '1px solid #d4ac20',
          borderRadius: 3,
          color: '#7a5200',
          fontWeight: 500,
        }}>
          Fee account names not configured — set PLATFORM_FEE_ACCOUNT and
          PROCESSING_FEE_ACCOUNT in backend/exporters/sales_receipt_csv.py before importing.
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, auto)', gap: '4px 20px', marginBottom: 8 }}>
        <span style={{ color: 'var(--muted)' }}>Receipts written</span>
        <span style={{ color: 'var(--muted)' }}>Skipped (unmapped)</span>
        <span style={{ color: 'var(--muted)' }}>Recon failures</span>
        <span style={{ color: 'var(--muted)' }}>Deposit to</span>

        <strong>{report.written.toLocaleString()}</strong>
        <strong style={{ color: report.skipped_unmapped > 0 ? '#7a5200' : 'inherit' }}>
          {report.skipped_unmapped.toLocaleString()}
        </strong>
        <strong style={{ color: report.recon_failures?.length > 0 ? 'var(--danger)' : 'inherit' }}>
          {report.recon_failures?.length ?? 0}
        </strong>
        <strong>{report.config?.deposit_to_account}</strong>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, auto)', gap: '4px 20px', marginBottom: 8 }}>
        {[
          ['Gross', t.gross],
          ['Platform fees', t.platform_fee],
          ['Processing fees', t.processing_fee],
          ['Net (deposit)', t.net],
        ].map(([label, val]) => (
          <>
            <span key={label + 'l'} style={{ color: 'var(--muted)' }}>{label}</span>
            <span key={label + 'v'} style={{ fontVariantNumeric: 'tabular-nums' }}>{fmt$(val)}</span>
          </>
        ))}
      </div>

      {report.recon_failures?.length > 0 && (
        <div style={{ marginTop: 6, borderTop: '1px solid var(--border)', paddingTop: 6 }}>
          <div style={{ fontWeight: 600, color: 'var(--danger)', marginBottom: 4 }}>
            Reconciliation failures — review before importing:
          </div>
          {report.recon_failures.map(f => (
            <div key={f.transaction_id} style={{ marginBottom: 2, color: 'var(--danger)' }}>
              #{f.transaction_id} {f.donor_name} — gross {fmt$(f.gross)} − fees{' '}
              {fmt$(f.platform_fee + f.processing_fee)} = {fmt$(f.computed_net)}, recorded net {fmt$(f.net)}{' '}
              (Δ {fmt$(f.delta)})
            </div>
          ))}
        </div>
      )}

      <div style={{ marginTop: 6, borderTop: '1px solid var(--border)', paddingTop: 6, color: 'var(--muted)' }}>
        Columns: {report.columns_used?.join(', ')}
        {' — '}
        <span>Verify against QBO → Settings → Import Data → Sales Receipts template before first sandbox import.</span>
      </div>
    </div>
  )
}

export default function TransactionTable() {
  const [data, setData]       = useState(null)
  const [error, setError]     = useState(null)
  const [loading, setLoading] = useState(true)
  const [text, setText]       = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo]     = useState('')
  const [sort, setSort] = useState({ key: 'transaction_date', dir: 'desc' })

  // export state
  const [exportReport, setExportReport]   = useState(null)
  const [exportLoading, setExportLoading] = useState(false)
  const [exportError, setExportError]     = useState(null)
  const [showReport, setShowReport]       = useState(false)

  useEffect(() => {
    api('/classy/transactions/all')
      .then(r => { if (!r.ok) throw new Error(r.statusText); return r.json() })
      .then(d => { setData(d); setLoading(false) })
      .catch(e => { setError(e instanceof TypeError ? '__network__' : e.message); setLoading(false) })
  }, [])

  function handleSort(key) {
    setSort(prev => prev.key === key
      ? { key, dir: prev.dir === 'asc' ? 'desc' : 'asc' }
      : { key, dir: key.endsWith('_amount') || key.endsWith('_fee') ? 'desc' : 'asc' }
    )
  }

  async function handleExport() {
    setExportLoading(true)
    setExportError(null)
    setExportReport(null)
    setShowReport(true)
    try {
      const res = await api('/export/sales-receipts/report')
      if (!res.ok) throw new Error(res.statusText)
      const report = await res.json()
      setExportReport(report)
    } catch (e) {
      setExportError(e.message)
    } finally {
      setExportLoading(false)
    }
  }

  const filtered = useMemo(() => {
    if (!data) return []
    let rows = data.transactions
    const q = text.trim().toLowerCase()
    if (q) {
      rows = rows.filter(r =>
        (r.donor_name    || '').toLowerCase().includes(q) ||
        (r.campaign_name || '').toLowerCase().includes(q)
      )
    }
    if (dateFrom) rows = rows.filter(r => r.transaction_date.slice(0, 10) >= dateFrom)
    if (dateTo)   rows = rows.filter(r => r.transaction_date.slice(0, 10) <= dateTo)
    return rows
  }, [data, text, dateFrom, dateTo])

  const sorted = useMemo(() => {
    const { key, dir } = sort
    return [...filtered].sort((a, b) => {
      const av = a[key] ?? ''
      const bv = b[key] ?? ''
      if (typeof av === 'number') return dir === 'asc' ? av - bv : bv - av
      const cmp = String(av).localeCompare(String(bv), undefined, { sensitivity: 'base' })
      return dir === 'asc' ? cmp : -cmp
    })
  }, [filtered, sort])

  const filteredTotals = useMemo(() => ({
    gross:          round2(filtered.reduce((s, r) => s + r.gross_amount,     0)),
    platform_fee:   round2(filtered.reduce((s, r) => s + r.platform_fee,     0)),
    processing_fee: round2(filtered.reduce((s, r) => s + r.processing_fee,   0)),
    net:            round2(filtered.reduce((s, r) => s + r.net_amount,       0)),
  }), [filtered])

  if (error) {
    if (error === '__network__') return <BackendError context="transactions" />
    return (
      <div style={{ color: 'var(--danger)', padding: 12, fontSize: 12 }}>
        Error loading transactions: {error}
      </div>
    )
  }

  if (loading) return (
    <div style={{ color: 'var(--muted)', padding: 12, fontSize: 12 }}>
      Loading all transactions… (first load fetches from Classy API and may take ~30 seconds; subsequent loads use a 1-hour cache)
    </div>
  )

  return (
    <div>
      {/* summary */}
      <SummaryBar
        summary={data.summary}
        filteredCount={filtered.length}
        filteredTotals={filteredTotals}
      />

      {/* export */}
      <div style={{ marginBottom: 10 }}>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <button
            type="button"
            onClick={handleExport}
            disabled={exportLoading}
            style={{
              padding: '4px 12px',
              fontSize: 12,
              fontWeight: 500,
              background: exportLoading ? 'var(--border)' : 'var(--accent)',
              color: exportLoading ? 'var(--muted)' : '#fff',
              border: 'none',
              borderRadius: 3,
              cursor: exportLoading ? 'default' : 'pointer',
            }}
          >
            {exportLoading ? 'Generating report…' : 'Export to QBO CSV'}
          </button>

          {exportReport && !exportLoading && (
            <a
              href={apiUrl('/export/sales-receipts/download')}
              style={{
                padding: '4px 12px',
                fontSize: 12,
                fontWeight: 500,
                background: 'var(--surface)',
                color: 'var(--accent)',
                border: '1px solid var(--accent)',
                borderRadius: 3,
                textDecoration: 'none',
              }}
            >
              Download CSV
            </a>
          )}

          {exportReport && (
            <button
              type="button"
              onClick={() => setShowReport(r => !r)}
              style={{ ...clearBtnStyle, fontSize: 11 }}
            >
              {showReport ? 'Hide report' : 'Show report'}
            </button>
          )}
        </div>

        {exportError && (
          <div style={{ marginTop: 6, fontSize: 11, color: 'var(--danger)' }}>
            Export error: {exportError}
          </div>
        )}

        {showReport && exportReport && (
          <ExportReport report={exportReport} />
        )}
      </div>

      {/* filters */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 10, flexWrap: 'wrap', alignItems: 'center' }}>
        <input
          type="search"
          placeholder="Filter by donor or campaign…"
          value={text}
          onChange={e => setText(e.target.value)}
          style={{ ...inputStyle, width: 240 }}
        />
        <span style={{ fontSize: 11, color: 'var(--muted)' }}>From</span>
        <input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)} style={inputStyle} />
        <span style={{ fontSize: 11, color: 'var(--muted)' }}>To</span>
        <input type="date" value={dateTo}   onChange={e => setDateTo(e.target.value)}   style={inputStyle} />
        {(text || dateFrom || dateTo) && (
          <button
            type="button"
            onClick={() => { setText(''); setDateFrom(''); setDateTo('') }}
            style={clearBtnStyle}
          >
            Clear
          </button>
        )}
      </div>

      {/* table */}
      <div style={{ overflowX: 'auto', border: '1px solid var(--border)', borderRadius: 4 }}>
        <table style={{ borderCollapse: 'collapse', width: '100%', fontSize: 11 }}>
          <thead>
            <tr style={{ background: 'var(--bg)', borderBottom: '1px solid var(--border)' }}>
              {COLS.map(col => (
                <th
                  key={col.key}
                  onClick={() => handleSort(col.key)}
                  style={{
                    padding: '5px 8px',
                    textAlign: col.align,
                    whiteSpace: 'nowrap',
                    color: 'var(--muted)',
                    fontWeight: 500,
                    cursor: 'pointer',
                    userSelect: 'none',
                    minWidth: col.w,
                    borderRight: '1px solid var(--border-soft, #ece7e2)',
                  }}
                >
                  {col.label}
                  <SortIcon active={sort.key === col.key} dir={sort.dir} />
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sorted.length === 0 ? (
              <tr>
                <td colSpan={COLS.length} style={{ padding: '12px 14px', color: 'var(--muted)', fontSize: 12 }}>
                  No transactions match the current filters.
                </td>
              </tr>
            ) : sorted.map((row, i) => (
              <tr
                key={row.transaction_id}
                style={{
                  background: i % 2 === 0 ? 'var(--surface)' : 'var(--bg)',
                  borderBottom: '1px solid var(--border-soft, #ece7e2)',
                }}
              >
                {/* date */}
                <td style={tdStyle('left')}>{fmtDate(row.transaction_date)}</td>

                {/* donor */}
                <td style={{ ...tdStyle('left'), maxWidth: 160, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  <span title={row.donor_name}>{row.donor_name || '—'}</span>
                </td>

                {/* campaign */}
                <td style={{ ...tdStyle('left'), maxWidth: 190, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  <span title={row.campaign_name}>{row.campaign_name || '—'}</span>
                </td>

                {/* platform */}
                <td style={tdStyle('left')}>
                  <span style={{
                    fontSize: 10,
                    padding: '1px 5px',
                    borderRadius: 3,
                    background: 'var(--platform-bg)',
                    color: 'var(--platform)',
                    border: '1px solid #b2d0ca',
                    fontWeight: 500,
                    whiteSpace: 'nowrap',
                  }}>
                    {row.platform}
                  </span>
                </td>

                {/* money cols */}
                <td style={moneyTd}>{fmt$(row.gross_amount)}</td>
                <td style={{ ...moneyTd, color: 'var(--muted)' }}>{fmt$(row.platform_fee)}</td>
                <td style={{ ...moneyTd, color: 'var(--muted)' }}>{fmt$(row.processing_fee)}</td>
                <td style={{ ...moneyTd, fontWeight: 500 }}>{fmt$(row.net_amount)}</td>

                {/* qbo account */}
                <td style={{ ...tdStyle('left'), maxWidth: 210, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  <span title={row.qbo_account}>{row.qbo_account || <span style={{ color: 'var(--muted)' }}>—</span>}</span>
                </td>

                {/* qbo class */}
                <td style={{ ...tdStyle('left'), maxWidth: 150, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  <span title={row.qbo_class}>{row.qbo_class || <span style={{ color: 'var(--muted)' }}>—</span>}</span>
                </td>

                {/* status */}
                <td style={{ ...tdStyle('center') }}>
                  <StatusBadge status={row.mapping_status} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function round2(n) { return Math.round(n * 100) / 100 }

const tdStyle = align => ({
  padding: '4px 8px',
  textAlign: align,
  verticalAlign: 'middle',
  color: 'var(--text)',
  borderRight: '1px solid var(--border-soft, #ece7e2)',
})

const moneyTd = {
  ...tdStyle('right'),
  fontVariantNumeric: 'tabular-nums',
  whiteSpace: 'nowrap',
}

const inputStyle = {
  padding: '4px 8px',
  border: '1px solid var(--border)',
  borderRadius: 3,
  background: 'var(--surface)',
  color: 'var(--text)',
  fontSize: 12,
  outline: 'none',
}

const clearBtnStyle = {
  padding: '4px 10px',
  background: 'none',
  border: '1px solid var(--border)',
  borderRadius: 3,
  color: 'var(--muted)',
  fontSize: 12,
  cursor: 'pointer',
}
