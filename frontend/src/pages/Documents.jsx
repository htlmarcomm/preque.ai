import { useState, useEffect } from 'react'
import { Plus, Upload, Trash2, Download, ExternalLink, Search, FolderOpen, Loader2, Tag, Database } from 'lucide-react'
import { docsApi } from '../lib/api'

export default function Documents() {
  const [docs, setDocs] = useState([])
  const [types, setTypes] = useState([])
  const [activeType, setActiveType] = useState(null)
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [seeding, setSeeding] = useState(false)
  const [adding, setAdding] = useState(false)
  const [newDoc, setNewDoc] = useState({ name: '', doc_type: '', sharepoint_link: '', tags: '', file: null })
  const [downloadingId, setDownloadingId] = useState(null)

  const load = async () => {
    setLoading(true)
    const [d, t] = await Promise.all([docsApi.list(activeType), docsApi.getTypes()])
    setDocs(d.data.documents || [])
    setTypes(t.data.types || [])
    setLoading(false)
  }

  useEffect(() => { load() }, [activeType])

  const seed = async () => {
    setSeeding(true)
    await docsApi.seed()
    await load()
    setSeeding(false)
  }

  const addDoc = async () => {
    if (!newDoc.name || !newDoc.doc_type) return
    await docsApi.upload(newDoc.name, newDoc.doc_type, newDoc.file, newDoc.sharepoint_link, newDoc.tags)
    setAdding(false)
    setNewDoc({ name: '', doc_type: '', sharepoint_link: '', tags: '', file: null })
    load()
  }

  const deleteDoc = async (id) => {
    if (!confirm('Remove this document?')) return
    await docsApi.delete(id)
    load()
  }

  // A plain <a href download> can't carry the X-API-Key header the backend
  // now requires, so this goes through the authenticated client instead.
  const downloadDoc = async (doc) => {
    setDownloadingId(doc.id)
    try {
      await docsApi.download(doc.id, doc.name)
    } catch (e) {
      console.error(e)
    } finally {
      setDownloadingId(null)
    }
  }

  const filtered = docs.filter(d =>
    !search || d.name?.toLowerCase().includes(search.toLowerCase()) ||
    d.doc_type?.toLowerCase().includes(search.toLowerCase())
  )

  const grouped = filtered.reduce((acc, d) => {
    const t = d.doc_type || 'Other'
    if (!acc[t]) acc[t] = []
    acc[t].push(d)
    return acc
  }, {})

  return (
    <div className="p-8 max-w-5xl">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">Documents</h1>
          <p className="text-sm text-gray-500 mt-1">{docs.length} documents · Linked to your company data and form outputs</p>
        </div>
        <div className="flex gap-2">
          {docs.length === 0 && (
            <button onClick={seed} disabled={seeding} className="btn-primary">
              {seeding ? <Loader2 size={15} className="animate-spin" /> : <Database size={15} />}
              Load Document List
            </button>
          )}
          <button onClick={() => setAdding(true)} className="btn-primary"><Plus size={15} />Add Document</button>
        </div>
      </div>

      <div className="flex gap-3 mb-6">
        <div className="relative flex-1 max-w-xs">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input className="input w-full pl-9 text-sm" placeholder="Search documents…"
            value={search} onChange={e => setSearch(e.target.value)} />
        </div>
      </div>

      {adding && (
        <div className="card p-5 mb-6">
          <h3 className="font-medium text-sm text-gray-900 mb-4">Add Document</h3>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-gray-500 mb-1">Document name</label>
              <input className="input w-full text-sm" placeholder="e.g. GST Certificate FY24"
                value={newDoc.name} onChange={e => setNewDoc(p => ({ ...p, name: e.target.value }))} />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">Document type</label>
              <select className="input w-full text-sm" value={newDoc.doc_type}
                onChange={e => setNewDoc(p => ({ ...p, doc_type: e.target.value }))}>
                <option value="">Select type…</option>
                {types.map(t => <option key={t}>{t}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">SharePoint / Drive link</label>
              <input className="input w-full text-sm" placeholder="https://…"
                value={newDoc.sharepoint_link} onChange={e => setNewDoc(p => ({ ...p, sharepoint_link: e.target.value }))} />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">Tags (comma-separated)</label>
              <input className="input w-full text-sm" placeholder="gst, tax, legal"
                value={newDoc.tags} onChange={e => setNewDoc(p => ({ ...p, tags: e.target.value }))} />
            </div>
            <div className="col-span-2">
              <label className="block text-xs text-gray-500 mb-1">Upload file (optional)</label>
              <input type="file" className="text-sm text-gray-600"
                onChange={e => setNewDoc(p => ({ ...p, file: e.target.files[0] }))} />
            </div>
          </div>
          <div className="flex gap-2 mt-4">
            <button onClick={addDoc} className="btn-primary">Save Document</button>
            <button onClick={() => setAdding(false)} className="btn-secondary">Cancel</button>
          </div>
        </div>
      )}

      {loading ? (
        <div className="text-center py-20"><Loader2 size={28} className="animate-spin text-brand-500 mx-auto" /></div>
      ) : docs.length === 0 ? (
        <div className="card p-16 text-center">
          <FolderOpen size={40} className="text-gray-200 mx-auto mb-4" />
          <p className="font-medium text-gray-700">No documents yet</p>
          <p className="text-sm text-gray-400 mt-1">Click "Load Document List" to seed the default HTL document list, then add SharePoint links or upload files</p>
        </div>
      ) : (
        <div className="space-y-4">
          {Object.entries(grouped).map(([type, typeDocs]) => (
            <div key={type} className="card overflow-hidden">
              <div className="px-4 py-3 bg-gray-50 border-b border-gray-100 flex items-center justify-between">
                <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">{type}</h3>
                <span className="badge-gray">{typeDocs.length}</span>
              </div>
              <div className="divide-y divide-gray-50">
                {typeDocs.map(doc => (
                  <div key={doc.id} className="px-4 py-3 flex items-center justify-between gap-4 group">
                    <div className="flex items-center gap-3 min-w-0">
                      <div className={`w-2 h-2 rounded-full shrink-0 ${doc.has_file ? 'bg-green-400' : doc.sharepoint_link ? 'bg-blue-400' : 'bg-gray-200'}`} />
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-gray-900">{doc.name}</p>
                        {doc.tags?.length > 0 && (
                          <div className="flex gap-1 mt-0.5 flex-wrap">
                            {doc.tags.map(tag => (
                              <span key={tag} className="badge-gray text-[10px] py-0 px-1.5">{tag}</span>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      {doc.has_file && (
                        <button onClick={() => downloadDoc(doc)} disabled={downloadingId === doc.id}
                          className="btn-ghost text-xs py-1 px-2">
                          {downloadingId === doc.id ? <Loader2 size={13} className="animate-spin" /> : <Download size={13} />}Download
                        </button>
                      )}
                      {doc.sharepoint_link && (
                        <a href={doc.sharepoint_link} target="_blank" rel="noopener noreferrer"
                          className="btn-ghost text-xs py-1 px-2">
                          <ExternalLink size={13} />SharePoint
                        </a>
                      )}
                      {!doc.has_file && !doc.sharepoint_link && (
                        <span className="badge-gray">No file</span>
                      )}
                      <button onClick={() => deleteDoc(doc.id)}
                        className="p-1 text-gray-300 hover:text-red-500 opacity-0 group-hover:opacity-100 transition-all rounded">
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
