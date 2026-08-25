import axios from 'axios'

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000',
  timeout: 60000, // 60s default timeout
  headers: import.meta.env.VITE_API_KEY ? { 'X-API-Key': import.meta.env.VITE_API_KEY } : {},
})

// A plain <a href> or <img>/<iframe src> can't carry the X-API-Key header, so
// any endpoint protected by the API key (all of /api/*) can't be linked to
// directly -- it has to be fetched through the authenticated `api` client and
// turned into a blob first. These two helpers are that path.

// Fetches an authenticated GET endpoint and triggers a normal browser
// "Save As" for it.
export async function downloadFile(url, filename) {
  const res = await api.get(url, { responseType: 'blob' })
  const blobUrl = window.URL.createObjectURL(res.data)
  const a = document.createElement('a')
  a.href = blobUrl
  a.download = filename || ''
  document.body.appendChild(a)
  a.click()
  a.remove()
  window.URL.revokeObjectURL(blobUrl)
}

// Fetches an authenticated GET endpoint as a blob object URL, for inline
// <img>/<iframe> previews. Caller owns the returned URL and must
// window.URL.revokeObjectURL(...) it once no longer displayed.
export async function fetchAsObjectURL(url) {
  const res = await api.get(url, { responseType: 'blob' })
  return window.URL.createObjectURL(res.data)
}

// Company Data
export const companyApi = {
  getFields: (category) => api.get('/api/company/fields', { params: category ? { category } : {} }),
  createField: (data) => api.post('/api/company/fields', data),
  updateField: (id, data) => api.put(`/api/company/fields/${id}`, data),
  deleteField: (id) => api.delete(`/api/company/fields/${id}`),
  getCategories: () => api.get('/api/company/categories'),
  seed: () => api.post('/api/company/seed'),
  importExcel: (file) => {
    const fd = new FormData(); fd.append('file', file)
    return api.post('/api/company/import-excel', fd)
  },
  importProjectsExcel: (file) => {
    const fd = new FormData(); fd.append('file', file)
    return api.post('/api/company/import-projects', fd)
  },
  getFinancialRecords: (category, year) => api.get('/api/company/financial-records', { params: { category, year } }),
  getProjectReferences: (region, status, client) => api.get('/api/company/project-references', { params: { region, status, client } }),
  searchCompanyData: (q, type, category, year) => api.get('/api/company/search', { params: { q, type, category, year } }),
}

// Documents
export const docsApi = {
  list: (type) => api.get('/api/documents/', { params: type ? { doc_type: type } : {} }),
  getTypes: () => api.get('/api/documents/types'),
  upload: (name, docType, file, sharepointLink, tags) => {
    const fd = new FormData()
    fd.append('name', name)
    fd.append('doc_type', docType)
    if (file) fd.append('file', file)
    fd.append('sharepoint_link', sharepointLink || '')
    fd.append('tags', tags || '')
    return api.post('/api/documents/upload', fd)
  },
  update: (id, data) => api.put(`/api/documents/${id}`, data),
  delete: (id) => api.delete(`/api/documents/${id}`),
  download: (id, filename) => downloadFile(`/api/documents/download/${id}`, filename),
  seed: () => api.post('/api/documents/seed'),
}

// Agent
export const agentApi = {
  processExcel: (clientName, file) => {
    const fd = new FormData()
    fd.append('client_name', clientName)
    fd.append('file', file)
    return api.post('/api/agent/process-excel', fd, { timeout: 600000 }) // 10 min — multi-sheet GPT-4o vision
  },
  processImage: (clientName, file) => {
    const fd = new FormData()
    fd.append('client_name', clientName)
    fd.append('file', file)
    return api.post('/api/agent/process-image', fd, { timeout: 600000 }) // 10 min — GPT-4o vision
  },
  saveLearnedAnswer: (fieldLabel, answer, formId, saveToDb) => {
    const fd = new FormData()
    fd.append('field_label', fieldLabel)
    fd.append('answer', answer)
    if (formId) fd.append('form_id', formId)
    fd.append('save_to_db', saveToDb ? 'true' : 'false')
    return api.post('/api/agent/save-learned-answer', fd)
  },
}

