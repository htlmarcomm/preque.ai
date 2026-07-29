import { useState, useEffect } from 'react'
import { Plus, Search, Edit2, Trash2, Upload, Users, Loader2 } from 'lucide-react'
import { subcontractorsApi } from '../lib/api'

export default function SubContractors() {
  const [subcontractors, setSubcontractors] = useState([])
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [adding, setAdding] = useState(false)
  const [importing, setImporting] = useState(false)
  const [editingId, setEditingId] = useState(null)
  
  const defaultSub = {
    name: '', address: '', work_description: '',
    contact_name: '', contact_phone: '', contact_email: '', notes: ''
  }
  const [newSub, setNewSub] = useState(defaultSub)
  const [editVal, setEditVal] = useState({})

  const load = async () => {
    setLoading(true)
    try {
      const res = await subcontractorsApi.getAll()
      setSubcontractors(res.data)
    } catch (err) {
      console.error(err)
    }
    setLoading(false)
  }

  useEffect(() => { load() }, [])

  const startEdit = (sub) => {
    setEditingId(sub.id)
    setEditVal({
      name: sub.name, address: sub.address || '',
      work_description: sub.work_description || '',
      contact_name: sub.contact_name || '', contact_phone: sub.contact_phone || '',
      contact_email: sub.contact_email || '', notes: sub.notes || ''
    })
  }

  const saveEdit = async (id) => {
    await subcontractorsApi.update(id, editVal)
    setEditingId(null)
    load()
  }

  const deleteSub = async (id) => {
    if (!window.confirm('Delete this subcontractor?')) return
    await subcontractorsApi.delete(id)
    load()
  }

  const addSub = async () => {
    if (!newSub.name) return
    await subcontractorsApi.create(newSub)
    setAdding(false)
    setNewSub(defaultSub)
    load()
  }

  const handleImport = async (e) => {
    const file = e.target.files[0]
    if (!file) return
    setImporting(true)
    try {
      const res = await subcontractorsApi.importCsv(file)
      alert(`Success! Imported ${res.data.imported} subcontractors (skipped ${res.data.skipped} duplicates).`)
      await load()
    } catch (err) {
      alert('Error importing file: ' + err.message)
    } finally {
      setImporting(false)
      e.target.value = ''
    }
  }

  const filtered = subcontractors.filter(s =>
    !search || 
    s.name?.toLowerCase().includes(search.toLowerCase()) ||
    s.work_description?.toLowerCase().includes(search.toLowerCase())
  )

  return (
    <div className="p-8 max-w-6xl mx-auto">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">Subcontractors</h1>
          <p className="text-sm text-gray-500 mt-1">{subcontractors.length} registered subcontractors</p>
        </div>
        <div className="flex gap-2">
          <label className={`btn-secondary ${importing ? 'opacity-70 cursor-not-allowed' : 'cursor-pointer'}`}>
            {importing ? <Loader2 size={15} className="animate-spin" /> : <Upload size={15} />}
            {importing ? 'Importing...' : 'Import CSV/Excel'}
            <input type="file" className="hidden" accept=".csv,.xlsx,.xls" onChange={handleImport} disabled={importing} />
          </label>
          <button onClick={() => setAdding(true)} className="btn-primary">
            <Plus size={15} />Add Subcontractor
          </button>
        </div>
      </div>

      <div className="flex gap-3 mb-6">
        <div className="relative flex-1 max-w-md">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input className="input w-full pl-9 text-sm" placeholder="Search by name or work description…"
            value={search} onChange={e => setSearch(e.target.value)} />
        </div>
      </div>

      {adding && (
        <div className="card p-5 mb-6 bg-brand-50/50">
          <h3 className="font-medium text-sm text-gray-900 mb-4">New Subcontractor</h3>
          <div className="grid grid-cols-2 gap-4">
            <div><label className="block text-xs text-gray-500 mb-1">Name *</label><input className="input w-full text-sm" value={newSub.name} onChange={e => setNewSub(p => ({ ...p, name: e.target.value }))} /></div>
            <div><label className="block text-xs text-gray-500 mb-1">Work Description</label><input className="input w-full text-sm" value={newSub.work_description} onChange={e => setNewSub(p => ({ ...p, work_description: e.target.value }))} /></div>
            <div className="col-span-2"><label className="block text-xs text-gray-500 mb-1">Address</label><input className="input w-full text-sm" value={newSub.address} onChange={e => setNewSub(p => ({ ...p, address: e.target.value }))} /></div>
            <div><label className="block text-xs text-gray-500 mb-1">Contact Name</label><input className="input w-full text-sm" value={newSub.contact_name} onChange={e => setNewSub(p => ({ ...p, contact_name: e.target.value }))} /></div>
            <div><label className="block text-xs text-gray-500 mb-1">Contact Phone</label><input className="input w-full text-sm" value={newSub.contact_phone} onChange={e => setNewSub(p => ({ ...p, contact_phone: e.target.value }))} /></div>
            <div><label className="block text-xs text-gray-500 mb-1">Contact Email</label><input className="input w-full text-sm" value={newSub.contact_email} onChange={e => setNewSub(p => ({ ...p, contact_email: e.target.value }))} /></div>
            <div><label className="block text-xs text-gray-500 mb-1">Notes</label><input className="input w-full text-sm" value={newSub.notes} onChange={e => setNewSub(p => ({ ...p, notes: e.target.value }))} /></div>
          </div>
          <div className="flex gap-2 justify-end mt-4">
            <button onClick={() => setAdding(false)} className="btn-secondary">Cancel</button>
            <button onClick={addSub} disabled={!newSub.name} className="btn-primary">Save Subcontractor</button>
          </div>
        </div>
      )}

      <div className="card overflow-hidden">
        <table className="w-full text-left text-sm">
          <thead className="bg-gray-50 border-b border-gray-100 text-xs font-medium text-gray-500 uppercase tracking-wider">
            <tr>
              <th className="px-4 py-3 w-1/4">Name & Address</th>
              <th className="px-4 py-3 w-1/4">Work Description</th>
              <th className="px-4 py-3 w-1/4">Contact Details</th>
              <th className="px-4 py-3">Notes</th>
              <th className="px-4 py-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {loading ? (
              <tr><td colSpan="5" className="px-4 py-8 text-center text-gray-400">Loading...</td></tr>
            ) : filtered.length === 0 ? (
              <tr><td colSpan="5" className="px-4 py-8 text-center text-gray-400">No subcontractors found.</td></tr>
            ) : (
              filtered.map(sub => (
                <tr key={sub.id} className="hover:bg-gray-50/50 transition-colors group">
                  {editingId === sub.id ? (
                    <td colSpan="5" className="px-4 py-3 bg-brand-50/30">
                      <div className="grid grid-cols-4 gap-3 mb-3">
                        <input className="input text-sm font-medium" value={editVal.name} onChange={e => setEditVal(p => ({ ...p, name: e.target.value }))} placeholder="Name" />
                        <input className="input text-sm" value={editVal.work_description} onChange={e => setEditVal(p => ({ ...p, work_description: e.target.value }))} placeholder="Work Description" />
                        <input className="input text-sm" value={editVal.contact_name} onChange={e => setEditVal(p => ({ ...p, contact_name: e.target.value }))} placeholder="Contact Name" />
                        <input className="input text-sm" value={editVal.contact_phone} onChange={e => setEditVal(p => ({ ...p, contact_phone: e.target.value }))} placeholder="Phone" />
                        <input className="input text-sm" value={editVal.contact_email} onChange={e => setEditVal(p => ({ ...p, contact_email: e.target.value }))} placeholder="Email" />
                        <input className="input text-sm col-span-3" value={editVal.address} onChange={e => setEditVal(p => ({ ...p, address: e.target.value }))} placeholder="Address" />
                        <input className="input text-sm col-span-4" value={editVal.notes} onChange={e => setEditVal(p => ({ ...p, notes: e.target.value }))} placeholder="Notes" />
                      </div>
                      <div className="flex gap-2 justify-end">
                        <button onClick={() => setEditingId(null)} className="btn-secondary text-xs py-1 px-3">Cancel</button>
                        <button onClick={() => saveEdit(sub.id)} className="btn-primary text-xs py-1 px-3">Save</button>
                      </div>
                    </td>
                  ) : (
                    <>
                      <td className="px-4 py-3 align-top">
                        <div className="font-medium text-gray-900">{sub.name}</div>
                        {sub.address && <div className="text-xs text-gray-500 mt-1">{sub.address}</div>}
                      </td>
                      <td className="px-4 py-3 align-top text-gray-600">
                        {sub.work_description || <span className="text-gray-400 italic">--</span>}
                      </td>
                      <td className="px-4 py-3 align-top">
                        {sub.contact_name && <div className="font-medium text-gray-800 text-xs">{sub.contact_name}</div>}
                        {sub.contact_phone && <div className="text-xs text-gray-600">{sub.contact_phone}</div>}
                        {sub.contact_email && <div className="text-xs text-gray-600">{sub.contact_email}</div>}
                        {!sub.contact_name && !sub.contact_phone && !sub.contact_email && <span className="text-gray-400 italic">--</span>}
                      </td>
                      <td className="px-4 py-3 align-top text-xs text-gray-500 whitespace-pre-line">
                        {sub.notes || <span className="text-gray-400 italic">--</span>}
                      </td>
                      <td className="px-4 py-3 align-top text-right">
                        <div className="flex items-center justify-end gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                          <button onClick={() => startEdit(sub)} className="p-1.5 text-gray-400 hover:text-brand-600 rounded-md hover:bg-brand-50 transition-colors" title="Edit">
                            <Edit2 size={14} />
                          </button>
                          <button onClick={() => deleteSub(sub.id)} className="p-1.5 text-gray-400 hover:text-red-600 rounded-md hover:bg-red-50 transition-colors" title="Delete">
                            <Trash2 size={14} />
                          </button>
                        </div>
                      </td>
                    </>
                  )}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
