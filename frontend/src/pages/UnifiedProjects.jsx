import { useEffect, useMemo, useState, useCallback } from 'react'
import { Search, Download, RefreshCw, Loader2, Layers, CheckSquare, X } from 'lucide-react'
import { unifiedProjectsApi } from '../lib/api'

const PAGE_SIZE = 50
const fmtCr = (v) => (v == null ? '—' : `₹${v >= 100 ? v.toFixed(0) : v.toFixed(2)} Cr`)
const fmtArea = (v) => (v == null ? '—' : Math.round(v).toLocaleString('en-IN'))

export default function UnifiedProjects() {
  const [items, setItems] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [opts, setOpts] = useState({})
  const [stats, setStats] = useState(null)
  const [f, setF] = useState({ q: '', sector: '', city: '', scope: '', status: '', year_from: '', year_to: '', min_value: '', level: 'project', selected: '', sort: 'value_desc' })
  const [picked, setPicked] = useState(new Set()) // ids ticked on screen (persist across pages)
  const [rebuilding, setRebuilding] = useState(false)

  const params = useMemo(() => {
    const p = { page, page_size: PAGE_SIZE, sort: f.sort, level: f.level }
    for (const k of ['q', 'sector', 'city', 'scope', 'status', 'year_from', 'year_to', 'min_value']) if (f[k] !== '') p[k] = f[k]
    if (f.selected !== '') p.selected = f.selected === 'yes'
    return p
  }, [f, page])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const { data } = await unifiedProjectsApi.list(params)
      setItems(data.items); setTotal(data.total)
    } finally { setLoading(false) }
  }, [params])

  const loadMeta = useCallback(async () => {
    const [o, s] = await Promise.all([unifiedProjectsApi.filterOptions(), unifiedProjectsApi.stats()])
    setOpts(o.data); setStats(s.data)
  }, [])

  useEffect(() => { load() }, [load])
  useEffect(() => { loadMeta() }, [loadMeta])

  const set = (k, v) => { setF((x) => ({ ...x, [k]: v })); setPage(1) }
  const togglePick = (id) => setPicked((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n })
  const pageAllPicked = items.length > 0 && items.every((i) => picked.has(i.id))
  const togglePage = () => setPicked((s) => { const n = new Set(s); items.forEach((i) => (pageAllPicked ? n.delete(i.id) : n.add(i.id))); return n })

  const setDeck = async (ids, selected) => {
    await unifiedProjectsApi.select(ids, selected)
    setPicked(new Set()); await Promise.all([load(), loadMeta()])
  }
  const rebuild = async () => {
    if (!window.confirm('Re-read all source files and regenerate the unified table? Deck selections are kept.')) return
    setRebuilding(true)
    try { await unifiedProjectsApi.rebuild(); await Promise.all([load(), loadMeta()]) } finally { setRebuilding(false) }
  }

  const Select = ({ k, label, values }) => (
    <select value={f[k]} onChange={(e) => set(k, e.target.value)} className="input text-sm">
      <option value="">{label}</option>
      {(values || []).map((v) => <option key={v} value={v}>{v}</option>)}
    </select>
  )

  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  return (
    <div className="p-8 max-w-[1400px] mx-auto">
      <div className="flex items-start justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900 flex items-center gap-2"><Layers size={22} /> Unified Projects</h1>
          <p className="text-sm text-gray-500 mt-1">
            One merged list of every project from the sector register, File Cabinet registry files and consolidated master.
            Tick projects and add them to the deck selection — the deck app reads that selection from <code>/api/unified-projects/deck</code>.
          </p>
          {stats && (
            <p className="text-sm text-gray-600 mt-2">
              <b>{stats.projects.toLocaleString()}</b> projects · <b>{stats.client_rollups.toLocaleString()}</b> client roll-ups ·
              <b> {Math.round(stats.total_value_cr).toLocaleString('en-IN')}</b> Cr total value ·
              <b> {stats.selected_for_deck}</b> selected for deck
            </p>
          )}
        </div>
        <div className="flex gap-2">
          <button onClick={() => unifiedProjectsApi.export(picked.size ? [...picked] : null)} className="btn-secondary">
            <Download size={15} /> Export {picked.size ? `${picked.size} to` : 'all to'} Excel
          </button>
          <button onClick={rebuild} disabled={rebuilding} className="btn-secondary">
            {rebuilding ? <Loader2 size={15} className="animate-spin" /> : <RefreshCw size={15} />} Rebuild
          </button>
        </div>
      </div>

      <div className="flex flex-wrap gap-2 mb-4">
        <div className="relative">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input value={f.q} onChange={(e) => set('q', e.target.value)} placeholder="Search project, client, PMC…" className="input pl-9 text-sm w-64" />
        </div>
        <Select k="sector" label="All sectors" values={opts.sector} />
        <Select k="city" label="All cities" values={opts.city} />
        <Select k="scope" label="All scopes" values={opts.scope} />
        <Select k="status" label="Any status" values={opts.status} />
        <Select k="year_from" label="From year" values={opts.year} />
        <Select k="year_to" label="To year" values={opts.year} />
        <input value={f.min_value} onChange={(e) => set('min_value', e.target.value)} placeholder="Min ₹ Cr" className="input text-sm w-28" />
        <select value={f.selected} onChange={(e) => set('selected', e.target.value)} className="input text-sm">
          <option value="">Deck: all</option><option value="yes">In deck</option><option value="no">Not in deck</option>
        </select>
        <select value={f.level} onChange={(e) => set('level', e.target.value)} className="input text-sm">
          <option value="project">Projects</option><option value="client_rollup">Client roll-ups</option><option value="all">Both</option>
        </select>
        <select value={f.sort} onChange={(e) => set('sort', e.target.value)} className="input text-sm">
          <option value="value_desc">Largest value</option><option value="area_desc">Largest area</option>
          <option value="year_desc">Newest</option><option value="name">Name A–Z</option>
        </select>
      </div>

      {picked.size > 0 && (
        <div className="flex items-center gap-3 mb-3 px-4 py-2 rounded-lg bg-blue-50 border border-blue-200 text-sm">
          <CheckSquare size={16} className="text-blue-600" /> {picked.size} ticked
          <button onClick={() => setDeck([...picked], true)} className="btn-primary py-1">Add to deck</button>
          <button onClick={() => setDeck([...picked], false)} className="btn-secondary py-1">Remove from deck</button>
          <button onClick={() => setPicked(new Set())} className="ml-auto text-gray-500 hover:text-gray-800"><X size={16} /></button>
        </div>
      )}

      <div className="bg-white border border-gray-200 rounded-xl overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-gray-600 text-left">
            <tr>
              <th className="p-3 w-8"><input type="checkbox" checked={pageAllPicked} onChange={togglePage} /></th>
              <th className="p-3">Project</th><th className="p-3">Client</th><th className="p-3">Sector</th>
              <th className="p-3">City</th><th className="p-3">Scope</th><th className="p-3 text-right">Area (sq ft)</th>
              <th className="p-3 text-right">Value</th><th className="p-3">Year</th><th className="p-3">Status</th>
              <th className="p-3">PMC</th><th className="p-3">Deck</th>
            </tr>
          </thead>
          <tbody>
            {loading && <tr><td colSpan={12} className="p-8 text-center text-gray-400"><Loader2 className="animate-spin inline" /></td></tr>}
            {!loading && items.length === 0 && <tr><td colSpan={12} className="p-8 text-center text-gray-400">No projects match.</td></tr>}
            {!loading && items.map((p) => (
              <tr key={p.id} className="border-t border-gray-100 hover:bg-gray-50" title={(p.sources || []).map((s) => `${s.file} / ${s.sheet}`).join('\n')}>
                <td className="p-3"><input type="checkbox" checked={picked.has(p.id)} onChange={() => togglePick(p.id)} /></td>
                <td className="p-3 font-medium text-gray-900 max-w-xs truncate">{p.project_name}</td>
                <td className="p-3 max-w-[200px] truncate">{p.client_name || '—'}</td>
                <td className="p-3">{p.sector || '—'}</td>
                <td className="p-3">{p.city || '—'}</td>
                <td className="p-3">{p.scope || '—'}</td>
                <td className="p-3 text-right tabular-nums">{fmtArea(p.area_sqft)}</td>
                <td className="p-3 text-right tabular-nums">{fmtCr(p.value_cr)}</td>
                <td className="p-3">{p.year || '—'}</td>
                <td className="p-3">{p.status}</td>
                <td className="p-3">{p.pmc || '—'}</td>
                <td className="p-3">{p.selected_for_deck ? <span className="text-green-700 font-medium">✓ In deck</span> : ''}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between mt-4 text-sm text-gray-600">
        <span>{total.toLocaleString()} results</span>
        <div className="flex items-center gap-2">
          <button disabled={page <= 1} onClick={() => setPage(page - 1)} className="btn-secondary py-1">Prev</button>
          <span>Page {page} of {pages}</span>
          <button disabled={page >= pages} onClick={() => setPage(page + 1)} className="btn-secondary py-1">Next</button>
        </div>
      </div>
    </div>
  )
}
