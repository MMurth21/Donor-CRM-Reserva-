import { useEffect, useState, useMemo } from 'react'
import { api } from './api'
import BackendError from './BackendError'

// ── formatting ────────────────────────────────────────────────────────────────

const fmt$ = v =>
  v == null
    ? '—'
    : '$' + Number(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

const fmtDate = s => {
  if (!s) return '—'
  const d = new Date(s)
  if (isNaN(d.getTime())) return s.slice(0, 10)
  const mm = d.getUTCMonth() + 1
  const dd = d.getUTCDate()
  const yy = String(d.getUTCFullYear()).slice(2)
  return `${mm}/${dd}/${yy}`
}

function round2(n) { return Math.round(n * 100) / 100 }

// ── safe donor key — NO PII in URLs ──────────────────────────────────────────

/** djb2-derived hash; returns 8-char base-36 string — not for crypto, only URL safety */
function _hash(str) {
  let h = 5381
  for (let i = 0; i < str.length; i++) {
    h = (Math.imul(31, h) + str.charCodeAt(i)) | 0
  }
  return (h >>> 0).toString(36).padStart(7, '0')
}

/** Computes a safe, stable, non-PII key for a transaction's donor. */
function donorKey(txn) {
  if (txn.donor_supporter_id) return 'sid_' + txn.donor_supporter_id
  if (txn.donor_email)        return 'em_'  + _hash(txn.donor_email)
  return 'unk'
}

// ── privacy enforcement — render layer only ───────────────────────────────────

/** Returns the display name. Anonymous donors always show "Anonymous donor". */
function privacyName(donor) {
  return donor.is_anonymous ? 'Anonymous donor' : (donor.donor_name || '—')
}

/** Returns contact fields only if donor is not anonymous. */
function privacyContact(donor, field) {
  return donor.is_anonymous ? null : (donor[field] || null)
}

// ── donor grouping ────────────────────────────────────────────────────────────

function groupByDonor(transactions) {
  const map = new Map()

  for (const txn of transactions) {
    const key = donorKey(txn)

    if (!map.has(key)) {
      map.set(key, {
        donor_id:           key,
        donor_supporter_id: txn.donor_supporter_id || '',
        donor_name:         txn.donor_name  || '',
        donor_email:        txn.donor_email || '',
        donor_phone:        txn.donor_phone || '',
        company_name:       txn.company_name || '',
        is_anonymous:       false,
        transactions:       [],
      })
    }

    const d = map.get(key)
    // Any transaction flagged anonymous/redacted makes the entire donor record anonymous.
    if (txn.is_anonymous || txn.is_redacted) d.is_anonymous = true
    d.transactions.push(txn)
  }

  const result = []
  for (const d of map.values()) {
    const txns = d.transactions
    const dates  = txns.map(t => t.transaction_date).filter(Boolean).sort()
    const camps  = [...new Set(txns.map(t => t.campaign_name).filter(Boolean))]

    result.push({
      ...d,
      total_given:     round2(txns.reduce((s, t) => s + (t.gross_amount || 0), 0)),
      gift_count:      txns.length,
      first_gift_date: dates[0] || '',
      last_gift_date:  dates[dates.length - 1] || '',
      campaigns:       camps,
      campaign_count:  camps.length,
      is_recurring:    txns.some(t => !!t.recurring_donation_plan_id),
    })
  }

  return result
}

// ── presets ───────────────────────────────────────────────────────────────────

const PRESET_TAGS = [
  'Major donor',
  'Board contact',
  'Do not list publicly',
  'Recurring',
  'Lapsed',
  'Foundation',
]

// ── shared style tokens ───────────────────────────────────────────────────────

const td = (align = 'left', extra = {}) => ({
  padding: '3px 7px',
  textAlign: align,
  verticalAlign: 'middle',
  borderRight: '1px solid var(--border-soft, #ece7e2)',
  fontSize: 11,
  color: 'var(--text)',
  ...extra,
})

const tdMoney = td('right', {
  fontVariantNumeric: 'tabular-nums',
  whiteSpace: 'nowrap',
  fontFamily: 'ui-monospace, "Cascadia Code", "Fira Mono", Menlo, monospace',
})

const inputStyle = {
  padding: '4px 8px',
  border: '1px solid var(--border)',
  borderRadius: 3,
  background: 'var(--surface)',
  color: 'var(--text)',
  fontSize: 12,
  outline: 'none',
}

const btnGhost = {
  padding: '3px 9px',
  fontSize: 11,
  background: 'none',
  border: '1px solid var(--border)',
  borderRadius: 3,
  color: 'var(--muted)',
  cursor: 'pointer',
}

const btnAccent = {
  ...btnGhost,
  background: 'var(--accent)',
  border: 'none',
  color: '#fff',
  fontWeight: 500,
}

const thBase = {
  padding: '5px 7px',
  whiteSpace: 'nowrap',
  color: 'var(--muted)',
  fontWeight: 500,
  userSelect: 'none',
  borderRight: '1px solid var(--border-soft, #ece7e2)',
  fontSize: 11,
}

// ── SummaryStrip ──────────────────────────────────────────────────────────────

function SummaryStrip({ donors, transactions, filtered, taggedCount }) {
  const totalRaised  = round2(transactions.reduce((s, t) => s + (t.gross_amount || 0), 0))
  const recurringCt  = donors.filter(d => d.is_recurring).length
  const anonCt       = donors.filter(d => d.is_anonymous).length
  const isFiltered   = filtered.length !== donors.length

  return (
    <div style={{
      display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 14,
      padding: '7px 13px', background: 'var(--surface)',
      border: '1px solid var(--border)', borderRadius: 4, marginBottom: 10, fontSize: 12,
    }}>
      <span style={{ color: 'var(--muted)' }}>
        {isFiltered
          ? <><Num>{filtered.length}</Num> of <Num>{donors.length}</Num> donors</>
          : <><Num>{donors.length}</Num> donors</>
        }
      </span>
      <Sep />
      <span style={{ color: 'var(--muted)' }}>
        Total raised: <strong style={{ color: 'var(--text)', fontVariantNumeric: 'tabular-nums' }}>{fmt$(totalRaised)}</strong>
      </span>
      <Sep />
      <span style={{ color: 'var(--muted)' }}>
        <Num>{recurringCt}</Num> recurring
      </span>
      <Sep />
      <span style={{ color: 'var(--muted)' }}>
        <Num>{anonCt}</Num> anonymous
      </span>
      {taggedCount > 0 && (
        <>
          <Sep />
          <span style={{ color: 'var(--muted)' }}>
            <Num>{taggedCount}</Num> tagged
          </span>
        </>
      )}
    </div>
  )
}

function Num({ children }) {
  return <strong style={{ color: 'var(--text)' }}>{Number(children).toLocaleString()}</strong>
}

function Sep() {
  return <span style={{ color: 'var(--border)', userSelect: 'none' }}>|</span>
}

// ── TagChip ───────────────────────────────────────────────────────────────────

function TagChip({ label, onRemove }) {
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 3,
      fontSize: 10, padding: '1px 5px', borderRadius: 3,
      background: 'var(--accent-dim)', color: 'var(--accent)',
      border: '1px solid #c0d8c0', whiteSpace: 'nowrap',
    }}>
      {label}
      {onRemove && (
        <button
          type="button"
          onClick={onRemove}
          style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0, lineHeight: 1, color: 'var(--muted)', fontSize: 10 }}
          title={`Remove tag "${label}"`}
        >×</button>
      )}
    </span>
  )
}

