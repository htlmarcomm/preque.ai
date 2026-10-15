import { Link } from 'react-router-dom'
import { FolderOpen, AlertTriangle, ArrowRight } from 'lucide-react'

// Shown after a form is filled: every field answered "Attached" has its documents gathered into a
// Draft Workspace folder for the user to review before sending.
export default function DocumentsFolderCard({ info }) {
  if (!info || (!info.package_id && !(info.missing || []).length)) return null
  const folders = (info.kinds || []).filter((k) => k.files > 0)
  return (
    <div className="card border-blue-100">
      <div className="p-4 flex items-start justify-between gap-4">
        <div className="flex items-start gap-3">
          <div className="w-9 h-9 rounded-lg bg-blue-50 flex items-center justify-center shrink-0">
            <FolderOpen size={18} className="text-blue-600" />
          </div>
          <div>
            <h3 className="font-medium text-gray-900">
              {info.package_id ? 'Documents folder ready for review' : 'Documents asked for, none found yet'}
            </h3>
            {info.package_id && (
              <p className="text-xs text-gray-500 mt-0.5">
                {info.files} file{info.files === 1 ? '' : 's'} in {info.folders} folder{info.folders === 1 ? '' : 's'}, gathered
                for the fields answered &ldquo;Attached&rdquo;. Open it in Workspaces to check, add or remove files.
              </p>
            )}
            {folders.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mt-2.5">
                {folders.map((k) => (
                  <span key={k.kind} className="text-[11px] px-2 py-0.5 rounded bg-gray-100 text-gray-600">
                    {k.folder} <b className="text-gray-800">{k.files}</b>
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>
        {info.package_id && (
          <Link to={`/workspaces?pkg=${info.package_id}`} className="btn-primary text-sm shrink-0">
            Open folder <ArrowRight size={14} />
          </Link>
        )}
      </div>
      {(info.missing || []).length > 0 && (
        <div className="px-4 pb-4">
          <div className="flex items-start gap-2 text-xs text-amber-800 bg-amber-50 border border-amber-100 rounded-lg px-3 py-2">
            <AlertTriangle size={14} className="mt-0.5 shrink-0" />
            <span>
              Not in the File Cabinet yet, upload before sending: <b>{info.missing.join(', ')}</b>.
            </span>
          </div>
        </div>
      )}
    </div>
  )
}
