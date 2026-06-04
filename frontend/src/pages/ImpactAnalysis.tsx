import { useState, useEffect, useRef } from 'react'

interface Org {
  id: string
  name: string
  org_type: string
}

interface Retrieval {
  id: string
  org_id: string
  status: string
  artifact_key: string | null
  created_at: string
  completed_at: string | null
}

interface Analysis {
  id: string
  org_id: string
  retrieval_id?: string | null
  comparison_id?: string | null
  status: string
  analysis_type: string
  risk_level: string | null
  risk_score: number | null
  release_score: number | null
  go_no_go_decision: string | null
  release_readiness: number | null
  recommendation: string | null
  changed_items_count: number
  impacted_components_count: number
  created_at: string
  completed_at: string | null
  llm_used?: boolean | null
}

interface AnalysisDetail {
  id: string
  org_id: string
  retrieval_id?: string | null
  comparison_id?: string | null
  status: string
  analysis_type: string
  changed_items: Record<string, string[]>
  impacted_components: Record<string, string[]> | null
  risk_score: number | null
  risk_level: string | null
  release_score: number | null
  go_no_go_decision: string | null
  decision_reasoning: string | null
  // AI Release Intelligence (full)
  release_readiness: number | null
  risk_areas: any[] | null
  recommendation: string | null
  suggested_actions: string[] | null
  git_diff?: string | null
  ai_summary: string | null
  ai_recommendations: string[] | null
  predicted_issues: any[] | null
  suggested_package: any | null
  dependencies: any[]
  created_at: string
  completed_at: string | null
  llm_used?: boolean | null
}

interface DependencyGraph {
  nodes: Array<{
    id: string
    type: string
    name: string
    is_changed: boolean
    is_impacted: boolean
    risk_level: string | null
  }>
  edges: Array<{
    source: string
    target: string
    dependency_type: string
    confidence: number | null
  }>
  stats: Record<string, number>
}

function Spinner() {
  return <span className="inline-block w-4 h-4 border-2 border-af-blue border-t-transparent rounded-full animate-spin" />
}

function RiskBadge({ level, score }: { level: string | null; score: number | null }) {
  if (!level) return <span className="text-xs text-slate-500">Not analyzed</span>
  
  const colors = {
    low: 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-400',
    medium: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/40 dark:text-yellow-400',
    high: 'bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-400',
    critical: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-400',
  }
  
  return (
    <span className={`text-xs font-semibold px-2 py-1 rounded-full ${colors[level as keyof typeof colors] || colors.medium}`}>
      {level.toUpperCase()} {score !== null && `(${score}/100)`}
    </span>
  )
}

function StatusBadge({ status }: { status: string }) {
  const colors = {
    pending: 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400',
    running: 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-400',
    completed: 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-400',
    failed: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-400',
  }
  
  return (
    <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${colors[status as keyof typeof colors] || colors.pending}`}>
      {status}
    </span>
  )
}

function GoNoGoBadge({ decision, score }: { decision: string | null; score: number | null }) {
  if (!decision) return null
  
  const colors = {
    GO: 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-400 border-green-300 dark:border-green-700',
    HOLD: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/40 dark:text-yellow-400 border-yellow-300 dark:border-yellow-700',
    'NO-GO': 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-400 border-red-300 dark:border-red-700',
  }
  
  const icons = {
    GO: '✓',
    HOLD: '⚠',
    'NO-GO': '✗',
  }
  
  return (
    <div className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border-2 font-bold text-sm ${colors[decision as keyof typeof colors] || colors.HOLD}`}>
      <span className="text-lg">{icons[decision as keyof typeof icons] || '•'}</span>
      <span>{decision}</span>
      {score !== null && <span className="font-normal">({score}/100)</span>}
    </div>
  )
}

