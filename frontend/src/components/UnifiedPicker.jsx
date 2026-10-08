import { useEffect, useMemo, useState } from 'react'
import { Search, Loader2, Sparkles } from 'lucide-react'
import { unifiedProjectsApi } from '../lib/api'

const fmtCr = (v) => (v == null ? '—' : `₹${v >= 100 ? Math.round(v) : Math.round(v * 100) / 100} Cr`)

// Heading hints such as "Hospitality" or "Data center" -> the register's sector names.
function matchSector(hint, options) {
  if (!hint) return ''
  const words = hint.toLowerCase().split(/[^a-z]+/).filter((w) => w.length >= 4)
  const stem = (w) => w.slice(0, 5)
  return options.find((o) => words.some((w) => o.toLowerCase().includes(stem(w)))) || ''
}

// Project picker for one table in the form. Starts pre-filtered from the table's own heading
// (completed vs ongoing, a sector, a scope, "last N years") so the user only sees the projects
// that belong in that table, and can change any filter.
export default function UnifiedPicker({ table, selected, setSelected, cap }) {
  const [opts, setOpts] = useState(null)
  const [f, setF] = useState(null)
  const [items, setItems] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    unifiedProjectsApi.filterOptions().then(({ data }) => {
      setOpts(data)
      const yearsBack = Number(table.years_back) || 0
      setF({
        q: '',
        // Many register rows have no end date, so their status is 'Unknown'. A "completed work"
        // table should still offer them; only the ones known to be ongoing are left out.
        status: table.status_filter === 'Completed' ? 'Completed,Unknown' : (table.status_filter || ''),
        sector: matchSector(table.sector_hint, data.sector || []),
        // The form's wording ("MEP works") rarely matches the register's scope labels (VRV, Fitout, ...),
        // so the scope hint is not applied automatically; it would hide most projects.
        scope: '',
        year_from: yearsBack ? String(new Date().getFullYear() - yearsBack) : '',
        min_value: '',
        sort: 'value_desc',
      })
    })
  }, [table])

  const params = useMemo(() => {
    if (!f) return null
    const p = { page, page_size: 50, sort: f.sort, level: 'project', keep_unknown_year: true }
    for (const k of ['q', 'status', 'sector', 'scope', 'year_from', 'min_value']) if (f[k] !== '') p[k] = f[k]
    return p
  }, [f, page])

  useEffect(() => {
    if (!params) return
    setLoading(true)
    const t = setTimeout(async () => {
      try {
        const { data } = await unifiedProjectsApi.list(params)
        setItems(data.items); setTotal(data.total)
      } finally { setLoading(false) }
    }, 300)
    return () => clearTimeout(t)
  }, [params])

  const set = (k, v) => { setF((x) => ({ ...x, [k]: v })); setPage(1) }
  const atCap = cap && selected.size >= cap
  const toggle = (id) => setSelected((prev) => {
    const next = new Set(prev)
    if (next.has(id)) next.delete(id)
    else if (!cap || next.size < cap) next.add(id)
    return next
  })

  if (!f) return <div className="py-12 flex justify-center"><Loader2 size={28} className="animate-spin text-brand-500" /></div>

  const hints = [
    table.status_filter && `${table.status_filter} projects`,
    table.sector_hint && `${table.sector_hint} category`,
    table.years_back && `last ${table.years_back} years`,
  ].filter(Boolean)
  const pages = Math.max(1, Math.ceil(total / 50))
  const Sel = ({ k, label, values }) => (
    <select className="input text-xs py-1 max-w-[170px]" value={f[k]} onChange={(e) => set(k, e.target.value)}>
      <option value="">{label}</option>
      {(values || []).map((v) => <option key={v} value={v}>{v}</option>)}
    </select>
  )

  return (
    <div className="space-y-3">
      {hints.length > 0 && (
        <div className="flex items-center gap-2 text-xs text-brand-700 bg-brand-50 border border-brand-100 rounded-lg px-3 py-2">
          <Sparkles size={14} />
          <span>Filtered from this section's heading: <b>{hints.join(' · ')}</b>. Change any filter below to see other projects.</span>
        </div>
      )}
      <div className="flex gap-2 flex-wrap items-center bg-gray-50 p-2 rounded-lg border border-gray-200">
        <div className="relative flex-1 min-w-[180px] max-w-xs">
          <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400" />
          <input type="text" value={f.q} onChange={(e) => set('q', e.target.value)} placeholder="Search project, client, PMC…" className="input w-full pl-8 py-1.5 text-xs" />
        </div>
        <select className="input text-xs py-1" value={f.status} onChange={(e) => set('status', e.target.value)}>
          <option value="">Any status</option>
          <option value="Completed,Unknown">Completed / not confirmed</option>
          <option value="Completed">Completed only</option>
          <option value="Ongoing">Ongoing</option>
          <option value="Unknown">Status not confirmed</option>
        </select>
        <Sel k="sector" label="All categories" values={opts.sector} />
        <Sel k="scope" label="All scopes" values={opts.scope} />
        <Sel k="year_from" label="From year" values={opts.year} />
        <input type="number" min="0" step="0.5" value={f.min_value} onChange={(e) => set('min_value', e.target.value)} placeholder="Min ₹ Cr" className="input text-xs py-1 w-24" />
        <select className="input text-xs py-1" value={f.sort} onChange={(e) => set('sort', e.target.value)}>
          <option value="value_desc">Largest value</option><option value="area_desc">Largest area</option>
          <option value="year_desc">Newest</option><option value="name">Name A–Z</option>
        </select>
        {atCap && <span className="ml-auto text-xs font-semibold text-amber-600 bg-amber-50 px-2 py-1 rounded">Maximum reached</span>}
      </div>

      <div className="border border-gray-200 rounded-xl overflow-x-auto min-h-[250px] max-h-[400px] relative">
        {loading ? (
          <div className="py-12 flex justify-center"><Loader2 size={28} className="animate-spin text-brand-500" /></div>
        ) : items.length === 0 ? (
          <div className="p-12 text-center text-gray-500 text-sm">No projects match these filters.</div>
        ) : (
          <table className="w-full text-sm text-left">
            <thead className="bg-gray-50 border-b border-gray-200 text-[11px] text-gray-500 uppercase tracking-wider sticky top-0 z-20">
              <tr>
                <th className="px-4 py-2 font-medium w-12">Select</th>
                <th className="px-4 py-2 font-medium">Project</th>
                <th className="px-4 py-2 font-medium">Client</th>
                <th className="px-4 py-2 font-medium">Category</th>
                <th className="px-4 py-2 font-medium">City</th>
                <th className="px-4 py-2 font-medium">Scope</th>
                <th className="px-4 py-2 font-medium text-right">Area (sq ft)</th>
                <th className="px-4 py-2 font-medium text-right">Value</th>
                <th className="px-4 py-2 font-medium">Dates</th>
                <th className="px-4 py-2 font-medium">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 bg-white">
              {items.map((p) => {
                const on = selected.has(p.id)
                const disabled = !on && atCap
                return (
                  <tr key={p.id} onClick={() => !disabled && toggle(p.id)}
                    className={`${disabled ? 'opacity-50' : 'hover:bg-gray-50 cursor-pointer'} ${on ? 'bg-brand-50' : ''}`}>
                    <td className="px-4 py-2.5"><input type="checkbox" checked={on} disabled={disabled} readOnly className="w-4 h-4 rounded border-gray-300" /></td>
                    <td className="px-4 py-2.5 font-medium text-gray-900 max-w-[260px] truncate">{p.project_name}</td>
                    <td className="px-4 py-2.5 max-w-[180px] truncate">{p.client_name || '—'}</td>
                    <td className="px-4 py-2.5 whitespace-nowrap">{p.sector || '—'}</td>
                    <td className="px-4 py-2.5">{p.city || '—'}</td>
                    <td className="px-4 py-2.5">{p.scope || '—'}</td>
                    <td className="px-4 py-2.5 text-right tabular-nums">{p.area_sqft ? Math.round(p.area_sqft).toLocaleString('en-IN') : '—'}</td>
                    <td className="px-4 py-2.5 text-right tabular-nums whitespace-nowrap">{fmtCr(p.value_cr)}</td>
                    <td className="px-4 py-2.5 whitespace-nowrap text-xs text-gray-500">{p.start_date || '—'} → {p.end_date || (p.status === 'Ongoing' ? 'Ongoing' : '—')}</td>
                    <td className="px-4 py-2.5">{p.status}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>
      <div className="flex items-center justify-between text-xs text-gray-500">
        <span>{total.toLocaleString()} projects · {selected.size} selected for this table</span>
        <div className="flex items-center gap-2">
          <button className="btn-secondary py-1" disabled={page <= 1} onClick={() => setPage(page - 1)}>Prev</button>
          <span>Page {page} of {pages}</span>
          <button className="btn-secondary py-1" disabled={page >= pages} onClick={() => setPage(page + 1)}>Next</button>
        </div>
      </div>
    </div>
  )
}
