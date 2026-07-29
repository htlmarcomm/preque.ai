import axios from 'axios'

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000',
})

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
  seed: () => api.post('/api/documents/seed'),
}

// Agent
export const agentApi = {
  processExcel: (clientName, file) => {
    const fd = new FormData()
    fd.append('client_name', clientName)
    fd.append('file', file)
    return api.post('/api/agent/process-excel', fd)
  },
  processImage: (clientName, file) => {
    const fd = new FormData()
    fd.append('client_name', clientName)
    fd.append('file', file)
    return api.post('/api/agent/process-image', fd)
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
  download: (id) => `${api.defaults.baseURL}/api/forms/${id}/download`,
  preview: (id) => api.get(`/api/forms/${id}/preview`),
  exportToGoogleSheets: (id) => api.post(`/api/google/export-form/${id}`),
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
  fillProjectTable: (formId, sheetName, tableType, selectedIds) =>
    api.post(`/api/agent/forms/${formId}/fill-project-table`, {
      sheet_name: sheetName, table_type: tableType, selected_ids: selectedIds
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