export default function ImpactAnalysisPage() {
  const [orgs, setOrgs] = useState<Org[]>([])
  const [selectedOrg, setSelectedOrg] = useState('')
  const [retrievals, setRetrievals] = useState<Retrieval[]>([])
  const [selectedRetrieval, setSelectedRetrieval] = useState('')
  const [analyses, setAnalyses] = useState<Analysis[]>([])
  const [selectedAnalysis, setSelectedAnalysis] = useState<AnalysisDetail | null>(null)
  const [graph, setGraph] = useState<DependencyGraph | null>(null)
  const [loading, setLoading] = useState(false)
  const [loadingRetrievals, setLoadingRetrievals] = useState(false)
  const [creating, setCreating] = useState(false)
  const [isAnalyzing, setIsAnalyzing] = useState(false)
  const [gitDiffInput, setGitDiffInput] = useState('')
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // Toggle like Deployments/Retrievals: Analysis (form + single recent) | History (full list of analyses)
  const [view, setView] = useState<'analysis' | 'history'>('analysis')

  // Map of retrieval id -> label for display (populated from loaded successful retrievals)
  const retrievalLabels = retrievals.reduce<Record<string, string>>((acc, r) => {
    const when = new Date(r.created_at).toLocaleString()
    acc[r.id] = `${when} - ${r.artifact_key || 'Package'}`
    return acc
  }, {})

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current)
        pollRef.current = null
      }
    }
  }, [])

  useEffect(() => {
    fetch('/api/v1/orgs').then(r => r.json()).then(d => setOrgs(d.orgs ?? d)).catch(() => {})
  }, [])

  useEffect(() => {
    if (selectedOrg) {
      setSelectedRetrieval('') // clear previous org's selection
      setGitDiffInput('') // clear diff for new org
      if (pollRef.current) {
        clearInterval(pollRef.current)
        pollRef.current = null
      }
      setIsAnalyzing(false)
      setCreating(false)
      loadAnalyses()
      loadRetrievals()
    } else {
      setSelectedRetrieval('')
      setRetrievals([])
      setGitDiffInput('')
      if (pollRef.current) {
        clearInterval(pollRef.current)
        pollRef.current = null
      }
      setIsAnalyzing(false)
    }
  }, [selectedOrg])

  const loadAnalyses = async () => {
    if (!selectedOrg) return
    setLoading(true)
    try {
      const res = await fetch(`/api/v1/impact-analysis?org_id=${selectedOrg}`)
      const data = await res.json()
      setAnalyses(data.analyses || [])
    } catch (e) {
      console.error('Failed to load analyses:', e)
    }
    setLoading(false)
  }

  const loadRetrievals = async () => {
    if (!selectedOrg) return
    setLoadingRetrievals(true)
    try {
      const res = await fetch(`/api/v1/retrievals?org_id=${selectedOrg}`)
      const data = await res.json()
      // API returns array directly (or {retrievals: []} for compat); filter only successful/completed retrievals
      const list: Retrieval[] = Array.isArray(data) ? data : (data.retrievals || [])
      const completed = list.filter((r: Retrieval) => r.status === 'success' || r.status === 'completed')
      setRetrievals(completed)
    } catch (e) {
      console.error('Failed to load retrievals:', e)
    }
    setLoadingRetrievals(false)
  }

  const analyzeRetrieval = async () => {
    if (!selectedOrg || !selectedRetrieval) {
      alert('Please select a retrieval package')
      return
    }

    console.log('[ImpactAnalysis] Starting analyze for retrieval:', selectedRetrieval, 'org:', selectedOrg)

    setCreating(true)
    setIsAnalyzing(true)

    try {
      const payload: any = {
        org_id: selectedOrg,
        retrieval_id: selectedRetrieval,
        analysis_type: 'pre_deployment',
        changed_items: {}, // backend will extract from the retrieval package.xml
        git_diff: gitDiffInput.trim() || undefined,
      }
      console.log('[ImpactAnalysis] POST /impact-analysis payload:', payload)

      // 1. Create the analysis record immediately (returns id + pending status quickly)
      const createRes = await fetch('/api/v1/impact-analysis', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })

      console.log('[ImpactAnalysis] Create response status:', createRes.status)
      if (!createRes.ok) {
        const errText = await createRes.text()
        console.error('[ImpactAnalysis] Create failed body:', errText)
        throw new Error(`Create failed: HTTP ${createRes.status} - ${errText}`)
      }
      let analysis: any = await createRes.json()
      console.log('[ImpactAnalysis] Created analysis:', { id: analysis.id, status: analysis.status, llm_used: analysis.llm_used })

      setSelectedAnalysis(analysis)
      loadAnalyses() // so it appears in the Recent Analyses list right away

      // 2. Fire the run (it will set status=running and do the heavy work including LLM)
      // We don't block the UI on this response; we poll instead.
      console.log('[ImpactAnalysis] Triggering run for analysis:', analysis.id)
      fetch(`/api/v1/impact-analysis/${analysis.id}/run`, {
        method: 'POST',
      }).catch((err) => console.warn('[ImpactAnalysis] Run trigger failed (polling should still work):', err))

      // 3. Poll the status for live progress updates
      if (pollRef.current) clearInterval(pollRef.current)
      pollRef.current = setInterval(async () => {
        try {
          const res = await fetch(`/api/v1/impact-analysis/${analysis.id}`)
          if (!res.ok) return
          const updated: AnalysisDetail = await res.json()
          console.log('[ImpactAnalysis] Poll update:', { id: updated.id, status: updated.status, llm_used: updated.llm_used, ai_summary_preview: (updated.ai_summary || 'null').substring(0, 80) + '...' })
          setSelectedAnalysis(updated)

          // Refresh the list so running/completed status is visible in Recent Analyses
          loadAnalyses()

          if (updated.status === 'completed' || updated.status === 'failed') {
            if (pollRef.current) {
              clearInterval(pollRef.current)
              pollRef.current = null
            }
            setCreating(false)
            setIsAnalyzing(false)
            loadAnalyses()
            if (updated.status === 'completed') {
              loadGraph(updated.id)
            }
            // clear the picklist selection so user can easily start another
            setSelectedRetrieval('')
            console.log('[ImpactAnalysis] Analysis finished. Final llm_used:', updated.llm_used)
          }
        } catch (e) {
          console.error('[ImpactAnalysis] Analysis polling error:', e)
        }
      }, 1500)
    } catch (e: any) {
      console.error('[ImpactAnalysis] analyzeRetrieval error:', e)
      alert(`Failed to start analysis: ${e.message}`)
      setCreating(false)
      setIsAnalyzing(false)
      if (pollRef.current) {
        clearInterval(pollRef.current)
        pollRef.current = null
      }
    }
  }

  const loadAnalysisDetail = async (id: string) => {
    try {
      console.log('[ImpactAnalysis] loadAnalysisDetail for id:', id)
      const res = await fetch(`/api/v1/impact-analysis/${id}`)
      const data = await res.json()
      console.log('[ImpactAnalysis] Loaded detail:', { id: data.id, status: data.status, llm_used: data.llm_used })
      setSelectedAnalysis(data)
      loadGraph(id)

      // If it's a running analysis, start polling it for live progress
      if (data.status === 'pending' || data.status === 'running') {
        console.log('[ImpactAnalysis] Starting poll for running analysis:', id)
        if (pollRef.current) clearInterval(pollRef.current)
        setIsAnalyzing(true)
        setCreating(false)
        pollRef.current = setInterval(async () => {
          try {
            const r = await fetch(`/api/v1/impact-analysis/${id}`)
            const u = await r.json()
            console.log('[ImpactAnalysis] Detail-poll update:', { id: u.id, status: u.status, llm_used: u.llm_used, ai_summary_preview: (u.ai_summary || 'null').substring(0, 80) + '...' })
            setSelectedAnalysis(u)
            loadAnalyses()
            if (u.status === 'completed' || u.status === 'failed') {
              if (pollRef.current) {
                clearInterval(pollRef.current)
                pollRef.current = null
              }
              setIsAnalyzing(false)
              loadAnalyses()
              if (u.status === 'completed') loadGraph(u.id)
              console.log('[ImpactAnalysis] Running analysis finished via detail poll. llm_used:', u.llm_used)
            }
          } catch (e) { /* ignore poll errors */ }
        }, 1500)
      } else {
        if (pollRef.current && !isAnalyzing) {
          // stop any stray poll if user clicked a finished analysis
          clearInterval(pollRef.current)
          pollRef.current = null
          setIsAnalyzing(false)
        }
      }

      // Ensure we have a label for its retrieval (in case not in current filtered list)
      if (data.retrieval_id && !retrievalLabels[data.retrieval_id]) {
        fetch(`/api/v1/retrievals/${data.retrieval_id}`)
          .then(r => r.ok ? r.json() : null)
          .then(rj => {
            if (rj && rj.id) {
              // temporarily augment labels via state hack: re-compute will pick if we refetch all, but for now inline update not easy; show id is fine
            }
          })
          .catch(() => {})
      }
    } catch (e) {
      console.error('[ImpactAnalysis] Failed to load analysis:', e)
    }
  }

  const loadGraph = async (id: string) => {
    try {
      const res = await fetch(`/api/v1/impact-analysis/${id}/graph`)
      const data = await res.json()
      setGraph(data)
    } catch (e) {
      console.error('Failed to load graph:', e)
    }
  }

  const downloadReleaseIntelligencePdf = async (analysisId: string) => {
    try {
      const res = await fetch(`/api/v1/impact-analysis/${analysisId}/report/pdf`)
      if (!res.ok) {
        const txt = await res.text().catch(() => '')
        throw new Error(`HTTP ${res.status} ${txt}`)
      }
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `ai-release-intelligence-${analysisId}.pdf`
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      alert('Failed to download AI Release Intelligence PDF: ' + e)
    }
  }

  return (
    <div className="max-w-7xl mx-auto px-6 py-8">
      {/* Header */}
      <div className="flex items-start justify-between mb-8">
        <div>
          <h1 className="font-display text-3xl font-bold af-gradient-text mb-1">
            Deployment Impact Analysis
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            AI Release Intelligence — one AI layer before every deployment (Git diff, metadata, histories, telemetry, incidents, tests → readiness, risk areas, recommendation + actions)
          </p>
        </div>

        {/* Top-right toggle: Analysis (form + single recent) | History (full list) - like Deployments */}
        <div className="inline-flex rounded-lg border border-slate-200 dark:border-white/10 overflow-hidden text-sm shadow-sm shrink-0">
          <button
            onClick={() => setView('analysis')}
            className={`px-3.5 py-1.5 font-semibold transition-colors ${view === 'analysis' ? 'bg-af-blue text-white' : 'bg-white dark:bg-af-darkcard hover:bg-slate-50 dark:hover:bg-slate-800'}`}
          >
            Analysis
          </button>
          <button
            onClick={() => setView('history')}
            className={`px-3.5 py-1.5 font-semibold transition-colors ${view === 'history' ? 'bg-af-blue text-white' : 'bg-white dark:bg-af-darkcard hover:bg-slate-50 dark:hover:bg-slate-800'}`}
          >
            History
          </button>
        </div>
      </div>

      {/* Org Selector + Retrieval Package Picklist (for Impact Analysis) */}
      {view === 'analysis' && (
        <div className="af-panel mb-6">
          <div className="flex items-end gap-4">
            <div className="flex-1">
              <label className="block text-xs text-slate-400 mb-1 font-semibold uppercase tracking-wide">Org</label>
              <select
                className="af-input text-sm"
                value={selectedOrg}
                onChange={e => setSelectedOrg(e.target.value)}
              >
                <option value="">Select org…</option>
                {orgs.map(o => (
                  <option key={o.id} value={o.id}>{o.name} ({o.org_type})</option>
                ))}
              </select>
            </div>

            <div className="flex-1">
              <label className="block text-xs text-slate-400 mb-1 font-semibold uppercase tracking-wide">
                Retrieval Package to Analyze
              </label>
              {loadingRetrievals ? (
                <div className="af-input text-sm flex items-center h-9"><Spinner /></div>
              ) : retrievals.length === 0 ? (
                <div className="text-sm text-slate-500 py-2">
                  No completed retrievals. Retrieve metadata first in the Retrievals tab.
                </div>
              ) : (
                <select
                  className="af-input text-sm"
                  value={selectedRetrieval}
                  onChange={e => setSelectedRetrieval(e.target.value)}
                  disabled={isAnalyzing}
                >
                  <option value="">Select retrieval package…</option>
                  {retrievals.map(r => (
                    <option key={r.id} value={r.id}>
                      {new Date(r.created_at).toLocaleString()} - {r.artifact_key || 'Package'}
                    </option>
                  ))}
                </select>
              )}
            </div>

            <div>
              <button
                onClick={analyzeRetrieval}
                disabled={!selectedOrg || !selectedRetrieval || creating || isAnalyzing}
                className="af-btn-primary flex items-center gap-2"
              >
                {(creating || isAnalyzing) && <Spinner />}
                {isAnalyzing ? 'Analyzing...' : creating ? 'Starting...' : 'Analyze Package'}
              </button>
            </div>
          </div>

          {/* Optional Git Diff for richer AI Release Intelligence (per spec) */}
          <details className="mt-3 text-xs">
            <summary className="cursor-pointer text-af-blue hover:underline">+ Provide Git diff / changeset (optional, makes AI intelligence stronger)</summary>
            <textarea
              className="mt-2 w-full af-input text-xs font-mono h-20"
              placeholder="Paste relevant git diff or change description here (e.g. diff of Apex classes, flows, etc.)"
              value={gitDiffInput}
              onChange={(e) => setGitDiffInput(e.target.value)}
            />
            <div className="text-[10px] text-slate-500 mt-0.5">Will be sent with the next "Analyze Package" for this retrieval. Clears on org change.</div>
          </details>

          {!selectedOrg && (
            <p className="mt-3 text-xs text-slate-500">Select an org to load available retrieval packages for impact analysis.</p>
          )}
          {selectedOrg && retrievals.length === 0 && !loadingRetrievals && (
            <p className="mt-3 text-xs text-slate-500">No completed retrievals found for this org. Please retrieve metadata first in the Retrievals tab.</p>
          )}

          {/* Live progress while analysis is running (polled from backend status) */}
          {(isAnalyzing || (selectedAnalysis && (selectedAnalysis.status === 'pending' || selectedAnalysis.status === 'running'))) && (
            <div className="mt-4 p-4 rounded-lg border border-af-blue/30 bg-af-blue/5 dark:bg-af-blue/10">
              <div className="flex items-center justify-between mb-2">
                <div className="font-semibold text-sm flex items-center gap-2">
                  Analyzing deployment impact (exact to selected retrieval package)
                  <Spinner />
                </div>
                <StatusBadge status={selectedAnalysis?.status || 'running'} />
              </div>

              <div className="h-1.5 bg-slate-200 dark:bg-slate-700 rounded-full overflow-hidden mb-3">
                <div
                  className={`h-full bg-af-blue transition-all duration-500 ${selectedAnalysis?.status === 'running' ? 'w-[65%] animate-pulse' : 'w-[30%]'}`}
                />
              </div>

              <div className="text-xs text-slate-600 dark:text-slate-300 space-y-1.5">
                <div className={selectedAnalysis?.status === 'pending' ? 'font-medium text-af-blue' : ''}>
                  1. Extracting metadata from selected retrieval package.xml
                </div>
                <div className={selectedAnalysis?.status === 'running' ? 'font-medium text-af-blue' : ''}>
                  2. Detecting dependencies • Calculating risk + release readiness
                </div>
                <div className={selectedAnalysis?.status === 'running' ? 'font-medium text-af-blue' : ''}>
                  3. Generating full AI Release Intelligence via LLM (Git diff, histories, telemetry, incidents, tests)
                </div>
                <div>
                  4. Building suggested deployment package
                </div>
                {selectedAnalysis?.status === 'running' && (
                  <div className="pt-1 text-[10px] text-slate-500">Updates every ~1.5s — you can select other analyses while this runs.</div>
                )}
              </div>
            </div>
          )}
        </div>
      )}

      {view === 'history' && selectedOrg === '' && (
        <p className="text-xs text-slate-500 mb-4">Select an org in the Analysis tab first to load its analysis history.</p>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* LEFT: Analysis List (single in analysis tab, full in history) */}
        <div className="lg:col-span-1">
          <div className="af-panel">
            <h2 className="font-semibold text-slate-700 dark:text-slate-200 mb-4">
              {view === 'analysis' ? 'Recent Analysis' : 'All Analyses'}
            </h2>
            {loading ? (
              <div className="flex items-center justify-center py-8">
                <Spinner />
              </div>
            ) : analyses.length === 0 ? (
              <p className="text-sm text-slate-500 text-center py-8">
                No analyses yet. Create one to get started.
              </p>
            ) : (
              <div className="space-y-2 max-h-[600px] overflow-y-auto">
                {(view === 'analysis' ? analyses.slice(0, 1) : analyses).map(a => (
                  <button
                    key={a.id}
                    onClick={() => {
                      console.log('[ImpactAnalysis] Clicked analysis from list:', a.id, 'llm_used:', a.llm_used)
                      loadAnalysisDetail(a.id)
                    }}
                    className={`w-full text-left p-3 rounded-lg border transition ${
                      selectedAnalysis?.id === a.id
                        ? 'border-af-blue bg-af-blue/5'
                        : 'border-slate-200 dark:border-slate-700 hover:border-af-blue/50'
                    }`}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <StatusBadge status={a.status} />
                      <div className="flex items-center gap-2">
                        <RiskBadge level={a.risk_level} score={a.risk_score} />
                        {a.release_readiness != null && (
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-400 font-mono">{a.release_readiness}%</span>
                        )}
                      </div>
                    </div>
                    <div className="text-xs text-slate-500 space-y-1">
                      <div>Changed: {a.changed_items_count} components</div>
                      <div>Impacted: {a.impacted_components_count} components</div>
                      {a.retrieval_id && (
                        <div className="text-af-blue">From: {retrievalLabels[a.retrieval_id] || a.retrieval_id.substring(0, 8) + '…'}</div>
                      )}
                      <div>{new Date(a.created_at).toLocaleString()}</div>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* RIGHT: Analysis Detail */}
        <div className="lg:col-span-2 space-y-6">
          {!selectedAnalysis ? (
            <div className="af-panel flex flex-col items-center justify-center py-16 text-center">
              <div className="text-5xl mb-4">📊</div>
              <p className="font-semibold text-slate-600 dark:text-slate-400 mb-2">
                No analysis selected
              </p>
              <p className="text-sm text-slate-500">
                Select an analysis from the list or create a new one
              </p>
            </div>
          ) : (
            <>
              {/* Risk Overview */}
              <div className="af-panel">
                <div className="flex items-center justify-between mb-4">
                  <h2 className="font-semibold text-slate-700 dark:text-slate-200">
                    Risk Assessment
                  </h2>
                  <RiskBadge level={selectedAnalysis.risk_level} score={selectedAnalysis.risk_score} />
                </div>

                {selectedAnalysis.retrieval_id && (
                  <div className="mb-4 p-2 rounded bg-slate-50 dark:bg-slate-800/50 text-xs">
                    <span className="text-slate-500">Source Retrieval Package: </span>
                    <span className="font-mono text-af-blue">{retrievalLabels[selectedAnalysis.retrieval_id] || selectedAnalysis.retrieval_id}</span>
                  </div>
                )}

                {/* Go/No-Go Decision - Prominent Display (from intelligence layer) */}
                {selectedAnalysis.go_no_go_decision && (
                  <div className="mb-4 p-4 rounded-lg border-2 border-slate-200 dark:border-slate-700 bg-gradient-to-br from-slate-50 to-white dark:from-slate-800/50 dark:to-slate-900/50">
                    <div className="flex items-center justify-between mb-3">
                      <div>
                        <div className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">Deployment Decision</div>
                        <GoNoGoBadge decision={selectedAnalysis.go_no_go_decision} score={selectedAnalysis.release_score} />
                      </div>
                      {selectedAnalysis.release_score !== null && (
                        <div className="text-right">
                          <div className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">Release Score</div>
                          <div className="text-3xl font-bold text-af-blue">{selectedAnalysis.release_score}<span className="text-lg text-slate-400">/100</span></div>
                        </div>
                      )}
                    </div>
                    {selectedAnalysis.decision_reasoning && (
                      <div className="pt-3 border-t border-slate-200 dark:border-slate-700">
                        <div className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">Reasoning</div>
                        <p className="text-sm text-slate-600 dark:text-slate-300">{selectedAnalysis.decision_reasoning}</p>
                      </div>
                    )}
                  </div>
                )}

                {/* AI RELEASE INTELLIGENCE — Best overall (primary new output) */}
                {(selectedAnalysis.release_readiness != null || selectedAnalysis.recommendation || (selectedAnalysis.risk_areas && selectedAnalysis.risk_areas.length > 0) || (selectedAnalysis.suggested_actions && selectedAnalysis.suggested_actions.length > 0)) && (
                  <div className="mb-5 p-4 rounded-xl border-2 border-emerald-200 dark:border-emerald-800 bg-emerald-50/60 dark:bg-emerald-950/30">
                    <div className="flex items-center justify-between mb-3">
                      <div>
                        <div className="text-xs font-bold uppercase tracking-[1px] text-emerald-700 dark:text-emerald-400">AI Release Intelligence</div>
                        <div className="text-[10px] text-emerald-600 dark:text-emerald-500">One AI layer before deployment • powered by LLM</div>
                      </div>
                      {selectedAnalysis.release_readiness != null && (
                        <div className="text-right">
                          <div className="text-[10px] font-semibold text-emerald-700 dark:text-emerald-400">RELEASE READINESS</div>
                          <div className="text-4xl font-bold tabular-nums text-emerald-700 dark:text-emerald-300">{selectedAnalysis.release_readiness}<span className="text-xl align-super">%</span></div>
                        </div>
                      )}
                    </div>

                    {/* Risk Areas */}
                    {selectedAnalysis.risk_areas && selectedAnalysis.risk_areas.length > 0 && (
                      <div className="mb-3">
                        <div className="text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1.5">Risk Areas</div>
                        <div className="flex flex-wrap gap-1.5">
                          {selectedAnalysis.risk_areas.slice(0, 6).map((ra: any, i: number) => (
                            <span key={i} className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full border ${ra.severity === 'high' || ra.severity === 'critical' ? 'bg-red-100 text-red-700 border-red-200 dark:bg-red-900/40 dark:text-red-300' : ra.severity === 'medium' ? 'bg-amber-100 text-amber-700 border-amber-200 dark:bg-amber-900/40' : 'bg-slate-100 text-slate-600 border-slate-200 dark:bg-slate-800'}`}>
                              {ra.name}
                              {ra.severity && <span className="opacity-70">·{ra.severity}</span>}
                            </span>
                          ))}
                        </div>
                        {selectedAnalysis.risk_areas[0]?.details && (
                          <div className="mt-1 text-xs text-slate-500 dark:text-slate-400 line-clamp-2">{selectedAnalysis.risk_areas[0].details}</div>
                        )}
                      </div>
                    )}

                    {/* Recommendation */}
                    {selectedAnalysis.recommendation && (
                      <div className="mb-3 p-2.5 rounded-lg bg-white/70 dark:bg-black/20 text-sm">
                        <span className="font-semibold text-emerald-700 dark:text-emerald-400">Recommendation: </span>
                        <span className="text-slate-700 dark:text-slate-200">{selectedAnalysis.recommendation}</span>
                      </div>
                    )}

                    {/* Action Buttons (the key "Actions" from the spec) */}
                    {selectedAnalysis.suggested_actions && selectedAnalysis.suggested_actions.length > 0 && (
                      <div>
                        <div className="text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1.5">Actions</div>
                        <div className="flex flex-wrap gap-2">
                          {selectedAnalysis.suggested_actions.map((action: string, idx: number) => {
                            const label = action.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
                            const isPrimary = ['approve', 'generate release plan'].some(k => action.toLowerCase().includes(k))
                            return (
                              <button
                                key={idx}
                                onClick={() => {
                                  if (action.toLowerCase().includes('approve')) {
                                    // Quick path: if we have a retrieval, offer to start a deployment
                                    if (selectedAnalysis.retrieval_id && selectedOrg) {
                                      // Navigate hint + pre-create deployment (simple UX)
                                      alert('Approved by AI intelligence. Creating deployment job from this retrieval...')
                                      fetch('/api/v1/deployments', {
                                        method: 'POST',
                                        headers: { 'Content-Type': 'application/json' },
                                        body: JSON.stringify({ org_id: selectedOrg, retrieval_id: selectedAnalysis.retrieval_id, deployment_type: 'validate_only', check_only: true, test_level: 'RunLocalTests' })
                                      }).then(r => r.json()).then(() => { window.location.href = '#deployments' }).catch(() => {})
                                    }
                                  } else if (action.toLowerCase().includes('hold')) {
                                    alert('AI recommends HOLD. Review risk areas and recommendations before proceeding.')
                                  } else if (action.toLowerCase().includes('fix') || action.toLowerCase().includes('suggest')) {
                                    alert('Suggested fixes: See AI Recommendations + Predicted Issues below. You can also supply a git diff on next analysis for deeper guidance.')
                                  } else if (action.toLowerCase().includes('plan') || action.toLowerCase().includes('release')) {
                                    // Scroll to or highlight the package section
                                    const el = document.querySelector('[data-suggested-package]')
                                    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' })
                                  } else {
                                    alert(`AI suggested action: ${label}`)
                                  }
                                }}
                                className={`text-xs px-3 py-1 rounded-lg font-semibold border transition active:scale-[0.985] ${isPrimary ? 'bg-emerald-600 text-white border-emerald-700 hover:bg-emerald-700' : 'bg-white dark:bg-slate-900 text-slate-700 dark:text-slate-200 border-slate-300 dark:border-slate-700 hover:bg-slate-50'}`}
                              >
                                {label}
                              </button>
                            )
                          })}
                        </div>
                        <div className="text-[10px] text-emerald-600/70 dark:text-emerald-500/70 mt-1">Clicking actions performs the step or provides guidance (prototype).</div>
                      </div>
                    )}
                  </div>
                )}
                
                {selectedAnalysis.ai_summary && (
                  <p className="text-sm text-slate-600 dark:text-slate-300 mb-4">
                    {selectedAnalysis.ai_summary}
                    {selectedAnalysis.llm_used === true && (
                      <span className="ml-2 text-[10px] font-mono bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-400 px-1.5 py-0.5 rounded align-middle">powered by LLM</span>
                    )}
                    {selectedAnalysis.llm_used === false && (
                      <span className="ml-2 text-[10px] font-mono bg-slate-200 text-slate-600 dark:bg-slate-700 dark:text-slate-400 px-1.5 py-0.5 rounded align-middle">fallback</span>
                    )}
                  </p>
                )}

                <div className="grid grid-cols-3 gap-4 text-center">
                  <div className="p-3 rounded-lg bg-slate-50 dark:bg-slate-800/50">
                    <div className="text-2xl font-bold text-af-blue">
                      {Object.values(selectedAnalysis.changed_items).flat().length}
                    </div>
                    <div className="text-xs text-slate-500">Changed</div>
                  </div>
                  <div className="p-3 rounded-lg bg-slate-50 dark:bg-slate-800/50">
                    <div className="text-2xl font-bold text-orange-500">
                      {selectedAnalysis.impacted_components
                        ? Object.values(selectedAnalysis.impacted_components).flat().length
                        : 0}
                    </div>
                    <div className="text-xs text-slate-500">Impacted</div>
                  </div>
                  <div className="p-3 rounded-lg bg-slate-50 dark:bg-slate-800/50">
                    <div className="text-2xl font-bold text-purple-500">
                      {selectedAnalysis.dependencies.length}
                    </div>
                    <div className="text-xs text-slate-500">Dependencies</div>
                  </div>
                </div>
              </div>

              {/* AI Recommendations */}
              {selectedAnalysis.ai_recommendations && selectedAnalysis.ai_recommendations.length > 0 && (
                <div className="af-panel">
                  <h3 className="font-semibold text-slate-700 dark:text-slate-200 mb-3 flex items-center gap-2">
                    AI Recommendations
                    {selectedAnalysis.llm_used === true && (
                      <span className="text-[10px] font-mono bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-400 px-1.5 py-0.5 rounded">LLM</span>
                    )}
                    {selectedAnalysis.llm_used === false && (
                      <span className="text-[10px] font-mono bg-slate-200 text-slate-600 dark:bg-slate-700 dark:text-slate-400 px-1.5 py-0.5 rounded">fallback</span>
                    )}
                  </h3>
                  <ul className="space-y-2">
                    {selectedAnalysis.ai_recommendations.map((rec, i) => (
                      <li key={i} className="flex items-start gap-2 text-sm">
                        <span className="text-af-blue shrink-0">✓</span>
                        <span className="text-slate-600 dark:text-slate-300">{rec}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Predicted Issues (from real LLM when available) */}
              {selectedAnalysis.predicted_issues && selectedAnalysis.predicted_issues.length > 0 && (
                <div className="af-panel">
                  <h3 className="font-semibold text-slate-700 dark:text-slate-200 mb-3 flex items-center gap-2">
                    Predicted Issues
                    {selectedAnalysis.llm_used === true && (
                      <span className="text-[10px] font-mono bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-400 px-1.5 py-0.5 rounded">LLM</span>
                    )}
                    {selectedAnalysis.llm_used === false && (
                      <span className="text-[10px] font-mono bg-slate-200 text-slate-600 dark:bg-slate-700 dark:text-slate-400 px-1.5 py-0.5 rounded">fallback</span>
                    )}
                  </h3>
                  <div className="space-y-3">
                    {selectedAnalysis.predicted_issues.map((issue: any, i: number) => (
                      <div key={i} className="p-3 rounded-lg bg-slate-50 dark:bg-slate-800/60 text-sm border border-slate-200 dark:border-slate-700">
                        <div className="flex items-center gap-2 mb-1">
                          <span className={`text-xs font-semibold px-2 py-0.5 rounded ${issue.severity === 'high' || issue.severity === 'critical' ? 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-400' : 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/40 dark:text-yellow-400'}`}>
                            {issue.severity?.toUpperCase() || 'MEDIUM'}
                          </span>
                          <span className="font-semibold text-slate-700 dark:text-slate-200">{issue.component}</span>
                        </div>
                        <div className="text-slate-600 dark:text-slate-300 mb-1">{issue.description}</div>
                        {issue.recommendation && (
                          <div className="text-xs text-af-blue">→ {issue.recommendation}</div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Dependency Graph Visualization */}
              {graph && (
                <div className="af-panel">
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="font-semibold text-slate-700 dark:text-slate-200">
                      Dependency Graph
                    </h3>
                    <button
                      onClick={() => {
                        const id = selectedAnalysis?.id;
                        const url = id ? `/?page=dependency-graph&analysisId=${id}` : '/?page=dependency-graph';
                        window.location.href = url;
                        // reload to let App pick up the page param
                        setTimeout(() => window.location.reload(), 50);
                      }}
                      className="text-xs px-3 py-1.5 rounded bg-af-blue text-white hover:bg-blue-700"
                    >
                      Open Full AI Dependency Graph + Auto Package Builder →
                    </button>
                  </div>
                  <div className="bg-slate-50 dark:bg-slate-900 rounded-lg p-4 mb-4">
                    <div className="grid grid-cols-4 gap-2 text-xs text-center">
                      <div>
                        <div className="font-semibold text-slate-700 dark:text-slate-300">{graph.stats.total_nodes}</div>
                        <div className="text-slate-500">Nodes</div>
                      </div>
                      <div>
                        <div className="font-semibold text-slate-700 dark:text-slate-300">{graph.stats.total_edges}</div>
                        <div className="text-slate-500">Edges</div>
                      </div>
                      <div>
                        <div className="font-semibold text-af-blue">{graph.stats.changed_count}</div>
                        <div className="text-slate-500">Changed</div>
                      </div>
                      <div>
                        <div className="font-semibold text-orange-500">{graph.stats.impacted_count}</div>
                        <div className="text-slate-500">Impacted</div>
                      </div>
                    </div>
                  </div>
                  
                  {/* Simple node list (in production, use a graph visualization library) */}
                  <div className="space-y-2 max-h-64 overflow-y-auto">
                    {graph.nodes.map(node => (
                      <div
                        key={node.id}
                        className={`p-2 rounded text-xs border ${
                          node.is_changed
                            ? 'border-af-blue bg-af-blue/5'
                            : node.is_impacted
                            ? 'border-orange-400 bg-orange-50 dark:bg-orange-900/10'
                            : 'border-slate-200 dark:border-slate-700'
                        }`}
                      >
                        <div className="font-mono font-semibold">{node.name}</div>
                        <div className="text-slate-500">{node.type}</div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Deployment Package */}
              {selectedAnalysis.suggested_package && (
                <div className="af-panel">
                  <h3 className="font-semibold text-slate-700 dark:text-slate-200 mb-3">
                    Suggested Deployment Package
                  </h3>
                  <div className="space-y-3">
                    <div>
                      <div className="text-xs text-slate-400 mb-1">Components</div>
                      <div className="text-sm space-y-1">
                        {Object.entries(selectedAnalysis.suggested_package.components).map(([type, items]: [string, any]) => (
                          <div key={type} className="flex gap-2">
                            <span className="font-semibold text-slate-600 dark:text-slate-400">{type}:</span>
                            <span className="text-slate-500">{items.length} items</span>
                          </div>
                        ))}
                      </div>
                    </div>
                    {selectedAnalysis.suggested_package.test_classes?.length > 0 && (
                      <div>
                        <div className="text-xs text-slate-400 mb-1">Test Classes</div>
                        <div className="text-sm text-slate-600 dark:text-slate-300">
                          {selectedAnalysis.suggested_package.test_classes.join(', ')}
                        </div>
                      </div>
                    )}
                    <div className="flex flex-wrap gap-2">
                      <button
                        onClick={() => downloadReleaseIntelligencePdf(selectedAnalysis.id)}
                        className="af-btn-primary text-sm"
                      >
                        Download AI Release Intelligence PDF
                      </button>
                      <button
                        onClick={() => {
                          const xml = selectedAnalysis.suggested_package?.package_xml || ''
                          const blob = new Blob([xml], { type: 'text/xml' })
                          const url = URL.createObjectURL(blob)
                          const a = document.createElement('a')
                          a.href = url
                          a.download = `package-${selectedAnalysis.id}.xml`
                          a.click()
                          URL.revokeObjectURL(url)
                        }}
                        className="af-btn-secondary text-sm"
                      >
                        Download package.xml
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}

// Made with Bob
