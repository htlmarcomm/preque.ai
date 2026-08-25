import { useState, useEffect, useRef } from 'react'
import { Search, Upload, Link, X, Eye, Download, Trash2, ChevronDown, ChevronRight, Tag, Building2, FileSpreadsheet, Plus, Copy, Check, FileText, Loader2 } from 'lucide-react'
import { projectFilesApi } from '../lib/api'

const CATEGORY_COLORS = {
  'Project Registry':        '#f59e0b',
  'Client Specific Data':    '#3b82f6',
  'Company General Data':    '#10b981',
  'Company Financial Data':  '#8b5cf6',
  'Company Compliance Data': '#ec4899',
  'Employee Details':        '#14b8a6',
  'Company Reports':         '#ef4444',
  'Project Completion Certificate and Appreciation': '#f97316',
  'Safety and HSE':          '#22c55e',
  'Policies':                '#dc2626',
}

export default function ProjectFiles() {
  const [files, setFiles]               = useState([])
  const [categories, setCategories]     = useState([])
  const [search, setSearch]             = useState('')
  const [filterClient, setFilterClient] = useState('')
  const [filterCat, setFilterCat]       = useState('')
  const [collapsed, setCollapsed]       = useState({})
  const [showUpload, setShowUpload]     = useState(false)
  const [showLink, setShowLink]         = useState(false)
  const [preview, setPreview]           = useState(null)   // { name, sheets }
  const [activeSheet, setActiveSheet]   = useState(null)
  const [previewSearch, setPreviewSearch] = useState('')
  const [columnFilters, setColumnFilters] = useState({})
  const [copiedCell, setCopiedCell]     = useState(null)
  const [loading, setLoading]           = useState(false)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [downloadingId, setDownloadingId] = useState(null)
  const mediaObjectUrlRef = useRef(null)

  useEffect(() => { fetchFiles(); fetchCategories() }, [])
  useEffect(() => () => releaseMediaPreview(), [])

  async function fetchFiles() {
    setLoading(true)
    try {
      const params = {}
      if (search)       params.search   = search
      if (filterClient) params.client   = filterClient
      if (filterCat)    params.category = filterCat
      const res = await projectFilesApi.list(params)
      setFiles(res.data.files || [])
    } catch (e) { console.error(e) }
    setLoading(false)
  }

  async function fetchCategories() {
    try {
      const res = await projectFilesApi.getCategories()
      setCategories(res.data.categories || [])
    } catch (e) {}
  }

  useEffect(() => { fetchFiles() }, [search, filterClient, filterCat])

  async function deleteFile(id) {
    if (!confirm('Delete this file?')) return
    await projectFilesApi.delete(id)
    fetchFiles()
  }

  async function updateFileCategory(id, newCategory) {
    await projectFilesApi.update(id, { category: newCategory })
    fetchFiles()
  }

  async function downloadFileById(file) {
    setDownloadingId(file.id)
    try {
      await projectFilesApi.download(file.id, file.filename || file.name)
    } catch (e) {
      alert(e.response?.data?.detail || e.message || 'Download failed.')
    } finally {
      setDownloadingId(null)
    }
  }

  // Object URLs used for inline PDF/image previews must be revoked once
  // they're no longer shown, or each preview leaks the blob's memory.
  function releaseMediaPreview() {
    if (mediaObjectUrlRef.current) {
      window.URL.revokeObjectURL(mediaObjectUrlRef.current)
      mediaObjectUrlRef.current = null
    }
  }

  function closePreview() {
    releaseMediaPreview()
    setPreview(null)
  }

  async function openPreview(file) {
    if (!file.filename) {
      alert('No uploaded file — only a SharePoint link is stored. Open it via the link.')
      return
    }
    releaseMediaPreview()
    setPreviewLoading(true)
    setPreview(null)
    setActiveSheet(null)
    setPreviewSearch('')
    setColumnFilters({})

    const ext = file.filename.split('.').pop().toLowerCase()

    try {
      if (['xlsx', 'xls', 'csv'].includes(ext)) {
        const res = await projectFilesApi.preview(file.id)
        setPreview({ type: 'excel', ...res.data })
        const firstSheet = Object.keys(res.data.sheets || {})[0]
        setActiveSheet(firstSheet)
      } else if (['pdf', 'jpg', 'jpeg', 'png', 'gif'].includes(ext)) {
        const url = await projectFilesApi.viewUrl(file.id)
        mediaObjectUrlRef.current = url
        setPreview({ type: 'media', url, name: file.name, ext })
      } else {
        throw new Error('Preview not supported for this file type. Please click Download.')
      }
    } catch (e) {
      setPreview(null)
      alert(e.response?.data?.detail || e.message)
    }
    setPreviewLoading(false)
  }

  function copyCell(value) {
    navigator.clipboard.writeText(value)
    setCopiedCell(value)
    setTimeout(() => setCopiedCell(null), 1500)
  }

  function copyRow(row) {
    navigator.clipboard.writeText(row.join('\t'))
    setCopiedCell('__row__')
    setTimeout(() => setCopiedCell(null), 1500)
  }

  // Group files by category
  const grouped = {}
  files.forEach(f => {
    const cat = f.category || 'Company General Data'
    if (!grouped[cat]) grouped[cat] = []
    grouped[cat].push(f)
  })

  const allClients = [...new Set(files.map(f => f.client).filter(Boolean))]

  const currentSheetData = preview && activeSheet
    ? preview.sheets[activeSheet]
    : null

  const filteredRows = currentSheetData
    ? currentSheetData.rows.filter(row => {
        // Global search
        if (previewSearch && !row.some(cell => String(cell || '').toLowerCase().includes(previewSearch.toLowerCase()))) {
          return false
        }
        // Column filters
        return Object.entries(columnFilters).every(([colIdx, filterText]) => {
          if (!filterText) return true
          const cellVal = row[colIdx]
          return String(cellVal || '').toLowerCase().includes(filterText.toLowerCase())
        })
      })
    : []

  return (
    <div style={{ minHeight: '100vh', background: '#f8fafc', fontFamily: 'Inter, system-ui, sans-serif' }}>

      {/* Header */}
      <div style={{ background: '#fff', borderBottom: '1px solid #e2e8f0', padding: '20px 28px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700, color: '#0f172a', letterSpacing: '-0.3px' }}>File Cabinet</h1>
          <p style={{ margin: '2px 0 0', fontSize: 13, color: '#64748b' }}>{files.length} file{files.length !== 1 ? 's' : ''} stored</p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button onClick={() => { setShowLink(false); setShowUpload(v => !v) }}
            style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '8px 14px', background: '#dc2626', color: '#fff', border: 'none', borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: 'pointer' }}>
            <Upload size={15} /> Upload File
          </button>
          <button onClick={() => { setShowUpload(false); setShowLink(v => !v) }}
            style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '8px 14px', background: '#fff', color: '#374151', border: '1.5px solid #d1d5db', borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: 'pointer' }}>
            <Link size={15} /> Add Link
          </button>
        </div>
      </div>

      <div style={{ padding: '20px 28px', maxWidth: 1400, margin: '0 auto' }}>

        {/* Upload Panel */}
        {showUpload && <UploadForm categories={categories} onDone={() => { setShowUpload(false); fetchFiles() }} onCancel={() => setShowUpload(false)} />}
        {showLink   && <LinkForm   categories={categories} onDone={() => { setShowLink(false);   fetchFiles() }} onCancel={() => setShowLink(false)} />}

        {/* Filters */}
        <div style={{ display: 'flex', gap: 10, marginBottom: 20, flexWrap: 'wrap' }}>
          <div style={{ position: 'relative', flex: '1 1 220px' }}>
            <Search size={15} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: '#94a3b8' }} />
            <input
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Search files, clients, notes…"
              style={{ width: '100%', padding: '8px 10px 8px 32px', border: '1.5px solid #e2e8f0', borderRadius: 8, fontSize: 13, background: '#fff', boxSizing: 'border-box', outline: 'none' }}
            />
          </div>
          <select value={filterClient} onChange={e => setFilterClient(e.target.value)}
            style={{ padding: '8px 12px', border: '1.5px solid #e2e8f0', borderRadius: 8, fontSize: 13, background: '#fff', color: filterClient ? '#0f172a' : '#94a3b8', minWidth: 160 }}>
            <option value="">All clients</option>
            {allClients.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
          <select value={filterCat} onChange={e => setFilterCat(e.target.value)}
            style={{ padding: '8px 12px', border: '1.5px solid #e2e8f0', borderRadius: 8, fontSize: 13, background: '#fff', color: filterCat ? '#0f172a' : '#94a3b8', minWidth: 160 }}>
            <option value="">All categories</option>
            {categories.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>

        {/* File Groups */}
        {loading ? (
          <div style={{ textAlign: 'center', padding: 60, color: '#94a3b8', fontSize: 14 }}>Loading files…</div>
        ) : files.length === 0 ? (
          <EmptyState onUpload={() => setShowUpload(true)} />
        ) : (
          Object.entries(grouped).map(([cat, catFiles]) => (
            <CategoryGroup
              key={cat}
              cat={cat}
              files={catFiles}
              collapsed={collapsed[cat]}
              onToggle={() => setCollapsed(p => ({ ...p, [cat]: !p[cat] }))}
              onPreview={openPreview}
              onDelete={deleteFile}
              onDownload={downloadFileById}
              downloadingId={downloadingId}
              categories={categories}
              onUpdateCategory={updateFileCategory}
            />
          ))
        )}
      </div>

      {/* Preview Modal */}
      {(preview || previewLoading) && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)', zIndex: 1000, display: 'flex', flexDirection: 'column', padding: 20 }}>
          <div style={{ background: '#fff', borderRadius: 12, flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', maxHeight: '100%' }}>

            {/* Modal Header */}
            <div style={{ padding: '14px 20px', borderBottom: '1px solid #e2e8f0', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <FileSpreadsheet size={18} color="#10b981" />
                <span style={{ fontWeight: 700, fontSize: 15, color: '#0f172a' }}>{preview?.name || 'Loading…'}</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                {preview && preview.type === 'excel' && (
                  <div style={{ position: 'relative' }}>
                    <Search size={13} style={{ position: 'absolute', left: 8, top: '50%', transform: 'translateY(-50%)', color: '#94a3b8' }} />
                    <input
                      value={previewSearch}
                      onChange={e => setPreviewSearch(e.target.value)}
                      placeholder="Search in sheet…"
                      style={{ padding: '6px 10px 6px 26px', border: '1.5px solid #e2e8f0', borderRadius: 6, fontSize: 12, width: 200, outline: 'none' }}
                    />
                  </div>
                )}
                <button onClick={closePreview} style={{ background: '#f1f5f9', border: 'none', borderRadius: 6, padding: '6px 8px', cursor: 'pointer' }}>
                  <X size={16} color="#64748b" />
                </button>
              </div>
            </div>

            {previewLoading && (
              <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#94a3b8', fontSize: 14 }}>
                Loading file…
              </div>
            )}

            {preview && preview.type === 'excel' && (
              <>
                {/* Sheet Tabs */}
                <div style={{ display: 'flex', gap: 0, borderBottom: '1px solid #e2e8f0', padding: '0 20px', overflowX: 'auto' }}>
                  {Object.keys(preview.sheets).map(sh => (
                    <button key={sh} onClick={() => { setActiveSheet(sh); setPreviewSearch(''); setColumnFilters({}) }}
                      style={{
                        padding: '8px 16px', border: 'none', background: 'none', cursor: 'pointer', fontSize: 12, fontWeight: activeSheet === sh ? 700 : 400,
                        color: activeSheet === sh ? '#dc2626' : '#64748b',
                        borderBottom: activeSheet === sh ? '2px solid #dc2626' : '2px solid transparent',
                        whiteSpace: 'nowrap'
                      }}>
                      {sh}
                    </button>
                  ))}
                </div>

                {/* Sheet info bar */}
                {currentSheetData && (
                  <div style={{ padding: '6px 20px', background: '#f8fafc', borderBottom: '1px solid #e2e8f0', fontSize: 11, color: '#64748b' }}>
                    {filteredRows.length} row{filteredRows.length !== 1 ? 's' : ''} {previewSearch ? `matching "${previewSearch}"` : ''} — click a cell to copy it, click <strong>⊞</strong> to copy the row
                  </div>
                )}

                {/* Table */}
                <div style={{ flex: 1, overflow: 'auto' }}>
                  {currentSheetData ? (
                    <table style={{ borderCollapse: 'collapse', width: '100%', fontSize: 12 }}>
                      <thead>
                        <tr style={{ background: '#f1f5f9', position: 'sticky', top: 0, zIndex: 1 }}>
                          <th style={{ padding: '6px 10px', border: '1px solid #e2e8f0', color: '#64748b', fontWeight: 600, width: 30 }}>#</th>
                          {currentSheetData.headers.map((h, i) => (
                            <th key={i} style={{ padding: '6px 10px', border: '1px solid #e2e8f0', color: '#374151', fontWeight: 600, whiteSpace: 'nowrap', textAlign: 'left', verticalAlign: 'top' }}>
                              <div style={{ marginBottom: 4 }}>{h || `Col ${i + 1}`}</div>
                              <input 
                                type="text"
                                placeholder="Filter..."
                                value={columnFilters[i] || ''}
                                onChange={e => setColumnFilters(prev => ({...prev, [i]: e.target.value}))}
                                style={{ width: '100%', padding: '3px 6px', fontSize: 11, border: '1px solid #cbd5e1', borderRadius: 4, outline: 'none', boxSizing: 'border-box', fontWeight: 400 }}
                              />
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {filteredRows.map((row, ri) => (
                          <tr key={ri} style={{ background: ri % 2 === 0 ? '#fff' : '#fafafa' }}>
                            <td style={{ padding: '5px 10px', border: '1px solid #e2e8f0', color: '#94a3b8', textAlign: 'center' }}>
                              <button onClick={() => copyRow(row)} title="Copy row"
                                style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0, color: copiedCell === '__row__' ? '#10b981' : '#94a3b8' }}>
                                {copiedCell === '__row__' ? <Check size={12} /> : '⊞'}
                              </button>
                            </td>
                            {row.map((cell, ci) => (
                              <td key={ci}
                                onClick={() => copyCell(cell)}
                                title="Click to copy"
                                style={{
                                  padding: '5px 10px', border: '1px solid #e2e8f0', cursor: 'pointer', whiteSpace: 'nowrap', maxWidth: 300, overflow: 'hidden', textOverflow: 'ellipsis',
                                  background: copiedCell === cell && cell ? '#d1fae5' : undefined,
                                  color: '#0f172a', transition: 'background 0.2s'
                                }}>
                                {cell}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  ) : (
                    <div style={{ padding: 40, textAlign: 'center', color: '#94a3b8' }}>Select a sheet above</div>
                  )}
                </div>
              </>
            )}

            {preview && preview.type === 'media' && (
              <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#f8fafc', padding: 20 }}>
                {preview.ext === 'pdf' ? (
                  <iframe src={preview.url} style={{ width: '100%', height: '100%', border: 'none', borderRadius: 8 }} />
                ) : (
                  <img src={preview.url} alt={preview.name} style={{ maxWidth: '100%', maxHeight: '100%', objectFit: 'contain', borderRadius: 8 }} />
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

/* ── Category Group ── */
function CategoryGroup({ cat, files, collapsed, onToggle, onPreview, onDelete, onDownload, downloadingId, categories, onUpdateCategory }) {
  const color = CATEGORY_COLORS[cat] || '#6b7280'
  return (
    <div style={{ marginBottom: 14, background: '#fff', borderRadius: 10, border: '1.5px solid #e2e8f0', overflow: 'hidden' }}>
      <button onClick={onToggle}
        style={{ width: '100%', display: 'flex', alignItems: 'center', gap: 10, padding: '12px 16px', background: 'none', border: 'none', cursor: 'pointer', textAlign: 'left' }}>
        <span style={{ width: 10, height: 10, borderRadius: '50%', background: color, flexShrink: 0 }} />
        <span style={{ fontWeight: 700, fontSize: 14, color: '#0f172a', flex: 1 }}>{cat}</span>
        <span style={{ fontSize: 12, color: '#94a3b8', marginRight: 6 }}>{files.length} file{files.length !== 1 ? 's' : ''}</span>
        {collapsed ? <ChevronRight size={15} color="#94a3b8" /> : <ChevronDown size={15} color="#94a3b8" />}
      </button>
      {!collapsed && (
        <div style={{ borderTop: '1px solid #f1f5f9' }}>
          {files.map(f => <FileRow key={f.id} file={f} onPreview={onPreview} onDelete={onDelete} onDownload={onDownload} downloadingId={downloadingId} categories={categories} onUpdateCategory={onUpdateCategory} />)}
        </div>
      )}
    </div>
  )
}

/* ── File Row ── */
function FileRow({ file, onPreview, onDelete, onDownload, downloadingId, categories, onUpdateCategory }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 16px', borderBottom: '1px solid #f8fafc', flexWrap: 'wrap' }}>
      {file.filename && !['xlsx', 'xls', 'csv'].includes(file.filename.split('.').pop().toLowerCase()) 
        ? <FileText size={16} color="#3b82f6" style={{ flexShrink: 0 }} />
        : <FileSpreadsheet size={16} color="#10b981" style={{ flexShrink: 0 }} />
      }
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontWeight: 600, fontSize: 13, color: '#0f172a', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{file.name}</div>
        <div style={{ display: 'flex', gap: 8, marginTop: 3, flexWrap: 'wrap', alignItems: 'center' }}>
          {file.client && (
            <span style={{ display: 'flex', alignItems: 'center', gap: 3, fontSize: 11, color: '#64748b' }}>
              <Building2 size={11} /> {file.client}
            </span>
          )}
          {file.sheet_names?.length > 0 && (
            <span style={{ fontSize: 11, color: '#94a3b8' }}>{file.sheet_names.length} sheet{file.sheet_names.length !== 1 ? 's' : ''}</span>
          )}
          {file.row_count > 0 && (
            <span style={{ fontSize: 11, color: '#94a3b8' }}>{file.row_count} rows</span>
          )}
          {file.tags?.map(t => (
            <span key={t} style={{ display: 'inline-flex', alignItems: 'center', gap: 3, fontSize: 10, background: '#f1f5f9', color: '#64748b', borderRadius: 4, padding: '1px 6px' }}>
              <Tag size={9} />{t}
            </span>
          ))}
          <select 
            value={file.category || 'Company General Data'} 
            onChange={(e) => onUpdateCategory(file.id, e.target.value)}
            style={{ fontSize: 11, color: '#dc2626', padding: '1px 4px', border: '1px solid #e0e7ff', borderRadius: 4, background: '#e0e7ff', cursor: 'pointer', outline: 'none', fontWeight: 600 }}
          >
            {categories.map(c => <option key={c} value={c}>{c}</option>)}
            {!categories.includes('Imported') && file.category === 'Imported' && <option value="Imported">Imported</option>}
          </select>
        </div>
      </div>
      <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
        {file.sharepoint_link && (
          <a href={file.sharepoint_link} target="_blank" rel="noopener noreferrer"
            style={{ display: 'flex', alignItems: 'center', gap: 4, padding: '5px 10px', background: '#f1f5f9', border: 'none', borderRadius: 6, fontSize: 11, color: '#374151', cursor: 'pointer', textDecoration: 'none' }}>
            <Link size={12} /> SharePoint
          </a>
        )}
        {file.filename && (
          <>
            <button onClick={() => onPreview(file)}
              style={{ display: 'flex', alignItems: 'center', gap: 4, padding: '5px 10px', background: '#ede9fe', border: 'none', borderRadius: 6, fontSize: 11, color: '#dc2626', cursor: 'pointer', fontWeight: 600 }}>
              <Eye size={12} /> Preview
            </button>
            <button onClick={() => onDownload(file)} disabled={downloadingId === file.id}
              style={{ display: 'flex', alignItems: 'center', gap: 4, padding: '5px 10px', background: '#f0fdf4', border: 'none', borderRadius: 6, fontSize: 11, color: '#10b981', cursor: 'pointer' }}>
              {downloadingId === file.id ? <Loader2 size={12} className="animate-spin" /> : <Download size={12} />} Download
            </button>
          </>
        )}
        <button onClick={() => onDelete(file.id)}
          style={{ display: 'flex', alignItems: 'center', padding: '5px 8px', background: '#fff0f0', border: 'none', borderRadius: 6, cursor: 'pointer' }}>
          <Trash2 size={12} color="#ef4444" />
        </button>
      </div>
    </div>
  )
}

/* ── Upload Form ── */
function UploadForm({ categories, onDone, onCancel }) {
  const [form, setForm] = useState({ name: '', client: '', category: 'Company General Data', tags: '', notes: '' })
  const [file, setFile] = useState(null)
  const [loading, setLoading] = useState(false)

  async function submit() {
    if (!form.name) return alert('Name is required')
    setLoading(true)
    const fd = new FormData()
    Object.entries(form).forEach(([k, v]) => fd.append(k, v))
    if (file) fd.append('file', file)
    await projectFilesApi.upload(fd)
    setLoading(false)
    onDone()
  }

  return (
    <FormPanel title="Upload File" onCancel={onCancel} onSubmit={submit} loading={loading} submitLabel="Upload">
      <FormRow label="Name *"><input value={form.name} onChange={e => setForm(p => ({ ...p, name: e.target.value }))} placeholder="e.g. Hinduja House PQ Form" style={inp} /></FormRow>
      <FormRow label="Client"><input value={form.client} onChange={e => setForm(p => ({ ...p, client: e.target.value }))} placeholder="e.g. JLL India" style={inp} /></FormRow>
      <FormRow label="Category">
        <select value={form.category} onChange={e => setForm(p => ({ ...p, category: e.target.value }))} style={inp}>
          {categories.map(c => <option key={c}>{c}</option>)}
        </select>
      </FormRow>
      <FormRow label="Tags"><input value={form.tags} onChange={e => setForm(p => ({ ...p, tags: e.target.value }))} placeholder="comma-separated e.g. HTL, 2024, Mumbai" style={inp} /></FormRow>
      <FormRow label="Notes"><input value={form.notes} onChange={e => setForm(p => ({ ...p, notes: e.target.value }))} placeholder="Optional notes" style={inp} /></FormRow>
      <FormRow label="File">
        <input type="file" onChange={e => setFile(e.target.files[0])} style={{ fontSize: 13 }} />
      </FormRow>
    </FormPanel>
  )
}

/* ── Link Form ── */
function LinkForm({ categories, onDone, onCancel }) {
  const [form, setForm] = useState({ name: '', client: '', category: 'Company General Data', tags: '', notes: '', sharepoint_link: '' })
  const [loading, setLoading] = useState(false)

  async function submit() {
    if (!form.name || !form.sharepoint_link) return alert('Name and link are required')
    setLoading(true)
    const fd = new FormData()
    Object.entries(form).forEach(([k, v]) => fd.append(k, v))
    await projectFilesApi.addSharepoint(fd)
    setLoading(false)
    onDone()
  }

  return (
    <FormPanel title="Add SharePoint Link" onCancel={onCancel} onSubmit={submit} loading={loading} submitLabel="Save Link">
      <FormRow label="Name *"><input value={form.name} onChange={e => setForm(p => ({ ...p, name: e.target.value }))} placeholder="e.g. HTL Sector Register" style={inp} /></FormRow>
      <FormRow label="Client"><input value={form.client} onChange={e => setForm(p => ({ ...p, client: e.target.value }))} placeholder="e.g. HTL Aircon" style={inp} /></FormRow>
      <FormRow label="Category">
        <select value={form.category} onChange={e => setForm(p => ({ ...p, category: e.target.value }))} style={inp}>
          {categories.map(c => <option key={c}>{c}</option>)}
        </select>
      </FormRow>
      <FormRow label="SharePoint URL *"><input value={form.sharepoint_link} onChange={e => setForm(p => ({ ...p, sharepoint_link: e.target.value }))} placeholder="https://..." style={inp} /></FormRow>
      <FormRow label="Tags"><input value={form.tags} onChange={e => setForm(p => ({ ...p, tags: e.target.value }))} placeholder="comma-separated" style={inp} /></FormRow>
      <FormRow label="Notes"><input value={form.notes} onChange={e => setForm(p => ({ ...p, notes: e.target.value }))} placeholder="Optional notes" style={inp} /></FormRow>
    </FormPanel>
  )
}

function FormPanel({ title, onCancel, onSubmit, loading, submitLabel, children }) {
  return (
    <div style={{ background: '#fff', border: '1.5px solid #e2e8f0', borderRadius: 10, padding: 20, marginBottom: 20 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <h3 style={{ margin: 0, fontSize: 15, fontWeight: 700, color: '#0f172a' }}>{title}</h3>
        <button onClick={onCancel} style={{ background: 'none', border: 'none', cursor: 'pointer' }}><X size={16} color="#64748b" /></button>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        {children}
      </div>
      <div style={{ marginTop: 16, display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
        <button onClick={onCancel} style={{ padding: '8px 16px', background: '#f1f5f9', border: 'none', borderRadius: 8, fontSize: 13, cursor: 'pointer', color: '#374151' }}>Cancel</button>
        <button onClick={onSubmit} disabled={loading}
          style={{ padding: '8px 16px', background: '#dc2626', color: '#fff', border: 'none', borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: 'pointer', opacity: loading ? 0.7 : 1 }}>
          {loading ? 'Saving…' : submitLabel}
        </button>
      </div>
    </div>
  )
}

function FormRow({ label, children }) {
  return (
    <div>
      <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: '#374151', marginBottom: 4 }}>{label}</label>
      {children}
    </div>
  )
}

function EmptyState({ onUpload }) {
  return (
    <div style={{ textAlign: 'center', padding: '60px 20px', color: '#94a3b8' }}>
      <FileSpreadsheet size={40} color="#cbd5e1" style={{ marginBottom: 12 }} />
      <p style={{ fontSize: 15, fontWeight: 600, color: '#64748b', margin: '0 0 6px' }}>No files yet</p>
      <p style={{ fontSize: 13, margin: '0 0 16px' }}>Upload a file or add a SharePoint link to get started</p>
      <button onClick={onUpload}
        style={{ padding: '9px 18px', background: '#dc2626', color: '#fff', border: 'none', borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: 'pointer' }}>
        <Plus size={14} style={{ marginRight: 5, verticalAlign: 'middle' }} /> Upload your first file
      </button>
    </div>
  )
}

const inp = {
  width: '100%', padding: '8px 10px', border: '1.5px solid #e2e8f0', borderRadius: 7,
  fontSize: 13, outline: 'none', boxSizing: 'border-box', background: '#fff'
}
