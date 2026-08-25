import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'
import { Database, FileText, FolderOpen, History, Zap, Archive, Briefcase, Search, Users } from 'lucide-react'
import FillForm from './pages/FillForm'
import CompanyDB from './pages/CompanyDB'
import FormHistory from './pages/FormHistory'
import ProjectFiles from './pages/ProjectFiles'
import Documents from './pages/Documents'
import Workspace from './pages/Workspace'
import DocumentSearch from './pages/DocumentSearch'
import SubContractors from './pages/SubContractors'
import ProjectHistory from './pages/ProjectHistory'

// FIX: this page/route was missing entirely -- Documents.jsx is the only UI
// that creates ProjectFile rows with source_module="document" (via
// POST /api/documents/upload), which is what get_doc_checklist() in
// forms.py matches against to build the "Documents to attach" checklist on
// every filled form. Without a route to it, that checklist could only ever
// grow via the one-time /api/documents/seed list -- there was no way for a
// user to add a newly-obtained certificate to it at all.
const navItems = [
  { to: '/',          icon: Zap,        label: 'Fill Form'    },
  { to: '/history',   icon: History,    label: 'History'      },
  { to: '/company',   icon: Database,   label: 'Company Data' },
  { to: '/files',     icon: Archive,    label: 'File Cabinet' },
  { to: '/documents', icon: FileText,   label: 'Documents'    },
  { to: '/workspaces',icon: Briefcase,  label: 'Workspaces'   },
  { to: '/subcontractors', icon: Users, label: 'Subcontractors' },
  { to: '/projects', icon: Briefcase, label: 'Project History' },
  { to: '/search',    icon: Search,     label: 'Document Search' },
]

export default function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen flex">
        <aside className="w-56 bg-white border-r border-gray-100 flex flex-col py-6 px-3 fixed h-full z-10">
          <div className="px-3 mb-8">
            <div className="h-10 w-auto flex items-center font-bold text-xl text-gray-800">HTL PreQue</div>
          </div>
          <nav className="flex-1 space-y-1">
            {navItems.map(({ to, icon: Icon, label }) => (
              <NavLink key={to} to={to} end={to === '/'}
                className={({ isActive }) =>
                  `flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                    isActive ? 'bg-red-50 text-red-700' : 'text-gray-500 hover:text-red-700 hover:bg-red-50'
                  }`}
              >
                <Icon size={17} />{label}
              </NavLink>
            ))}
          </nav>
          <div className="px-3 pt-4 border-t border-gray-100">
            <p className="text-xs text-gray-400">Pre-Qual Automation</p>
            <p className="text-xs text-gray-300 mt-0.5">v1.0 · HTL Internal</p>
          </div>
        </aside>
        <main className="ml-56 flex-1 min-h-screen">
          <Routes>
            <Route path="/" element={<FillForm />} />
            <Route path="/history" element={<FormHistory />} />
            <Route path="/company" element={<CompanyDB />} />
            <Route path="/files" element={<ProjectFiles />} />
            <Route path="/documents" element={<Documents />} />
            <Route path="/workspaces" element={<Workspace />} />
            <Route path="/subcontractors" element={<SubContractors />} />
            <Route path="/projects" element={<ProjectHistory />} />
            <Route path="/search" element={<DocumentSearch />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}
