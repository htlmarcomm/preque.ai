import { useState, useEffect } from 'react'
import { Plus, Search, Edit2, Trash2, Check, X, Upload, Database, Loader2, Building2, Briefcase, FileText } from 'lucide-react'
import { companyApi, projectDataApi } from '../lib/api'

export default function CompanyDB() {
  const [activeTab, setActiveTab] = useState('Fields') // 'Fields' | 'Financials' | 'Project References'
  
  // Fields state
  const [fields, setFields] = useState([])
  const [categories, setCategories] = useState([])
  const [activeCategory, setActiveCategory] = useState(null)
  
  // Financials state
  const [financials, setFinancials] = useState([])
  const [finYearFilter, setFinYearFilter] = useState('')
  
  // Projects state
  const [projects, setProjects] = useState([])
  const [projRegionFilter, setProjRegionFilter] = useState('')
  const [projStatusFilter, setProjStatusFilter] = useState('')

  // Project Details state
  const [pdFiles, setPdFiles] = useState([])
  const [pdActiveFile, setPdActiveFile] = useState(null)
  const [pdActiveSheet, setPdActiveSheet] = useState(null)
  const [pdRecords, setPdRecords] = useState(null)
  const [pdRecordsTotal, setPdRecordsTotal] = useState(0)
  const [pdPage, setPdPage] = useState(1)
  const [pdSearch, setPdSearch] = useState('')
  const [pdFilters, setPdFilters] = useState([])
  const [pdActiveFilterValues, setPdActiveFilterValues] = useState({})
  const [pdUploading, setPdUploading] = useState(false)
  const [pdUploadResult, setPdUploadResult] = useState(null)
  const [pdLoadingRecords, setPdLoadingRecords] = useState(false)

  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [seeding, setSeeding] = useState(false)
  const [editingId, setEditingId] = useState(null)
  const [editVal, setEditVal] = useState({})
  const [adding, setAdding] = useState(false)
  const [importing, setImporting] = useState(false)
  const [newField, setNewField] = useState({ category: '', field_key: '', field_label: '', value: '', document_link: '' })

  const loadFields = async () => {
    const [f, c] = await Promise.all([companyApi.getFields(activeCategory), companyApi.getCategories()])
    setFields(f.data.fields || [])
    setCategories(c.data.categories || [])
  }

  const loadFinancials = async () => {
    const res = await companyApi.getFinancialRecords()
    setFinancials(res.data || [])
  }

  const loadProjects = async () => {
    const res = await companyApi.getProjectReferences()
    setProjects(res.data || [])
  }

  const loadFiles = async () => {
    const res = await projectDataApi.getFiles()
    setPdFiles(res.data)
    if (!pdActiveFile && res.data.length > 0) {
      setPdActiveFile(res.data[0].source_file)
      if (res.data[0].sheets.length > 0) {
        setPdActiveSheet(res.data[0].sheets[0].source_sheet)
      }
    }
  }

  const loadSheetData = async () => {
    if (!pdActiveFile || !pdActiveSheet) return
    setPdLoadingRecords(true)
    try {
      const filtersResponse = await projectDataApi.getSheetFilters(pdActiveFile, pdActiveSheet)
      setPdFilters(filtersResponse.data.filters || [])
      
      const filterParams = {}
      Object.entries(pdActiveFilterValues).forEach(([k, v]) => {
        if (v) filterParams[k] = v
      })
      
      const recordsResponse = await projectDataApi.getSheetRecords(pdActiveFile, pdActiveSheet, {
        page: pdPage,
        page_size: 50,
        search: pdSearch,
        ...filterParams
      })
      
      setPdRecords(recordsResponse.data)
      setPdRecordsTotal(recordsResponse.data.total)
    } catch (err) {
      console.error("Error loading sheet records", err)
    } finally {
      setPdLoadingRecords(false)
    }
  }

  useEffect(() => {
    if (activeTab === 'Project Details') {
      loadFiles()
    }
  }, [activeTab])

  useEffect(() => {
    if (activeTab === 'Project Details' && pdActiveFile && pdActiveSheet) {
      const timeoutId = setTimeout(() => {
        loadSheetData()
      }, 400)
      return () => clearTimeout(timeoutId)
    }
  }, [pdActiveFile, pdActiveSheet, pdPage, pdSearch, pdActiveFilterValues])

  const handlePdImport = async (e) => {
    const file = e.target.files[0]
    if (!file) return
    setPdUploading(true)
    setPdUploadResult(null)
    try {
      const res = await projectDataApi.importExcel(file)
      setPdUploadResult(`Imported ${res.data.rows_ingested} rows from ${res.data.sheets_processed} sheets in ${res.data.file} (${res.data.rows_skipped_duplicate} duplicates skipped).`)
      await loadFiles()
      setPdActiveFile(res.data.file)
      setPdSearch('')
      setPdActiveFilterValues({})
      setPdPage(1)
      
      const newlyLoadedFiles = await projectDataApi.getFiles()
      const newFileObj = newlyLoadedFiles.data.find(f => f.source_file === res.data.file)
      if (newFileObj && newFileObj.sheets.length > 0) {
        setPdActiveSheet(newFileObj.sheets[0].source_sheet)
      }
    } catch (err) {
      setPdUploadResult('Error importing file: ' + err.message)
    } finally {
      setPdUploading(false)
      e.target.value = ''
    }
  }

  const handlePdFileClick = (fileObj) => {
    setPdActiveFile(fileObj.source_file)
    if (fileObj.sheets.length > 0) setPdActiveSheet(fileObj.sheets[0].source_sheet)
    setPdSearch('')
    setPdActiveFilterValues({})
    setPdPage(1)
  }

  const handlePdSheetClick = (sheetName) => {
    setPdActiveSheet(sheetName)
    setPdSearch('')
    setPdActiveFilterValues({})
    setPdPage(1)
  }

  const loadAll = async () => {
    setLoading(true)
    if (activeTab === 'Fields') await loadFields()
    if (activeTab === 'Financials') await loadFinancials()
    if (activeTab === 'Project References') await loadProjects()
    setLoading(false)
  }

  // eslint-disable-next-line
  useEffect(() => { loadAll() }, [activeTab, activeCategory])
  // We don't reload on finYearFilter or projRegionFilter because we filter locally for instant UI

  const seed = async () => {
    setSeeding(true)
    await companyApi.seed()
    await companyApi.seed.call(null) // documents seed via separate call
    await loadAll()
    setSeeding(false)
  }

  const startEdit = (field) => {
    setEditingId(field.id)
    setEditVal({ value: field.value || '', document_link: field.document_link || '', notes: field.notes || '' })
  }

  const saveEdit = async (id) => {
    await companyApi.updateField(id, editVal)
    setEditingId(null)
    loadAll()
  }

  const deleteField = async (id) => {
    if (!confirm('Delete this field?')) return
    await companyApi.deleteField(id)
    loadAll()
  }

  const addField = async () => {
    if (!newField.field_label || !newField.category) return
    const key = newField.field_key || newField.field_label.toLowerCase().replace(/\s+/g, '_').replace(/[^a-z0-9_]/g, '')
    await companyApi.createField({ ...newField, field_key: key })
    setAdding(false)
    setNewField({ category: '', field_key: '', field_label: '', value: '', document_link: '' })
    loadAll()
  }

  const handleImport = async (e) => {
    const file = e.target.files[0]
    if (!file) return
    setImporting(true)
    try {
      const res = await companyApi.importExcel(file)
      alert(`Success! Imported ${res.data.imported} new fields and updated ${res.data.updated} existing fields.`)
      await loadAll()
    } catch (err) {
      alert('Error importing file: ' + err.message)
    } finally {
      setImporting(false)
      e.target.value = ''
    }
  }

  const handleImportProjects = async (e) => {
    const file = e.target.files[0]
    if (!file) return
    setImporting(true)
    try {
      const res = await companyApi.importProjectsExcel(file)
      alert(`Success! Imported ${res.data.imported} project references.`)
      await loadAll()
    } catch (err) {
      alert('Error importing file: ' + err.message)
    } finally {
      setImporting(false)
      e.target.value = ''
    }
  }

  // --- Filtering Logic ---
  
  // Fields
  const filteredFields = fields.filter(f =>
    !search || f.field_label?.toLowerCase().includes(search.toLowerCase()) ||
    f.value?.toLowerCase().includes(search.toLowerCase())
  )
  const groupedFields = filteredFields.reduce((acc, f) => {
    const cat = f.category || 'Other'
    if (!acc[cat]) acc[cat] = []
    acc[cat].push(f)
    return acc
  }, {})

  // Financials
  const distinctYears = [...new Set(financials.map(f => f.fiscal_year).filter(Boolean))].sort().reverse()
  const filteredFinancials = financials.filter(f => {
    if (finYearFilter && f.fiscal_year !== finYearFilter) return false
    if (search && !f.metric_label?.toLowerCase().includes(search.toLowerCase()) && !f.value?.toLowerCase().includes(search.toLowerCase())) return false
    return true
  })
  const groupedFinancials = filteredFinancials.reduce((acc, f) => {
    const yr = f.fiscal_year || 'Unknown Year'
    if (!acc[yr]) acc[yr] = []
    acc[yr].push(f)
    return acc
  }, {})

  // Projects
  const distinctRegions = [...new Set(projects.map(p => p.region).filter(Boolean))].sort()
  const distinctStatuses = [...new Set(projects.map(p => p.status).filter(Boolean))].sort()
  const filteredProjects = projects.filter(p => {
    if (projRegionFilter && p.region !== projRegionFilter) return false
    if (projStatusFilter && p.status !== projStatusFilter) return false
    if (search && 
      !p.project_name?.toLowerCase().includes(search.toLowerCase()) &&
      !p.client_name?.toLowerCase().includes(search.toLowerCase()) &&
      !p.location?.toLowerCase().includes(search.toLowerCase()) &&
      !p.consultant?.toLowerCase().includes(search.toLowerCase()) &&
      !p.pmc?.toLowerCase().includes(search.toLowerCase())
    ) return false
    return true
  })

  return (
    <div className="p-8 max-w-7xl mx-auto h-[100vh] flex flex-col overflow-hidden">
      <div className="flex items-center justify-between mb-6 shrink-0">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">Company Database</h1>
          <p className="text-sm text-gray-500 mt-1">Source of truth for all form filling</p>
        </div>
        
        {/* Actions for Fields tab */}
        {activeTab === 'Fields' && (
          <div className="flex gap-2">
            {fields.length === 0 && (
              <button onClick={seed} disabled={seeding} className="btn-primary">
                {seeding ? <Loader2 size={15} className="animate-spin" /> : <Database size={15} />}
                Load HTL Data
              </button>
            )}
            <label className={`btn-secondary ${importing ? 'opacity-70 cursor-not-allowed' : 'cursor-pointer'}`}>
              {importing ? <Loader2 size={15} className="animate-spin" /> : <Upload size={15} />}
              {importing ? 'Importing...' : 'Import Excel'}
              <input type="file" className="hidden" accept=".xlsx,.xls" onChange={handleImport} disabled={importing} />
            </label>
            <button onClick={() => setAdding(true)} className="btn-primary">
              <Plus size={15} />Add Field
            </button>
          </div>
        )}

        {/* Actions for Projects tab */}
        {activeTab === 'Project References' && (
          <div className="flex gap-2">
            <label className={`btn-secondary ${importing ? 'opacity-70 cursor-not-allowed' : 'cursor-pointer'}`}>
              {importing ? <Loader2 size={15} className="animate-spin" /> : <Upload size={15} />}
              {importing ? 'Importing...' : 'Import Excel'}
              <input type="file" className="hidden" accept=".xlsx,.xls" onChange={handleImportProjects} disabled={importing} />
            </label>
          </div>
        )}
      </div>

      {/* Tabs */}
      <div className="flex gap-6 border-b border-gray-200 mb-6 shrink-0">
        <button 
          onClick={() => { setActiveTab('Fields'); setSearch(''); }}
          className={`pb-3 text-sm font-medium border-b-2 flex items-center gap-2 transition-colors ${activeTab === 'Fields' ? 'border-brand-600 text-brand-600' : 'border-transparent text-gray-500 hover:text-gray-700'}`}>
          <FileText size={16} /> Fields
        </button>
        <button 
          onClick={() => { setActiveTab('Financials'); setSearch(''); }}
          className={`pb-3 text-sm font-medium border-b-2 flex items-center gap-2 transition-colors ${activeTab === 'Financials' ? 'border-brand-600 text-brand-600' : 'border-transparent text-gray-500 hover:text-gray-700'}`}>
          <Building2 size={16} /> Financials
        </button>
        <button 
          onClick={() => { setActiveTab('Project References'); setSearch(''); }}
          className={`pb-3 text-sm font-medium border-b-2 flex items-center gap-2 transition-colors ${activeTab === 'Project References' ? 'border-brand-600 text-brand-600' : 'border-transparent text-gray-500 hover:text-gray-700'}`}>
          <Briefcase size={16} /> Project References
        </button>
        <button 
          onClick={() => { setActiveTab('Project Details'); setSearch(''); }}
          className={`pb-3 text-sm font-medium border-b-2 flex items-center gap-2 transition-colors ${activeTab === 'Project Details' ? 'border-brand-600 text-brand-600' : 'border-transparent text-gray-500 hover:text-gray-700'}`}>
          <Database size={16} /> Project Details
        </button>
      </div>

      <div className="flex-1 overflow-auto min-h-0 pb-12 pr-2">
        {/* Filters Area */}
        <div className="flex gap-3 mb-6 shrink-0">
        <div className="relative flex-1 max-w-xs">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input className="input w-full pl-9 text-sm" placeholder={`Search ${activeTab.toLowerCase()}…`}
            value={search} onChange={e => setSearch(e.target.value)} />
        </div>
        
        {/* Fields Filters */}
        {activeTab === 'Fields' && (
          <div className="flex gap-1 flex-wrap">
            <button onClick={() => setActiveCategory(null)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${!activeCategory ? 'bg-brand-50 text-brand-700' : 'text-gray-500 hover:bg-gray-100'}`}>
              All
            </button>
            {categories.map(cat => (
              <button key={cat} onClick={() => setActiveCategory(cat === activeCategory ? null : cat)}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${activeCategory === cat ? 'bg-brand-50 text-brand-700' : 'text-gray-500 hover:bg-gray-100'}`}>
                {cat}
              </button>
            ))}
          </div>
        )}

        {/* Financials Filters */}
        {activeTab === 'Financials' && (
          <div className="flex gap-2 items-center">
            <span className="text-sm text-gray-500 font-medium">Year:</span>
            <select className="input text-sm py-1.5" value={finYearFilter} onChange={e => setFinYearFilter(e.target.value)}>
              <option value="">All Years</option>
              {distinctYears.map(y => <option key={y} value={y}>{y}</option>)}
            </select>
          </div>
        )}

        {/* Projects Filters */}
        {activeTab === 'Project References' && (
          <>
            <div className="flex gap-2 items-center">
              <span className="text-sm text-gray-500 font-medium">Region:</span>
              <select className="input text-sm py-1.5" value={projRegionFilter} onChange={e => setProjRegionFilter(e.target.value)}>
                <option value="">All Regions</option>
                {distinctRegions.map(r => <option key={r} value={r}>{r}</option>)}
              </select>
            </div>
            <div className="flex gap-2 items-center">
              <span className="text-sm text-gray-500 font-medium">Status:</span>
              <select className="input text-sm py-1.5" value={projStatusFilter} onChange={e => setProjStatusFilter(e.target.value)}>
                <option value="">All Statuses</option>
                {distinctStatuses.map(s => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
          </>
        )}
      </div>

      {/* Loading state */}
      {loading && <div className="text-center py-20"><Loader2 size={28} className="animate-spin text-brand-500 mx-auto" /></div>}

      {/* FIELDS TAB */}
      {!loading && activeTab === 'Fields' && (
        <>
          {adding && (
            <div className="card p-5 mb-6">
              <h3 className="font-medium text-sm text-gray-900 mb-4">New Field</h3>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-gray-500 mb-1">Category</label>
                  <select className="input w-full text-sm" value={newField.category}
                    onChange={e => setNewField(p => ({ ...p, category: e.target.value }))}>
                    <option value="">Select…</option>
                    {categories.map(c => <option key={c}>{c}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-xs text-gray-500 mb-1">Label</label>
                  <input className="input w-full text-sm" placeholder="e.g. Director Name"
                    value={newField.field_label} onChange={e => setNewField(p => ({ ...p, field_label: e.target.value }))} />
                </div>
                <div>
                  <label className="block text-xs text-gray-500 mb-1">Value</label>
                  <input className="input w-full text-sm" placeholder="The actual answer"
                    value={newField.value} onChange={e => setNewField(p => ({ ...p, value: e.target.value }))} />
                </div>
                <div>
                  <label className="block text-xs text-gray-500 mb-1">Document link (optional)</label>
                  <input className="input w-full text-sm" placeholder="SharePoint URL"
                    value={newField.document_link} onChange={e => setNewField(p => ({ ...p, document_link: e.target.value }))} />
                </div>
              </div>
              <div className="flex gap-2 mt-4">
                <button onClick={addField} className="btn-primary"><Check size={14} />Save</button>
                <button onClick={() => setAdding(false)} className="btn-secondary"><X size={14} />Cancel</button>
              </div>
            </div>
          )}

          {fields.length === 0 ? (
            <div className="card p-16 text-center">
              <Database size={40} className="text-gray-200 mx-auto mb-4" />
              <p className="font-medium text-gray-700">No company data yet</p>
              <p className="text-sm text-gray-400 mt-1">Click "Load HTL Data" to seed from the pre-qual form, or import an Excel file</p>
            </div>
          ) : (
            <div className="space-y-6">
              {Object.entries(groupedFields).map(([cat, catFields]) => (
                <div key={cat} className="card overflow-hidden">
                  <div className="px-4 py-3 bg-gray-50 border-b border-gray-100">
                    <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">{cat}</h3>
                  </div>
                  <table className="w-full text-sm">
                    <colgroup><col className="w-64" /><col /><col className="w-48" /><col className="w-20" /></colgroup>
                    <tbody className="divide-y divide-gray-50">
                      {catFields.map(field => (
                        <tr key={field.id} className="hover:bg-gray-50 group">
                          <td className="px-4 py-3">
                            <div className="flex items-center gap-2">
                              <span className="text-gray-900 font-medium">{field.field_label}</span>
                              <span title={`Confidence: ${field.confidence || 'verified'}`} className={`w-2 h-2 rounded-full flex-shrink-0 ${!field.confidence || field.confidence === 'verified' ? 'bg-green-500' : field.confidence === 'learned' ? 'bg-yellow-400' : 'bg-red-400'}`}></span>
                            </div>
                            {field.aliases && field.aliases.length > 0 && (
                              <div className="flex flex-wrap gap-1 mt-1.5">
                                {field.aliases.map(a => (
                                  <span key={a} className="px-1.5 py-0.5 rounded bg-gray-100 text-[10px] text-gray-500">{a}</span>
                                ))}
                              </div>
                            )}
                            {field.usage_count > 0 && (
                              <div className="text-[10px] text-gray-400 mt-1">Used {field.usage_count} time{field.usage_count !== 1 ? 's' : ''}</div>
                            )}
                          </td>
                          <td className="px-4 py-3">
                            {editingId === field.id ? (
                              <input className="input w-full text-sm" value={editVal.value}
                                onChange={e => setEditVal(p => ({ ...p, value: e.target.value }))}
                                onKeyDown={e => e.key === 'Enter' && saveEdit(field.id)} autoFocus />
                            ) : (
                              <span className={field.value ? 'text-gray-900' : 'text-gray-300 italic'}>
                                {field.value || 'Not set'}
                              </span>
                            )}
                          </td>
                          <td className="px-4 py-3">
                            {editingId === field.id ? (
                              <input className="input w-full text-xs" placeholder="Doc link" value={editVal.document_link}
                                onChange={e => setEditVal(p => ({ ...p, document_link: e.target.value }))} />
                            ) : (
                              field.document_link
                                ? <a href={field.document_link} target="_blank" rel="noreferrer" className="text-xs text-brand-600 hover:underline truncate block max-w-[180px]">Link ↗</a>
                                : null
                            )}
                          </td>
                          <td className="px-4 py-3">
                            <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                              {editingId === field.id ? (
                                <>
                                  <button onClick={() => saveEdit(field.id)} className="p-1 text-green-600 hover:bg-green-50 rounded"><Check size={14} /></button>
                                  <button onClick={() => setEditingId(null)} className="p-1 text-gray-400 hover:bg-gray-100 rounded"><X size={14} /></button>
                                </>
                              ) : (
                                <>
                                  <button onClick={() => startEdit(field)} className="p-1 text-gray-400 hover:text-brand-600 hover:bg-brand-50 rounded"><Edit2 size={14} /></button>
                                  <button onClick={() => deleteField(field.id)} className="p-1 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded"><Trash2 size={14} /></button>
                                </>
                              )}
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {/* FINANCIALS TAB */}
      {!loading && activeTab === 'Financials' && (
        financials.length === 0 ? (
          <div className="card p-16 text-center">
            <Building2 size={40} className="text-gray-200 mx-auto mb-4" />
            <p className="font-medium text-gray-700">No financial records</p>
            <p className="text-sm text-gray-400 mt-1">Run the database seed scripts to import financial data</p>
          </div>
        ) : (
          <div className="space-y-6">
            {Object.entries(groupedFinancials).sort(([a], [b]) => b.localeCompare(a)).map(([yr, yrFinancials]) => (
              <div key={yr} className="card overflow-hidden">
                <div className="px-4 py-3 bg-gray-50 border-b border-gray-100 flex justify-between items-center">
                  <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">{yr}</h3>
                  <span className="text-xs text-gray-400">{yrFinancials.length} records</span>
                </div>
                <table className="w-full text-sm">
                  <colgroup><col className="w-64" /><col /><col className="w-32" /><col className="w-48" /></colgroup>
                  <thead className="bg-white border-b border-gray-100 text-xs text-gray-500">
                    <tr>
                      <th className="px-4 py-2 text-left font-medium">Metric</th>
                      <th className="px-4 py-2 text-left font-medium">Value</th>
                      <th className="px-4 py-2 text-left font-medium">Category</th>
                      <th className="px-4 py-2 text-left font-medium">Source</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-50">
                    {yrFinancials.map(f => (
                      <tr key={f.id} className="hover:bg-gray-50">
                        <td className="px-4 py-3 font-medium text-gray-900">{f.metric_label}</td>
                        <td className="px-4 py-3">
                          <span className="text-gray-900">{f.value || '-'}</span>
                          {f.unit && <span className="ml-1 text-gray-500 text-xs">{f.unit}</span>}
                        </td>
                        <td className="px-4 py-3 text-gray-500">{f.category}</td>
                        <td className="px-4 py-3 text-gray-400 text-xs truncate max-w-[150px]" title={f.source}>{f.source}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))}
          </div>
        )
      )}

      {/* PROJECTS TAB */}
      {!loading && activeTab === 'Project References' && (
        projects.length === 0 ? (
          <div className="card p-16 text-center">
            <Briefcase size={40} className="text-gray-200 mx-auto mb-4" />
            <p className="font-medium text-gray-700">No project references</p>
            <p className="text-sm text-gray-400 mt-1">Run the project reference import script to populate this table</p>
          </div>
        ) : (
          <div className="card overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead className="bg-gray-50 border-b border-gray-100 text-xs text-gray-500 uppercase tracking-wider">
                <tr>
                  <th className="px-4 py-3 font-medium">Project Name</th>
                  <th className="px-4 py-3 font-medium">Client</th>
                  <th className="px-4 py-3 font-medium">Location</th>
                  <th className="px-4 py-3 font-medium">Consultant</th>
                  <th className="px-4 py-3 font-medium">PMC</th>
                  <th className="px-4 py-3 font-medium">Sector</th>
                  <th className="px-4 py-3 font-medium">Type</th>
                  <th className="px-4 py-3 font-medium">Value</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="px-4 py-3 font-medium">Timeline</th>
                  <th className="px-4 py-3 font-medium">Rep Contact</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {filteredProjects.map(p => (
                  <tr key={p.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3 font-medium text-gray-900 max-w-[250px] truncate" title={p.project_name}>
                      {p.project_name}
                      <div className="text-[10px] text-gray-400 font-normal mt-0.5">{p.region}</div>
                    </td>
                    <td className="px-4 py-3 text-gray-700 max-w-[150px] truncate" title={p.client_name}>{p.client_name}</td>
                    <td className="px-4 py-3 text-gray-500">{p.location || '-'}</td>
                    <td className="px-4 py-3 text-gray-500">{p.consultant || '-'}</td>
                    <td className="px-4 py-3 text-gray-500">{p.pmc || '-'}</td>
                    <td className="px-4 py-3 text-gray-500">{p.project_sector || '-'}</td>
                    <td className="px-4 py-3 text-gray-500 max-w-[150px] truncate" title={p.project_type}>{p.project_type || '-'}</td>
                    <td className="px-4 py-3 text-gray-900">{p.project_value || '-'}</td>
                    <td className="px-4 py-3">
                      {p.status && (
                        <span className={`px-2 py-0.5 rounded-full text-[10px] font-medium ${
                          p.status.toLowerCase().includes('completed') ? 'bg-green-100 text-green-700' :
                          p.status.toLowerCase().includes('ongoing') ? 'bg-blue-100 text-blue-700' :
                          'bg-gray-100 text-gray-700'
                        }`}>
                          {p.status}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-gray-500 whitespace-nowrap text-xs">
                      {p.start_date || p.end_date ? (
                        <>
                          <div>{p.start_date || '-'}</div>
                          <div className="text-gray-400">to {p.end_date || '-'}</div>
                        </>
                      ) : '-'}
                    </td>
                    <td className="px-4 py-3 text-xs">
                      {p.client_rep_name ? (
                        <div>
                          <div className="font-medium text-gray-900">{p.client_rep_name}</div>
                          {p.client_rep_designation && <div className="text-gray-500">{p.client_rep_designation}</div>}
                          {p.client_rep_phone && <div className="text-brand-600 mt-0.5">{p.client_rep_phone}</div>}
                          {p.client_rep_email && <div className="text-brand-600 truncate max-w-[150px]" title={p.client_rep_email}>{p.client_rep_email}</div>}
                        </div>
                      ) : <span className="text-gray-400 italic">No contact</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      )}
      {/* PROJECT DETAILS TAB */}
      {activeTab === 'Project Details' && (
        <div className="space-y-6">
          {/* Upload Section */}
          <div className="flex gap-4 items-center bg-gray-50 p-4 rounded-xl border border-gray-100">
            <label className={`btn-primary ${pdUploading ? 'opacity-70 cursor-not-allowed' : 'cursor-pointer'}`}>
              {pdUploading ? <Loader2 size={15} className="animate-spin" /> : <Upload size={15} />}
              {pdUploading ? 'Uploading...' : 'Upload Excel File'}
              <input type="file" className="hidden" accept=".xlsx,.xls" onChange={handlePdImport} disabled={pdUploading} />
            </label>
            {pdUploadResult && (
              <div className={`text-sm flex-1 ${pdUploadResult.startsWith('Error') ? 'text-red-600' : 'text-green-600'}`}>
                {pdUploadResult}
              </div>
            )}
          </div>

          {pdFiles.length === 0 ? (
            <div className="card p-16 text-center">
              <Database size={40} className="text-gray-200 mx-auto mb-4" />
              <p className="font-medium text-gray-700">No project files uploaded yet</p>
              <p className="text-sm text-gray-400 mt-1">Upload an Excel file to get started</p>
            </div>
          ) : (
            <>
              {/* File Tabs */}
              <div className="flex gap-2 overflow-x-auto pb-2">
                {pdFiles.map(f => (
                  <button 
                    key={f.source_file}
                    onClick={() => handlePdFileClick(f)}
                    title={f.source_file}
                    className={`flex items-center gap-2 px-4 py-2 rounded-full text-sm whitespace-nowrap transition-colors ${pdActiveFile === f.source_file ? 'bg-gray-900 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'}`}
                  >
                    <span className="max-w-[150px] truncate">{f.source_file}</span>
                    <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${pdActiveFile === f.source_file ? 'bg-gray-700 text-gray-300' : 'bg-gray-200 text-gray-500'}`}>
                      {f.total_rows}
                    </span>
                  </button>
                ))}
              </div>

              {/* Sheet Tabs */}
              {pdActiveFile && pdFiles.find(f => f.source_file === pdActiveFile)?.sheets.length > 1 && (
                <div className="flex gap-2 overflow-x-auto pb-2 ml-4 border-l-2 border-gray-200 pl-4">
                  {pdFiles.find(f => f.source_file === pdActiveFile)?.sheets.map(s => (
                    <button 
                      key={s.source_sheet}
                      onClick={() => handlePdSheetClick(s.source_sheet)}
                      title={s.source_sheet}
                      className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm whitespace-nowrap transition-colors ${pdActiveSheet === s.source_sheet ? 'bg-brand-50 text-brand-700 border border-brand-200' : 'bg-white text-gray-500 border border-gray-200 hover:bg-gray-50'}`}
                    >
                      <span className="max-w-[200px] truncate">{s.source_sheet}</span>
                      <span className="text-[10px] bg-gray-100 px-1.5 py-0.5 rounded-full text-gray-500">
                        {s.row_count}
                      </span>
                    </button>
                  ))}
                </div>
              )}

              {/* Filter Bar */}
              <div className="flex gap-3 flex-wrap items-center bg-white p-3 rounded-xl border border-gray-200">
                <div className="relative flex-1 min-w-[200px] max-w-xs">
                  <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
                  <input className="input w-full pl-9 text-sm" placeholder="Search this sheet..."
                    value={pdSearch} onChange={e => { setPdSearch(e.target.value); setPdPage(1); }} />
                </div>
                
                {pdFilters.map(filter => (
                  <div key={filter.key} className="flex items-center gap-2">
                    <span className="text-xs font-medium text-gray-500">{filter.display_label}:</span>
                    <select 
                      className="input text-sm py-1.5 min-w-[120px] max-w-[200px]" 
                      value={pdActiveFilterValues[`filter_${filter.key}`] || ''} 
                      onChange={e => {
                        setPdActiveFilterValues(prev => ({...prev, [`filter_${filter.key}`]: e.target.value}));
                        setPdPage(1);
                      }}
                    >
                      <option value="">All</option>
                      {filter.values.map(v => <option key={v} value={v}>{v}</option>)}
                    </select>
                  </div>
                ))}
              </div>

              {/* Data Table */}
              <div className="card overflow-x-auto min-h-[300px] relative">
                {pdLoadingRecords && (
                  <div className="absolute inset-0 bg-white/50 flex items-center justify-center z-10">
                    <Loader2 size={30} className="animate-spin text-brand-500" />
                  </div>
                )}
                
                {pdRecords?.records?.length === 0 ? (
                  <div className="p-12 text-center text-gray-500">No records found matching criteria</div>
                ) : (
                  <table className="w-full text-sm text-left">
                    <thead className="bg-gray-50 border-b border-gray-100 text-xs text-gray-500 uppercase tracking-wider">
                      <tr>
                        {pdRecords?.columns?.map(c => (
                          <th key={c.key} className="px-4 py-3 font-medium whitespace-nowrap">{c.display_label}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                      {pdRecords?.records?.map(r => (
                        <tr key={r.id} className="hover:bg-gray-50">
                          {pdRecords?.columns?.map(c => (
                            <td key={c.key} className="px-4 py-3 whitespace-nowrap">
                              {r.data[c.key] ? <span className="text-gray-900">{r.data[c.key]}</span> : <span className="text-gray-300">—</span>}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>

              {/* Pagination */}
              {pdRecordsTotal > 0 && (
                <div className="flex items-center justify-between text-sm text-gray-500 px-2">
                  <div>Showing page {pdPage} of {Math.ceil(pdRecordsTotal / 50)}</div>
                  <div className="flex gap-2">
                    <button 
                      disabled={pdPage <= 1} 
                      onClick={() => setPdPage(p => p - 1)}
                      className="px-3 py-1.5 rounded-lg border border-gray-200 hover:bg-gray-50 disabled:opacity-50"
                    >Previous</button>
                    <button 
                      disabled={pdPage >= Math.ceil(pdRecordsTotal / 50)} 
                      onClick={() => setPdPage(p => p + 1)}
                      className="px-3 py-1.5 rounded-lg border border-gray-200 hover:bg-gray-50 disabled:opacity-50"
                    >Next</button>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      )}
      </div>
    </div>
  )
}
