import { useState } from 'react'
import { Search, Sparkles, Loader2, FileText, ChevronDown, ChevronRight, ExternalLink } from 'lucide-react'
import { searchApi } from '../lib/api'

export default function DocumentSearch() {
  const [query, setQuery] = useState('')
  const [sourceType, setSourceType] = useState('all') // 'all', 'project_file', 'document'
  const [loading, setLoading] = useState(false)
  const [answer, setAnswer] = useState(null) // null when not searched, empty string/message if none
  const [sources, setSources] = useState([])
  const [rawResults, setRawResults] = useState([])
  const [showRaw, setShowRaw] = useState(false)
  
  const handleSearch = async () => {
    if (!query.trim()) return
    setLoading(true)
    setAnswer(null)
    setSources([])
    setRawResults([])
    setShowRaw(false)
    
    try {
      const typeParam = sourceType === 'all' ? null : sourceType
      // Call Ask
      const askRes = await searchApi.ask(query, 15, typeParam)
      setAnswer(askRes.data.answer || askRes.data.message)
      setSources(askRes.data.sources || [])
      
      // Also get raw to allow advanced view
      const rawRes = await searchApi.search(query, 15, typeParam)
      setRawResults(rawRes.data.results || [])
    } catch (err) {
      console.error(err)
      setAnswer("Sorry, an error occurred while searching. Ensure the AI models are loaded.")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="p-8 max-w-4xl mx-auto">
      <div className="mb-8">
        <h1 className="text-2xl font-semibold text-gray-900">Document Search</h1>
        <p className="text-sm text-gray-500 mt-1">Ask questions across all your uploaded documents and project files</p>
      </div>

      <div className="card p-6 mb-6">
        <div className="flex flex-col gap-4">
          <div className="relative">
            <Search size={18} className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-400" />
            <input 
              className="input w-full pl-11 py-3 text-base" 
              placeholder="E.g., What was our turnover in 2022-23?"
              value={query} 
              onChange={e => setQuery(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSearch()}
            />
          </div>
          
          <div className="flex items-center justify-between">
            <div className="flex gap-1">
              <span className="text-sm text-gray-500 mr-2 self-center">Search in:</span>
              {['all', 'project_file', 'document'].map(type => (
                <button 
                  key={type} 
                  onClick={() => setSourceType(type)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${sourceType === type ? 'bg-brand-50 text-brand-700' : 'text-gray-500 hover:bg-gray-100'}`}
                >
                  {type === 'all' ? 'All' : type === 'project_file' ? 'Project Files' : 'Documents'}
                </button>
              ))}
            </div>
            
            <button onClick={handleSearch} disabled={loading || !query.trim()} className="btn-primary">
              {loading ? <Loader2 size={16} className="animate-spin" /> : <Sparkles size={16} />}
              Ask AI
            </button>
          </div>
        </div>
      </div>

      {loading && (
        <div className="flex justify-center items-center py-12 text-gray-400">
          <Loader2 size={32} className="animate-spin" />
        </div>
      )}

      {!loading && answer && (
        <div className="space-y-6">
          {sources.length > 0 ? (
            <div className="card border-green-100 bg-green-50/30 overflow-hidden">
              <div className="p-5">
                <h3 className="font-medium text-green-900 mb-2 flex items-center gap-2">
                  <Sparkles size={16} className="text-green-600" />
                  Answer
                </h3>
                <div className="text-sm text-gray-800 leading-relaxed whitespace-pre-wrap">
                  {answer}
                </div>
              </div>
            </div>
          ) : (
            <div className="card p-8 text-center text-gray-500">
              <Search size={24} className="mx-auto mb-3 text-gray-300" />
              <p>{answer}</p>
            </div>
          )}

          {sources.length > 0 && (
            <div>
              <h3 className="text-sm font-semibold text-gray-900 mb-3 uppercase tracking-wider">Sources cited</h3>
              <div className="grid gap-3">
                {sources.map((s, i) => (
                  <div key={i} className="card p-4 flex flex-col gap-2">
                    <div className="flex items-start justify-between">
                      <div className="flex items-center gap-2 font-medium text-sm text-gray-900">
                        <FileText size={15} className="text-brand-500" />
                        {s.name}
                        {s.sheet_or_page && <span className="text-xs text-gray-500 font-normal">({s.sheet_or_page})</span>}
                      </div>
                      {s.link && (
                        <a href={s.link} target="_blank" rel="noreferrer" className="text-xs text-brand-600 hover:text-brand-800 flex items-center gap-1">
                          View <ExternalLink size={12} />
                        </a>
                      )}
                    </div>
                    <div className="text-xs text-gray-500 italic bg-gray-50 p-2 rounded border border-gray-100">
                      "{s.excerpt}"
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
          
          {/* Advanced Raw Matches */}
          {rawResults.length > 0 && (
            <div className="mt-8 pt-6 border-t border-gray-100">
              <button 
                onClick={() => setShowRaw(!showRaw)}
                className="flex items-center gap-1.5 text-xs font-medium text-gray-500 hover:text-gray-700 transition-colors"
              >
                {showRaw ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                Advanced: browse raw matches
              </button>
              
              {showRaw && (
                <div className="mt-4 grid gap-3">
                  {rawResults.map((r, i) => (
                    <div key={i} className="card p-3 border-dashed bg-gray-50">
                      <div className="flex justify-between items-center mb-1">
                        <span className="text-[10px] font-medium uppercase text-gray-400">{r.source_type} (Score: {r.score?.toFixed(3)})</span>
                        <span className="text-xs text-gray-500">{r.sheet_or_page}</span>
                      </div>
                      <p className="text-xs text-gray-600">{r.text}</p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
