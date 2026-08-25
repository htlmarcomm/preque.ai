import { useState, useEffect } from 'react'
import { History, FileSpreadsheet, Image, Download, ChevronRight, CheckCircle2, AlertCircle, Loader2 } from 'lucide-react'
import { formsApi } from '../lib/api'

export default function FormHistory() {
  const [forms, setForms] = useState([])
  const [loading, setLoading] = useState(true)
  const [expanded, setExpanded] = useState(null)
  const [downloadingId, setDownloadingId] = useState(null)

  // A plain <a href download> can't carry the X-API-Key header the backend
  // now requires, so this goes through the authenticated client instead.
  const downloadForm = async (form) => {
    setDownloadingId(form.id)
    try {
      await formsApi.download(form.id, `${form.client_name || 'form'}.xlsx`)
    } catch (e) {
      console.error(e)
    } finally {
      setDownloadingId(null)
    }
  }

  useEffect(() => {
    formsApi.history().then(r => {
      setForms(r.data.forms || [])
      setLoading(false)
    })
  }, [])

  const fmt = (ts) => ts ? new Date(ts).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : ''

  return (
    <div className="p-8 max-w-4xl">
      <div className="mb-8">
        <h1 className="text-2xl font-semibold text-gray-900">Form History</h1>
        <p className="text-sm text-gray-500 mt-1">{forms.length} forms filled · All answers saved for future auto-fill</p>
      </div>

      {loading ? (
        <div className="text-center py-20"><Loader2 size={28} className="animate-spin text-brand-500 mx-auto" /></div>
      ) : forms.length === 0 ? (
        <div className="card p-16 text-center">
          <History size={40} className="text-gray-200 mx-auto mb-4" />
          <p className="font-medium text-gray-700">No forms filled yet</p>
          <p className="text-sm text-gray-400 mt-1">Filled forms will appear here with all their answers and document checklists</p>
        </div>
      ) : (
        <div className="space-y-3">
          {forms.map(form => (
            <div key={form.id} className="card overflow-hidden">
              <button
                onClick={() => setExpanded(expanded === form.id ? null : form.id)}
                className="w-full px-5 py-4 flex items-center gap-4 text-left hover:bg-gray-50 transition-colors"
              >
                <div className={`w-9 h-9 rounded-xl flex items-center justify-center shrink-0 ${
                  form.form_type === 'excel' ? 'bg-green-50' : 'bg-purple-50'
                }`}>
                  {form.form_type === 'excel'
                    ? <FileSpreadsheet size={18} className="text-green-600" />
                    : <Image size={18} className="text-purple-600" />
                  }
                </div>
                <div className="flex-1 min-w-0">
                  <p className="font-medium text-gray-900 text-sm">{form.client_name}</p>
                  <p className="text-xs text-gray-400 mt-0.5">{form.original_filename} · {fmt(form.created_at)}</p>
                </div>
                <div className="flex items-center gap-3 shrink-0">
                  {form.unknown_fields?.length === 0 ? (
                    <span className="badge-green"><CheckCircle2 size={11} />Complete</span>
                  ) : (
                    <span className="badge-amber"><AlertCircle size={11} />{form.unknown_fields?.length} pending</span>
                  )}
                  <span className="badge-blue">{Object.keys(form.filled_data || {}).length} fields</span>
                  <ChevronRight size={15} className={`text-gray-300 transition-transform ${expanded === form.id ? 'rotate-90' : ''}`} />
                </div>
              </button>

              {expanded === form.id && (
                <div className="border-t border-gray-100 bg-gray-50">
                  {/* Filled data */}
                  <div className="p-4">
                    <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">Filled answers</p>
                    <div className="bg-white rounded-lg border border-gray-100 divide-y divide-gray-50">
                      {Object.entries(form.filled_data || {}).map(([key, data]) => {
                        // FIX: excel-mode fills store {label, value} objects here (see
                        // agent.py's process_excel_form / save_learned_answer), not plain
                        // strings -- rendering `data` directly crashed React ("Objects are
                        // not valid as a React child") for any form filled that way.
                        const label = typeof data === 'object' && data !== null ? data.label : key
                        const value = typeof data === 'object' && data !== null ? data.value : data
                        return (
                          <div key={key} className="px-4 py-2 flex gap-4">
                            <span className="text-xs text-gray-400 w-56 shrink-0 pt-0.5">{label}</span>
                            <span className="text-xs font-medium text-gray-800 flex-1">{value}</span>
                          </div>
                        )
                      })}
                    </div>
                  </div>

                  {/* Pending */}
                  {form.unknown_fields?.length > 0 && (
                    <div className="px-4 pb-4">
                      <p className="text-xs font-semibold text-amber-600 uppercase tracking-wider mb-2">Pending fields</p>
                      <div className="flex flex-wrap gap-2">
                        {form.unknown_fields.map((f, i) => {
                          // FIX: entries here are {label, cell, suggested_answer, ...}
                          // objects for excel-mode forms (see agent.py's enriched_unknown),
                          // not plain strings -- same crash as filled_data above, plus using
                          // the object itself as a React `key` produced duplicate-key warnings.
                          const label = typeof f === 'object' && f !== null ? f.label : f
                          return <span key={i} className="badge-amber text-xs">{label}</span>
                        })}
                      </div>
                    </div>
                  )}

                  {/* Doc checklist */}
                  {form.doc_checklist?.length > 0 && (
                    <div className="px-4 pb-4">
                      <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">Document checklist</p>
                      <div className="flex flex-wrap gap-2">
                        {form.doc_checklist.map((doc, i) => (
                          <span key={i} className={`text-xs px-2 py-1 rounded-lg font-medium ${doc.has_file ? 'bg-green-50 text-green-700' : 'bg-gray-100 text-gray-500'}`}>
                            {doc.name}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Download */}
                  {form.form_type === 'excel' && (
                    <div className="px-4 pb-4">
                      <button onClick={() => downloadForm(form)} disabled={downloadingId === form.id} className="btn-secondary text-sm">
                        {downloadingId === form.id ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />}Download filled form
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