// ── AnnotationEditor ──────────────────────────────────────────────────────────

function AnnotationEditor({ donor_id, annotation, onSave, onCancel }) {
  const [tags,   setTags]   = useState(annotation?.tags || [])
  const [note,   setNote]   = useState(annotation?.note || '')
  const [newTag, setNewTag] = useState('')
  const [saving, setSaving] = useState(false)
  const [err,    setErr]    = useState(null)

  function addTag(raw) {
    const t = raw.trim()
    if (t && !tags.includes(t)) setTags(prev => [...prev, t])
    setNewTag('')
  }

  async function handleSave() {
    setSaving(true)
    setErr(null)
    try {
      await onSave(donor_id, { tags, note })
    } catch (e) {
      setErr(e.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <tr>
      <td
        colSpan={14}
        style={{ padding: '10px 14px', background: '#f6f2ec', borderBottom: '1px solid var(--border)' }}
      >
        {err && (
          <div style={{ marginBottom: 6, fontSize: 11, color: 'var(--danger)' }}>
            Save failed: {err}
          </div>
        )}
        <div style={{ display: 'flex', gap: 20, alignItems: 'flex-start', flexWrap: 'wrap' }}>
          {/* tags column */}
          <div style={{ flex: '0 0 auto', minWidth: 270 }}>
            <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 5, fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
              Tags
            </div>

            {/* applied tags */}
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 3, minHeight: 22, marginBottom: 6 }}>
              {tags.length === 0
                ? <span style={{ fontSize: 11, color: 'var(--muted)', fontStyle: 'italic' }}>No tags applied</span>
                : tags.map(t => (
                    <TagChip key={t} label={t} onRemove={() => setTags(prev => prev.filter(x => x !== t))} />
                  ))
              }
            </div>

            {/* preset quick-adds */}
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 3, marginBottom: 6 }}>
              {PRESET_TAGS.filter(t => !tags.includes(t)).map(t => (
                <button
                  key={t} type="button"
                  onClick={() => addTag(t)}
                  style={{ ...btnGhost, fontSize: 10, padding: '1px 6px' }}
                >
                  + {t}
                </button>
              ))}
            </div>

            {/* free-text tag */}
            <div style={{ display: 'flex', gap: 4 }}>
              <input
                placeholder="Custom tag…"
                value={newTag}
                onChange={e => setNewTag(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); addTag(newTag) } }}
                style={{ ...inputStyle, width: 150, fontSize: 11 }}
              />
              <button
                type="button"
                onClick={() => addTag(newTag)}
                style={{ ...btnGhost, fontSize: 11 }}
              >
                Add
              </button>
            </div>
          </div>

          {/* note column */}
          <div style={{ flex: 1, minWidth: 200 }}>
            <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 5, fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
              Internal note
            </div>
            <textarea
              value={note}
              onChange={e => setNote(e.target.value)}
              rows={4}
              style={{ ...inputStyle, width: '100%', resize: 'vertical', fontSize: 11, fontFamily: 'inherit' }}
              placeholder="Internal note — never shared with or shown to donors…"
            />
          </div>

          {/* actions */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6, paddingTop: 24, flexShrink: 0 }}>
            <button type="button" onClick={handleSave} disabled={saving} style={btnAccent}>
              {saving ? 'Saving…' : 'Save'}
            </button>
            <button type="button" onClick={onCancel} style={btnGhost}>
              Cancel
            </button>
          </div>
        </div>
      </td>
    </tr>
  )
}

