import React, { createContext, useContext, useState, useRef } from 'react'

const FillFormContext = createContext()

export function FillFormProvider({ children }) {
  const [step, setStep] = useState(0)
  const [mode, setMode] = useState(null)
  const [clientName, setClientName] = useState('')
  const [file, setFile] = useState(null)
  const [dragOver, setDragOver] = useState(false)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [humanAnswers, setHumanAnswers] = useState({})
  const [savingField, setSavingField] = useState(null)
  const [savedFields, setSavedFields] = useState(new Set())
  const [copied, setCopied] = useState(false)
  const [error, setError] = useState(null)
  
  // Picker state
  const [pendingTables, setPendingTables] = useState([])
  const [activePendingIndex, setActivePendingIndex] = useState(null)
  const [pickerCandidates, setPickerCandidates] = useState([])
  const [pickerSelectedIds, setPickerSelectedIds] = useState(new Set())
  const [pickerSearch, setPickerSearch] = useState('')
  const [pickerLoading, setPickerLoading] = useState(false)
  const [pickerSubmitting, setPickerSubmitting] = useState(false)
  
  // PR variables for project_reference table types
  const [refRegionFilter, setRefRegionFilter] = useState('')
  const [refStatusFilter, setRefStatusFilter] = useState('')
  
  // PD variables for project_details table types
  const [pdFiles, setPdFiles] = useState([])
  const [pdActiveFile, setPdActiveFile] = useState(null)
  const [pdActiveSheet, setPdActiveSheet] = useState(null)
  const [pdRecords, setPdRecords] = useState(null)
  const [pdRecordsTotal, setPdRecordsTotal] = useState(0)
  const [pdPage, setPdPage] = useState(1)
  const [pdSearch, setPdSearch] = useState('')
  const [pdFilters, setPdFilters] = useState([])
  const [pdActiveFilterValues, setPdActiveFilterValues] = useState({})
  const [pdLoadingRecords, setPdLoadingRecords] = useState(false)
  
  // Preview state
  const [preview, setPreview] = useState(null)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [activeSheet, setActiveSheet] = useState(null)
  const [previewSearch, setPreviewSearch] = useState('')
  const [copiedCell, setCopiedCell] = useState(null)
  
  // Export state
  const [exporting, setExporting] = useState(false)
  const [googleSheetLink, setGoogleSheetLink] = useState(null)
  
  const reset = () => {
    setStep(0); setMode(null); setClientName(''); setFile(null)
    setResult(null); setHumanAnswers({}); setSavedFields(new Set()); setError(null)
    setPreview(null); setPreviewLoading(false); setActiveSheet(null)
    setExporting(false); setGoogleSheetLink(null)
    setPendingTables([]); setActivePendingIndex(null); setPickerCandidates([]); setPickerSelectedIds(new Set()); setPickerSearch('')
    setRefRegionFilter(''); setRefStatusFilter('');
    setPdFiles([]); setPdActiveFile(null); setPdActiveSheet(null); setPdRecords(null); setPdRecordsTotal(0); setPdPage(1); setPdSearch(''); setPdFilters([]); setPdActiveFilterValues({});
  }

  const value = {
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
  }

  return (
    <FillFormContext.Provider value={value}>
      {children}
    </FillFormContext.Provider>
  )
}

export function useFillForm() {
  const context = useContext(FillFormContext)
  if (!context) {
    throw new Error('useFillForm must be used within a FillFormProvider')
  }
  return context
}