// Forms
export const formsApi = {
  history: () => api.get('/api/forms/history'),
  get: (id) => api.get(`/api/forms/${id}`),
  download: (id, filename) => downloadFile(`/api/forms/${id}/download`, filename),
  preview: (id) => api.get(`/api/forms/${id}/preview`),
  exportToGoogleSheets: (id) => api.post(`/api/google/export-form/${id}`),
}

// Project Files ("File Cabinet")
export const projectFilesApi = {
  list: (params) => api.get('/api/project-files/', { params }),
  getCategories: () => api.get('/api/project-files/categories'),
  delete: (id) => api.delete(`/api/project-files/${id}`),
  update: (id, data) => api.put(`/api/project-files/${id}`, data),
  preview: (id) => api.get(`/api/project-files/${id}/preview`),
  viewUrl: (id) => fetchAsObjectURL(`/api/project-files/${id}/view`),
  download: (id, filename) => downloadFile(`/api/project-files/${id}/download`, filename),
  upload: (formData) => api.post('/api/project-files/upload', formData),
  addSharepoint: (formData) => api.post('/api/project-files/add-sharepoint', formData),
}

// Workspace (client SharePoint export packages)
export const workspaceApi = {
  list: () => api.get('/api/workspace/'),
  create: (data) => api.post('/api/workspace/', data),
  update: (id, data) => api.put(`/api/workspace/${id}`, data),
  export: (id) => api.post(`/api/workspace/${id}/export`),
  import: (data) => api.post('/api/workspace/import', data),
}

// Search
export const searchApi = {
  search: (q, topK, sourceType) => api.get('/api/search', 
    { params: { q, top_k: topK, source_type: sourceType } }),
  ask: (question, topK, sourceType) => api.post('/api/search/ask', 
    { question, top_k: topK, source_type: sourceType }),
}

export const subcontractorsApi = {
  getAll: (search) => api.get('/api/subcontractors/', { params: search ? { search } : {} }),
  create: (data) => api.post('/api/subcontractors/', data),
  update: (id, data) => api.put(`/api/subcontractors/${id}`, data),
  delete: (id) => api.delete(`/api/subcontractors/${id}`),
  importCsv: (file) => {
    const fd = new FormData()
    fd.append('file', file)
    return api.post('/api/subcontractors/import-csv', fd)
  }
}

export const projectDataApi = {
  importExcel: (file) => {
    const fd = new FormData()
    fd.append('file', file)
    return api.post('/api/project-data/import', fd)
  },
  getFiles: () => api.get('/api/project-data/files'),
  getSheetRecords: (sourceFile, sourceSheet, params) =>
    api.get(`/api/project-data/files/${encodeURIComponent(sourceFile)}/sheets/${encodeURIComponent(sourceSheet)}/records`, { params }),
  getSheetFilters: (sourceFile, sourceSheet) =>
    api.get(`/api/project-data/files/${encodeURIComponent(sourceFile)}/sheets/${encodeURIComponent(sourceSheet)}/filters`),
  getSummary: () => api.get('/api/project-data/summary'),
  deleteRecord: (id) => api.delete(`/api/project-data/records/${id}`),
}

export const projectPickerApi = {
  getReferences: (params) => api.get('/api/project-picker/references', { params }),
  getDetails: (params) => api.get('/api/project-picker/details', { params }),
  fillProjectTable: (formId, sheetName, tableType, selectedIds, subheading) =>
    api.post(`/api/agent/forms/${formId}/fill-project-table`, {
      sheet_name: sheetName, table_type: tableType, selected_ids: selectedIds, subheading
    }),
}

export const projectHistoryApi = {
  getAll: () => api.get('/api/projects/'),
  create: (data) => api.post('/api/projects/', data),
  update: (id, data) => api.put(`/api/projects/${id}`, data),
  delete: (id) => api.delete(`/api/projects/${id}`),
  importCsv: (file) => {
    const fd = new FormData()
    fd.append('file', file)
    return api.post('/api/projects/import-csv', fd)
  }
}