// ── Expanded transaction rows ─────────────────────────────────────────────────

function TransactionRows({ donor }) {
  const sorted = [...donor.transactions].sort((a, b) =>
    (b.transaction_date || '').localeCompare(a.transaction_date || '')
  )

  return (
    <>
      {/* sub-header */}
      <tr style={{ background: '#eae5de', borderBottom: '1px solid var(--border)' }}>
        {/* indent cell spans expand + name cols */}
        <td colSpan={2} style={{ ...td('left'), paddingLeft: 32, color: 'var(--muted)', fontWeight: 600, fontSize: 10 }}>
          DATE
        </td>
        <td style={{ ...td('left'), color: 'var(--muted)', fontWeight: 600, fontSize: 10 }}>CAMPAIGN</td>
        <td style={{ ...td('right'), color: 'var(--muted)', fontWeight: 600, fontSize: 10 }}>GROSS</td>
        <td style={{ ...td('right'), color: 'var(--muted)', fontWeight: 600, fontSize: 10 }}>PLAT FEE</td>
        <td style={{ ...td('right'), color: 'var(--muted)', fontWeight: 600, fontSize: 10 }}>PROC FEE</td>
        <td style={{ ...td('right'), color: 'var(--muted)', fontWeight: 600, fontSize: 10 }}>NET</td>
        <td style={{ ...td('left'), color: 'var(--muted)', fontWeight: 600, fontSize: 10 }}>CLASS</td>
        <td style={{ ...td('left'), color: 'var(--muted)', fontWeight: 600, fontSize: 10 }}>PROCESSOR</td>
        <td style={{ ...td('center'), color: 'var(--muted)', fontWeight: 600, fontSize: 10 }}>RECUR</td>
        <td colSpan={4} />
      </tr>

      {sorted.map(txn => {
        const amtHidden = txn.donation_amount_is_hidden
        const hiddenCell = <span style={{ color: 'var(--muted)', fontStyle: 'italic' }}>[hidden]</span>

        return (
          <tr key={txn.transaction_id} style={{ background: '#f6f2ec', borderBottom: '1px solid var(--border-soft)' }}>
            <td colSpan={2} style={{ ...td('left'), paddingLeft: 32, color: 'var(--muted)' }}>
              {fmtDate(txn.transaction_date)}
            </td>
            <td style={{ ...td('left'), maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              <span title={txn.campaign_name} style={{ color: 'var(--muted)' }}>
                {txn.campaign_name || '—'}
              </span>
            </td>
            <td style={tdMoney}>
              {amtHidden ? hiddenCell : fmt$(txn.gross_amount)}
            </td>
            <td style={{ ...tdMoney, color: 'var(--muted)' }}>
              {amtHidden ? hiddenCell : fmt$(txn.platform_fee)}
            </td>
            <td style={{ ...tdMoney, color: 'var(--muted)' }}>
              {amtHidden ? hiddenCell : fmt$(txn.processing_fee)}
            </td>
            <td style={{ ...tdMoney, fontWeight: 500 }}>
              {amtHidden ? hiddenCell : fmt$(txn.net_amount)}
            </td>
            <td style={{ ...td('left'), color: 'var(--muted)', fontSize: 10, maxWidth: 140, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              <span title={txn.qbo_class}>{txn.qbo_class || '—'}</span>
            </td>
            <td style={{ ...td('left'), color: 'var(--muted)', fontSize: 10, whiteSpace: 'nowrap' }}>
              {txn.processor || '—'}
            </td>
            <td style={{ ...td('center') }}>
              {txn.recurring_donation_plan_id
                ? <span title="Recurring gift" style={{ color: 'var(--accent)', fontSize: 12 }}>↻</span>
                : <span style={{ color: 'var(--muted)' }}>—</span>
              }
            </td>
            <td colSpan={4} />
          </tr>
        )
      })}

      {/* comment row if any transaction has a comment */}
      {sorted.filter(t => t.donor_comment).map(txn => (
        <tr key={txn.transaction_id + '_comment'} style={{ background: '#f3efe9', borderBottom: '1px solid var(--border-soft)' }}>
          <td colSpan={2} style={{ ...td('left'), paddingLeft: 32, color: 'var(--muted)', fontSize: 10, fontStyle: 'italic' }}>
            {fmtDate(txn.transaction_date)} note:
          </td>
          <td colSpan={12} style={{ ...td('left'), color: 'var(--muted)', fontSize: 10, fontStyle: 'italic' }}>
            "{txn.donor_comment}"
          </td>
        </tr>
      ))}
    </>
  )
}

// ── DonorRow ──────────────────────────────────────────────────────────────────

function DonorRow({ donor, annotation, expanded, rowIndex, onToggle, onAnnotate, onSaveAnnotation, editingAnnotation, onCancelAnnotation }) {
  const isAnon   = donor.is_anonymous
  const name     = privacyName(donor)
  const email    = privacyContact(donor, 'donor_email')
  const phone    = privacyContact(donor, 'donor_phone')
  const company  = privacyContact(donor, 'company_name') // company is not strictly PII but suppress with anon
  const tags     = annotation?.tags || []
  const hasNote  = !!(annotation?.note?.trim())
  const rowBg    = rowIndex % 2 === 0 ? 'var(--surface)' : 'var(--bg)'
  const activeBg = '#e8e2db'

  return (
    <>
      <tr
        style={{ background: expanded ? activeBg : rowBg, borderBottom: '1px solid var(--border-soft)', cursor: 'pointer' }}
        onClick={onToggle}
      >
        {/* ▶/▼ toggle */}
        <td style={{ ...td('center'), width: 24, color: 'var(--muted)', fontSize: 9, userSelect: 'none' }}>
          {expanded ? '▼' : '▶'}
        </td>

        {/* name */}
        <td style={{ ...td('left'), maxWidth: 160, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          <span
            title={isAnon ? undefined : (donor.donor_name || '')}
            style={{ fontWeight: 500, color: isAnon ? 'var(--muted)' : 'var(--text)', fontStyle: isAnon ? 'italic' : 'normal' }}
          >
            {name}
          </span>
          {isAnon && <span style={{ marginLeft: 5, fontSize: 9 }}>🔒</span>}
        </td>

        {/* email */}
        <td style={{ ...td('left'), maxWidth: 170, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: 'var(--muted)', fontSize: 10 }}>
          {email || <span style={{ opacity: 0.4 }}>—</span>}
        </td>

        {/* phone */}
        <td style={{ ...td('left'), whiteSpace: 'nowrap', color: 'var(--muted)', fontSize: 10 }}>
          {phone || <span style={{ opacity: 0.4 }}>—</span>}
        </td>

        {/* company */}
        <td style={{ ...td('left'), maxWidth: 130, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: 'var(--muted)', fontSize: 10 }}>
          <span title={company || ''}>{company || <span style={{ opacity: 0.4 }}>—</span>}</span>
        </td>

        {/* total given */}
        <td style={{ ...tdMoney, fontWeight: 600 }}>
          {fmt$(donor.total_given)}
        </td>

        {/* gifts */}
        <td style={{ ...td('center') }}>
          {donor.gift_count}
        </td>

        {/* first gift */}
        <td style={{ ...td('left'), fontSize: 10, color: 'var(--muted)', whiteSpace: 'nowrap' }}>
          {fmtDate(donor.first_gift_date)}
        </td>

        {/* last gift */}
        <td style={{ ...td('left'), fontSize: 10, color: 'var(--muted)', whiteSpace: 'nowrap' }}>
          {fmtDate(donor.last_gift_date)}
        </td>

        {/* campaign count */}
        <td
          style={{ ...td('center') }}
          title={donor.campaigns.join('\n') || 'No campaigns'}
        >
          {donor.campaign_count}
        </td>

        {/* recurring */}
        <td style={{ ...td('center') }}>
          {donor.is_recurring
            ? <span style={{ color: 'var(--accent)', fontWeight: 700, fontSize: 11 }} title="Has recurring gifts">✓</span>
            : <span style={{ color: 'var(--muted)', opacity: 0.4 }}>—</span>
          }
        </td>

        {/* tags */}
        <td
          style={{ ...td('left'), minWidth: 110 }}
          onClick={e => e.stopPropagation()}
        >
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 2 }}>
            {tags.map(t => <TagChip key={t} label={t} />)}
          </div>
        </td>

        {/* annotate / note indicator */}
        <td
          style={{ ...td('center'), width: 66 }}
          onClick={e => e.stopPropagation()}
        >
          <button
            type="button"
            onClick={onAnnotate}
            title={editingAnnotation ? 'Close annotation editor' : hasNote ? 'Edit note' : 'Add note / tags'}
            style={{
              ...btnGhost,
              fontSize: 10,
              padding: '2px 6px',
              color: editingAnnotation ? 'var(--accent)' : hasNote ? 'var(--text)' : 'var(--muted)',
              borderColor: editingAnnotation ? 'var(--accent)' : undefined,
            }}
          >
            {hasNote ? '✏ note' : '+ note'}
          </button>
        </td>
      </tr>

      {/* inline annotation editor */}
      {editingAnnotation && (
        <AnnotationEditor
          donor_id={donor.donor_id}
          annotation={annotation}
          onSave={onSaveAnnotation}
          onCancel={onCancelAnnotation}
        />
      )}

      {/* expanded transaction detail */}
      {expanded && <TransactionRows donor={donor} />}
    </>
  )
}

// ── column defs ───────────────────────────────────────────────────────────────

const COLS = [
  // { sortKey, label, width, align }
  { key: 'donor_name',      label: 'Donor',      w: 155, align: 'left'   },
  { key: 'donor_email',     label: 'Email',       w: 165, align: 'left'   },
  { key: 'donor_phone',     label: 'Phone',       w: 100, align: 'left'   },
  { key: 'company_name',    label: 'Company',     w: 120, align: 'left'   },
  { key: 'total_given',     label: 'Total Given', w: 96,  align: 'right'  },
  { key: 'gift_count',      label: 'Gifts',       w: 44,  align: 'center' },
  { key: 'first_gift_date', label: 'First Gift',  w: 72,  align: 'left'   },
  { key: 'last_gift_date',  label: 'Last Gift',   w: 72,  align: 'left'   },
  { key: 'campaign_count',  label: 'Camps.',      w: 50,  align: 'center' },
  { key: 'is_recurring',    label: 'Recur.',      w: 46,  align: 'center' },
  { key: null,              label: 'Tags',        w: 110, align: 'left'   },
  { key: null,              label: '',            w: 66,  align: 'center' },
]

// ── main component ────────────────────────────────────────────────────────────

export default function DonorCRM() {
  // data
  const [data,        setData]        = useState(null)
  const [error,       setError]       = useState(null)
  const [loading,     setLoading]     = useState(true)
  const [annotations, setAnnotations] = useState({})

  // sort
  const [sortKey, setSortKey] = useState('total_given')
  const [sortDir, setSortDir] = useState('desc')

  // filters
  const [filterText,      setFilterText]      = useState('')
  const [filterTag,       setFilterTag]       = useState('')
  const [filterCampaign,  setFilterCampaign]  = useState('')
  const [filterRecurring, setFilterRecurring] = useState(false)
  const [showAnonymous,   setShowAnonymous]   = useState(true)

  // ui state
  const [expanded,         setExpanded]         = useState(new Set())
  const [editingAnnotation, setEditingAnnotation] = useState(null) // donor_id or null

  // ── data load ───────────────────────────────────────────────────────────────

  useEffect(() => {
    api('/classy/transactions/all')
      .then(r => { if (!r.ok) throw new Error(r.statusText); return r.json() })
      .then(d => { setData(d); setLoading(false) })
      .catch(e => {
        setError(e instanceof TypeError ? '__network__' : e.message)
        setLoading(false)
      })
  }, [])

  useEffect(() => {
    api('/donors/annotations')
      .then(r => r.ok ? r.json() : {})
      .then(d => setAnnotations(d))
      .catch(() => {}) // annotations are optional; silently tolerate failure
  }, [])

  // ── derived state ────────────────────────────────────────────────────────────

  const donors = useMemo(() => {
    if (!data) return []
    return groupByDonor(data.transactions)
  }, [data])

  const allTags = useMemo(() => {
    const s = new Set()
    Object.values(annotations).forEach(a => (a.tags || []).forEach(t => s.add(t)))
    return [...s].sort()
  }, [annotations])

  const allCampaigns = useMemo(() => {
    const s = new Set()
    donors.forEach(d => d.campaigns.forEach(c => s.add(c)))
    return [...s].sort()
  }, [donors])

  const taggedCount = useMemo(
    () => donors.filter(d => (annotations[d.donor_id]?.tags || []).length > 0).length,
    [donors, annotations]
  )

  const filtered = useMemo(() => {
    let rows = donors

    const q = filterText.trim().toLowerCase()
    if (q) {
      rows = rows.filter(d => {
        // Privacy: never search anonymous donors by name/email
        if (!d.is_anonymous) {
          if ((d.donor_name  || '').toLowerCase().includes(q)) return true
          if ((d.donor_email || '').toLowerCase().includes(q)) return true
        }
        if (d.campaigns.some(c => c.toLowerCase().includes(q))) return true
        return false
      })
    }

    if (!showAnonymous)  rows = rows.filter(d => !d.is_anonymous)
    if (filterRecurring) rows = rows.filter(d => d.is_recurring)
    if (filterTag)       rows = rows.filter(d => (annotations[d.donor_id]?.tags || []).includes(filterTag))
    if (filterCampaign)  rows = rows.filter(d => d.campaigns.includes(filterCampaign))

    return rows
  }, [donors, filterText, showAnonymous, filterRecurring, filterTag, filterCampaign, annotations])

  const sorted = useMemo(() => {
    return [...filtered].sort((a, b) => {
      const av = a[sortKey]; const bv = b[sortKey]
      // boolean: true > false
      if (typeof av === 'boolean') {
        const diff = (av ? 1 : 0) - (bv ? 1 : 0)
        return sortDir === 'asc' ? diff : -diff
      }
      if (typeof av === 'number') {
        return sortDir === 'asc' ? av - bv : bv - av
      }
      const cmp = String(av || '').localeCompare(String(bv || ''), undefined, { sensitivity: 'base' })
      return sortDir === 'asc' ? cmp : -cmp
    })
  }, [filtered, sortKey, sortDir])

  // ── event handlers ───────────────────────────────────────────────────────────

  function handleSort(key) {
    if (!key) return
    if (sortKey === key) {
      setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    } else {
      setSortKey(key)
      setSortDir(['total_given', 'gift_count', 'last_gift_date'].includes(key) ? 'desc' : 'asc')
    }
  }

  function toggleExpand(donor_id) {
    setExpanded(prev => {
      const next = new Set(prev)
      next.has(donor_id) ? next.delete(donor_id) : next.add(donor_id)
      return next
    })
  }

  async function handleSaveAnnotation(donor_id, { tags, note }) {
    const res = await api(`/donors/${encodeURIComponent(donor_id)}/annotations`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tags, note }),
    })
    if (!res.ok) throw new Error(await res.text())
    const saved = await res.json()
    setAnnotations(prev => ({ ...prev, [donor_id]: saved }))
    setEditingAnnotation(null)
  }

  function clearFilters() {
    setFilterText('')
    setFilterTag('')
    setFilterCampaign('')
    setFilterRecurring(false)
    setShowAnonymous(true)
  }

  const anyFilter = filterText || filterTag || filterCampaign || filterRecurring || !showAnonymous

  // ── loading / error states ───────────────────────────────────────────────────

  if (loading) {
    return (
      <div style={{ color: 'var(--muted)', padding: '16px 0', fontSize: 12 }}>
        Loading donor records… (first load fetches from Classy API and may take ~30 seconds; subsequent loads use a 1-hour cache)
      </div>
    )
  }

  if (error) {
    if (error === '__network__') return <BackendError context="donor transactions" />
    return (
      <div style={{ color: 'var(--danger)', padding: '12px 0', fontSize: 12 }}>
        Error loading transactions: {error}
      </div>
    )
  }

  // ── render ───────────────────────────────────────────────────────────────────

  return (
    <div>
      {/* summary strip */}
      <SummaryStrip
        donors={donors}
        transactions={data?.transactions || []}
        filtered={filtered}
        taggedCount={taggedCount}
      />

      {/* filter bar */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 10, flexWrap: 'wrap', alignItems: 'center' }}>
        <input
          type="search"
          placeholder="Search name / email / campaign…"
          value={filterText}
          onChange={e => setFilterText(e.target.value)}
          style={{ ...inputStyle, width: 230 }}
        />

        {allTags.length > 0 && (
          <select value={filterTag} onChange={e => setFilterTag(e.target.value)} style={inputStyle}>
            <option value="">All tags</option>
            {allTags.map(t => <option key={t} value={t}>{t}</option>)}
          </select>
        )}

        <select value={filterCampaign} onChange={e => setFilterCampaign(e.target.value)} style={{ ...inputStyle, maxWidth: 200 }}>
          <option value="">All campaigns</option>
          {allCampaigns.map(c => <option key={c} value={c}>{c.length > 36 ? c.slice(0, 34) + '…' : c}</option>)}
        </select>

        <label style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 12, color: 'var(--muted)', cursor: 'pointer', userSelect: 'none' }}>
          <input
            type="checkbox"
            checked={filterRecurring}
            onChange={e => setFilterRecurring(e.target.checked)}
          />
          Recurring only
        </label>

        <label style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 12, color: 'var(--muted)', cursor: 'pointer', userSelect: 'none' }}>
          <input
            type="checkbox"
            checked={showAnonymous}
            onChange={e => setShowAnonymous(e.target.checked)}
          />
          Show anonymous
        </label>

        {anyFilter && (
          <button type="button" onClick={clearFilters} style={btnGhost}>
            Clear filters
          </button>
        )}

        <span style={{ marginLeft: 'auto', fontSize: 11, color: 'var(--muted)', whiteSpace: 'nowrap' }}>
          {filtered.length !== donors.length
            ? <><strong>{filtered.length.toLocaleString()}</strong> of {donors.length.toLocaleString()} donors</>
            : <><strong>{donors.length.toLocaleString()}</strong> donors</>
          }
        </span>
      </div>

      {/* table */}
      <div style={{ overflowX: 'auto', border: '1px solid var(--border)', borderRadius: 4 }}>
        <table style={{ borderCollapse: 'collapse', width: '100%', fontSize: 11 }}>
          <thead>
            <tr style={{ background: 'var(--bg)', borderBottom: '2px solid var(--border)' }}>
              {/* expand toggle header */}
              <th style={{ ...thBase, width: 24 }} />
              {COLS.map((col, i) => (
                <th
                  key={i}
                  onClick={() => handleSort(col.key)}
                  style={{
                    ...thBase,
                    textAlign: col.align || 'left',
                    minWidth: col.w,
                    cursor: col.key ? 'pointer' : 'default',
                  }}
                >
                  {col.label}
                  {col.key && (
                    <span style={{ marginLeft: 3, fontSize: 9, opacity: sortKey === col.key ? 1 : 0.3 }}>
                      {sortKey === col.key ? (sortDir === 'asc' ? '↑' : '↓') : '↕'}
                    </span>
                  )}
                </th>
              ))}
            </tr>
          </thead>

          <tbody>
            {sorted.length === 0 ? (
              <tr>
                <td
                  colSpan={COLS.length + 1}
                  style={{ padding: '14px', color: 'var(--muted)', fontSize: 12, textAlign: 'center' }}
                >
                  No donors match the current filters.
                </td>
              </tr>
            ) : (
              sorted.map((donor, i) => (
                <DonorRow
                  key={donor.donor_id}
                  donor={donor}
                  annotation={annotations[donor.donor_id]}
                  expanded={expanded.has(donor.donor_id)}
                  rowIndex={i}
                  onToggle={() => toggleExpand(donor.donor_id)}
                  onAnnotate={() =>
                    setEditingAnnotation(prev => prev === donor.donor_id ? null : donor.donor_id)
                  }
                  onSaveAnnotation={handleSaveAnnotation}
                  editingAnnotation={editingAnnotation === donor.donor_id}
                  onCancelAnnotation={() => setEditingAnnotation(null)}
                />
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* privacy footer */}
      <div style={{ marginTop: 8, fontSize: 10, color: 'var(--muted)', textAlign: 'right' }}>
        🔒 Anonymous and redacted donors are permanently masked — they remain anonymous in all views, sorts, and exports.
        &nbsp;Tags and notes are internal only; they are never shown to or shared with donors.
      </div>
    </div>
  )
}
