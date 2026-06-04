import { useState, useEffect, useRef, Fragment } from 'react'

function StatusPill({ status }: { status: string }) {
  const active = ['queued', 'running', 'validating', 'deploying', 'pmd_check_queued', 'pmd_checking'].includes(status)
  const cls =
    status === 'success'    ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-400' :
    status === 'failed'     ? 'bg-red-100 text-red-600 dark:bg-red-900/40 dark:text-red-400' :
    status === 'deploying' || status === 'validating' || status === 'running' || status === 'queued' || status === 'pmd_check_queued' || status === 'pmd_checking' ? 'bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-af-blue' :
    'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-400'
  return <span className={`inline-flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded-full ${cls}`}>{active && <span className="w-1.5 h-1.5 rounded-full bg-current animate-pulse" />} {status}</span>
}

export default function DeploymentsPage() {
  const [deployments, setDeployments] = useState<any[]>([])
  const [orgs, setOrgs] = useState<any[]>([])
  const [retrievals, setRetrievals] = useState<any[]>([])
  const [selectedOrg, setSelectedOrg] = useState('')
  const [selectedRetrieval, setSelectedRetrieval] = useState('')
  const [deploymentType, setDeploymentType] = useState('validate_only')
  const [checkOnly, setCheckOnly] = useState(true)
  const [testLevel, setTestLevel] = useState('RunLocalTests')
  const [runTestsInput, setRunTestsInput] = useState('')  // comma separated for specified tests
  const [loading, setLoading] = useState(false)
  const [formError, setFormError] = useState('')
  const [expandedJob, setExpandedJob] = useState<string | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // Toggle like Retrievals: Deployment (form + recent 3) | History (full list)
  const [view, setView] = useState<'deployment' | 'history'>('deployment')
  // 3-step Salesforce-like path for Deployment (1. Org, 2. Retrieval, 3. Configure & Start)
  const [currentStep, setCurrentStep] = useState(1)

  // AI Release Intelligence pre-flight for the current retrieval (makes "one AI layer before every deployment")
  const [aiIntel, setAiIntel] = useState<any | null>(null)
  const [aiLoading, setAiLoading] = useState(false)
  const aiPollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const fetchData = async () => {
    const [orgsRes, retrievalsRes, depsRes] = await Promise.all([
      fetch('/api/v1/orgs'), fetch('/api/v1/retrievals'), fetch('/api/v1/deployments')
    ])
    if (orgsRes.ok) setOrgs(await orgsRes.json())
    if (retrievalsRes.ok) setRetrievals(await retrievalsRes.json())
    if (depsRes.ok) setDeployments(await depsRes.json())
  }

  const hasActiveJobs = Array.isArray(deployments) && deployments.some((d: any) => ['queued','running','validating','deploying','pmd_check_queued','pmd_checking'].includes(d.status))

  // Auto-poll every 3s while any deployment job is active (like Retrievals page).
  useEffect(() => {
    if (hasActiveJobs && !pollRef.current) {
      pollRef.current = setInterval(async () => {
        await fetchData()
        // Note: we re-compute hasActiveJobs on next render via state change
      }, 3000)
    } else if (!hasActiveJobs && pollRef.current) {
      clearInterval(pollRef.current); pollRef.current = null
    }
    return () => { if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null } }
  }, [hasActiveJobs])

  useEffect(() => {
    fetchData()
    const params = new URLSearchParams(window.location.search)
    const preOrg = params.get('org'); const preRetrieval = params.get('retrieval')
    if (preOrg) setSelectedOrg(preOrg)
    if (preRetrieval) setSelectedRetrieval(preRetrieval)
  }, [])

  const createDeployment = async () => {
    if (!selectedOrg) { alert('Please select an org'); return }
    setLoading(true)
    setFormError('')
    const runTests = runTestsInput.trim() ? runTestsInput.split(',').map(s => s.trim()).filter(Boolean) : null
    const effectiveCheckOnly = checkOnly || deploymentType === 'validate_only'
    try {
      // Create job + immediately start PMD pre-check (via /run action=pmd_check). Then reset wizard to step 1.
      // Job appears in Recent Deployments below with live progress.
      const res = await fetch('/api/v1/deployments', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          org_id: selectedOrg,
          retrieval_id: selectedRetrieval || null,
          deployment_type: deploymentType,
          artifact_key: null,
          check_only: effectiveCheckOnly,
          test_level: testLevel || (effectiveCheckOnly ? 'RunLocalTests' : null),
          run_tests: runTests,
          enable_pmd_check: true,
          pmd_block_on_violation: false,
          // Link the AI Release Intelligence that was run for this retrieval (stored in options for history)
          ...(aiIntel?.id ? { intelligence_analysis_id: aiIntel.id, intelligence_readiness: aiIntel.release_readiness, intelligence_decision: aiIntel.go_no_go_decision } : {}),
        }),
      })
      if (res.ok) {
        let jobData: any = null
        try { jobData = await res.json() } catch {}
        if (jobData) {
          // Optimistically add the new pending job at the top of history so it is "added below" instantly.
          setDeployments((prev: any[]) => {
            const filtered = prev.filter((d: any) => d.id !== jobData.id)
            return [jobData, ...filtered]
          })
          setExpandedJob(jobData.id)

          // Auto-trigger PMD check first; user then decides Run Validation / Run Deployment.
          try {
            const runRes = await fetch(`/api/v1/deployments/${jobData.id}/run`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ action: 'pmd_check' }),
            });
            if (runRes.ok) {
              const runData = await runRes.json().catch(() => null);
              if (runData) {
                setDeployments((prev: any[]) => prev.map((d: any) => d.id === jobData.id ? runData : d));
              }
            }
          } catch (e) {
            // still queued, polling will pick up progress
          }
        }
        await fetchData()
        // Reset wizard back to first step after job created + started
        setCurrentStep(1)
      } else {
        const txt = await res.text().catch(() => '')
        setFormError('Failed to create deployment job: ' + txt)
      }
    } catch (e: any) {
      setFormError('Error creating deployment job: ' + (e?.message || e))
    }
    setLoading(false)
  }

  // Run the AI Release Intelligence for the selected retrieval (core of "One AI layer before every deployment")
  const runAiPrecheck = async () => {
    if (!selectedOrg || !selectedRetrieval) return
    setAiLoading(true)
    setAiIntel(null)
    try {
      // Use quick-analyze for convenience (create + run in one)
      const res = await fetch('/api/v1/impact-analysis/quick-analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          org_id: selectedOrg,
          retrieval_id: selectedRetrieval,
          analysis_type: 'pre_deployment',
          changed_items: {},
        }),
      })
      if (!res.ok) throw new Error('Failed to start AI analysis')
      let intel: any = await res.json()
      setAiIntel(intel)

      // Poll until completed (LLM can take time)
      if (aiPollRef.current) clearInterval(aiPollRef.current)
      aiPollRef.current = setInterval(async () => {
        try {
          const pollRes = await fetch(`/api/v1/impact-analysis/${intel.id}`)
          if (!pollRes.ok) return
          const updated = await pollRes.json()
          setAiIntel(updated)
          if (updated.status === 'completed' || updated.status === 'failed') {
            if (aiPollRef.current) {
              clearInterval(aiPollRef.current)
              aiPollRef.current = null
            }
            setAiLoading(false)
          }
        } catch {}
      }, 1800)
    } catch (e: any) {
      alert('AI pre-check failed: ' + (e?.message || e))
      setAiLoading(false)
    }
  }

  // Cleanup AI poll
  useEffect(() => {
    return () => {
      if (aiPollRef.current) {
        clearInterval(aiPollRef.current)
        aiPollRef.current = null
      }
    }
  }, [])

  // When retrieval changes, clear previous intel (user can re-run for the new package)
  useEffect(() => {
    setAiIntel(null)
    if (aiPollRef.current) {
      clearInterval(aiPollRef.current)
      aiPollRef.current = null
    }
  }, [selectedRetrieval])

  const runDeployment = async (id: string, action: 'pmd_check' | 'validate' | 'deploy' = 'validate') => {
    setFormError('')
    try {
      const res = await fetch(`/api/v1/deployments/${id}/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action }),
      })
      if (res.ok) {
        const updated = await res.json()
        // Update the item in list
        setDeployments((prev: any[]) => prev.map(d => d.id === id ? updated : d))
        // Auto expand to show progress below
        setExpandedJob(id)
        // Ensure polling is active
        if (!pollRef.current) {
          pollRef.current = setInterval(async () => { await fetchData() }, 3000)
        }
        // Force a refresh shortly after to catch early task state changes (esp. in dev)
        setTimeout(() => { fetchData().catch(()=>{}) }, 800)
      } else {
        const txt = await res.text().catch(() => '')
        setFormError('Failed to start action: ' + txt)
      }
    } catch (e: any) {
      setFormError('Error starting action: ' + (e?.message || e))
    }
  }

  const downloadPmdReport = async (deploymentId: string) => {
    try {
      const res = await fetch(`/api/v1/deployments/${deploymentId}/pmd/report/pdf`)
      if (!res.ok) {
        const txt = await res.text().catch(() => '')
        throw new Error(`HTTP ${res.status} ${txt}`)
      }
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `ibm-salesforce-pmd-analysis-${deploymentId}.pdf`
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      alert('Failed to download PMD report: ' + e)
    }
  }

  const toggleJob = (id: string) => {
    setExpandedJob(expandedJob === id ? null : id)
  }

  const advanceStatus = async (id: string, newStatus: string) => {
    try {
      await fetch(`/api/v1/deployments/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: newStatus }),
      })
      await fetchData()
    } catch { alert('Failed to update status') }
  }

  // --- Error summary for nice display in headers and simple cards ---
  const getDeployErrorSummary = (err: string | undefined): string => {
    if (!err) return '';
    if (err.includes('FailedValidationError') || err.includes('test coverage')) {
      const cov = err.match(/is (\d+)%/);
      const testMatches = err.match(/,[A-Za-z0-9_]+\.[A-Za-z0-9_]+/g) || [];
      const tests = testMatches.length;
      return `Validation failed${cov ? ` — ${cov[1]}% coverage (need 75%)` : ''}${tests ? ` + ${tests} failing test(s)` : ''}`;
    }
    return err.split('\n')[0].slice(0, 100) + (err.length > 100 ? '…' : '');
  };

  const goToStep = (step: number) => setCurrentStep(step);

  const canStartDeployment = !!selectedOrg; // retrieval is recommended but optional

  const parseFailedValidation = (err: string) => {
    const covMatch = err.match(/Average test coverage across all Apex Classes and Triggers is (\d+)%/);
    const coverage = covMatch ? parseInt(covMatch[1], 10) : null;
    const idMatch = err.match(/the deployment \(([^\)]+)\)/);
    const deployId = idMatch ? idMatch[1] : null;
    const testFailures: Array<{name: string, message: string}> = [];
    const dueToPart = err.split(/Due To:/i)[1] || err;
    const chunks = dueToPart.split(/,(?=[A-Z][A-Za-z0-9_]+\.[A-Za-z][A-Za-z0-9_]*\s*-)/);
    for (const chunk of chunks) {
      const tm = chunk.match(/([A-Za-z][A-Za-z0-9_]*\.[A-Za-z][A-Za-z0-9_]*)\s*-\s*([\s\S]*)/);
      if (tm) {
        testFailures.push({ name: tm[1], message: tm[2].trim() });
      }
    }
    if (testFailures.length === 0) {
      const lines = dueToPart.split(/[\r\n,]+/);
      for (const line of lines) {
        const tm = line.match(/([A-Za-z][A-Za-z0-9_]*\.[A-Za-z][A-Za-z0-9_]*)\s*-\s*(.*)/);
        if (tm) testFailures.push({ name: tm[1], message: tm[2].trim() });
      }
    }
    return { coverage, deployId, testFailures };
  };

  const getPmdSummary = (dep: any) => {
    const pmd = dep?.options?.pmd_result
    if (!pmd) return null

    const totals = pmd?.totals && typeof pmd.totals === 'object' ? pmd.totals : {}
    const toNum = (v: any) => {
      const n = Number(v)
      return Number.isFinite(n) ? n : 0
    }

    const critical = toNum(totals.critical)
    const high = toNum(totals.high)
    const medium = toNum(totals.medium)
    const low = toNum(totals.low)
    let total = toNum(totals.total_issues)

    if (!total) {
      total = critical + high + medium + low
      if (!total && Array.isArray(pmd.issues)) {
        total = pmd.issues.length
      }
    }

    return {
      critical,
      high,
      medium,
      low,
      total,
      passed: total === 0,
    }
  }

  return (
    <div className="max-w-5xl mx-auto px-6 py-10">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="font-display text-3xl font-bold af-gradient-text mb-1">Deployments</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">Deploy metadata to Salesforce orgs. Select org + retrieval, configure, start deployment.</p>
        </div>

        {/* Top-right toggle: Deployment (form + recent) | History (full) */}
        <div className="inline-flex rounded-lg border border-slate-200 dark:border-white/10 overflow-hidden text-sm shadow-sm">
          <button
            onClick={() => setView('deployment')}
            className={`px-3.5 py-1.5 font-semibold transition-colors ${view === 'deployment' ? 'bg-af-blue text-white' : 'bg-white dark:bg-af-darkcard hover:bg-slate-50 dark:hover:bg-slate-800'}`}
          >
            Deployment
          </button>
          <button
            onClick={() => setView('history')}
            className={`px-3.5 py-1.5 font-semibold transition-colors ${view === 'history' ? 'bg-af-blue text-white' : 'bg-white dark:bg-af-darkcard hover:bg-slate-50 dark:hover:bg-slate-800'}`}
          >
            Jobs History
          </button>
        </div>
      </div>

      {view === 'deployment' ? (
        <>
          <div className="af-panel">
            {/* 3-step Salesforce-like horizontal path for Deployment */}
            <div className="mb-5">
              <div className="flex items-center gap-0 mb-1">
                {[1, 2, 3].map((s, idx) => (
                  <Fragment key={s}>
                    <button
                      onClick={() => goToStep(s)}
                      className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold border-2 transition-all
                        ${currentStep === s
                          ? 'bg-af-blue text-white border-af-blue scale-105'
                          : currentStep > s
                            ? 'bg-emerald-500 text-white border-emerald-500'
                            : 'bg-white dark:bg-slate-800 text-slate-500 border-slate-300 hover:border-af-blue/50'}`}
                      title={`Go to step ${s}`}
                    >
                      {s}
                    </button>
                    {idx < 2 && (
                      <div className={`flex-1 h-[3px] mx-1 rounded ${currentStep > s ? 'bg-emerald-500' : 'bg-slate-200 dark:bg-slate-700'}`} />
                    )}
                  </Fragment>
                ))}
              </div>
              <div className="flex justify-between text-[10px] text-slate-500 px-1">
                <div>1. Select Org</div>
                <div>2. Select Retrieval</div>
                <div>3. Configure &amp; Start</div>
              </div>
            </div>

            {/* Step 1: Org */}
            {currentStep === 1 && (
              <div>
                <label className="block text-sm font-semibold mb-1.5">Select connected Org</label>
                <select
                  className="af-input"
                  value={selectedOrg}
                  onChange={e => setSelectedOrg(e.target.value)}
                >
                  <option value="">— Select an org —</option>
                  {(Array.isArray(orgs) ? orgs : []).map((o: any) => (
                    <option key={o?.id} value={o?.id}>{o?.name} {o?.username ? `(${o?.username})` : ''}</option>
                  ))}
                </select>
                {(Array.isArray(orgs) ? orgs.length : 0) === 0 && (
                  <p className="mt-1 text-xs text-amber-600">No orgs connected yet. Go to the Orgs tab to connect one.</p>
                )}
              </div>
            )}

            {/* Step 2: Select Retrieval */}
            {currentStep === 2 && (
              <div>
                <label className="block text-sm font-semibold mb-1.5">Select successful Retrieval (recommended — provides the source to deploy)</label>
                <select
                  className="af-input"
                  value={selectedRetrieval}
                  onChange={e => setSelectedRetrieval(e.target.value)}
                >
                  <option value="">— No retrieval (use other source later) —</option>
                  {retrievals.filter((r: any) => r.status === 'success').map((r: any) => (
                    <option key={r.id} value={r.id}>Retrieval {r.id}</option>
                  ))}
                </select>
                <p className="mt-2 text-xs text-slate-500">Deployments work best when linked to a prior successful retrieval (the source zip will be used automatically).</p>

                {/* AI Release Intelligence pre-flight — the "one AI layer before every deployment" */}
                <div className="mt-4 p-3 rounded-lg border border-emerald-200 dark:border-emerald-800 bg-emerald-50/50 dark:bg-emerald-950/20">
                  <div className="flex items-center justify-between mb-2">
                    <div className="text-sm font-semibold text-emerald-700 dark:text-emerald-400">AI Release Intelligence Pre-Check</div>
                    <button
                      onClick={runAiPrecheck}
                      disabled={!selectedRetrieval || aiLoading}
                      className="text-xs px-3 py-1 rounded bg-emerald-600 text-white disabled:opacity-50"
                    >
                      {aiLoading ? 'Analyzing with LLM...' : aiIntel ? 'Re-run AI Check' : 'Run AI Release Intelligence'}
                    </button>
                  </div>

                  {aiIntel && (
                    <div className="text-xs space-y-1.5">
                      {aiIntel.release_readiness != null && (
                        <div>
                          <span className="font-mono font-bold text-emerald-700 dark:text-emerald-300 text-base">{aiIntel.release_readiness}%</span>
                          <span className="ml-1 text-emerald-600 dark:text-emerald-400">Release Readiness</span>
                          {aiIntel.go_no_go_decision && <span className="ml-2 px-1.5 py-0.5 rounded bg-white/70 dark:bg-black/30">{aiIntel.go_no_go_decision}</span>}
                        </div>
                      )}
                      {aiIntel.recommendation && <div><span className="font-semibold">Rec:</span> {aiIntel.recommendation}</div>}
                      {aiIntel.risk_areas && aiIntel.risk_areas.length > 0 && (
                        <div className="flex flex-wrap gap-1">
                          {aiIntel.risk_areas.slice(0, 3).map((ra: any, i: number) => (
                            <span key={i} className="px-1.5 py-0 rounded bg-white/70 dark:bg-black/30 text-[10px]">{ra.name}</span>
                          ))}
                        </div>
                      )}
                      {aiIntel.suggested_actions && aiIntel.suggested_actions.length > 0 && (
                        <div className="pt-1 flex gap-1 flex-wrap">
                          {aiIntel.suggested_actions.map((act: string, i: number) => (
                            <span key={i} className="text-[10px] px-2 py-0.5 border rounded">{act.replace(/_/g, ' ')}</span>
                          ))}
                        </div>
                      )}
                      <div className="text-[10px] text-emerald-600 dark:text-emerald-500">Full details in the AI Release Intel tab. Low readiness? Consider fixes first.</div>
                    </div>
                  )}
                  {!aiIntel && !aiLoading && selectedRetrieval && (
                    <div className="text-xs text-slate-500">Run the AI check to see readiness %, risk areas, recommendation and suggested actions before deploying.</div>
                  )}
                </div>
              </div>
            )}

            {/* Step 3: Configure & Start */}
            {currentStep === 3 && (
              <div>
                <div className="mb-3">
                  <div className="text-sm font-semibold mb-1.5">Deployment Type</div>
                  <select className="af-input" value={deploymentType} onChange={e => setDeploymentType(e.target.value)}>
                    <option value="validate_only">Validate Only (check-only / dry-run)</option>
                    <option value="quick_deploy">Quick Deploy (after prior validation)</option>
                    <option value="full_deploy">Full Deploy</option>
                  </select>
                </div>

                <div className="flex gap-3 mb-3">
                  <label className="text-sm flex items-center gap-2 text-slate-600 dark:text-slate-300">
                    <input type="checkbox" checked={checkOnly} onChange={e=>setCheckOnly(e.target.checked)} /> Check Only / Validate
                  </label>
                  <select className="af-input flex-1" value={testLevel} onChange={e=>setTestLevel(e.target.value)}>
                    <option value="RunLocalTests">RunLocalTests (default)</option>
                    <option value="RunAllTestsInOrg">RunAllTestsInOrg</option>
                    <option value="RunSpecifiedTests">RunSpecifiedTests</option>
                    <option value="NoTestRun">NoTestRun</option>
                  </select>
                </div>

                {testLevel === 'RunSpecifiedTests' && (
                  <input
                    className="af-input mb-3"
                    placeholder="Comma-separated test classes e.g. MyTest,AccountTest"
                    value={runTestsInput}
                    onChange={e=>setRunTestsInput(e.target.value)}
                  />
                )}

                <button
                  onClick={createDeployment}
                  disabled={!canStartDeployment || loading}
                  className="af-btn-primary w-full py-2.5 text-base mt-3"
                  title="Create the deployment job and start PMD pre-check"
                >
                  {loading ? 'Starting PMD pre-check…' : 'Start Deployment (PMD First)'}
                </button>
                {formError && <p className="text-xs text-red-600 mt-1">{formError}</p>}
                <p className="mt-2 text-xs text-slate-500">A job is created, PMD runs first, then you can choose Run Validation or Run Deployment after reviewing PMD results.</p>
              </div>
            )}

            {/* Navigation for the path */}
            <div className="flex justify-between mt-4 pt-3 border-t border-slate-200 dark:border-white/10">
              {currentStep > 1 ? (
                <button onClick={() => goToStep(currentStep - 1)} className="px-3 py-1 text-sm rounded border">← Back</button>
              ) : <div />}
              {currentStep < 3 ? (
                <button onClick={() => goToStep(currentStep + 1)} className="px-3 py-1 text-sm rounded bg-af-blue text-white">Next →</button>
              ) : (
                <button onClick={() => { setCurrentStep(1); }} className="px-3 py-1.5 rounded border">Restart Path</button>
              )}
            </div>
          </div>

          {/* 3 Recent Deployments below form, like Retrievals */}
          <div className="mt-6">
            <div className="flex items-baseline justify-between mb-2">
              <div className="font-semibold text-sm">Recent Deployments (last 3)</div>
              <button onClick={() => setView('history')} className="text-xs text-af-blue hover:underline">View full history →</button>
            </div>
            {deployments.length === 0 ? (
              <div className="af-card p-4 text-xs text-slate-500">No deployment jobs yet. Complete the path (the Start button is in step 3).</div>
            ) : (
              <div className="space-y-2">
                {deployments.slice(0, 3).map((dep: any) => {
                  const canRun = dep.status === 'pending';
                  const hasPmd = !!dep.options?.pmd_result;
                  return (
                    <div key={dep.id} className="af-card p-3 text-sm flex flex-col sm:flex-row sm:items-center gap-2">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <StatusPill status={dep.status} />
                          <span className="text-xs text-slate-500">{dep.deployment_type}</span>
                        </div>
                        <div className="af-mono-badge text-[10px] mt-0.5">{dep.id}</div>
                        {dep.retrieval_id && <div className="text-[10px] text-af-blue">Linked: {dep.retrieval_id}</div>}
                        {/* Show AI Release Intelligence summary if this deploy was pre-checked */}
                        {dep.options && (dep.options.intelligence_readiness != null || dep.options.intelligence_decision) && (
                          <div className="text-[10px] mt-0.5 inline-flex items-center gap-1 text-emerald-700 dark:text-emerald-400">
                            AI: {dep.options.intelligence_readiness ?? '?'}%
                            {dep.options.intelligence_decision && <span className="font-mono">({dep.options.intelligence_decision})</span>}
                          </div>
                        )}
                        {dep.error_message && dep.status==='failed' && (
                          <div className="text-[10px] text-red-400 mt-0.5 truncate">{getDeployErrorSummary(dep.error_message)}</div>
                        )}
                      </div>
                      <div className="flex gap-1.5 shrink-0">
                        {canRun && (
                          hasPmd ? (
                            <>
                              <button onClick={() => runDeployment(dep.id, 'validate')} className="px-2.5 py-1 text-xs rounded bg-sky-600 text-white hover:bg-sky-700">
                                Run Validation
                              </button>
                              <button onClick={() => runDeployment(dep.id, 'deploy')} className="px-2.5 py-1 text-xs rounded bg-emerald-600 text-white hover:bg-emerald-700">
                                Run Deployment
                              </button>
                            </>
                          ) : (
                            <button onClick={() => runDeployment(dep.id, 'pmd_check')} className="px-2.5 py-1 text-xs rounded bg-indigo-600 text-white hover:bg-indigo-700">
                              Run PMD Check
                            </button>
                          )
                        )}
                        <button onClick={() => { setExpandedJob(dep.id); setView('history'); }} className="px-2.5 py-1 text-xs rounded border border-slate-300 dark:border-white/20 hover:bg-slate-50 dark:hover:bg-slate-800">
                          Details
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </>
      ) : (
        /* Full history */
        <>
          <h2 className="font-semibold text-slate-700 dark:text-slate-200 mb-3">Deployment History (Recent Jobs)</h2>
      <p className="text-xs text-slate-500 mb-2">Full list of all deployment jobs. Use Run on pending ones. Expand any job for live progress, steps, beautiful error analysis (coverage % gauge + failing tests list when validation fails).</p>
      {deployments.length === 0 ? (
        <div className="af-card p-8 text-center text-slate-400">No deployments yet. Switch to Deployment tab to start one (Start button only on last step).</div>
      ) : (
        <div className="space-y-3">
          {deployments.map((dep: any) => {
            const isExpanded = expandedJob === dep.id
            const canRun = dep.status === 'pending'
            const pmdSummary = getPmdSummary(dep)
            const hasPmd = !!dep.options?.pmd_result
            return (
              <div key={dep.id} className="af-card p-5">
                <div className="flex justify-between items-start gap-4 cursor-pointer" onClick={() => toggleJob(dep.id)}>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <StatusPill status={dep.status} />
                      <span className="text-xs text-slate-500 dark:text-slate-400 font-semibold">{dep.deployment_type}</span>
                    </div>
                    {dep.options && (dep.options.test_level || dep.options.check_only) && (
                      <div className="text-[10px] text-slate-500 dark:text-slate-400 mb-0.5">
                        {dep.options.check_only ? 'validate' : 'deploy'} · {dep.options.test_level || 'default tests'}
                        {dep.options.run_tests && dep.options.run_tests.length ? ` · ${dep.options.run_tests.length} specified` : ''}
                      </div>
                    )}
                    {dep.options?.enable_pmd_check && (
                      <div className="text-[10px] text-indigo-400 mb-0.5">
                        PMD pre-check: {pmdSummary ? (pmdSummary.passed ? 'passed (report ready)' : `${pmdSummary.total} issue(s) found`) : 'enabled'}
                      </div>
                    )}
                    <div className="af-mono-badge inline-block mb-1">{dep.id}</div>
                    {dep.retrieval_id && (
                      <div className="text-xs text-af-blue mt-1">Linked retrieval: <span className="font-mono">{dep.retrieval_id}</span></div>
                    )}
                    {dep.error_message && dep.status === 'failed' && (
                      <div className="text-xs text-red-400 mt-1 overflow-hidden text-ellipsis" style={{display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical'}}>
                        {getDeployErrorSummary(dep.error_message)}
                      </div>
                    )}
                    <div className="text-[10px] text-slate-400 mt-0.5">{isExpanded ? 'Click to collapse ▲' : 'Click to expand for progress/details ▼'}</div>
                  </div>
                  <div className="flex gap-1.5 shrink-0 flex-wrap justify-end" onClick={e => e.stopPropagation()}>
                    {canRun && (
                      hasPmd ? (
                        <>
                          <button
                            onClick={() => runDeployment(dep.id, 'validate')}
                            className="px-3 py-1 rounded text-xs font-semibold bg-sky-600 text-white hover:bg-sky-700 transition"
                          >
                            Run Validation
                          </button>
                          <button
                            onClick={() => runDeployment(dep.id, 'deploy')}
                            className="px-3 py-1 rounded text-xs font-semibold bg-emerald-600 text-white hover:bg-emerald-700 transition"
                          >
                            Run Deployment
                          </button>
                        </>
                      ) : (
                        <button
                          onClick={() => runDeployment(dep.id, 'pmd_check')}
                          className="px-3 py-1 rounded text-xs font-semibold bg-indigo-600 text-white hover:bg-indigo-700 transition"
                        >
                          Run PMD Check
                        </button>
                      )
                    )}
                    {/* Legacy manual controls kept only for recovery on active/failed jobs */}
                    {!canRun && dep.status !== 'success' && dep.status !== 'failed' && (
                      <button onClick={() => advanceStatus(dep.id, 'success')} className="px-2 py-0.5 text-[10px] text-slate-400 hover:text-slate-200">Force success</button>
                    )}
                  </div>
                </div>

                {/* Beautiful Progress / Details shown BELOW the job header when expanded */}
                {isExpanded && (
                  <div className="mt-4 pt-4 border-t border-slate-600/60">
                    <div className="flex items-center justify-between mb-3">
                      <div className="flex items-center gap-2">
                        <span className="text-base">📋</span>
                        <span className="font-semibold text-slate-200">Progress & Results</span>
                      </div>
                      <button 
                        onClick={(e) => { e.stopPropagation(); fetchData(); }}
                        className="text-[10px] px-2 py-0.5 rounded bg-slate-700 hover:bg-slate-600 text-slate-300 transition"
                      >
                        ↻ Refresh
                      </button>
                    </div>

                    {/* Status summary card */}
                    <div className={`rounded-lg p-3 mb-3 border ${dep.status === 'success' ? 'bg-emerald-900/30 border-emerald-700/50' : dep.status === 'failed' ? 'bg-red-900/30 border-red-700/50' : 'bg-slate-800/60 border-slate-600/50'}`}>
                      <div className="flex items-center gap-3">
                        <StatusPill status={dep.status} />
                        <div className="flex-1">
                          {dep.status === 'pending' && <span className="text-amber-400 text-sm">{dep.options?.pmd_result ? 'PMD check completed. Review PMD and choose Run Validation or Run Deployment.' : 'Ready for PMD pre-check. Run PMD first before validation/deployment.'}</span>}
                          {['queued','running','validating','deploying','pmd_check_queued','pmd_checking'].includes(dep.status) && <span className="text-sky-400 text-sm">Running in background via Celery worker. Updates every few seconds.</span>}
                          {dep.status === 'success' && <span className="text-emerald-400 text-sm font-medium">Deployment/validation completed successfully.</span>}
                          {dep.status === 'failed' && <span className="text-red-400 text-sm font-medium">Execution failed. See error below.</span>}
                        </div>
                      </div>
                    </div>

                    {/* Key metrics */}
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm mb-3">
                      <div className="bg-slate-800/40 rounded p-2.5">
                        <div className="text-[10px] uppercase tracking-wide text-slate-400 mb-0.5">Started</div>
                        <div className="font-mono text-xs">{dep.started_at ? new Date(dep.started_at).toLocaleString() : '—'}</div>
                      </div>
                      <div className="bg-slate-800/40 rounded p-2.5">
                        <div className="text-[10px] uppercase tracking-wide text-slate-400 mb-0.5">Completed</div>
                        <div className="font-mono text-xs">{dep.completed_at ? new Date(dep.completed_at).toLocaleString() : '— (in progress)'}</div>
                      </div>
                      <div className="bg-slate-800/40 rounded p-2.5 col-span-1 sm:col-span-2">
                        <div className="text-[10px] uppercase tracking-wide text-slate-400 mb-0.5">Salesforce Deploy Job ID</div>
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-xs break-all">{dep.salesforce_deployment_id || '— (available after validation succeeds for quick-deploy)'}</span>
                          {dep.salesforce_deployment_id && (
                            <button 
                              onClick={(e) => { e.stopPropagation(); navigator.clipboard.writeText(dep.salesforce_deployment_id); alert('Copied SF Deploy ID'); }}
                              className="text-[10px] px-1.5 py-px bg-slate-700 rounded hover:bg-slate-600"
                            >
                              Copy
                            </button>
                          )}
                        </div>
                      </div>
                    </div>

                    {/* Config summary */}
                    {dep.options && (
                      <div className="text-[11px] bg-slate-800/30 rounded p-2 mb-3 text-slate-300">
                        <span className="font-semibold">Config:</span> {dep.options.check_only ? 'Validate only (dry-run)' : 'Full deploy'} 
                        &nbsp;•&nbsp; Test level: <span className="font-mono">{dep.options.test_level || 'default (RunLocalTests)'}</span>
                        {dep.options.run_tests?.length ? ` &nbsp;•&nbsp; ${dep.options.run_tests.length} specific test(s)` : ''}
                        {dep.options.enable_pmd_check ? ' • PMD pre-check ON' : ' • PMD pre-check OFF'}
                      </div>
                    )}

                    {dep.options?.enable_pmd_check && dep.options?.pmd_result && (
                      <>
                        {pmdSummary && (
                          <div className={`mb-3 rounded p-2.5 border ${pmdSummary.passed ? 'bg-emerald-900/25 border-emerald-700/40' : 'bg-amber-900/20 border-amber-700/40'}`}>
                            <div className="flex items-center justify-between gap-2 mb-2">
                              <div className="text-xs font-semibold text-slate-200">PMD Pre-Check Summary</div>
                              <div className={`text-[10px] px-2 py-0.5 rounded ${pmdSummary.passed ? 'bg-emerald-700/40 text-emerald-300' : 'bg-amber-700/40 text-amber-300'}`}>
                                {pmdSummary.passed ? 'PASSED' : 'ISSUES FOUND'}
                              </div>
                            </div>
                            <div className="flex flex-wrap gap-1.5 text-[10px]">
                              <span className="px-1.5 py-0.5 rounded bg-red-900/40 text-red-300">Critical: {pmdSummary.critical}</span>
                              <span className="px-1.5 py-0.5 rounded bg-orange-900/40 text-orange-300">High: {pmdSummary.high}</span>
                              <span className="px-1.5 py-0.5 rounded bg-amber-900/40 text-amber-300">Medium: {pmdSummary.medium}</span>
                              <span className="px-1.5 py-0.5 rounded bg-yellow-900/40 text-yellow-300">Low: {pmdSummary.low}</span>
                              <span className="px-1.5 py-0.5 rounded bg-slate-700/50 text-slate-200">Total: {pmdSummary.total}</span>
                            </div>
                          </div>
                        )}

                        <div className="mb-3">
                          <button
                            onClick={(e) => { e.stopPropagation(); downloadPmdReport(dep.id) }}
                            className="px-2.5 py-1 text-xs rounded bg-indigo-600 text-white hover:bg-indigo-700 transition"
                          >
                            Download PMD Report (PDF)
                          </button>
                        </div>
                      </>
                    )}

                    {/* Beautiful progress steps / results area */}
                    <div className="space-y-2">
                      {/* Step indicators */}
                      <div className="text-[10px] font-semibold uppercase text-slate-400 mb-1">Execution Steps</div>
                      
                      <div className="space-y-1.5 pl-1">
                        <div className={`flex items-start gap-2 text-xs ${dep.status !== 'pending' ? 'text-emerald-400' : 'text-slate-400'}`}>
                          <span className="mt-0.5">✓</span> 
                          <span>Job record created (pending → ready for run)</span>
                        </div>
                        
                        <div className={`flex items-start gap-2 text-xs ${['queued','running','validating','deploying','success','failed'].includes(dep.status) ? 'text-emerald-400' : 'text-slate-400'}`}>
                          <span className="mt-0.5">{['queued','running','validating','deploying','success','failed'].includes(dep.status) ? '✓' : '○'}</span> 
                          <span>Execution queued (Celery task started)</span>
                        </div>

                        {dep.retrieval_id && (
                          <div className={`flex items-start gap-2 text-xs ${['validating','deploying','success','failed'].includes(dep.status) ? 'text-emerald-400' : 'text-slate-400'}`}>
                            <span className="mt-0.5">{['validating','deploying','success','failed'].includes(dep.status) ? '✓' : '○'}</span> 
                            <span>Source unpacked from linked retrieval (force-app + manifest)</span>
                          </div>
                        )}

                        <div className={`flex items-start gap-2 text-xs ${['validating','deploying','success','failed'].includes(dep.status) ? 'text-sky-400' : 'text-slate-400'}`}>
                          <span className="mt-0.5">{['validating','deploying'].includes(dep.status) ? '⟳' : ['success','failed'].includes(dep.status) ? '✓' : '○'}</span> 
                          <span>
                            {dep.options?.check_only ? 'Running sf project deploy validate' : 'Running sf project deploy start'} 
                            {dep.options?.test_level ? ` with --test-level ${dep.options.test_level}` : ''}
                          </span>
                        </div>

                        {dep.options?.enable_pmd_check && (
                          <div className={`flex items-start gap-2 text-xs ${dep.options?.pmd_result ? 'text-emerald-400' : ['validating','deploying','success','failed'].includes(dep.status) ? 'text-sky-400' : 'text-slate-400'}`}>
                            <span className="mt-0.5">{dep.options?.pmd_result ? '✓' : ['validating','deploying'].includes(dep.status) ? '⟳' : ['success','failed'].includes(dep.status) ? '✓' : '○'}</span>
                            <span>PMD analysis pre-check before validation/deploy</span>
                          </div>
                        )}

                        {dep.status === 'success' && (
                          <div className="flex items-start gap-2 text-xs text-emerald-400">
                            <span className="mt-0.5">✓</span> 
                            <span>Completed. {dep.options?.check_only ? 'Validation passed — use the SF Deploy ID above for a fast quick-deploy later if needed.' : 'Changes deployed to the org.'}</span>
                          </div>
                        )}
                        {dep.status === 'failed' && (
                          <div className="flex items-start gap-2 text-xs text-red-400">
                            <span className="mt-0.5">✕</span> 
                            <span>Failed — detailed analysis below (coverage, failing tests, root cause).</span>
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Beautiful parsed error view for validation / deploy failures */}
                    {dep.status === 'failed' && dep.error_message && (
                      <div className="mt-3">
                        {(() => {
                          const parsed = parseFailedValidation(dep.error_message);
                          const isCoverageFail = parsed.coverage !== null;
                          const isTestFail = parsed.testFailures.length > 0;
                          return (
                            <div className="space-y-3">
                              <div className="rounded-lg border border-red-600/70 bg-red-950/50 p-3">
                                <div className="flex items-center gap-2 text-red-300">
                                  <span className="text-lg">❌</span>
                                  <div>
                                    <div className="font-semibold">Validation / Deployment Failed</div>
                                    {parsed.deployId && <div className="text-[10px] text-red-400/70 font-mono">SF Deploy ID: {parsed.deployId}</div>}
                                  </div>
                                </div>
                              </div>
                              {isCoverageFail && (
                                <div className="rounded-lg border border-red-700/60 bg-red-950/30 p-3">
                                  <div className="flex justify-between items-end mb-1.5">
                                    <div>
                                      <div className="uppercase text-[10px] tracking-[1px] text-red-400 font-semibold">Code Coverage</div>
                                      <div className="text-4xl font-bold text-red-300 tabular-nums leading-none">{parsed.coverage}<span className="text-lg align-super">%</span></div>
                                    </div>
                                    <div className="text-right text-xs text-red-400/80">
                                      Required<br />
                                      <span className="font-semibold text-red-300">75%</span>
                                    </div>
                                  </div>
                                  <div className="h-2 w-full rounded bg-red-900/60 overflow-hidden">
                                    <div className="h-2 bg-gradient-to-r from-red-500 to-red-400 transition-all" style={{ width: `${Math.min(Math.max(parsed.coverage || 0, 0), 100)}%` }} />
                                  </div>
                                  <div className="mt-1 text-[10px] text-red-400/70">Average test coverage across all Apex Classes and Triggers is too low.</div>
                                </div>
                              )}
                              {isTestFail && (
                                <div>
                                  <div className="flex items-center justify-between mb-1.5">
                                    <div className="uppercase text-[10px] tracking-[1px] text-red-400 font-semibold">Failing Tests ({parsed.testFailures.length})</div>
                                  </div>
                                  <div className="space-y-1.5 max-h-[210px] overflow-auto pr-1">
                                    {parsed.testFailures.slice(0, 4).map((t, idx) => (
                                      <div key={idx} className="group rounded border-l-3 border-red-600 bg-red-950/25 px-2.5 py-1.5 text-xs">
                                        <div className="font-mono text-red-200 break-all leading-tight">{t.name}</div>
                                        <div className="text-red-300/90 mt-0.5 text-[10px] leading-snug line-clamp-3">{t.message}</div>
                                      </div>
                                    ))}
                                  </div>
                                  {parsed.testFailures.length > 4 && <div className="mt-1 text-[10px] text-red-400/70 pl-0.5">+{parsed.testFailures.length - 4} more (see raw)</div>}
                                </div>
                              )}
                              {!isCoverageFail && !isTestFail && (
                                <div className="rounded border border-red-700/60 bg-red-950/30 p-2.5 text-xs text-red-300">
                                  {getDeployErrorSummary(dep.error_message)}
                                </div>
                              )}
                              <details className="text-[10px]">
                                <summary className="cursor-pointer select-none text-red-400/80 hover:text-red-400 font-medium">Show raw Salesforce error</summary>
                                <pre className="mt-1.5 max-h-40 overflow-auto whitespace-pre-wrap rounded bg-black/50 p-2 text-red-300/90 border border-red-900/40 text-[9px] leading-tight">
                                  {dep.error_message}
                                </pre>
                              </details>
                            </div>
                          );
                        })()}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>
        ) }
        </>
      )}
    </div>
  )
}
