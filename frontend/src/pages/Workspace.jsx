import { useState, useEffect } from 'react'
import { Folder, File, Plus, X, UploadCloud, ChevronRight, Archive, Send, Edit, Clock, HardDrive, CheckCircle2 } from 'lucide-react'
import { workspaceApi, projectFilesApi } from '../lib/api'

export default function Workspace() {
  const [packages, setPackages] = useState([])
  const [files, setFiles] = useState([])
  const [fileSearch, setFileSearch] = useState('')
  const [fileCategory, setFileCategory] = useState('')
  
  const [activePackage, setActivePackage] = useState(null)
  
  const uniqueCategories = Array.from(new Set(files.map(f => f.category))).filter(Boolean)
  const filteredFiles = files.filter(f => {
    const matchesSearch = f.name.toLowerCase().includes(fileSearch.toLowerCase())
    const matchesCategory = fileCategory ? f.category === fileCategory : true
    return matchesSearch && matchesCategory
  })
  
  // Modals
  const [showExportModal, setShowExportModal] = useState(false)
  const [exportTarget, setExportTarget] = useState('')
  const [showImportModal, setShowImportModal] = useState(false)
  const [importData, setImportData] = useState({ name: '', client: '', target_sharepoint_url: '' })
  const [isImporting, setIsImporting] = useState(false)

  useEffect(() => {
    fetchPackages()
    fetchFiles()
  }, [])

  const fetchPackages = async () => {
    const res = await workspaceApi.list()
    setPackages(res.data)
  }

  const fetchFiles = async () => {
    const res = await projectFilesApi.list()
    setFiles(res.data.files || [])
  }

  const startNewPackage = () => {
    setActivePackage({
      name: 'New Client Package',
      client: '',
      target_sharepoint_url: '',
      status: 'Draft',
      data: { folders: [], items: [] }
    })
  }

  const savePackage = async () => {
    if (!activePackage.name || !activePackage.client) {
      alert("Please provide a package name and client.")
      return
    }
    
    const isNew = !activePackage.id
    const res = isNew ? await workspaceApi.create(activePackage) : await workspaceApi.update(activePackage.id, activePackage)

    setActivePackage(res.data)
    fetchPackages()
  }

  const exportPackage = async () => {
    if (!exportTarget) return alert("Please provide a target SharePoint URL")
    
    // First save the package with the new target URL
    const pkgToSave = { ...activePackage, target_sharepoint_url: exportTarget }
    const isNew = !pkgToSave.id
    const saveRes = isNew ? await workspaceApi.create(pkgToSave) : await workspaceApi.update(pkgToSave.id, pkgToSave)
    const savedPkg = saveRes.data

    // Then trigger export
    const exportRes = await workspaceApi.export(savedPkg.id)

    setActivePackage(exportRes.data)
    fetchPackages()
    setShowExportModal(false)
    alert("Package successfully exported to SharePoint!")
  }

  const handleImportSubmit = async () => {
    if (!importData.name || !importData.client || !importData.target_sharepoint_url) {
      return alert("Please fill all fields")
    }
    setIsImporting(true)
    try {
      await workspaceApi.import(importData)
      await fetchPackages()
      setShowImportModal(false)
      setImportData({ name: '', client: '', target_sharepoint_url: '' })
      alert("Successfully imported folder!")
    } catch (e) {
      alert("Import error: " + (e.response?.data?.detail || e.message))
    } finally {
      setIsImporting(false)
    }
  }

  // Drag and Drop handlers
  const handleDragStart = (e, file) => {
    e.dataTransfer.setData('application/json', JSON.stringify({ type: 'file', payload: file }))
  }

  const handleDrop = (e, folderId) => {
    e.preventDefault()
    const dataString = e.dataTransfer.getData('application/json')
    if (!dataString) return
    const data = JSON.parse(dataString)

    if (data.type === 'file') {
      const file = data.payload
      // Check if already in folder
      if (!activePackage.data) activePackage.data = { folders: [], items: [] };
      if (!activePackage.data.items) activePackage.data.items = [];
      const exists = activePackage.data.items.find(i => i.file.id === file.id && i.folderId === folderId)
      if (exists) return

      const newItem = { id: `item_${Date.now()}`, folderId, file }
      setActivePackage(prev => ({
        ...prev,
        data: {
          ...prev.data,
          items: [...prev.data.items, newItem]
        }
      }))
    }
  }

  const handleDragOver = (e) => {
    e.preventDefault()
  }

  const addFolder = () => {
    const folderName = prompt("Folder name:")
    if (!folderName) return
    const newFolder = { id: `folder_${Date.now()}`, name: folderName, parentId: null }
    setActivePackage(prev => ({
      ...prev,
      data: { ...prev.data, folders: [...prev.data.folders, newFolder] }
    }))
  }

  const removeItem = (itemId) => {
    setActivePackage(prev => ({
      ...prev,
      data: { ...prev.data, items: prev.data.items.filter(i => i.id !== itemId) }
    }))
  }
  
  const removeFolder = (folderId) => {
    setActivePackage(prev => ({
      ...prev,
      data: { 
        ...prev.data, 
        folders: prev.data.folders.filter(f => f.id !== folderId),
        items: prev.data.items.filter(i => i.folderId !== folderId)
      }
    }))
  }

  if (activePackage) {
    return (
      <div style={{ padding: 32, height: 'calc(100vh - 64px)', display: 'flex', flexDirection: 'column', boxSizing: 'border-box' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            <button onClick={() => setActivePackage(null)} style={{ background: 'none', border: 'none', color: '#64748b', cursor: 'pointer' }}>
              ← Back to History
            </button>
            <input 
              value={activePackage.name} 
              onChange={e => setActivePackage({...activePackage, name: e.target.value})}
              style={{ fontSize: 24, fontWeight: 'bold', border: 'none', outline: 'none', background: 'transparent' }}
              placeholder="Package Name"
            />
            <span style={{ padding: '4px 8px', borderRadius: 12, fontSize: 12, fontWeight: 600, background: activePackage.status === 'Exported' ? '#dcfce7' : '#f1f5f9', color: activePackage.status === 'Exported' ? '#166534' : '#475569' }}>
              {activePackage.status}
            </span>
          </div>
          <div style={{ display: 'flex', gap: 12 }}>
            <button onClick={savePackage} style={{ padding: '8px 16px', background: '#f1f5f9', color: '#0f172a', border: 'none', borderRadius: 6, cursor: 'pointer', fontWeight: 500, display: 'flex', alignItems: 'center', gap: 8 }}>
              <HardDrive size={16} /> Save Draft
            </button>
            <button onClick={() => { setExportTarget(activePackage.target_sharepoint_url || ''); setShowExportModal(true) }} style={{ padding: '8px 16px', background: '#dc2626', color: 'white', border: 'none', borderRadius: 6, cursor: 'pointer', fontWeight: 500, display: 'flex', alignItems: 'center', gap: 8 }}>
              <Send size={16} /> Export to SharePoint
            </button>
          </div>
        </div>

        <div style={{ display: 'flex', gap: 24, flex: 1, minHeight: 0 }}>
          {/* LEFT: File Cabinet */}
          <div style={{ width: 350, background: 'white', border: '1px solid #e2e8f0', borderRadius: 8, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
            <div style={{ padding: '16px 20px', borderBottom: '1px solid #e2e8f0', background: '#f8fafc' }}>
              <h3 style={{ margin: 0, fontSize: 16, display: 'flex', alignItems: 'center', gap: 8 }}><Archive size={18} /> File Cabinet</h3>
              <p style={{ margin: '4px 0 12px', fontSize: 13, color: '#64748b' }}>Drag files from here into your package</p>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                <input 
                  type="text" 
                  placeholder="Search files..." 
                  value={fileSearch} 
                  onChange={(e) => setFileSearch(e.target.value)} 
                  style={{ width: '100%', padding: '6px 10px', border: '1px solid #cbd5e1', borderRadius: 6, fontSize: 13, boxSizing: 'border-box', outline: 'none' }}
                />
                <select 
                  value={fileCategory} 
                  onChange={(e) => setFileCategory(e.target.value)} 
                  style={{ width: '100%', padding: '6px 10px', border: '1px solid #cbd5e1', borderRadius: 6, fontSize: 13, boxSizing: 'border-box', outline: 'none' }}
                >
                  <option value="">All Categories</option>
                  {uniqueCategories.map(cat => <option key={cat} value={cat}>{cat}</option>)}
                </select>
              </div>
            </div>
            <div style={{ flex: 1, overflowY: 'auto', padding: 12, display: 'flex', flexDirection: 'column', gap: 8 }}>
              {filteredFiles.map(f => (
                <div 
                  key={f.id} 
                  draggable 
                  onDragStart={(e) => handleDragStart(e, f)}
                  style={{ padding: 12, border: '1px solid #e2e8f0', borderRadius: 6, cursor: 'grab', background: 'white', display: 'flex', alignItems: 'center', gap: 12, flexShrink: 0 }}
                >
                  <File size={16} color="#dc2626" />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 13, fontWeight: 500, color: '#0f172a', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{f.name}</div>
                    <div style={{ fontSize: 11, color: '#64748b' }}>{f.category}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* RIGHT: Workspace */}
          <div style={{ flex: 1, background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 8, display: 'flex', flexDirection: 'column' }}>
            <div style={{ padding: '16px 20px', borderBottom: '1px solid #e2e8f0', background: 'white', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <input 
                  value={activePackage.client} 
                  onChange={e => setActivePackage({...activePackage, client: e.target.value})}
                  style={{ fontSize: 14, padding: '4px 8px', border: '1px solid #cbd5e1', borderRadius: 4 }}
                  placeholder="Client Name..."
                />
              </div>
              <button onClick={addFolder} style={{ padding: '6px 12px', background: '#e0e7ff', color: '#4f46e5', border: 'none', borderRadius: 6, cursor: 'pointer', fontWeight: 500, display: 'flex', alignItems: 'center', gap: 6, fontSize: 13 }}>
                <Plus size={14} /> New Folder
              </button>
            </div>
            <div style={{ flex: 1, overflowY: 'auto', padding: 24, display: 'flex', flexDirection: 'column', gap: 16 }}>
              {(activePackage?.data?.folders || []).map(folder => (
                <div 
                  key={folder.id} 
                  onDrop={(e) => handleDrop(e, folder.id)}
                  onDragOver={handleDragOver}
                  style={{ background: 'white', border: '1px solid #cbd5e1', borderRadius: 8, overflow: 'hidden', flexShrink: 0 }}
                >
                  <div style={{ background: '#f1f5f9', padding: '12px 16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '1px solid #e2e8f0' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 600, color: '#0f172a' }}>
                      <Folder size={18} color="#f59e0b" /> {folder.name}
                    </div>
                    <button onClick={() => removeFolder(folder.id)} style={{ background: 'none', border: 'none', color: '#ef4444', cursor: 'pointer' }}><X size={16} /></button>
                  </div>
                  <div style={{ padding: 16, minHeight: 60, display: 'flex', flexDirection: 'column', gap: 8 }}>
                    {(activePackage?.data?.items || []).filter(i => i.folderId === folder.id).map(item => (
                      <div key={item.id} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '8px 12px', background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 6 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13 }}>
                          <File size={14} color="#64748b" /> {item.file.name}
                        </div>
                        <button onClick={() => removeItem(item.id)} style={{ background: 'none', border: 'none', color: '#94a3b8', cursor: 'pointer' }}><X size={14} /></button>
                      </div>
                    ))}
                    {(activePackage?.data?.items || []).filter(i => i.folderId === folder.id).length === 0 && (
                      <div style={{ fontSize: 13, color: '#94a3b8', fontStyle: 'italic', textAlign: 'center', padding: 10 }}>Drag files here</div>
                    )}
                  </div>
                </div>
              ))}
              
              {(activePackage?.data?.folders || []).length === 0 && (
                <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', color: '#64748b' }}>
                  <Folder size={48} color="#cbd5e1" style={{ marginBottom: 16 }} />
                  <p style={{ margin: 0, fontSize: 16, fontWeight: 500 }}>Workspace is empty</p>
                  <p style={{ margin: '8px 0 0', fontSize: 14 }}>Create a new folder to start dragging files.</p>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Export Modal */}
        {showExportModal && (
          <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100 }}>
            <div style={{ background: 'white', padding: 32, borderRadius: 12, width: 500, maxWidth: '90%' }}>
              <h2 style={{ margin: '0 0 16px', fontSize: 20 }}>Export to SharePoint</h2>
              <p style={{ margin: '0 0 24px', color: '#64748b', fontSize: 14, lineHeight: 1.5 }}>
                Enter the target SharePoint Folder URL where this package should be created. The Microsoft Graph API will build the folders and upload the files.
              </p>
              <div style={{ marginBottom: 24 }}>
                <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 8 }}>Target Location URL</label>
                <input 
                  value={exportTarget}
                  onChange={e => setExportTarget(e.target.value)}
                  placeholder="https://company.sharepoint.com/sites/Documents/..."
                  style={{ width: '100%', padding: '10px 12px', border: '1px solid #cbd5e1', borderRadius: 6, boxSizing: 'border-box' }}
                />
              </div>
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 12 }}>
                <button onClick={() => setShowExportModal(false)} style={{ padding: '10px 16px', background: 'white', border: '1px solid #cbd5e1', borderRadius: 6, cursor: 'pointer', fontWeight: 500 }}>Cancel</button>
                <button onClick={exportPackage} style={{ padding: '10px 16px', background: '#dc2626', color: 'white', border: 'none', borderRadius: 6, cursor: 'pointer', fontWeight: 500, display: 'flex', alignItems: 'center', gap: 8 }}>
                  <UploadCloud size={16} /> Execute Export
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    )
  }

  return (
    <div style={{ padding: 32 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 32 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 28, color: '#0f172a', display: 'flex', alignItems: 'center', gap: 12 }}>
            <Archive size={28} color="#dc2626" /> Client Workspaces
          </h1>
          <p style={{ margin: '8px 0 0', color: '#64748b', fontSize: 15 }}>
            Assemble packages and export directly to SharePoint.
          </p>
        </div>
        <div style={{ display: 'flex', gap: 12 }}>
          <button onClick={() => setShowImportModal(true)} style={{ background: 'white', color: '#0f172a', border: '1px solid #cbd5e1', padding: '10px 20px', borderRadius: 8, fontSize: 15, fontWeight: 600, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 8 }}>
            <UploadCloud size={18} color="#dc2626" /> Import from OneDrive
          </button>
          <button onClick={startNewPackage} style={{ background: '#dc2626', color: 'white', border: 'none', padding: '10px 20px', borderRadius: 8, fontSize: 15, fontWeight: 600, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 8 }}>
            <Plus size={18} /> New Package
          </button>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 20 }}>
        {packages.map(pkg => (
          <div key={pkg.id} style={{ background: 'white', border: '1px solid #e2e8f0', borderRadius: 12, padding: 20, display: 'flex', flexDirection: 'column' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
              <h3 style={{ margin: 0, fontSize: 18, color: '#0f172a' }}>{pkg.name}</h3>
              {pkg.status === 'Exported' ? (
                <CheckCircle2 size={20} color="#10b981" />
              ) : (
                <Clock size={20} color="#f59e0b" />
              )}
            </div>
            <div style={{ fontSize: 14, color: '#64748b', marginBottom: 16 }}>Client: <span style={{ fontWeight: 600, color: '#333' }}>{pkg.client}</span></div>
            
            {pkg.updated_at && (
              <div style={{ fontSize: 12, color: '#94a3b8', marginBottom: 16 }}>
                Last updated: {new Date(pkg.updated_at).toLocaleString()}
              </div>
            )}

            {pkg.share_link && (
              <a href={pkg.share_link} target="_blank" rel="noreferrer" style={{ fontSize: 13, color: '#3b82f6', textDecoration: 'none', marginBottom: 16, display: 'inline-block' }}>
                Open in SharePoint ↗
              </a>
            )}

            <div style={{ marginTop: 'auto', paddingTop: 16, borderTop: '1px solid #f1f5f9', display: 'flex', justifyContent: 'flex-end' }}>
              <button onClick={() => setActivePackage(pkg)} style={{ background: 'none', border: 'none', color: '#dc2626', fontSize: 14, fontWeight: 600, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 4 }}>
                <Edit size={14} /> Open Workspace
              </button>
            </div>
          </div>
        ))}

        {packages.length === 0 && (
          <div style={{ gridColumn: '1 / -1', padding: 60, textAlign: 'center', background: 'white', border: '1px dashed #cbd5e1', borderRadius: 12, color: '#64748b' }}>
            <Archive size={48} color="#cbd5e1" style={{ marginBottom: 16 }} />
            <h3 style={{ margin: '0 0 8px', color: '#0f172a' }}>No packages yet</h3>
            <p style={{ margin: 0 }}>Create your first workspace to start assembling documents.</p>
          </div>
        )}
      </div>

      {showImportModal && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100 }}>
          <div style={{ background: 'white', padding: 32, borderRadius: 12, width: 500, maxWidth: '90%' }}>
            <h2 style={{ margin: '0 0 16px', fontSize: 20 }}>Import from OneDrive</h2>
            <p style={{ margin: '0 0 24px', color: '#64748b', fontSize: 14, lineHeight: 1.5 }}>
              Enter the OneDrive or SharePoint URL of your existing client folder.
            </p>
            <div style={{ marginBottom: 16 }}>
              <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 8 }}>Client Name</label>
              <input 
                value={importData.client}
                onChange={e => setImportData({...importData, client: e.target.value})}
                placeholder="e.g. Jackson Solar"
                style={{ width: '100%', padding: '10px 12px', border: '1px solid #cbd5e1', borderRadius: 6, boxSizing: 'border-box' }}
              />
            </div>
            <div style={{ marginBottom: 16 }}>
              <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 8 }}>Package Name</label>
              <input 
                value={importData.name}
                onChange={e => setImportData({...importData, name: e.target.value})}
                placeholder="e.g. PQ Documents 2025"
                style={{ width: '100%', padding: '10px 12px', border: '1px solid #cbd5e1', borderRadius: 6, boxSizing: 'border-box' }}
              />
            </div>
            <div style={{ marginBottom: 24 }}>
              <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 8 }}>OneDrive Folder URL</label>
              <input 
                value={importData.target_sharepoint_url}
                onChange={e => setImportData({...importData, target_sharepoint_url: e.target.value})}
                placeholder="https://company-my.sharepoint.com/..."
                style={{ width: '100%', padding: '10px 12px', border: '1px solid #cbd5e1', borderRadius: 6, boxSizing: 'border-box' }}
              />
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 12 }}>
              <button onClick={() => setShowImportModal(false)} disabled={isImporting} style={{ padding: '10px 16px', background: 'white', border: '1px solid #cbd5e1', borderRadius: 6, cursor: 'pointer', fontWeight: 500 }}>Cancel</button>
              <button onClick={handleImportSubmit} disabled={isImporting} style={{ padding: '10px 16px', background: '#dc2626', color: 'white', border: 'none', borderRadius: 6, cursor: isImporting ? 'not-allowed' : 'pointer', fontWeight: 500, display: 'flex', alignItems: 'center', gap: 8, opacity: isImporting ? 0.7 : 1 }}>
                <UploadCloud size={16} /> {isImporting ? 'Importing...' : 'Start Import'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
