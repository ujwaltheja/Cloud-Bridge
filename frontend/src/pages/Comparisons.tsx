import { useState, useEffect } from 'react'

export default function ComparisonsPage() {
  const [sourceId, setSourceId] = useState('')
  const [targetId, setTargetId] = useState('')
  const [result, setResult] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [retrievalOptions, setRetrievalOptions] = useState<any[]>([])
  const [orgNames, setOrgNames] = useState<Record<string, string>>({})
  const [fullDiff, setFullDiff] = useState<any>(null)

  useEffect(() => {
    Promise.all([
      fetch('/api/v1/retrievals').then(r => r.json()),
      fetch('/api/v1/orgs').then(r => r.json()),
    ]).then(([retrievals, orgs]) => {
      const nameMap: Record<string, string> = {}
      if (Array.isArray(orgs)) orgs.forEach((o: any) => { nameMap[o.id] = o.name })
      setOrgNames(nameMap)
      setRetrievalOptions(
        Array.isArray(retrievals) ? retrievals.filter((r: any) => r.status === 'success') : []
      )
    }).catch(() => {})
  }, [])

  const runComparison = async () => {
    if (!sourceId || !targetId) { alert('Please select both retrievals'); return }
    setLoading(true); setResult(null); setFullDiff(null)
    try {
      const res = await fetch('/api/v1/comparisons', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source_retrieval_id: sourceId, target_retrieval_id: targetId }),
      })
      if (!res.ok) { alert('Error: ' + await res.text()); return }
      setResult(await res.json())
    } catch (e) { alert('Error: ' + e) }
    setLoading(false)
  }

  const viewDiff = async () => {
    if (!result?.id) return
    try {
      const res = await fetch(`/api/v1/comparisons/${result.id}`)
      if (!res.ok) { alert('Error: ' + await res.text()); return }
      const full = await res.json()
      if (full.diff_artifact_key) {
        const artifactRes = await fetch(`/api/v1/retrievals/${result.id}/artifact`)
        setFullDiff(artifactRes.ok ? await artifactRes.json() : full)
      } else {
        alert('No diff artifact stored yet.')
      }
    } catch (e) { alert('Error: ' + e) }
  }

  return (
    <div className="max-w-5xl mx-auto px-6 py-10">
      <h1 className="font-display text-3xl font-bold af-gradient-text mb-1">Metadata Comparison</h1>
      <p className="text-sm text-slate-500 dark:text-slate-400 mb-8">Diff two metadata retrievals to spot changes before deploying.</p>

      <div className="af-panel">
        <h2 className="font-semibold text-slate-700 dark:text-slate-200 mb-4">Compare Two Retrievals</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-5">
          <div>
            <label className="block text-xs text-slate-400 mb-1 font-semibold uppercase tracking-wide">Source</label>
            <select className="af-input text-sm" value={sourceId} onChange={e => setSourceId(e.target.value)}>
              <option value="">Select Source…</option>
              {retrievalOptions.map(r => (
                <option key={r.id} value={r.id}>
                  {orgNames[r.org_id] ?? r.org_id.slice(0, 8)} — {r.created_at ? new Date(r.created_at).toLocaleString() : r.id.slice(0, 8)}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1 font-semibold uppercase tracking-wide">Target</label>
            <select className="af-input text-sm" value={targetId} onChange={e => setTargetId(e.target.value)}>
              <option value="">Select Target…</option>
              {retrievalOptions.map(r => (
                <option key={r.id} value={r.id}>
                  {orgNames[r.org_id] ?? r.org_id.slice(0, 8)} — {r.created_at ? new Date(r.created_at).toLocaleString() : r.id.slice(0, 8)}
                </option>
              ))}
            </select>
          </div>
        </div>
        <button onClick={runComparison} disabled={loading || !sourceId || !targetId} className="af-btn-primary">
          {loading ? 'Comparing…' : 'Run Comparison'}
        </button>
        <p className="text-xs text-slate-400 mt-3">Tip: Only successful retrievals appear in the dropdowns above.</p>
      </div>

      {result && (
        <div className="af-panel">
          <h3 className="font-semibold text-slate-700 dark:text-slate-200 mb-5">Comparison Result</h3>
          <div className="grid grid-cols-3 gap-4 mb-6">
            <div className="rounded-xl p-4 bg-emerald-50 border border-emerald-200 dark:bg-emerald-900/20 dark:border-emerald-800">
              <div className="text-xs text-emerald-600 dark:text-emerald-400 font-semibold uppercase tracking-wide mb-1">Added</div>
              <div className="text-3xl font-bold text-emerald-600 dark:text-emerald-400">{result.diff_summary?.added_count || 0}</div>
            </div>
            <div className="rounded-xl p-4 bg-red-50 border border-red-200 dark:bg-red-900/20 dark:border-red-800">
              <div className="text-xs text-red-600 dark:text-red-400 font-semibold uppercase tracking-wide mb-1">Removed</div>
              <div className="text-3xl font-bold text-red-600 dark:text-red-400">{result.diff_summary?.removed_count || 0}</div>
            </div>
            <div className="rounded-xl p-4 bg-amber-50 border border-amber-200 dark:bg-amber-900/20 dark:border-amber-800">
              <div className="text-xs text-amber-600 dark:text-amber-400 font-semibold uppercase tracking-wide mb-1">Modified</div>
              <div className="text-3xl font-bold text-amber-600 dark:text-amber-400">{result.diff_summary?.modified_count || 0}</div>
            </div>
          </div>

          <div className="flex items-center gap-3 mb-5">
            <button onClick={viewDiff} className="af-btn-secondary text-sm">View Full Diff</button>
            {result.diff_artifact_key && (
              <span className="af-mono-badge">{result.diff_artifact_key}</span>
            )}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <div className="text-xs font-semibold text-emerald-600 dark:text-emerald-400 uppercase tracking-wide mb-2">
                Added ({result.diff_summary?.added_count || 0})
              </div>
              <div className="rounded-xl bg-slate-950 dark:bg-black p-3 text-sm max-h-56 overflow-auto font-mono">
                {result.diff_summary?.added?.length > 0
                  ? result.diff_summary.added.map((item: string, i: number) => (
                      <div key={i} className="text-emerald-400">+ {item}</div>
                    ))
                  : <span className="text-slate-500">None</span>}
              </div>
            </div>
            <div>
              <div className="text-xs font-semibold text-red-500 uppercase tracking-wide mb-2">
                Removed ({result.diff_summary?.removed_count || 0})
              </div>
              <div className="rounded-xl bg-slate-950 dark:bg-black p-3 text-sm max-h-56 overflow-auto font-mono">
                {result.diff_summary?.removed?.length > 0
                  ? result.diff_summary.removed.map((item: string, i: number) => (
                      <div key={i} className="text-red-400">- {item}</div>
                    ))
                  : <span className="text-slate-500">None</span>}
              </div>
            </div>
          </div>

          <details className="mt-5">
            <summary className="cursor-pointer text-xs text-slate-400 hover:text-slate-300">Raw response</summary>
            <pre className="text-xs overflow-auto bg-black rounded-xl p-4 mt-2 max-h-72 font-mono">
              {JSON.stringify(result, null, 2)}
            </pre>
          </details>

          {fullDiff && (
            <div className="mt-6 border-t border-slate-200 dark:border-white/10 pt-5">
              <h4 className="font-semibold text-af-purple mb-4">Full Diff Details</h4>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm mb-3">
                <div>
                  <div className="text-xs font-semibold text-emerald-500 uppercase tracking-wide mb-2">Added</div>
                  <div className="bg-black rounded-xl p-3 max-h-64 overflow-auto text-emerald-300 text-xs font-mono leading-snug">
                    {(fullDiff.diff_summary?.added || fullDiff.added)?.map((item: string, i: number) => <div key={i}>+ {item}</div>) || <span className="text-slate-500">None</span>}
                  </div>
                </div>
                <div>
                  <div className="text-xs font-semibold text-red-500 uppercase tracking-wide mb-2">Removed</div>
                  <div className="bg-black rounded-xl p-3 max-h-64 overflow-auto text-red-300 text-xs font-mono leading-snug">
                    {(fullDiff.diff_summary?.removed || fullDiff.removed)?.map((item: string, i: number) => <div key={i}>- {item}</div>) || <span className="text-slate-500">None</span>}
                  </div>
                </div>
              </div>
              <details className="mt-2">
                <summary className="cursor-pointer text-xs text-slate-400">Raw diff data</summary>
                <pre className="text-xs overflow-auto bg-black rounded-xl p-4 mt-2 max-h-96 font-mono">{JSON.stringify(fullDiff, null, 2)}</pre>
              </details>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
