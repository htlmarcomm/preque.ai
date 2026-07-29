import { useState, useEffect } from 'react'
import { Plus, Search, Edit2, Trash2, Upload, Briefcase, Loader2 } from 'lucide-react'
import { projectHistoryApi } from '../lib/api'

export default function ProjectHistory() {
  const [projects, setProjects] = useState([])
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [adding, setAdding] = useState(false)
  const [importing, setImporting] = useState(false)
  const [editingId, setEditingId] = useState(null)
  
  const defaultProj = {
    project_name: '', location: '', area_sqft: '',
    start_date: '', completion_date: '', status: 'completed',
    client_name: '', notes: ''
  }
  const [newProj, setNewProj] = useState(defaultProj)
  const [editVal, setEditVal] = useState({})

  const load = async () => {
    setLoading(true)
    try {
      const res = await projectHistoryApi.getAll()
      setProjects(res.data)
    } catch (err) {
      console.error(err)
    }
    setLoading(false)
  }

  useEffect(() => { load() }, [])

  const startEdit = (proj) => {
    setEditingId(proj.id)
    setEditVal({
      project_name: proj.project_name, location: proj.location || '',
      area_sqft: proj.area_sqft || '', start_date: proj.start_date || '',
      completion_date: proj.completion_date || '', status: proj.status || 'completed',
      client_name: proj.client_name || '', notes: proj.notes || ''
    })
  }

  const saveEdit = async (id) => {
    await projectHistoryApi.update(id, editVal)
    setEditingId(null)
    load()
  }

  const deleteProj = async (id) => {
    if (!window.confirm('Delete this project record?')) return
    await projectHistoryApi.delete(id)
    load()
  }

  const addProj = async () => {
    if (!newProj.project_name) return
    await projectHistoryApi.create(newProj)
    setAdding(false)
    setNewProj(defaultProj)
    load()
  }

  const handleImport = async (e) => {
    const file = e.target.files[0]
    if (!file) return
    setImporting(true)
    try {
      const res = await projectHistoryApi.importCsv(file)
      alert(`Success! Imported ${res.data.imported} projects.`)
      await load()
    } catch (err) {
      alert('Error importing file: ' + err.message)
    } finally {
      setImporting(false)
      e.target.value = ''
    }
  }

  const filtered = projects.filter(p =>
    !search || 
    p.project_name?.toLowerCase().includes(search.toLowerCase()) ||
    p.client_name?.toLowerCase().includes(search.toLowerCase()) ||
    p.location?.toLowerCase().includes(search.toLowerCase())
  )

  return (
    <div className="p-8 max-w-6xl mx-auto">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">Project History</h1>
          <p className="text-sm text-gray-500 mt-1">{projects.length} project records available for automation</p>
        </div>
        <div className="flex gap-2">
          <label className={`btn-secondary ${importing ? 'opacity-70 cursor-not-allowed' : 'cursor-pointer'}`}>
            {importing ? <Loader2 size={15} className="animate-spin" /> : <Upload size={15} />}
            {importing ? 'Importing...' : 'Import CSV'}
            <input type="file" className="hidden" accept=".csv" onChange={handleImport} disabled={importing} />
          </label>
          <button onClick={() => setAdding(true)} className="btn-primary">
            <Plus size={15} />Add Project
          </button>
        </div>
      </div>

      <div className="flex gap-3 mb-6">
        <div className="relative flex-1 max-w-md">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input className="input w-full pl-9 text-sm" placeholder="Search by project name, client, or location…"
            value={search} onChange={e => setSearch(e.target.value)} />
        </div>
      </div>

      {adding && (
        <div className="card p-5 mb-6 bg-brand-50/50">
          <h3 className="font-medium text-sm text-gray-900 mb-4">New Project</h3>
          <div className="grid grid-cols-2 gap-4">
            <div><label className="block text-xs text-gray-500 mb-1">Project Name *</label><input className="input w-full text-sm" value={newProj.project_name} onChange={e => setNewProj(p => ({ ...p, project_name: e.target.value }))} /></div>
            <div><label className="block text-xs text-gray-500 mb-1">Client Name</label><input className="input w-full text-sm" value={newProj.client_name} onChange={e => setNewProj(p => ({ ...p, client_name: e.target.value }))} /></div>
            <div><label className="block text-xs text-gray-500 mb-1">Location</label><input className="input w-full text-sm" value={newProj.location} onChange={e => setNewProj(p => ({ ...p, location: e.target.value }))} /></div>
            <div><label className="block text-xs text-gray-500 mb-1">Area (Sqft)</label><input className="input w-full text-sm" value={newProj.area_sqft} onChange={e => setNewProj(p => ({ ...p, area_sqft: e.target.value }))} /></div>
            <div><label className="block text-xs text-gray-500 mb-1">Start Date</label><input className="input w-full text-sm" value={newProj.start_date} onChange={e => setNewProj(p => ({ ...p, start_date: e.target.value }))} /></div>
            <div><label className="block text-xs text-gray-500 mb-1">Completion Date</label><input className="input w-full text-sm" value={newProj.completion_date} onChange={e => setNewProj(p => ({ ...p, completion_date: e.target.value }))} /></div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">Status</label>
              <select className="input w-full text-sm" value={newProj.status} onChange={e => setNewProj(p => ({ ...p, status: e.target.value }))}>
                <option value="completed">Completed</option>
                <option value="ongoing">Ongoing</option>
              </select>
            </div>
            <div><label className="block text-xs text-gray-500 mb-1">Notes</label><input className="input w-full text-sm" value={newProj.notes} onChange={e => setNewProj(p => ({ ...p, notes: e.target.value }))} /></div>
          </div>
          <div className="flex gap-2 justify-end mt-4">
            <button onClick={() => setAdding(false)} className="btn-secondary">Cancel</button>
            <button onClick={addProj} disabled={!newProj.project_name} className="btn-primary">Save Project</button>
          </div>
        </div>
      )}

      <div className="card overflow-hidden">
        <table className="w-full text-left text-sm">
          <thead className="bg-gray-50 border-b border-gray-100 text-xs font-medium text-gray-500 uppercase tracking-wider">
            <tr>
              <th className="px-4 py-3 w-1/4">Project & Client</th>
              <th className="px-4 py-3 w-1/4">Details</th>
              <th className="px-4 py-3 w-1/4">Timeline</th>
              <th className="px-4 py-3">Status & Notes</th>
              <th className="px-4 py-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {loading ? (
              <tr><td colSpan="5" className="px-4 py-8 text-center text-gray-400">Loading...</td></tr>
            ) : filtered.length === 0 ? (
              <tr><td colSpan="5" className="px-4 py-8 text-center text-gray-400">No project records found.</td></tr>
            ) : (
              filtered.map(proj => (
                <tr key={proj.id} className="hover:bg-gray-50/50 transition-colors group">
                  {editingId === proj.id ? (
                    <td colSpan="5" className="px-4 py-3 bg-brand-50/30">
                      <div className="grid grid-cols-4 gap-3 mb-3">
                        <input className="input text-sm font-medium" value={editVal.project_name} onChange={e => setEditVal(p => ({ ...p, project_name: e.target.value }))} placeholder="Project Name" />
                        <input className="input text-sm" value={editVal.client_name} onChange={e => setEditVal(p => ({ ...p, client_name: e.target.value }))} placeholder="Client Name" />
                        <input className="input text-sm" value={editVal.location} onChange={e => setEditVal(p => ({ ...p, location: e.target.value }))} placeholder="Location" />
                        <input className="input text-sm" value={editVal.area_sqft} onChange={e => setEditVal(p => ({ ...p, area_sqft: e.target.value }))} placeholder="Area (Sqft)" />
                        <input className="input text-sm" value={editVal.start_date} onChange={e => setEditVal(p => ({ ...p, start_date: e.target.value }))} placeholder="Start Date" />
                        <input className="input text-sm" value={editVal.completion_date} onChange={e => setEditVal(p => ({ ...p, completion_date: e.target.value }))} placeholder="Completion Date" />
                        <select className="input text-sm" value={editVal.status} onChange={e => setEditVal(p => ({ ...p, status: e.target.value }))}>
                          <option value="completed">Completed</option>
                          <option value="ongoing">Ongoing</option>
                        </select>
                        <input className="input text-sm" value={editVal.notes} onChange={e => setEditVal(p => ({ ...p, notes: e.target.value }))} placeholder="Notes" />
                      </div>
                      <div className="flex gap-2 justify-end">
                        <button onClick={() => setEditingId(null)} className="btn-secondary text-xs py-1 px-3">Cancel</button>
                        <button onClick={() => saveEdit(proj.id)} className="btn-primary text-xs py-1 px-3">Save</button>
                      </div>
                    </td>
                  ) : (
                    <>
                      <td className="px-4 py-3 align-top">
                        <div className="font-medium text-gray-900">{proj.project_name}</div>
                        {proj.client_name && <div className="text-xs text-gray-500 mt-1">{proj.client_name}</div>}
                      </td>
                      <td className="px-4 py-3 align-top">
                        {proj.location && <div className="text-gray-800 text-xs">📍 {proj.location}</div>}
                        {proj.area_sqft && <div className="text-xs text-gray-600 mt-1">📐 {proj.area_sqft}</div>}
                        {!proj.location && !proj.area_sqft && <span className="text-gray-400 italic">--</span>}
                      </td>
                      <td className="px-4 py-3 align-top">
                        {proj.start_date && <div className="text-gray-800 text-xs">Started: {proj.start_date}</div>}
                        {proj.completion_date && <div className="text-xs text-gray-600 mt-1">Completed: {proj.completion_date}</div>}
                        {!proj.start_date && !proj.completion_date && <span className="text-gray-400 italic">--</span>}
                      </td>
                      <td className="px-4 py-3 align-top">
                        <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                          proj.status === 'completed' ? 'bg-green-100 text-green-800' : 'bg-blue-100 text-blue-800'
                        }`}>
                          {proj.status === 'completed' ? 'Completed' : 'Ongoing'}
                        </span>
                        {proj.notes && <div className="text-xs text-gray-500 mt-2 whitespace-pre-line">{proj.notes}</div>}
                      </td>
                      <td className="px-4 py-3 align-top text-right">
                        <div className="flex items-center justify-end gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                          <button onClick={() => startEdit(proj)} className="p-1.5 text-gray-400 hover:text-brand-600 rounded-md hover:bg-brand-50 transition-colors" title="Edit">
                            <Edit2 size={14} />
                          </button>
                          <button onClick={() => deleteProj(proj.id)} className="p-1.5 text-gray-400 hover:text-red-600 rounded-md hover:bg-red-50 transition-colors" title="Delete">
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
