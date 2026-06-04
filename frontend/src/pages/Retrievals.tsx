import { useEffect, useRef, useState, Fragment } from 'react'

interface Retrieval {
  id: string
  org_id: string
  status: string
  artifact_key?: string
  error_message?: string
  created_at: string
  started_at?: string
  completed_at?: string
}

interface FileInfo {
  name: string
  type: string
  size: number
}

interface RetrievalFiles {
  job_id: string
  files: FileInfo[]
  metadata: {
    retrieved_at?: string
    org_name?: string
    metadata_types?: string[]
    total_files: number
  }
}

function StatusPill({ status }: { status: string }) {
  const active = status === 'running' || status === 'queued'
  const cls =
    status === 'success'  ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-400' :
    status === 'failed'   ? 'bg-red-100 text-red-600 dark:bg-red-900/40 dark:text-red-400' :
    status === 'running'  ? 'bg-sky-100 text-sky-600 dark:bg-sky-900/40 dark:text-af-blue' :
    'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-400'
  return <span className={`inline-flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded-full ${cls}`}>{active && <span className="w-1.5 h-1.5 rounded-full bg-current animate-pulse" />} {status}</span>;
}

function fmt(iso?: string) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'medium' })
}

export default function RetrievalsPage() {
  const [retrievals, setRetrievals] = useState<Retrieval[]>([])
  const [orgs, setOrgs] = useState<any[]>([])
  const [selectedOrg, setSelectedOrg] = useState('')
  const [retrievalMode, setRetrievalMode] = useState<'custom' | 'complete'>('custom')
  const [packageXml, setPackageXml] = useState(
    '<?xml version="1.0" encoding="UTF-8"?>\n<Package xmlns="http://soap.sforce.com/2006/04/metadata">\n  <types>\n    <members>*</members>\n    <name>ApexClass</name>\n  </types>\n  <version>62.0</version>\n</Package>'
  )

  // Special token (not valid XML) sent for Complete Backup mode.
  // Backend detects this exact token and runs `sf project generate manifest --from-org`
  // to build a true full-org package.xml. Using a magic token (instead of an XML snippet)
  // prevents any user-provided custom package.xml from accidentally triggering the complete path.
  const COMPLETE_SENTINEL = '__CLOUD_BRIDGE_COMPLETE_ORG_BACKUP__'

  // Package Builder state (for "package create" flow inside Custom mode)
  const [builderTypes, setBuilderTypes] = useState<any[]>([])
  const [selectedType, setSelectedType] = useState('')
  const [folder, setFolder] = useState('')
  const [builderMembers, setBuilderMembers] = useState<any[]>([])
  const [selectedMemberNames, setSelectedMemberNames] = useState<Set<string>>(new Set())
  const [memberFilter, setMemberFilter] = useState('')
  const [loadingTypes, setLoadingTypes] = useState(false)
  const [loadingMembers, setLoadingMembers] = useState(false)
  const [builderError, setBuilderError] = useState<string | null>(null)
  const [typeFilter, setTypeFilter] = useState('')

  const [loading, setLoading] = useState(false)
  const [statusMsg, setStatusMsg] = useState('')
  const [expandedJob, setExpandedJob] = useState<string | null>(null)
  const [jobFiles, setJobFiles] = useState<Record<string, RetrievalFiles>>({})
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // New: toggle between Metadata Retrieval wizard and full Jobs History, both in this tab
  const [view, setView] = useState<'retrieval' | 'history'>('retrieval')
  // 4-step wizard for Salesforce-like good UX (1. Org, 2. Configure+Build, 3. Review XML, 4. Retrieve)
  const [currentStep, setCurrentStep] = useState(1)

  // Derived values used by effects and render (hoisted before effects to satisfy declaration order and TS)
  const hasActiveJobs = Array.isArray(retrievals) && retrievals.some((j) => j.status === 'running' || j.status === 'queued')

  const fetchRetrievals = async () => {
    const res = await fetch('/api/v1/retrievals')
    if (res.ok) {
      const data: Retrieval[] = await res.json()
      setRetrievals(data)
      return data
    }
    return []
  }

  const fetchData = async () => {
    const [orgsRes] = await Promise.all([fetch('/api/v1/orgs'), fetchRetrievals()])
    if (orgsRes.ok) setOrgs(await orgsRes.json())
  }

  // Auto-poll every 3s while any job is active.
  // Depend only on the boolean "has active" so we don't restart the interval on every list refresh.
  useEffect(() => {
    if (hasActiveJobs && !pollRef.current) {
      pollRef.current = setInterval(async () => {
        const data = await fetchRetrievals()
        if (!data.some((j) => j.status === 'running' || j.status === 'queued')) {
          clearInterval(pollRef.current!); pollRef.current = null
        }
      }, 3000)
    } else if (!hasActiveJobs && pollRef.current) {
      clearInterval(pollRef.current); pollRef.current = null
    }
    return () => { if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null } }
  }, [hasActiveJobs])

  // Reset package builder when org changes (lists are org-specific)
  useEffect(() => {
    setBuilderTypes([])
    setSelectedType('')
    setFolder('')
    setBuilderMembers([])
    setSelectedMemberNames(new Set())
    setMemberFilter('')
    setBuilderError(null)
    setTypeFilter('')
  }, [selectedOrg])

  // When the expanded job reaches success, auto-load its files so the details list appears
  // without the user having to click "View Files". This makes the job feel "opened below"
  // with full info as soon as it completes.
  useEffect(() => {
    if (!expandedJob) return
    const j = Array.isArray(retrievals) ? retrievals.find(r => r.id === expandedJob) : null
    if (j && j.status === 'success' && j.artifact_key && !jobFiles[expandedJob]) {
      fetch(`/api/v1/retrievals/${expandedJob}/files`)
        .then(r => (r.ok ? r.json() : null))
        .then(d => { if (d) setJobFiles(prev => ({ ...prev, [expandedJob]: d })) })
        .catch(() => {})
    }
  }, [retrievals, expandedJob, jobFiles])

  useEffect(() => { fetchData() }, [])

  const compareWith = (jobId: string) => {
    navigator.clipboard.writeText(jobId)
    alert(`Copied ${jobId} — paste it on the Comparisons page.`)
  }

  const deleteJob = async (jobId: string) => {
    if (!confirm('Delete this retrieval job?')) return
    const res = await fetch(`/api/v1/retrievals/${jobId}`, { method: 'DELETE' })
    if (res.ok || res.status === 204) {
      setRetrievals(prev => prev.filter(j => j.id !== jobId))
    } else {
      alert('Delete failed: ' + await res.text())
    }
  }

  const downloadArtifact = async (jobId: string, format: 'sfdx' | 'json' = 'sfdx') => {
    try {
      const res = await fetch(`/api/v1/retrievals/${jobId}/download?format=${format}`)
      if (res.ok) {
        const blob = await res.blob()
        const url = window.URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        const filename = format === 'sfdx'
          ? `sfdx_project_${jobId.substring(0, 8)}.zip`
          : `retrieval_${jobId.substring(0, 8)}.zip`
        a.download = filename
        document.body.appendChild(a)
        a.click()
        window.URL.revokeObjectURL(url)
        document.body.removeChild(a)
      } else {
        alert('Failed to download artifact')
      }
    } catch (e) {
      alert('Error downloading: ' + e)
    }
  }

  const toggleJobDetails = async (jobId: string) => {
    if (expandedJob === jobId) {
      setExpandedJob(null)
      return
    }

    const job = Array.isArray(retrievals) ? retrievals.find((r) => r.id === jobId) : null;

    setExpandedJob(jobId);

    // Only attempt to load files for completed jobs that have an artifact.
    // Backend returns 400 otherwise (see list_retrieval_files).
    if (job && job.status === 'success' && job.artifact_key && !jobFiles[jobId]) {
      try {
        const res = await fetch(`/api/v1/retrievals/${jobId}/files`)
        if (res.ok) {
          const data = await res.json()
          setJobFiles(prev => ({ ...prev, [jobId]: data }))
        } else {
          console.warn('Failed to load files for job', jobId, res.status);
        }
      } catch (e) {
        console.error('Error loading files:', e)
      }
    }
  }

  const viewArtifact = async (jobId: string) => {
    try {
      const res = await fetch(`/api/v1/retrievals/${jobId}/artifact`)
      if (res.ok) {
        const data = await res.json()
        const formatted = JSON.stringify(data, null, 2)
        const win = window.open('', '_blank')
        if (win) {
          win.document.write(`<pre style="font-family: monospace; padding: 20px;">${formatted}</pre>`)
          win.document.title = `Artifact ${jobId.substring(0, 8)}`
        }
      } else {
        alert('Failed to load artifact')
      }
    } catch (e) {
      alert('Error: ' + e)
    }
  }

  const formatBytes = (bytes: number) => {
    if (bytes === 0) return '0 B'
    const k = 1024
    const sizes = ['B', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i]
  }

  // 4-step navigation (Salesforce-style wizard for better look & feel)
  const goToStep = (step: number) => {
    if (step >= 1 && step <= 4) setCurrentStep(step)
  }
  const nextStep = () => {
    if (currentStep === 1 && !selectedOrg) { alert('Please select an org first'); return }
    if (currentStep === 2 && retrievalMode === 'custom' && !packageXml.trim()) { alert('Build or provide a package.xml first'); return }
    if (currentStep < 4) setCurrentStep(currentStep + 1)
  }
  const prevStep = () => {
    if (currentStep > 1) setCurrentStep(currentStep - 1)
  }

  // --- Package Builder handlers ---
  const loadMetadataTypes = async () => {
    if (!selectedOrg) { alert('Please select an org first'); return }
    setLoadingTypes(true)
    setBuilderError(null)
    try {
      const res = await fetch('/api/v1/retrievals/package-builder/metadata-types', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ org_id: selectedOrg }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data?.detail || 'Failed to load types')

      const raw = (data.types || []) as any[]
      // Surface real CLI / Salesforce errors (auth, permissions, expired token, etc.)
      const firstErr = raw.find((t: any) => t && t.error)
      if (firstErr) {
        const msg = firstErr.error || (firstErr.details && (firstErr.details.message || firstErr.details.name)) || JSON.stringify(firstErr)
        setBuilderError(msg)
        setBuilderTypes([])
        return
      }

      const list = raw.filter((t: any) => t && t.xmlName && !t.error)
      setBuilderTypes(list)
      setSelectedType('')
      setBuilderMembers([])
      setSelectedMemberNames(new Set())
      setMemberFilter('')
      setTypeFilter('')

      if (list.length === 0) {
        setBuilderError('No metadata types returned from org. The connected Salesforce user may be missing the "Modify Metadata Through Metadata API Functions" permission (or "Modify All Data"). Reconnect the org after granting the permission, or use Complete Backup / paste XML manually.')
      }
    } catch (e: any) {
      const msg = 'Failed to load metadata types: ' + (e?.message || e)
      setBuilderError(msg)
    }
    setLoadingTypes(false)
  }

  const loadMetadataMembers = async () => {
    if (!selectedOrg || !selectedType) { alert('Select an org and a metadata type'); return }
    setLoadingMembers(true)
    setBuilderError(null)
    try {
      const body: any = { org_id: selectedOrg, metadataType: selectedType }
      if (folder && folder.trim()) body.folder = folder.trim()
      const res = await fetch('/api/v1/retrievals/package-builder/metadata-members', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data?.detail || 'Failed')

      const raw = (data.members || []) as any[]
      const firstErr = raw.find((m: any) => m && m.error)
      if (firstErr) {
        const msg = firstErr.error || (firstErr.details && (firstErr.details.message || firstErr.details.name)) || JSON.stringify(firstErr)
        setBuilderError(msg)
        setBuilderMembers([])
        return
      }

      const list = raw.filter((m: any) => m && m.fullName && !m.error)
      setBuilderMembers(list)
      setSelectedMemberNames(new Set())
      setMemberFilter('')
      if (list.length === 0) {
        setBuilderError(`No members returned for ${selectedType}. (Some types require a folder name, or the user lacks list metadata permissions.)`)
      }
    } catch (e: any) {
      setBuilderError('Failed to load members for ' + selectedType + ': ' + (e?.message || e))
    }
    setLoadingMembers(false)
  }

  const filteredMembers = builderMembers.filter((m: any) => {
    const name = (m.fullName || m.name || '').toLowerCase()
    return name.includes(memberFilter.toLowerCase())
  })

  const toggleMember = (name: string) => {
    setSelectedMemberNames(prev => {
      const next = new Set(prev)
      if (next.has(name)) next.delete(name)
      else next.add(name)
      return next
    })
  }

  const selectAllFiltered = () => {
    setSelectedMemberNames(prev => {
      const next = new Set(prev)
      filteredMembers.forEach((m: any) => {
        const n = m.fullName || m.name
        if (n) next.add(n)
      })
      return next
    })
  }

  const clearMemberSelection = () => setSelectedMemberNames(new Set())

  // very small escape for member names (rarely needed but safe)
  const escapeXml = (s: string) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')

  // --- package.xml helpers ---
  // Shared rebuild ensures <version> is always LAST (per Salesforce/Metadata API rules)
  // and produces nicely formatted (readable) output with each <members> on its own line.
  // This is important for the live editor textarea. Manual edits in the textarea are
  // preserved until the next add/remove/clear operation (which normalizes for consistency).
  const rebuildPackageXml = (typeBlocks: string[], version = '62.0') => {
    let body = ''
    typeBlocks.forEach(rawBlock => {
      const block = (rawBlock || '').trim()
      // Extract members and name, ignoring whatever whitespace the block currently has
      // (supports both pretty multi-line from previous builds and compact from manual paste)
      const memberRe = /<members>([\s\S]*?)<\/members>/gi
      const members: string[] = []
      let m: RegExpExecArray | null
      while ((m = memberRe.exec(block)) !== null) {
        const val = (m[1] || '').trim()
        if (val) members.push(val)
      }
      const nameMatch = block.match(/<name>([\s\S]*?)<\/name>/i)
      const name = nameMatch ? nameMatch[1].trim() : ''
      if (name) {
        const inner = members.map(mem => `    <members>${escapeXml(mem)}</members>`).join('\n')
        body += `  <types>\n${inner}\n    <name>${name}</name>\n  </types>\n`
      } else {
        // Fallback for malformed blocks
        body += `  ${block}\n`
      }
    })
    return `<?xml version="1.0" encoding="UTF-8"?>\n<Package xmlns="http://soap.sforce.com/2006/04/metadata">\n${body}  <version>${version}</version>\n</Package>`
  }

  const getCurrentPackageTypes = (): string[] => {
    const current = packageXml || ''
    const nameRe = /<types>[\s\S]*?<name>\s*([^<]+?)\s*<\/name>[\s\S]*?<\/types>/gi
    const types: string[] = []
    let m: RegExpExecArray | null
    while ((m = nameRe.exec(current)) !== null) {
      const nm = (m[1] || '').trim()
      if (nm) types.push(nm)
    }
    // dedupe, preserve first-seen order (case-insensitive compare)
    const seen = new Set<string>()
    return types.filter(t => {
      const key = t.toLowerCase()
      if (seen.has(key)) return false
      seen.add(key)
      return true
    })
  }

  const removeTypeFromPackage = (typeName: string) => {
    const current = (packageXml || '').trim()
    const verRe = /<version>\s*([\d.]+)\s*<\/version>/i
    const verMatch = current.match(verRe)
    const version = verMatch ? verMatch[1] : '62.0'

    const typesRe = /<types>[\s\S]*?<\/types>/gi
    const existing = current.match(typesRe) || []
    const keep = existing.filter((block: string) => {
      const nameMatch = block.match(/<name>\s*([^<]+?)\s*<\/name>/i)
      return nameMatch ? nameMatch[1].trim().toLowerCase() !== typeName.toLowerCase() : true
    })
    setPackageXml(rebuildPackageXml(keep, version))
  }

  const clearAllTypes = () => {
    setPackageXml(
      '<?xml version="1.0" encoding="UTF-8"?>\n<Package xmlns="http://soap.sforce.com/2006/04/metadata">\n  <version>62.0</version>\n</Package>'
    )
  }

  // Merge a <types>...</types> block into the current packageXml editor.
  // Always rebuilds a clean, valid package.xml with <version> LAST (after all <types>),
  // which is the required structure. This makes adds from the checkbox builder robust
  // even if the user manually edited the raw editor or started from the old default.
  const mergeBlockIntoPackage = (block: string) => {
    const current = (packageXml || '').trim()
    const verRe = /<version>\s*([\d.]+)\s*<\/version>/i
    const verMatch = current.match(verRe)
    const version = verMatch ? verMatch[1] : '62.0'
    const typesRe = /<types>[\s\S]*?<\/types>/gi
    const existingTypes = current.match(typesRe) || []
    const newBlocks = [...existingTypes, block.trim()]
    setPackageXml(rebuildPackageXml(newBlocks, version))
  }

  const addSelectedToPackage = () => {
    if (selectedMemberNames.size === 0 || !selectedType) return
    const members = Array.from(selectedMemberNames).sort()
    const block = `  <types>\n${members.map(m => `    <members>${escapeXml(m)}</members>`).join('\n')}\n    <name>${selectedType}</name>\n  </types>`
    mergeBlockIntoPackage(block)
  }

  const addWildcardForType = () => {
    if (!selectedType) return
    const block = `  <types>\n    <members>*</members>\n    <name>${selectedType}</name>\n  </types>`
    mergeBlockIntoPackage(block)
  }

  const triggerRetrieve = async () => {
    if (!selectedOrg) { alert('Please select an org'); return }
    setLoading(true)
    setStatusMsg('Connecting to Salesforce…')
    try {
      const xmlToUse = retrievalMode === 'complete' ? COMPLETE_SENTINEL : packageXml
      // Use background so the API returns immediately after creating/queuing the job.
      // This lets us refresh the Recent Jobs list right away so the new job appears
      // "opened below" with its progress, instead of only after full completion or
      // navigating away and back.
      const res = await fetch('/api/v1/retrievals?use_background=true', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ org_id: selectedOrg, package_xml: xmlToUse }),
      })
      if (res.ok) {
        let jobData: any = null
        try { jobData = await res.json() } catch {}
        setStatusMsg('Retrieval queued — see job below')
        await fetchData()
        // Auto-open the new job in the Recent Jobs list below so it's immediately visible/expanded
        if (jobData && jobData.id) {
          setExpandedJob(jobData.id)
          // Files list will be auto-loaded by effect once the job reaches success
        }
        if (jobData && jobData.status === 'failed') {
          alert('Retrieval started but job failed: ' + (jobData.error_message || 'See jobs list for details'))
          setStatusMsg('')
        } else {
          // brief message
          setTimeout(() => setStatusMsg(''), 1200)
        }
        // Reset wizard back to first step after job created + started
        setCurrentStep(1)
      } else {
        setStatusMsg('')
        alert('Failed: ' + await res.text())
      }
    } catch (e) {
      setStatusMsg('')
      alert('Error: ' + e)
    }
    setLoading(false)
  }

  // Reusable job card renderer used for both "last 3 recent" (compact) under wizard and full history list.
  const renderJobCard = (job: Retrieval, compact: boolean = false) => {
    const isExpanded = expandedJob === job.id
    const files = jobFiles[job.id]
    const orgName = (Array.isArray(orgs) ? orgs.find((o: any) => o.id === job.org_id) : null)?.name || 'Unknown Org'
    return (
      <div key={job.id} className={`af-card ${compact ? 'p-3 text-sm' : 'p-4'} mb-2`}>
        <div className="flex justify-between items-start gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <StatusPill status={job.status} />
              <span className="af-mono-badge text-xs">{job.id.substring(0, 8)}...</span>
              <span className="text-xs text-slate-500">{orgName}</span>
            </div>
            <div className="text-[10px] text-slate-400 mt-0.5">{fmt(job.created_at)}</div>
            {job.error_message && (
              <div className="mt-1 text-xs text-red-600 break-words">{job.error_message}</div>
            )}
          </div>
          <div className="flex items-center gap-1.5 shrink-0">
            <button
              onClick={() => toggleJobDetails(job.id)}
              className="text-xs text-af-blue hover:underline"
            >
              {isExpanded ? 'Hide' : 'Details'}
            </button>
            {!compact && (
              <>
                {job.status === 'success' && job.artifact_key && (
                  <button onClick={() => downloadArtifact(job.id, 'sfdx')} className="text-xs px-2 py-0.5 rounded bg-slate-100 hover:bg-slate-200 dark:bg-slate-800">SFDX</button>
                )}
                <button onClick={() => deleteJob(job.id)} className="text-xs px-2 py-0.5 rounded bg-red-100 text-red-600 hover:bg-red-200">Delete</button>
              </>
            )}
          </div>
        </div>

        {(job.status === 'running' || job.status === 'queued') && (
          <div className="mt-2 h-1 bg-slate-200 rounded overflow-hidden"><div className="h-1 bg-af-blue animate-pulse w-3/4" /></div>
        )}

        {isExpanded && (
          <div className="mt-3 pt-3 border-t border-slate-200 dark:border-white/10 text-xs">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-x-4 text-slate-500 mb-2">
              <div>Started: {fmt(job.started_at)}</div>
              <div>Completed: {fmt(job.completed_at)}</div>
              <div>ID: <span className="font-mono">{job.id}</span></div>
            </div>

            <div className="flex flex-wrap gap-2 mb-2">
              {job.status === 'success' && job.artifact_key && (
                <>
                  <button onClick={() => downloadArtifact(job.id, 'sfdx')} className="af-btn-secondary text-xs px-2 py-1">Download SFDX Zip</button>
                  <button onClick={() => downloadArtifact(job.id, 'json')} className="af-btn-secondary text-xs px-2 py-1">Download JSON</button>
                  <button onClick={() => viewArtifact(job.id)} className="af-btn-secondary text-xs px-2 py-1">View Artifact</button>
                </>
              )}
              <button onClick={() => compareWith(job.id)} className="af-btn-secondary text-xs px-2 py-1">Copy ID for Compare</button>
              <button onClick={() => deleteJob(job.id)} className="text-xs px-2 py-1 rounded bg-red-50 hover:bg-red-100 text-red-600">Delete Job</button>
            </div>

            {files && files.files && files.files.length > 0 ? (
              <div>
                <div className="font-semibold text-slate-600 dark:text-slate-300 mb-1">
                  Files ({files.metadata?.total_files || files.files.length})
                </div>
                <div className="max-h-40 overflow-auto bg-slate-50 dark:bg-slate-900/60 rounded p-2 font-mono text-[10px] leading-tight border border-slate-200 dark:border-white/10">
                  {files.files.slice(0, 30).map((f: FileInfo, idx: number) => (
                    <div key={idx} className="truncate">{f.name} <span className="text-slate-400">({formatBytes(f.size)})</span></div>
                  ))}
                  {files.files.length > 30 && <div className="text-slate-400">… +{files.files.length - 30} more</div>}
                </div>
              </div>
            ) : job.status === 'success' && job.artifact_key ? (
              <button onClick={() => toggleJobDetails(job.id)} className="text-af-blue text-xs underline">Load files list</button>
            ) : null}
          </div>
        )}
      </div>
    )
  }

  const recentJobs = (Array.isArray(retrievals) ? retrievals : []).slice(0, 3)
  const currentPackageTypes = getCurrentPackageTypes()

  return (
    <div className="max-w-5xl mx-auto px-6 py-10">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="font-display text-3xl font-bold af-gradient-text mb-1">Metadata Retrievals</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">Pull metadata packages from your Salesforce orgs. Salesforce-style 4-step wizard for great UX.</p>
        </div>

        {/* Top-right toggle: both views live inside the single Retrievals tab */}
        <div className="inline-flex rounded-lg border border-slate-200 dark:border-white/10 overflow-hidden text-sm shadow-sm">
          <button
            onClick={() => setView('retrieval')}
            className={`px-3.5 py-1.5 font-semibold transition-colors ${view === 'retrieval' ? 'bg-af-blue text-white' : 'bg-white dark:bg-af-darkcard hover:bg-slate-50 dark:hover:bg-slate-800'}`}
          >
            Metadata Retrieval
          </button>
          <button
            onClick={() => setView('history')}
            className={`px-3.5 py-1.5 font-semibold transition-colors ${view === 'history' ? 'bg-af-blue text-white' : 'bg-white dark:bg-af-darkcard hover:bg-slate-50 dark:hover:bg-slate-800'}`}
          >
            Jobs History
          </button>
        </div>
      </div>

      {view === 'retrieval' ? (
        <>
          {/* 4-step Salesforce-like horizontal wizard */}
          <div className="af-panel">
            {/* Stepper header */}
            <div className="mb-5">
              <div className="flex items-center gap-0 mb-1">
                {[1, 2, 3, 4].map((s, idx) => (
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
                    {idx < 3 && (
                      <div className={`flex-1 h-[3px] mx-1 rounded ${currentStep > s ? 'bg-emerald-500' : 'bg-slate-200 dark:bg-slate-700'}`} />
                    )}
                  </Fragment>
                ))}
              </div>
              <div className="flex justify-between text-[10px] text-slate-500 px-1">
                <div>1. Select Org</div>
                <div>2. Mode &amp; Build</div>
                <div>3. Review</div>
                <div>4. Retrieve</div>
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
                <p className="mt-2 text-xs text-slate-500">
                  The connected Salesforce user must have the <span className="font-medium">"Modify Metadata Through Metadata API Functions"</span> (or Modify All Data) permission to list metadata types and members.
                </p>
                {(Array.isArray(orgs) ? orgs.length : 0) === 0 && (
                  <p className="mt-1 text-xs text-amber-600">No orgs connected yet. Go to the Orgs tab to connect one.</p>
                )}
              </div>
            )}

            {/* Step 2: Mode + full Package Builder (only for custom) */}
            {currentStep === 2 && (
              <div>
                <div className="mb-3">
                  <div className="text-sm font-semibold mb-1.5">Retrieval Mode</div>
                  <div className="flex gap-2">
                    <button
                      onClick={() => setRetrievalMode('custom')}
                      className={`flex-1 rounded-lg px-3 py-2 text-sm font-semibold border transition ${retrievalMode === 'custom' ? 'bg-af-blue text-white border-af-blue' : 'bg-white dark:bg-slate-800 border-slate-200 hover:border-af-blue/40'}`}
                    >
                      Custom Package
                    </button>
                    <button
                      onClick={() => setRetrievalMode('complete')}
                      className={`flex-1 rounded-lg px-3 py-2 text-sm font-semibold border transition ${retrievalMode === 'complete' ? 'bg-af-blue text-white border-af-blue' : 'bg-white dark:bg-slate-800 border-slate-200 hover:border-af-blue/40'}`}
                    >
                      Complete Org Backup
                    </button>
                  </div>
                  {retrievalMode === 'complete' && (
                    <div className="mt-2 text-xs p-2 rounded bg-amber-50 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300 border border-amber-200/60">
                      Complete Backup uses <code>sf project generate manifest --from-org</code> on the backend to capture every metadata component. No package builder needed.
                    </div>
                  )}
                </div>

                {retrievalMode === 'custom' && (
                  <div className="mt-1 border border-slate-200 dark:border-white/10 rounded-xl p-4 bg-white/50 dark:bg-slate-900/30">
                    <div className="flex items-center justify-between mb-2">
                      <div className="font-semibold text-sm">Package Builder</div>
                      <button
                        onClick={loadMetadataTypes}
                        disabled={loadingTypes || !selectedOrg}
                        className="text-xs af-btn-secondary disabled:opacity-50"
                      >
                        {loadingTypes ? 'Loading…' : 'Load Metadata Types'}
                      </button>
                    </div>

                    {builderError && (
                      <div className="mb-2 text-xs bg-red-50 dark:bg-red-900/30 text-red-600 p-2 rounded border border-red-200/60">{builderError}</div>
                    )}

                    {builderTypes.length > 0 && (
                      <div className="space-y-2">
                        <div className="flex gap-2">
                          <input
                            className="af-input text-xs py-1 flex-1"
                            placeholder="Filter types (e.g. Apex)"
                            value={typeFilter}
                            onChange={e => setTypeFilter(e.target.value)}
                          />
                          <select
                            className="af-input text-xs py-1 flex-1"
                            value={selectedType}
                            onChange={e => { setSelectedType(e.target.value); setBuilderMembers([]); setSelectedMemberNames(new Set()) }}
                          >
                            <option value="">Select type…</option>
                            {builderTypes
                              .filter((t: any) => (t.xmlName || '').toLowerCase().includes(typeFilter.toLowerCase()))
                              .map((t: any) => (
                                <option key={t.xmlName} value={t.xmlName}>{t.xmlName}{t.inFolder ? ' (folder)' : ''}</option>
                              ))}
                          </select>
                          <input
                            className="af-input text-xs py-1 w-28"
                            placeholder="Folder (opt)"
                            value={folder}
                            onChange={e => setFolder(e.target.value)}
                          />
                          <button
                            onClick={loadMetadataMembers}
                            disabled={loadingMembers || !selectedType}
                            className="af-btn-secondary text-xs px-3"
                          >
                            {loadingMembers ? '…' : 'Load Members'}
                          </button>
                        </div>

                        {builderMembers.length > 0 && (
                          <div className="border border-slate-200 dark:border-white/10 rounded-lg p-2">
                            <div className="flex gap-2 mb-2">
                              <input
                                className="af-input text-xs py-1 flex-1"
                                placeholder="Filter members…"
                                value={memberFilter}
                                onChange={e => setMemberFilter(e.target.value)}
                              />
                              <button onClick={selectAllFiltered} className="text-xs af-btn-secondary">Select all shown</button>
                              <button onClick={clearMemberSelection} className="text-xs af-btn-secondary">Clear</button>
                            </div>

                            <div className="max-h-44 overflow-auto text-xs grid grid-cols-1 sm:grid-cols-2 gap-x-3 gap-y-0.5 pr-1">
                              {filteredMembers.map((m: any) => {
                                const name = m.fullName || m.name
                                const checked = selectedMemberNames.has(name)
                                return (
                                  <label key={name} className="flex items-center gap-1.5 cursor-pointer py-0.5">
                                    <input
                                      type="checkbox"
                                      checked={checked}
                                      onChange={() => toggleMember(name)}
                                    />
                                    <span className="truncate">{name}</span>
                                  </label>
                                )
                              })}
                              {filteredMembers.length === 0 && <div className="text-slate-400 col-span-2">No members match filter.</div>}
                            </div>

                            <div className="flex gap-2 mt-2">
                              <button onClick={addSelectedToPackage} disabled={selectedMemberNames.size === 0} className="text-xs af-btn-primary px-3 py-1 flex-1 disabled:opacity-40">Add selected to package.xml</button>
                              <button onClick={addWildcardForType} disabled={!selectedType} className="text-xs af-btn-secondary px-3 py-1">Add * for {selectedType || 'type'}</button>
                            </div>
                          </div>
                        )}
                      </div>
                    )}

                    {/* Live package.xml editor (always visible for custom so user sees & can tweak) */}
                    <div className="mt-3">
                      <div className="text-xs font-semibold mb-1 flex items-center justify-between">
                        <span>Current package.xml (updated live by builder + direct edits)</span>
                        <button
                          onClick={clearAllTypes}
                          className="text-[10px] text-red-600 hover:underline"
                          title="Remove every <types> block, leaving only the version"
                        >
                          Clear all types
                        </button>
                      </div>

                      {/* Live chips for current types — click × to remove a whole <types> block (e.g. remove ApexClass) */}
                      {currentPackageTypes.length > 0 && (
                        <div className="flex flex-wrap gap-1 mb-1.5">
                          {currentPackageTypes.map((t) => (
                            <span
                              key={t}
                              className="inline-flex items-center gap-1 rounded bg-slate-100 dark:bg-slate-800 px-1.5 py-0.5 text-[10px] text-slate-700 dark:text-slate-200 border border-slate-200 dark:border-white/10"
                            >
                              {t}
                              <button
                                onClick={() => removeTypeFromPackage(t)}
                                className="ml-0.5 text-red-500 hover:text-red-700 font-bold leading-none"
                                title={`Remove ${t} block`}
                              >
                                ×
                              </button>
                            </span>
                          ))}
                        </div>
                      )}
                      {currentPackageTypes.length === 0 && (
                        <div className="text-[10px] text-slate-400 mb-1">No &lt;types&gt; blocks — package will retrieve nothing (or add via builder above).</div>
                      )}

                      <textarea
                        rows={7}
                        className="af-input font-mono text-xs w-full"
                        value={packageXml}
                        onChange={e => setPackageXml(e.target.value)}
                      />
                      <p className="text-[10px] text-slate-500 mt-0.5">Editing here is live. Removing the last type produces exactly the minimal &lt;Package&gt; + &lt;version&gt; only.</p>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Step 3: Review */}
            {currentStep === 3 && (
              <div>
                <div className="text-sm font-semibold mb-2">Review what will be retrieved</div>
                {retrievalMode === 'complete' ? (
                  <div className="af-card p-4 text-sm bg-amber-50/70 dark:bg-amber-900/20 border border-amber-200/50">
                    <strong>Complete Org Backup</strong><br />
                    The backend will run <code>sf project generate manifest --from-org</code> using the selected org’s access token and then retrieve everything described by the generated manifest.
                    The resulting package.xml and zip will be stored with the job.
                  </div>
                ) : (
                  <>
                    <textarea
                      readOnly
                      rows={9}
                      className="af-input font-mono text-xs w-full"
                      value={packageXml}
                    />
                    <p className="text-[10px] text-slate-500 mt-1">This exact XML (with &lt;version&gt; last) will be sent to the Metadata API retrieve.</p>
                  </>
                )}
              </div>
            )}

            {/* Step 4: Start */}
            {currentStep === 4 && (
              <div>
                <div className="text-sm font-semibold mb-2">Ready to start retrieval?</div>
                <div className="mb-3 text-xs text-slate-500">
                  Org: <span className="font-medium">{(Array.isArray(orgs) ? orgs.find((o: any) => o.id === selectedOrg) : null)?.name || selectedOrg}</span> · Mode: <span className="font-medium">{retrievalMode === 'complete' ? 'Complete Backup' : 'Custom Package'}</span>
                </div>
                <button
                  onClick={triggerRetrieve}
                  disabled={loading || !selectedOrg}
                  className="af-btn-primary w-full py-2.5 text-base"
                >
                  {loading ? 'Starting…' : 'Start Retrieval'}
                </button>
                {statusMsg && <div className="mt-2 text-xs text-emerald-600">{statusMsg}</div>}
                <p className="mt-2 text-[10px] text-slate-500">The job will appear immediately in Recent Jobs below (progress updates automatically).</p>
              </div>
            )}

            {/* Wizard nav */}
            <div className="mt-5 flex items-center justify-between text-sm">
              <button onClick={prevStep} disabled={currentStep === 1} className="px-3 py-1.5 rounded border disabled:opacity-40">← Back</button>
              {currentStep < 4 ? (
                <button onClick={nextStep} className="px-4 py-1.5 rounded bg-af-blue text-white font-semibold">Next →</button>
              ) : (
                <button onClick={() => { setCurrentStep(1); setRetrievalMode('custom'); }} className="px-3 py-1.5 rounded border">Restart Wizard</button>
              )}
            </div>
          </div>

          {/* Recent (last 3) shown only under the wizard in "Metadata Retrieval" view */}
          <div className="mt-6">
            <div className="flex items-baseline justify-between mb-2">
              <div className="font-semibold text-sm">Recent Jobs (last 3)</div>
              <button onClick={() => setView('history')} className="text-xs text-af-blue hover:underline">View full history →</button>
            </div>
            {recentJobs.length === 0 ? (
              <div className="af-card p-4 text-xs text-slate-500">No retrieval jobs yet. Complete the wizard (step 4 has the Start button).</div>
            ) : (
              <div className="space-y-1">
                {recentJobs.map(job => renderJobCard(job, true))}
              </div>
            )}
          </div>
        </>
      ) : (
        /* Full Jobs History view */
        <div className="af-panel">
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-semibold">All Retrieval Jobs</h2>
            <button onClick={() => setView('retrieval')} className="text-xs text-af-blue hover:underline">← Back to Retrieval Wizard</button>
          </div>
          {(Array.isArray(retrievals) ? retrievals.length : 0) === 0 ? (
            <div className="text-center p-8 text-slate-400 text-sm">No jobs yet.</div>
          ) : (
            <div>
              {(Array.isArray(retrievals) ? retrievals : []).map(job => renderJobCard(job, false))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

