import { useState, useRef, useEffect } from 'react'
import { Upload, Image, FileSpreadsheet, Sparkles, CheckCircle2, AlertCircle, Download, Copy, FileCheck, ChevronRight, X, Save, Loader2, RotateCcw, FileText, Search, Eye, Check, Database } from 'lucide-react'
import { agentApi, formsApi, docsApi, projectPickerApi, projectDataApi } from '../lib/api'
import { useFillForm } from '../contexts/FillFormContext'

const BASE_STEPS = ['Upload', 'Processing', 'Review', 'Output']

export default function FillForm() {
  const {
    step, setStep,
    mode, setMode,
    clientName, setClientName,
    file, setFile,
    dragOver, setDragOver,
    loading, setLoading,
    result, setResult,
    humanAnswers, setHumanAnswers,
    savingField, setSavingField,
    savedFields, setSavedFields,
    copied, setCopied,
    error, setError,
    pendingTables, setPendingTables,
    activePendingIndex, setActivePendingIndex,
    pickerCandidates, setPickerCandidates,
    pickerSelectedIds, setPickerSelectedIds,
    pickerSearch, setPickerSearch,
    pickerLoading, setPickerLoading,
    pickerSubmitting, setPickerSubmitting,
    refRegionFilter, setRefRegionFilter,
    refStatusFilter, setRefStatusFilter,
    pdFiles, setPdFiles,
    pdActiveFile, setPdActiveFile,
    pdActiveSheet, setPdActiveSheet,
    pdRecords, setPdRecords,
    pdRecordsTotal, setPdRecordsTotal,
    pdPage, setPdPage,
    pdSearch, setPdSearch,
    pdFilters, setPdFilters,
    pdActiveFilterValues, setPdActiveFilterValues,
    pdLoadingRecords, setPdLoadingRecords,
    preview, setPreview,
    previewLoading, setPreviewLoading,
    activeSheet, setActiveSheet,
    previewSearch, setPreviewSearch,
    copiedCell, setCopiedCell,
    exporting, setExporting,
    googleSheetLink, setGoogleSheetLink,
    reset
  } = useFillForm()

  const fileRef = useRef()
  const [downloading, setDownloading] = useState(false)
  const [downloadingDocId, setDownloadingDocId] = useState(null)

  // Downloads have to go through the authenticated axios client and get
  // saved as a blob -- a plain <a href download> can't carry the X-API-Key
  // header the backend now requires on every /api/* request.
  const downloadFilledForm = async () => {
    if (!result?.form_id) return
    setDownloading(true)
    try {
      await formsApi.download(result.form_id, `${result.client_name}.xlsx`)
    } catch (e) {
      setError(e.response?.data?.detail || e.message || 'Download failed.')
    } finally {
      setDownloading(false)
    }
  }

  const downloadDoc = async (doc) => {
    setDownloadingDocId(doc.id)
    try {
      await docsApi.download(doc.id, doc.name)
    } catch (e) {
      setError(e.response?.data?.detail || e.message || `Could not download "${doc.name}".`)
    } finally {
      setDownloadingDocId(null)
    }
  }

  const handleFile = (f) => {
    setFile(f)
    setError(null)
  }

  const handleDrop = (e) => {
    e.preventDefault(); setDragOver(false)
    const f = e.dataTransfer.files[0]
    if (f) handleFile(f)
  }

  const openPreview = async () => {
    if (!result?.form_id) return
    setPreviewLoading(true)
    setPreview(null)
    setActiveSheet(null)
    setPreviewSearch('')
    setCopiedCell(null)
    
    try {
      const res = await formsApi.preview(result.form_id)
      const data = res.data
      setPreview({ type: 'excel', ...data })
      const firstSheet = Object.keys(data.sheets || {})[0]
      setActiveSheet(firstSheet)
    } catch (e) {
      setError(e.response?.data?.detail || e.message || 'Preview not available yet.')
    } finally {
      setPreviewLoading(false)
    }
  }

  const exportToGoogle = async () => {
    if (!result?.form_id) return
    // SECURITY: sharing with a specific person's Google account (rather than
    // "anyone with the link") keeps GSTIN/PAN/financial data in this export
    // from being viewable by anyone who ever gets hold of the link. Cancel
    // leaves recipientEmail null, which the backend still accepts -- falling
    // back to the old world-readable link -- so this never blocks the export
    // outright, just nudges toward the safer path.
    const recipientEmail = window.prompt(
      "Share with a specific Google account? Enter their email (recommended), or leave blank / Cancel to create a link anyone can view."
    )
    setExporting(true)
    setError(null)
    try {
      const res = await formsApi.exportToGoogleSheets(result.form_id, recipientEmail || undefined)
      setGoogleSheetLink(res.data.link)
    } catch (e) {
      const detail = e.response?.data?.detail
      setError(typeof detail === 'string' ? detail : e.message || 'Export failed')
    } finally {
      setExporting(false)
    }
  }

  const copyCell = (value) => {
    navigator.clipboard.writeText(value)
    setCopiedCell(value)
    setTimeout(() => setCopiedCell(null), 1500)
  }

  const copyRow = (row) => {
    navigator.clipboard.writeText(row.join('\t'))
    setCopiedCell('__row__')
    setTimeout(() => setCopiedCell(null), 1500)
  }

  const currentSheetData = preview && activeSheet ? preview.sheets[activeSheet] : null
  const filteredRows = currentSheetData
    ? currentSheetData.rows.filter(row => {
        if (previewSearch && !row.some(cell => String(cell || '').toLowerCase().includes(previewSearch.toLowerCase()))) {
          return false
        }
        return true
      })
    : []
    
  const getColumnLetter = (colIndex) => {
    let letter = '';
    let temp = colIndex;
    while (temp >= 0) {
      letter = String.fromCharCode((temp % 26) + 65) + letter;
      temp = Math.floor(temp / 26) - 1;
    }
    return letter;
  };
  
  useEffect(() => {
    if (activePendingIndex === null || !pendingTables[activePendingIndex]) return
    const current = pendingTables[activePendingIndex]
    
    const fetchCandidates = async () => {
      if (current.table_type !== 'project_reference') return // handled by pd logic now
      setPickerLoading(true)
      try {
        const res = await projectPickerApi.getReferences({ 
          search: pickerSearch,
          region: refRegionFilter || undefined,
          status: refStatusFilter || undefined
        })
        setPickerCandidates(res.data)
      } catch (e) {
        console.error(e)
      } finally {
        setPickerLoading(false)
      }
    }
    
    if (current.table_type === 'project_reference') {
      const debounceTimer = setTimeout(fetchCandidates, 400)
      return () => clearTimeout(debounceTimer)
    } else {
      // It's project_details, load files
      const loadFiles = async () => {
        setPickerLoading(true)
        try {
          const res = await projectDataApi.getFiles()
          setPdFiles(res.data)
          if (!pdActiveFile && res.data.length > 0) {
            setPdActiveFile(res.data[0].source_file)
            if (res.data[0].sheets.length > 0) {
              setPdActiveSheet(res.data[0].sheets[0].source_sheet)
            }
          }
        } catch (e) {
          console.error(e)
        } finally {
          setPickerLoading(false)
        }
      }
      loadFiles()
    }
  }, [activePendingIndex, pickerSearch, refRegionFilter, refStatusFilter, pendingTables])
  
  // Load sheet records for project_details
  useEffect(() => {
    if (activePendingIndex === null || !pendingTables[activePendingIndex]) return
    const current = pendingTables[activePendingIndex]
    if (current.table_type !== 'project_details') return
    if (!pdActiveFile || !pdActiveSheet) return

    const loadSheetData = async () => {
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
    
    const timeoutId = setTimeout(() => {
      loadSheetData()
    }, 400)
    return () => clearTimeout(timeoutId)
  }, [activePendingIndex, pdActiveFile, pdActiveSheet, pdPage, pdSearch, pdActiveFilterValues, pendingTables])
  
  useEffect(() => {
    setPickerSelectedIds(new Set())
  }, [activePendingIndex])
  
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

  const handleProcess = async () => {
    if (!file || !clientName.trim()) return
    setLoading(true); setError(null)
    setStep(1)
    try {
      const res = mode === 'excel'
        ? await agentApi.processExcel(clientName, file)
        : await agentApi.processImage(clientName, file)
      const newResult = res.data
      setResult(newResult)
      if (newResult.pending_project_tables?.length > 0) {
        setPendingTables(newResult.pending_project_tables)
        setActivePendingIndex(0)
        setStep(2) // Jump to Project Tables step
      } else {
        setStep(pendingTables.length > 0 ? 3 : 2) // Jump to Review step
      }
    } catch (e) {
      let msg
      if (e.code === 'ECONNABORTED' || e.message?.includes('timeout')) {
        msg = 'Request timed out. The form may have too many sheets. Please try again.'
      } else if (!e.response) {
        msg = 'Cannot connect to the backend server. Make sure the backend is running on port 8000.'
      } else {
        const detail = e.response?.data?.detail
        msg = typeof detail === 'string'
          ? detail
          : detail?.msg || JSON.stringify(detail) || e.message || 'Processing failed.'
      }
      setError(msg)
      console.error('Full error:', e.response?.data || e.message)
      setStep(0)
    } finally {
      setLoading(false)
    }
  }

  const saveAnswer = async (fieldLabel) => {
    const answer = humanAnswers[fieldLabel]
    if (!answer?.trim()) return
    setSavingField(fieldLabel)
    try {
      await agentApi.saveLearnedAnswer(fieldLabel, answer, result?.form_id, true)
      setSavedFields(prev => new Set([...prev, fieldLabel]))
    } catch (e) {
      setError(e.response?.data?.detail || e.message || `Could not save "${fieldLabel}".`)
    } finally { setSavingField(null) }
  }

  const saveAllAnswers = async () => {
    const toSave = Object.entries(humanAnswers).filter(([label, answer]) => answer?.trim() && !savedFields.has(label))
    try {
      await Promise.all(toSave.map(([label, answer]) => agentApi.saveLearnedAnswer(label, answer, result?.form_id, true)))
      setSavedFields(new Set(Object.keys(humanAnswers)))
      setStep(pendingTables.length > 0 ? 4 : 3)
    } catch (e) {
      setError(e.response?.data?.detail || e.message || 'Could not save one or more answers. Please try again.')
    }
  }

  const copyAllToClipboard = () => {
    if (!result) return
    const allData = { ...result.filled_data, ...humanAnswers }
    const text = Object.entries(allData)
      .map(([k, v]) => `${k}: ${v}`)
      .join('\n')
    navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }
  
  const handleConfirmPicker = async () => {
    const current = pendingTables[activePendingIndex]
    if (!current || pickerSelectedIds.size === 0) return
    
    setPickerSubmitting(true)
    try {
      const res = await projectPickerApi.fillProjectTable(
        result.form_id,
        current.sheet_name,
        current.table_type,
        Array.from(pickerSelectedIds),
        current.subheading
      )
      
      const freshResult = await formsApi.get(result.form_id)
      setResult(prev => ({ ...prev, filled_data: freshResult.data.filled_data }))
      
      if (activePendingIndex === pendingTables.length - 1) {
        setStep(pendingTables.length > 0 ? 3 : 2) // To Review step
      } else {
        setActivePendingIndex(prev => prev + 1)
      }
    } catch (e) {
      setError(e.response?.data?.detail || e.message || 'Failed to fill table.')
    } finally {
      setPickerSubmitting(false)
    }
  }

  const handleSkipPicker = () => {
    if (activePendingIndex === pendingTables.length - 1) {
      setStep(pendingTables.length > 0 ? 3 : 2)
    } else {
      setActivePendingIndex(prev => prev + 1)
    }
  }

  const isOutputStep = step === (pendingTables.length > 0 ? 4 : 3) && !!result

  return (
    <div className="p-8 max-w-5xl">
      {/* Header */}
      <div className="mb-8 flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-3">
            <div className="w-8 h-8 bg-red-600 rounded-lg flex items-center justify-center shadow-sm">
              <FileText size={16} className="text-white" />
            </div>
            <span className="font-bold text-lg text-gray-900">PreQue AI</span>
          </div>
          <h1 className="text-2xl font-semibold text-gray-900">Fill Pre-Qualification Form</h1>
          <p className="text-gray-500 text-sm mt-1">Upload a form or portal screenshot — AI fills it from your company database</p>
        </div>
        {isOutputStep && (
          <button onClick={reset} className="btn-secondary shrink-0"><RotateCcw size={16} />Fill a new form</button>
        )}
      </div>

      {/* Step indicator */}
      {(() => {
        const currentSteps = pendingTables.length > 0 
          ? ['Upload', 'Processing', 'Project Tables', 'Review', 'Output']
          : BASE_STEPS
          
        return (
          <div className="flex items-center gap-0 mb-8">
            {currentSteps.map((s, i) => (
              <div key={s} className="flex items-center">
                <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${
                  i < step ? 'bg-green-50 text-green-700' :
                  i === step ? 'bg-red-50 text-red-700' :
                  'text-gray-400'
                }`}>
                  {i < step ? <CheckCircle2 size={13} /> : <span className="w-4 h-4 rounded-full border flex items-center justify-center text-[10px] border-current">{i+1}</span>}
                  {s}
                </div>
                {i < currentSteps.length - 1 && <ChevronRight size={14} className="text-gray-300 mx-1" />}
              </div>
            ))}
          </div>
        )
      })()}

      {error && (
        <div className="mb-6 p-4 bg-red-50 border border-red-100 rounded-xl flex items-start gap-3">
          <AlertCircle size={18} className="text-red-500 mt-0.5 shrink-0" />
          <div>
            <p className="text-sm font-medium text-red-800">Error</p>
            <p className="text-sm text-red-600 mt-0.5">{error}</p>
          </div>
          <button onClick={() => setError(null)} className="ml-auto text-red-400 hover:text-red-600"><X size={16} /></button>
        </div>
      )}

      {/* STEP 0: Upload */}
      {step === 0 && (
        <div className="space-y-6">
          {/* Client name */}
          <div className="card p-6">
            <label className="block text-sm font-medium text-gray-700 mb-2">Client / Project Name</label>
            <input className="input w-full max-w-sm" placeholder="e.g. Hinduja House — JLL" value={clientName}
              onChange={e => setClientName(e.target.value)} />
            <p className="text-xs text-gray-400 mt-1.5">Used to identify this form in history</p>
          </div>

          {/* Mode selection */}
          <div className="grid grid-cols-2 gap-4">
            {[
              { id: 'excel', icon: FileSpreadsheet, title: 'Excel Form', desc: 'Upload .xlsx / .xls preque form received from client', color: 'text-green-600 bg-green-50' },
              { id: 'image', icon: Image, title: 'Portal Screenshot', desc: 'Upload screenshot of client\'s online pre-qual portal', color: 'text-purple-600 bg-purple-50' },
            ].map(({ id, icon: Icon, title, desc, color }) => (
              <button key={id} onClick={() => { setMode(id); setFile(null) }}
                className={`card p-5 text-left transition-all hover:shadow-md ${mode === id ? 'ring-2 ring-brand-500' : ''}`}>
                <div className={`w-10 h-10 rounded-xl ${color} flex items-center justify-center mb-3`}>
                  <Icon size={22} />
                </div>
                <p className="font-medium text-gray-900 text-sm">{title}</p>
                <p className="text-gray-500 text-xs mt-1">{desc}</p>
              </button>
            ))}
          </div>

          {/* File drop zone */}
          {mode && (
            <div
              className={`card p-8 border-2 border-dashed transition-colors text-center cursor-pointer ${
                dragOver ? 'border-brand-400 bg-brand-50' : 'border-gray-200 hover:border-brand-300'
              }`}
              onClick={() => fileRef.current?.click()}
              onDragOver={e => { e.preventDefault(); setDragOver(true) }}
              onDragLeave={() => setDragOver(false)}
              onDrop={handleDrop}
            >
              <input ref={fileRef} type="file" className="hidden"
                accept={mode === 'excel' ? '.xlsx,.xls' : 'image/*'}
                onChange={e => handleFile(e.target.files[0])} />
              {file ? (
                <div className="flex items-center justify-center gap-3">
                  <FileCheck size={24} className="text-brand-600" />
                  <div className="text-left">
                    <p className="font-medium text-gray-900 text-sm">{file.name}</p>
                    <p className="text-xs text-gray-400">{(file.size / 1024).toFixed(1)} KB</p>
                  </div>
                  <button onClick={e => { e.stopPropagation(); setFile(null) }}
                    className="ml-4 text-gray-400 hover:text-gray-600"><X size={16} /></button>
                </div>
              ) : (
                <>
                  <Upload size={32} className="text-gray-300 mx-auto mb-3" />
                  <p className="text-sm font-medium text-gray-700">Drop your {mode === 'excel' ? 'Excel form' : 'screenshot'} here</p>
                  <p className="text-xs text-gray-400 mt-1">or click to browse · {mode === 'excel' ? '.xlsx / .xls' : 'PNG / JPG / WEBP'}</p>
                </>
              )}
            </div>
          )}

          <button
            onClick={handleProcess}
            disabled={!file || !clientName.trim() || !mode}
            className="btn-primary"
          >
            <Sparkles size={16} />
            Process with AI
          </button>
        </div>
      )}

      {/* STEP 1: Processing */}
      {step === 1 && (
        <div className="card p-16 text-center">
          <Loader2 size={40} className="text-brand-600 mx-auto mb-4 animate-spin" />
          <p className="font-medium text-gray-900">AI is analysing your form…</p>
          <p className="text-sm text-gray-400 mt-1">
            {mode === 'image' ? 'Extracting fields from screenshot, then matching against company database' : 'Reading form structure and filling from company database'}
          </p>
        </div>
      )}
      
      {/* STEP 2 (Conditional): Project Tables */}
      {pendingTables.length > 0 && step === 2 && activePendingIndex !== null && pendingTables[activePendingIndex] && (
        <div className="space-y-6">
          {(() => {
            const current = pendingTables[activePendingIndex]
            const effCap = (current.max_rows && current.available_row_count) 
              ? Math.min(current.max_rows, current.available_row_count)
              : (current.max_rows || current.available_row_count)
              
            const isAtCap = effCap && pickerSelectedIds.size >= effCap
            
            return (
              <div className="card">
                <div className="p-5 border-b border-gray-100 flex items-start justify-between">
                  <div>
                    <h2 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
                      <FileSpreadsheet size={18} className="text-brand-600" />
                      Select projects for: <span className="text-brand-700">{current.sheet_name}</span>
                    </h2>
                    {current.subheading && (
                      <p className="text-sm font-medium text-brand-700 mt-2 bg-brand-50 inline-block px-2 py-0.5 rounded border border-brand-100">
                        Section: "{current.subheading}"
                      </p>
                    )}
                    <p className="text-sm text-gray-500 mt-2">
                      {current.table_type === 'project_reference' 
                        ? 'This table asks for client contact details from past projects.'
                        : 'This table asks for project name, location, area, and value details.'}
                    </p>
                    <p className="text-xs text-gray-400 mt-1.5 font-medium">Table {activePendingIndex + 1} of {pendingTables.length}</p>
                  </div>
                  {effCap && (
                    <div className={`text-right ${isAtCap ? 'text-amber-600' : 'text-gray-500'}`}>
                      <p className="text-sm font-bold">{pickerSelectedIds.size} / {current.max_rows || current.available_row_count} selected</p>
                      {current.max_rows && current.available_row_count && current.available_row_count < current.max_rows && (
                         <p className="text-xs">({current.available_row_count} rows available in the form)</p>
                      )}
                    </div>
                  )}
                </div>
                
                
                <div className="p-5 space-y-4">
                  {current.table_type === 'project_reference' ? (
                    <div className="space-y-4">
                      <div className="flex gap-2 flex-wrap items-center bg-gray-50 p-2 rounded-lg border border-gray-200">
                        <div className="relative flex-1 min-w-[180px] max-w-xs">
                          <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400" />
                          <input 
                            type="text" 
                            value={pickerSearch}
                            onChange={e => setPickerSearch(e.target.value)}
                            placeholder="Search references…" 
                            className="input w-full pl-8 py-1.5 text-xs"
                          />
                        </div>
                        
                        <div className="flex items-center gap-1.5">
                          <span className="text-[11px] font-medium text-gray-500">Region:</span>
                          <select 
                            className="input text-xs py-1 min-w-[100px] max-w-[160px]" 
                            value={refRegionFilter} 
                            onChange={e => setRefRegionFilter(e.target.value)}
                          >
                            <option value="">All Regions</option>
                            {[...new Set(pickerCandidates.map(c => c.region).filter(Boolean))].sort().map(v => (
                              <option key={v} value={v}>{v}</option>
                            ))}
                          </select>
                        </div>

                        <div className="flex items-center gap-1.5">
                          <span className="text-[11px] font-medium text-gray-500">Status:</span>
                          <select 
                            className="input text-xs py-1 min-w-[100px] max-w-[160px]" 
                            value={refStatusFilter} 
                            onChange={e => setRefStatusFilter(e.target.value)}
                          >
                            <option value="">All Statuses</option>
                            {[...new Set(pickerCandidates.map(c => c.status).filter(Boolean))].sort().map(v => (
                              <option key={v} value={v}>{v}</option>
                            ))}
                          </select>
                        </div>
                        
                        {isAtCap && <span className="ml-auto text-xs font-semibold text-amber-600 bg-amber-50 px-2 py-1 rounded">Maximum reached</span>}
                      </div>
                      
                      {pickerLoading ? (
                        <div className="py-12 flex justify-center"><Loader2 size={30} className="animate-spin text-brand-500" /></div>
                      ) : (
                        <div className="border border-gray-200 rounded-xl overflow-x-auto min-h-[250px] max-h-[400px] relative">
                          {pickerCandidates.length === 0 ? (
                            <div className="p-12 text-center text-gray-500 text-sm">No project references found.</div>
                          ) : (
                            <table className="w-full text-sm text-left">
                              <thead className="bg-gray-50 border-b border-gray-200 text-[11px] text-gray-500 uppercase tracking-wider sticky top-0 z-20">
                                <tr>
                                  <th className="px-4 py-2 font-medium w-12">Select</th>
                                  <th className="px-4 py-2 font-medium whitespace-nowrap">Project Name</th>
                                  <th className="px-4 py-2 font-medium whitespace-nowrap">Client</th>
                                  <th className="px-4 py-2 font-medium whitespace-nowrap">Location</th>
                                  <th className="px-4 py-2 font-medium whitespace-nowrap">Consultant</th>
                                  <th className="px-4 py-2 font-medium whitespace-nowrap">PMC</th>
                                  <th className="px-4 py-2 font-medium whitespace-nowrap">Sector</th>
                                  <th className="px-4 py-2 font-medium whitespace-nowrap">Type</th>
                                  <th className="px-4 py-2 font-medium whitespace-nowrap">Value</th>
                                  <th className="px-4 py-2 font-medium whitespace-nowrap">Status</th>
                                  <th className="px-4 py-2 font-medium whitespace-nowrap">Timeline</th>
                                  <th className="px-4 py-2 font-medium whitespace-nowrap">Rep Contact</th>
                                </tr>
                              </thead>
                              <tbody className="divide-y divide-gray-100 bg-white">
                                {pickerCandidates.map(p => {
                                  const isSelected = pickerSelectedIds.has(p.id)
                                  const disabled = !isSelected && isAtCap
                                  
                                  return (
                                    <tr key={p.id} 
                                      className={`transition-colors ${disabled ? 'opacity-50' : 'hover:bg-gray-50 cursor-pointer'} ${isSelected ? 'bg-brand-50 hover:bg-brand-50' : ''}`}
                                      onClick={() => {
                                        if (disabled) return
                                        setPickerSelectedIds(prev => {
                                          const next = new Set(prev)
                                          if (next.has(p.id)) next.delete(p.id)
                                          else next.add(p.id)
                                          return next
                                        })
                                      }}
                                    >
                                      <td className="px-4 py-2.5">
                                        <input 
                                          type="checkbox" 
                                          checked={isSelected}
                                          readOnly
                                          disabled={disabled}
                                          className="w-4 h-4 text-brand-600 rounded border-gray-300"
                                          onClick={e => e.stopPropagation()}
                                          onChange={() => {
                                            if (disabled) return
                                            setPickerSelectedIds(prev => {
                                              const next = new Set(prev)
                                              if (next.has(p.id)) next.delete(p.id)
                                              else next.add(p.id)
                                              return next
                                            })
                                          }}
                                        />
                                      </td>
                                      <td className="px-4 py-2.5 font-medium text-gray-900 max-w-[200px] truncate" title={p.project_name}>
                                        {p.project_name}
                                        <div className="text-[9px] text-gray-400 font-normal mt-0.5">{p.region}</div>
                                      </td>
                                      <td className="px-4 py-2.5 text-gray-700 max-w-[120px] truncate" title={p.client_name}>{p.client_name || '-'}</td>
                                      <td className="px-4 py-2.5 text-gray-500 whitespace-nowrap text-xs">{p.location || '-'}</td>
                                      <td className="px-4 py-2.5 text-gray-500 whitespace-nowrap text-xs">{p.consultant || '-'}</td>
                                      <td className="px-4 py-2.5 text-gray-500 whitespace-nowrap text-xs">{p.pmc || '-'}</td>
                                      <td className="px-4 py-2.5 text-gray-500 whitespace-nowrap text-xs">{p.project_sector || '-'}</td>
                                      <td className="px-4 py-2.5 text-gray-500 max-w-[120px] truncate text-xs" title={p.project_type}>{p.project_type || '-'}</td>
                                      <td className="px-4 py-2.5 text-gray-900 whitespace-nowrap text-xs">{p.project_value || '-'}</td>
                                      <td className="px-4 py-2.5 whitespace-nowrap">
                                        {p.status && (
                                          <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${
                                            p.status.toLowerCase().includes('completed') ? 'bg-green-100 text-green-700' :
                                            p.status.toLowerCase().includes('ongoing') ? 'bg-blue-100 text-blue-700' :
                                            'bg-gray-100 text-gray-700'
                                          }`}>
                                            {p.status}
                                          </span>
                                        )}
                                      </td>
                                      <td className="px-4 py-2.5 text-gray-500 whitespace-nowrap text-[10px]">
                                        {p.start_date || p.end_date ? (
                                          <>
                                            <div>{p.start_date || '-'}</div>
                                            <div className="text-gray-400">to {p.end_date || '-'}</div>
                                          </>
                                        ) : '-'}
                                      </td>
                                      <td className="px-4 py-2.5 text-[10px] whitespace-nowrap">
                                        {p.client_rep_name ? (
                                          <div>
                                            <div className="font-medium text-gray-900">{p.client_rep_name}</div>
                                            {p.client_rep_designation && <div className="text-gray-500">{p.client_rep_designation}</div>}
                                            {p.client_rep_phone && <div className="text-brand-600 mt-0.5">{p.client_rep_phone}</div>}
                                          </div>
                                        ) : <span className="text-gray-400 italic">No contact</span>}
                                      </td>
                                    </tr>
                                  )
                                })}
                              </tbody>
                            </table>
                          )}
                        </div>
                      )}
                    </div>
                  ) : (
                    // project_details table UI
                    <div className="space-y-4">
                      {pdFiles.length === 0 ? (
                        <div className="card p-12 text-center border-dashed bg-gray-50/50">
                          <Database size={30} className="text-gray-300 mx-auto mb-3" />
                          <p className="font-medium text-gray-700">No project files uploaded yet</p>
                          <p className="text-sm text-gray-500 mt-1">Please go to the Company Database page and upload project excel files first.</p>
                        </div>
                      ) : (
                        <>
                          <div className="flex items-center justify-between">
                             <div className="flex items-center gap-4">
                              <span className="text-sm font-medium text-gray-700">Source:</span>
                              <div className="flex gap-2 overflow-x-auto pb-1 max-w-[500px]">
                                {pdFiles.map(f => (
                                  <button 
                                    key={f.source_file}
                                    onClick={() => handlePdFileClick(f)}
                                    title={f.source_file}
                                    className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-xs whitespace-nowrap transition-colors ${pdActiveFile === f.source_file ? 'bg-gray-900 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'}`}
                                  >
                                    <span className="max-w-[120px] truncate">{f.source_file}</span>
                                    <span className={`text-[9px] px-1.5 py-0.5 rounded-full ${pdActiveFile === f.source_file ? 'bg-gray-700 text-gray-300' : 'bg-gray-200 text-gray-500'}`}>
                                      {f.total_rows}
                                    </span>
                                  </button>
                                ))}
                              </div>
                            </div>
                            {isAtCap && <span className="text-xs font-semibold text-amber-600 bg-amber-50 px-2 py-1 rounded">Maximum reached</span>}
                          </div>

                          {pdActiveFile && pdFiles.find(f => f.source_file === pdActiveFile)?.sheets.length > 1 && (
                            <div className="flex gap-2 overflow-x-auto pb-1 pl-12">
                              {pdFiles.find(f => f.source_file === pdActiveFile)?.sheets.map(s => (
                                <button 
                                  key={s.source_sheet}
                                  onClick={() => handlePdSheetClick(s.source_sheet)}
                                  title={s.source_sheet}
                                  className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs whitespace-nowrap transition-colors ${pdActiveSheet === s.source_sheet ? 'bg-brand-50 text-brand-700 border border-brand-200' : 'bg-white text-gray-500 border border-gray-200 hover:bg-gray-50'}`}
                                >
                                  <span className="max-w-[150px] truncate">{s.source_sheet}</span>
                                  <span className="text-[9px] bg-gray-100 px-1.5 py-0.5 rounded-full text-gray-500">
                                    {s.row_count}
                                  </span>
                                </button>
                              ))}
                            </div>
                          )}

                          <div className="flex gap-2 flex-wrap items-center bg-gray-50 p-2 rounded-lg border border-gray-200">
                            <div className="relative flex-1 min-w-[180px] max-w-xs">
                              <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400" />
                              <input className="input w-full pl-8 py-1.5 text-xs" placeholder="Search this sheet..."
                                value={pdSearch} onChange={e => { setPdSearch(e.target.value); setPdPage(1); }} />
                            </div>
                            
                            {pdFilters.map(filter => (
                              <div key={filter.key} className="flex items-center gap-1.5">
                                <span className="text-[11px] font-medium text-gray-500">{filter.display_label}:</span>
                                <select 
                                  className="input text-xs py-1 min-w-[100px] max-w-[160px]" 
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

                          <div className="border border-gray-200 rounded-xl overflow-x-auto min-h-[250px] max-h-[400px] relative">
                            {pdLoadingRecords && (
                              <div className="absolute inset-0 bg-white/50 flex items-center justify-center z-10">
                                <Loader2 size={30} className="animate-spin text-brand-500" />
                              </div>
                            )}
                            
                            {pdRecords?.records?.length === 0 ? (
                              <div className="p-12 text-center text-gray-500 text-sm">No records found</div>
                            ) : (
                              <table className="w-full text-sm text-left">
                                <thead className="bg-gray-50 border-b border-gray-200 text-[11px] text-gray-500 uppercase tracking-wider sticky top-0 z-20">
                                  <tr>
                                    <th className="px-4 py-2 font-medium w-12">Select</th>
                                    {pdRecords?.columns?.map(c => (
                                      <th key={c.key} className="px-4 py-2 font-medium whitespace-nowrap">{c.display_label}</th>
                                    ))}
                                  </tr>
                                </thead>
                                <tbody className="divide-y divide-gray-100 bg-white">
                                  {pdRecords?.records?.map(r => {
                                    const isSelected = pickerSelectedIds.has(r.id)
                                    const disabled = !isSelected && isAtCap
                                    return (
                                      <tr key={r.id} 
                                        className={`transition-colors ${disabled ? 'opacity-50' : 'hover:bg-gray-50 cursor-pointer'} ${isSelected ? 'bg-brand-50 hover:bg-brand-50' : ''}`}
                                        onClick={() => {
                                          if (disabled) return
                                          setPickerSelectedIds(prev => {
                                            const next = new Set(prev)
                                            if (next.has(r.id)) next.delete(r.id)
                                            else next.add(r.id)
                                            return next
                                          })
                                        }}
                                      >
                                        <td className="px-4 py-2.5">
                                          <input 
                                            type="checkbox" 
                                            checked={isSelected}
                                            readOnly
                                            disabled={disabled}
                                            className="w-4 h-4 text-brand-600 rounded border-gray-300"
                                            onClick={e => e.stopPropagation()} // Let the row click handle it
                                            onChange={() => {
                                              if (disabled) return
                                              setPickerSelectedIds(prev => {
                                                const next = new Set(prev)
                                                if (next.has(r.id)) next.delete(r.id)
                                                else next.add(r.id)
                                                return next
                                              })
                                            }}
                                          />
                                        </td>
                                        {pdRecords?.columns?.map(c => (
                                          <td key={c.key} className="px-4 py-2.5 whitespace-nowrap text-xs">
                                            {r.data[c.key] ? <span className="text-gray-900">{r.data[c.key]}</span> : <span className="text-gray-300">—</span>}
                                          </td>
                                        ))}
                                      </tr>
                                    )
                                  })}
                                </tbody>
                              </table>
                            )}
                          </div>

                          {pdRecordsTotal > 0 && (
                            <div className="flex items-center justify-between text-xs text-gray-500 px-1">
                              <div>Showing page {pdPage} of {Math.ceil(pdRecordsTotal / 50)}</div>
                              <div className="flex gap-2">
                                <button 
                                  disabled={pdPage <= 1} 
                                  onClick={() => setPdPage(p => p - 1)}
                                  className="px-3 py-1.5 rounded bg-gray-50 border border-gray-200 hover:bg-gray-100 disabled:opacity-50 transition-colors"
                                >Previous</button>
                                <button 
                                  disabled={pdPage >= Math.ceil(pdRecordsTotal / 50)} 
                                  onClick={() => setPdPage(p => p + 1)}
                                  className="px-3 py-1.5 rounded bg-gray-50 border border-gray-200 hover:bg-gray-100 disabled:opacity-50 transition-colors"
                                >Next</button>
                              </div>
                            </div>
                          )}
                        </>
                      )}
                    </div>
                  )}
                  
                  <div className="flex gap-3 pt-4 border-t border-gray-100">
                    <button 
                      onClick={handleConfirmPicker} 
                      disabled={pickerSelectedIds.size === 0 || pickerSubmitting} 
                      className="btn-primary"
                    >
                      {pickerSubmitting ? <Loader2 size={16} className="animate-spin" /> : <Check size={16} />}
                      Confirm selection
                    </button>
                    <button 
                      onClick={handleSkipPicker} 
                      disabled={pickerSubmitting}
                      className="btn-secondary"
                    >
                      Skip this table
                    </button>
                  </div>
                </div>
              </div>
            )
          })()}
        </div>
      )}

      {/* STEP 3: Review (previously step 2) */}
      {step === (pendingTables.length > 0 ? 3 : 2) && result && (
        <div className="space-y-6">
          {/* Stats bar */}
          <div className="grid grid-cols-4 gap-4">
            {[
              { label: 'Total fields', value: result.total_fields, color: 'text-gray-900' },
              { label: 'Auto-filled', value: result.auto_filled, color: 'text-green-700' },
              { label: 'Need input', value: result.unknown_count, color: result.unknown_count > 0 ? 'text-amber-700' : 'text-green-700' },
              { label: 'Documents', value: result.doc_checklist?.length || 0, color: 'text-blue-700' },
            ].map(({ label, value, color }) => (
              <div key={label} className="card p-4 text-center">
                <p className={`text-2xl font-semibold ${color}`}>{value}</p>
                <p className="text-xs text-gray-400 mt-0.5">{label}</p>
              </div>
            ))}
          </div>

          {/* Auto-filled answers */}
          <div className="card">
            <div className="p-4 border-b border-gray-100 flex items-center justify-between">
              <h3 className="font-medium text-gray-900 flex items-center gap-2">
                <CheckCircle2 size={17} className="text-green-600" />
                Auto-filled ({result.auto_filled} fields)
              </h3>
              <span className="badge-green">Ready</span>
            </div>
            <div className="divide-y divide-gray-50 p-4">
              {Object.entries(result.filled_data || {}).map(([key, data], idx) => {
                const label = typeof data === 'object' && data !== null ? data.label : key;
                const value = typeof data === 'object' && data !== null ? data.value : data;
                return (
                  <div key={idx} className="flex flex-col py-2 border-b last:border-0 border-gray-100/50">
                    <span className="text-xs text-gray-400 font-medium">{label}</span>
                    <span className="text-sm text-gray-800 font-semibold mt-0.5">{value}</span>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Unknown fields */}
          {result.unknown_fields?.length > 0 && (
            <div className="card">
              <div className="p-4 border-b border-gray-100 flex items-center justify-between">
                <h3 className="font-medium text-gray-900 flex items-center gap-2">
                  <AlertCircle size={17} className="text-amber-500" />
                  Needs your input ({result.unknown_fields.length} fields)
                </h3>
                <span className="badge-amber">Action required</span>
              </div>
              <div className="space-y-4 p-4">
                {result.unknown_fields.map((f, idx) => {
                  const fieldLabel = typeof f === 'object' ? f.label : f;
                  const fieldKey = typeof f === 'object' && f.cell ? f.cell : fieldLabel;
                  const suggested = typeof f === 'object' ? f.suggested_answer : '';
                  const source = typeof f === 'object' ? f.suggested_source : '';

                  return (
                    <div key={idx} className="flex flex-col p-4 bg-gray-50 border border-gray-100 rounded-xl relative group">
                      <div className="flex justify-between items-start mb-2">
                        <span className="text-sm font-semibold text-gray-800">{fieldLabel}</span>
                        {suggested && (
                          <span className="text-[10px] font-bold tracking-wider text-purple-600 uppercase bg-purple-100 px-2 py-0.5 rounded-full flex items-center gap-1">
                            <Sparkles size={10} /> AI Suggestion
                          </span>
                        )}
                      </div>
                      
                      {suggested && (
                        <div className="text-xs text-gray-500 mb-3 flex items-center gap-1.5">
                          <CheckCircle2 size={12} className="text-green-500" />
                          Found in: <span className="font-medium text-gray-700">{source}</span>
                        </div>
                      )}

                      <div className="relative">
                        <input
                          type="text"
                          className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all bg-white"
                          placeholder={suggested ? `Accept suggestion or type manually...` : `Type manual answer...`}
                          value={humanAnswers[fieldKey] || ''}
                          onChange={(e) => setHumanAnswers(prev => ({ ...prev, [fieldKey]: e.target.value }))}
                        />
                        {suggested && (
                          <button 
                            onClick={() => setHumanAnswers(prev => ({ ...prev, [fieldKey]: suggested }))}
                            className="absolute right-2 top-1.5 px-2 py-1 bg-purple-100 hover:bg-purple-200 text-purple-700 text-xs font-medium rounded-md transition-colors"
                          >
                            Use Suggestion
                          </button>
                        )}
                      </div>
                      <div className="mt-3 flex justify-end">
                        <button onClick={() => saveAnswer(fieldLabel)}
                          disabled={!humanAnswers[fieldKey]?.trim() || savingField === fieldLabel}
                          className={`px-3 py-2 rounded-lg text-xs font-medium transition-colors ${
                            savedFields.has(fieldLabel) ? 'bg-green-50 text-green-700' : 'bg-gray-100 hover:bg-brand-50 hover:text-brand-700 text-gray-600'
                          }`}>
                          {savingField === fieldLabel ? <Loader2 size={13} className="animate-spin" /> :
                           savedFields.has(fieldLabel) ? '✓ Saved' : <Save size={13} />}
                        </button>
                      </div>
                      <p className="text-xs text-gray-400 mt-1">Answer will be saved for future forms</p>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          <div className="flex gap-3">
            <button onClick={saveAllAnswers} className="btn-primary">
              <ChevronRight size={16} />
              Continue to Output
            </button>
            {result.unknown_count === 0 && (
              <button onClick={() => setStep(pendingTables.length > 0 ? 4 : 3)} className="btn-primary">
                <ChevronRight size={16} />
                View Output
              </button>
            )}
            <button onClick={reset} className="btn-secondary"><RotateCcw size={16} />Start over</button>
          </div>
        </div>
      )}

      {/* STEP 4: Output (previously step 3) */}
      {step === (pendingTables.length > 0 ? 4 : 3) && result && (
        <div className="space-y-6">
          <div className="p-4 bg-green-50 border border-green-100 rounded-xl flex items-center gap-3">
            <CheckCircle2 size={20} className="text-green-600 shrink-0" />
            <div>
              <p className="font-medium text-green-900 text-sm">Form complete for {result.client_name}</p>
              <p className="text-xs text-green-700 mt-0.5">{result.auto_filled} fields auto-filled · {Object.keys(humanAnswers).length} filled manually</p>
            </div>
          </div>

          {/* For Excel mode — download */}
          {mode === 'excel' && (
            <div className="card p-5">
              <h3 className="font-medium text-gray-900 mb-3 flex items-center gap-2">
                <FileSpreadsheet size={17} className="text-green-600" />
                Download filled Excel form
              </h3>
              <div className="flex flex-col gap-3">
                <div className="flex items-center gap-3">
                  <button onClick={openPreview}
                    className="btn-secondary inline-flex">
                    <Eye size={16} />
                    Preview Excel
                  </button>
                  <button onClick={downloadFilledForm} disabled={downloading}
                    className="btn-primary inline-flex">
                    {downloading ? <Loader2 size={16} className="animate-spin" /> : <Download size={16} />}
                    Download {result.client_name}.xlsx
                  </button>
                  <button onClick={exportToGoogle} disabled={exporting}
                    className="btn-secondary inline-flex text-green-700 bg-green-50 border-green-200 hover:bg-green-100">
                    {exporting ? <Loader2 size={16} className="animate-spin" /> : <FileSpreadsheet size={16} />}
                    Export to Google Sheets
                  </button>
                </div>
                {googleSheetLink && (
                  <div className="p-3 bg-green-50 rounded-lg border border-green-100 flex items-center justify-between">
                    <p className="text-sm text-green-800">✅ Export successful!</p>
                    <a href={googleSheetLink} target="_blank" rel="noreferrer" className="text-sm font-semibold text-green-700 hover:underline">
                      Open in Google Sheets ↗
                    </a>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* For image mode — copy-paste list */}
          <div className="card">
            <div className="p-4 border-b border-gray-100 flex items-center justify-between">
              <h3 className="font-medium text-gray-900 flex items-center gap-2">
                <Copy size={17} className="text-brand-600" />
                {mode === 'image' ? 'Copy-paste list for portal' : 'All filled values'}
              </h3>
              <button onClick={copyAllToClipboard} className="btn-secondary text-xs py-1.5">
                <Copy size={13} />
                {copied ? 'Copied!' : 'Copy all'}
              </button>
            </div>
            <div className="divide-y divide-gray-50">
              {[...Object.entries(result.filled_data || {}), ...Object.entries(humanAnswers)].map(([key, data]) => {
                const label = typeof data === 'object' && data !== null ? data.label : key;
                const value = typeof data === 'object' && data !== null ? data.value : data;
                return (
                  <div key={label} className="px-4 py-2.5 flex items-start justify-between gap-4 group">
                    <p className="text-xs text-gray-400 w-56 shrink-0 pt-0.5">{label}</p>
                    <p className="text-sm font-medium text-gray-900 flex-1">{value}</p>
                    <button onClick={() => { navigator.clipboard.writeText(value) }}
                      className="opacity-0 group-hover:opacity-100 text-gray-300 hover:text-gray-600 transition-opacity">
                      <Copy size={13} />
                    </button>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Document checklist */}
          {result.doc_checklist?.length > 0 && (
            <div className="card">
              <div className="p-4 border-b border-gray-100">
                <h3 className="font-medium text-gray-900 flex items-center gap-2">
                  <FileCheck size={17} className="text-blue-600" />
                  Documents to attach ({result.doc_checklist.length})
                </h3>
                <p className="text-xs text-gray-400 mt-0.5">Upload these when submitting the form</p>
              </div>
              <div className="divide-y divide-gray-50">
                {result.doc_checklist.map((doc, i) => (
                  <div key={i} className="px-4 py-3 flex items-center justify-between gap-3">
                    <div className="flex items-center gap-3">
                      <div className={`w-2 h-2 rounded-full ${doc.has_file ? 'bg-green-400' : 'bg-gray-300'}`} />
                      <div>
                        <p className="text-sm font-medium text-gray-900">{doc.name}</p>
                        <p className="text-xs text-gray-400">{doc.doc_type}</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      {doc.has_file && (
                        <button onClick={() => downloadDoc(doc)} disabled={downloadingDocId === doc.id}
                          className="btn-ghost text-xs py-1 px-2">
                          {downloadingDocId === doc.id ? <Loader2 size={13} className="animate-spin" /> : <Download size={13} />} Download
                        </button>
                      )}
                      {doc.sharepoint_link && (
                        <a href={doc.sharepoint_link} target="_blank" rel="noopener noreferrer"
                          className="btn-ghost text-xs py-1 px-2">
                          SharePoint ↗
                        </a>
                      )}
                      {!doc.has_file && !doc.sharepoint_link && (
                        <span className="badge-gray text-xs">Not uploaded yet</span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Preview Modal */}
      {(preview || previewLoading) && (
        <div className="fixed inset-0 bg-black/55 z-[1000] flex flex-col p-5">
          <div className="bg-white rounded-xl flex-1 flex flex-col overflow-hidden max-h-full">
            {/* Header */}
            <div className="px-5 py-3.5 border-b border-gray-200 flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <FileSpreadsheet size={18} className="text-green-500" />
                <span className="font-bold text-[15px] text-slate-900">{preview?.name || 'Loading…'}</span>
              </div>
              <div className="flex items-center gap-2.5">
                {preview && preview.type === 'excel' && (
                  <div className="relative">
                    <Search size={13} className="absolute left-2 top-1/2 -translate-y-1/2 text-slate-400" />
                    <input
                      value={previewSearch}
                      onChange={e => setPreviewSearch(e.target.value)}
                      placeholder="Search in sheet…"
                      className="py-1.5 pr-2.5 pl-[26px] border border-slate-200 rounded-md text-xs w-48 outline-none"
                    />
                  </div>
                )}
                <button onClick={() => setPreview(null)} className="bg-slate-100 hover:bg-slate-200 rounded-md p-1.5 transition-colors">
                  <X size={16} className="text-slate-500" />
                </button>
              </div>
            </div>

            {previewLoading && (
              <div className="flex-1 flex items-center justify-center text-sm text-slate-400">
                Loading preview…
              </div>
            )}

            {preview && preview.type === 'excel' && (
              <>
                {/* Tabs */}
                <div className="flex border-b border-slate-200 px-5 overflow-x-auto">
                  {Object.keys(preview.sheets).map(sh => (
                    <button key={sh} onClick={() => { setActiveSheet(sh); setPreviewSearch('') }}
                      className={`py-2 px-4 text-xs whitespace-nowrap border-b-2 transition-colors ${
                        activeSheet === sh ? 'font-bold text-red-600 border-red-600' : 'text-slate-500 border-transparent hover:text-slate-700'
                      }`}>
                      {sh}
                    </button>
                  ))}
                </div>

                {/* Info Bar */}
                {currentSheetData && (
                  <div className="px-5 py-1.5 bg-[#f8f9fa] border-b border-[#e2e3e3] text-[12px] text-slate-600 flex items-center justify-between">
                    <div>
                      {filteredRows.length + 1} row{filteredRows.length + 1 !== 1 ? 's' : ''} {previewSearch ? `matching "${previewSearch}"` : ''} — click a cell to copy, click row number to copy row
                    </div>
                    {copiedCell === '__row__' && <span className="text-[#1a73e8] font-medium">Row copied!</span>}
                  </div>
                )}

                {/* Table */}
                <div className="flex-1 overflow-auto">
                  {currentSheetData ? (
                    <div className="relative overflow-auto flex-1 bg-white" style={{ fontFamily: 'Arial, sans-serif', fontSize: '13px' }}>
                      <table className="border-collapse border-0">
                        <thead>
                          <tr className="bg-[#f8f9fa] sticky top-0 z-20">
                            {/* Top Left Corner */}
                            <th className="w-12 min-w-[48px] h-[25px] border-b border-r border-[#c0c0c0] bg-[#f8f9fa] sticky left-0 z-30 select-none"></th>
                            {/* Column Letters */}
                            {currentSheetData.headers.map((_, i) => (
                              <th key={i} className="border-b border-r border-[#c0c0c0] bg-[#f8f9fa] text-[#666] font-normal px-2 h-[25px] min-w-[100px] select-none text-center">
                                {getColumnLetter(i)}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {[currentSheetData.headers, ...filteredRows].map((row, ri) => (
                            <tr key={ri} className="bg-white">
                              {/* Row Number */}
                              <td 
                                onClick={() => copyRow(row)}
                                className="border-b border-r border-[#c0c0c0] bg-[#f8f9fa] sticky left-0 z-10 text-center text-[#666] font-normal select-none w-12 min-w-[48px] h-[21px] cursor-pointer hover:bg-[#e8ecee]"
                              >
                                {ri + 1}
                              </td>
                              {/* Cells */}
                              {row.map((cell, ci) => (
                                <td 
                                  key={ci} 
                                  onClick={() => copyCell(cell)} 
                                  title={cell ? "Click to copy" : ""}
                                  className={`border-b border-r border-[#e2e3e3] px-1.5 py-0 whitespace-nowrap overflow-hidden text-ellipsis max-w-[300px] h-[21px] cursor-cell ${
                                    copiedCell === cell && cell 
                                      ? 'outline outline-2 outline-[#1a73e8] outline-offset-[-2px] z-10 relative bg-[#e8f0fe] text-black' 
                                      : 'text-black'
                                  }`}
                                >
                                  {cell}
                                </td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <div className="p-10 text-center text-slate-400">Select a sheet above</div>
                  )}
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
