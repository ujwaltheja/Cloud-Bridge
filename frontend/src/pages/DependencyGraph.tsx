import React, { useState, useEffect } from 'react';

interface DependencyNode {
  id: string;
  type: string;
  name: string;
  is_changed: boolean;
  is_impacted: boolean;
  risk_level?: string;
}

interface DependencyEdge {
  source: string;
  target: string;
  dependency_type: string;
  confidence?: number;
}

interface MissingDependency {
  type: string;
  name: string;
  required_by: string[];
  severity: string;
  auto_addable: boolean;
  reason: string;
}

interface Retrieval {
  id: string;
  org_id: string;
  status: string;
  artifact_key?: string;
  package_xml?: string;
  created_at: string;
  completed_at?: string;
  started_at?: string;
  error_message?: string;
}

interface DependencyGraphData {
  analysis_id: string;
  graph: {
    nodes: DependencyNode[];
    edges: DependencyEdge[];
    stats: {
      total_nodes: number;
      total_edges: number;
      changed_components: number;
      impacted_components: number;
      missing_dependencies: number;
    };
  };
  missing_dependencies: MissingDependency[];
  deployment_order: string[];
  validation_order: string[];
  package_xml?: string;
  auto_added_components?: Array<{ type: string; names: string[] }>;
  stats: any;
}

const DependencyGraph: React.FC = () => {
  const searchParams = new URLSearchParams(window.location.search);
  const analysisId = searchParams.get('analysisId');
  const orgIdParam = searchParams.get('orgId');
  const retrievalIdParam = searchParams.get('retrievalId');
  
  const [graphData, setGraphData] = useState<DependencyGraphData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showPackageXml, setShowPackageXml] = useState(false);
  const [customInput, setCustomInput] = useState('');

  // For real retrieved packages
  const [orgs, setOrgs] = useState<any[]>([]);
  const [retrievals, setRetrievals] = useState<Retrieval[]>([]);
  const [selectedOrgId, setSelectedOrgId] = useState<string>(orgIdParam || '');
  const [selectedRetrievalId, setSelectedRetrievalId] = useState<string>(retrievalIdParam || '');
  const [sourceInfo, setSourceInfo] = useState<string>(''); // e.g. "Based on retrieval 2024-... (42 components)"

  // Parse Salesforce package.xml into components map { "ApexClass": ["Foo", "Bar"], ... }
  // Used to feed real retrieved packages into the AI dependency engine.
  const parsePackageXml = (xml: string): Record<string, string[]> => {
    const result: Record<string, string[]> = {};
    if (!xml || typeof xml !== 'string') return result;
    try {
      const parser = new DOMParser();
      const doc = parser.parseFromString(xml, 'text/xml');
      const parseErr = doc.querySelector('parsererror');
      if (parseErr) throw new Error('Invalid package.xml');

      const typeNodes = doc.getElementsByTagName('types');
      for (let i = 0; i < typeNodes.length; i++) {
        const t = typeNodes[i];
        const nameNode = t.getElementsByTagName('name')[0];
        const typeName = nameNode?.textContent?.trim();
        if (!typeName) continue;

        const members: string[] = [];
        const memberNodes = t.getElementsByTagName('members');
        for (let j = 0; j < memberNodes.length; j++) {
          const m = memberNodes[j].textContent?.trim();
          if (m && m !== '*') members.push(m);
        }
        if (members.length > 0) {
          result[typeName] = members;
        }
      }
    } catch (e) {
      console.warn('parsePackageXml failed:', e);
    }
    return result;
  };

  const formatComponentsToInput = (comps: Record<string, string[]>): string => {
    return Object.entries(comps)
      .map(([type, names]) => `${type}:${names.join(',')}`)
      .join('\n');
  };

  // Load orgs (for selecting which org's retrievals to use)
  const loadOrgs = async () => {
    try {
      const res = await fetch('/api/v1/orgs');
      if (res.ok) {
        const data = await res.json();
        setOrgs(Array.isArray(data) ? data : []);
        if (!selectedOrgId && data.length > 0 && !analysisId && !retrievalIdParam) {
          setSelectedOrgId(data[0].id);
        }
      }
    } catch {}
  };

  const loadRetrievalsForOrg = async (orgId: string) => {
    if (!orgId) { setRetrievals([]); return; }
    try {
      const res = await fetch(`/api/v1/retrievals?org_id=${orgId}`);
      if (res.ok) {
        const data = await res.json();
        console.log('📦 Retrievals API response:', data); // Debug log
        console.log(`📊 Total retrievals for org: ${data?.length || 0}`);
        
        if (!data || data.length === 0) {
          console.log('⚠️  No retrievals found for this org. Create one first!');
          setRetrievals([]);
          return;
        }
        
        // Show all completed retrievals - package_xml should always be present per API schema
        // If it's missing, we'll handle that when trying to load it
        const usable = (data || []).filter((r: Retrieval) => {
          const isCompleted = r.status === 'success' || r.status === 'completed' || !!r.completed_at;
          console.log(`  📄 Retrieval ${r.id?.slice(0,8)}: status=${r.status}, completed=${!!r.completed_at}, hasPackage=${!!r.package_xml}`);
          // Show all completed retrievals - we'll validate package_xml when loading
          return isCompleted;
        });
        
        console.log(`✅ Found ${usable.length} usable retrievals out of ${data?.length || 0} total`);
        
        // If no completed retrievals, show ALL retrievals so user can see what exists
        if (usable.length === 0 && data.length > 0) {
          console.log('⚠️  No completed retrievals, showing all retrievals for visibility');
          setRetrievals(data); // Show all, even pending/running ones
        } else {
          setRetrievals(usable);
        }

        // Pre-select the first usable retrieval in the dropdown for convenience
        if (!selectedRetrievalId && usable.length > 0) {
          setSelectedRetrievalId(usable[0].id);
        }
      }
    } catch (err) {
      console.error('❌ Failed to load retrievals:', err);
      setRetrievals([]);
    }
  };

  // Core new feature: take a real retrieved package.xml, parse components, run the full dependency graph + missing detection + package builder
  const loadFromRetrieval = async (retrievalId: string) => {
    if (!retrievalId) return;
    setLoading(true);
    setError(null);
    setSourceInfo('');

    try {
      const res = await fetch(`/api/v1/retrievals/${retrievalId}`);
      if (!res.ok) throw new Error(`Failed to load retrieval (${res.status})`);
      const ret = await res.json();

      const pkgXml: string = ret.package_xml || '';
      if (!pkgXml || pkgXml.length < 20) throw new Error('Retrieval has no usable package.xml');

      const components = parsePackageXml(pkgXml);
      const totalComps = Object.values(components).reduce((n, arr) => n + arr.length, 0);

      if (Object.keys(components).length === 0) {
        throw new Error('No explicit members found in package.xml (only wildcards or empty types?)');
      }

      // Make the components editable in the textarea too
      setCustomInput(formatComponentsToInput(components));

      // This calls the backend /build which does the full AI + rule dependency discovery, missing detection, ordering and package.xml generation
      // Pass ret.org_id explicitly so we never use a hardcoded dummy org id.
      // We manage loading at this level (the whole "load retrieval + build graph"), so pass false to buildGraph.
      await buildGraph(components, ret.org_id, false);

      const when = ret.completed_at ? new Date(ret.completed_at).toLocaleString() : 'recent';
      setSourceInfo(`Using retrieved package from ${when} • ${totalComps} components`);
      setSelectedRetrievalId(retrievalId);
      if (ret.org_id) {
        setSelectedOrgId(ret.org_id);
      }
    } catch (err: any) {
      setError(err?.message || 'Failed to run dependency check on retrieved package');
    } finally {
      setLoading(false);
    }
  };

  // Build dependency graph from components (real or manual)
  // forceOrgId is used when we just loaded a retrieval (so we have the real org id immediately)
  const buildGraph = async (components: Record<string, string[]>, forceOrgId?: string, manageLoading: boolean = true) => {
    if (manageLoading) setLoading(true);
    setError(null);

    const orgIdToUse = forceOrgId || selectedOrgId || orgIdParam;

    if (!orgIdToUse) {
      setError('Please select an organization first (or load from a retrieval that belongs to one).');
      if (manageLoading) setLoading(false);
      return;
    }
    
    try {
      const response = await fetch('/api/v1/dependency-graph/build', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          org_id: orgIdToUse,
          components,
          include_missing: true,
          generate_package: true,
        }),
      });

      if (!response.ok) {
        const txt = await response.text().catch(() => '');
        throw new Error(`Failed to build graph: ${response.status} ${txt}`);
      }

      const data = await response.json();
      setGraphData(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      if (manageLoading) setLoading(false);
    }
  };

  // Load existing graph
  const loadGraph = async (id: string) => {
    setLoading(true);
    setError(null);
    
    try {
      const response = await fetch(`/api/v1/dependency-graph/${id}`);
      
      if (!response.ok) {
        throw new Error(`Failed to load graph: ${response.statusText}`);
      }

      const data = await response.json();
      setGraphData(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  };

  // Auto-add missing dependencies
  const autoAddMissing = async () => {
    if (!graphData) return;
    
    setLoading(true);
    try {
      const response = await fetch(
        `/api/v1/dependency-graph/${graphData.analysis_id}/missing-dependencies/add`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(['PermissionSet', 'CustomMetadata']),
        }
      );

      if (!response.ok) {
        throw new Error('Failed to add missing dependencies');
      }

      const result = await response.json();
      const addedCount = result.added ? Object.values(result.added).flat().length : 0;
      alert(`Added ${addedCount} missing dependencies`);
      
      // Reload graph (will refresh missing list + package)
      await loadGraph(graphData.analysis_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  };

  const downloadDependencyGraphPdf = async () => {
    if (!graphData) return;
    try {
      const res = await fetch(`/api/v1/dependency-graph/${graphData.analysis_id}/report/pdf`);
      if (!res.ok) {
        const txt = await res.text().catch(() => '');
        throw new Error(`HTTP ${res.status} ${txt}`);
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `ai-dependency-graph-auto-package-${graphData.analysis_id}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      alert('Failed to download AI Dependency Graph PDF: ' + e);
    }
  };

  useEffect(() => {
    loadOrgs();

    if (analysisId) {
      loadGraph(analysisId);
    } else if (retrievalIdParam) {
      loadFromRetrieval(retrievalIdParam);
    }
    // No more auto demo with hardcoded components.
    // User must either:
    // - pick org + retrieval and click "Run Dependency Check", or
    // - use the manual section after selecting an org.
  }, [analysisId, retrievalIdParam]);

  useEffect(() => {
    if (selectedOrgId) loadRetrievalsForOrg(selectedOrgId);
  }, [selectedOrgId]);

  const getSeverityColor = (severity: string) => {
    switch (severity) {
      case 'critical': return 'bg-red-100 dark:bg-red-950/40 text-red-800 dark:text-red-300 border-red-300 dark:border-red-800/50';
      case 'high': return 'bg-orange-100 dark:bg-orange-950/40 text-orange-800 dark:text-orange-300 border-orange-300 dark:border-orange-800/50';
      case 'medium': return 'bg-yellow-100 dark:bg-yellow-950/40 text-yellow-800 dark:text-yellow-300 border-yellow-300 dark:border-yellow-800/50';
      case 'low': return 'bg-blue-100 dark:bg-blue-950/40 text-blue-800 dark:text-blue-300 border-blue-300 dark:border-blue-800/50';
      default: return 'bg-slate-100 dark:bg-slate-800 text-slate-800 dark:text-slate-300 border-slate-200 dark:border-white/10';
    }
  };

  const getNodeColor = (node: DependencyNode) => {
    if (node.is_changed) return 'bg-af-blue';
    if (node.is_impacted) return 'bg-amber-500';
    return 'bg-slate-400 dark:bg-slate-600';
  };

  // Parse textarea like "Flow:MyFlow\nApexClass:Handler" into components dict
  const parseComponents = (text: string): Record<string, string[]> => {
    const result: Record<string, string[]> = {};
    text.split(/\n+/).forEach(line => {
      const trimmed = line.trim();
      if (!trimmed || !trimmed.includes(':')) return;
      const [type, namesStr] = trimmed.split(':', 2);
      const names = namesStr.split(/[, ]+/).map(s => s.trim()).filter(Boolean);
      if (names.length) {
        const key = type.trim();
        result[key] = (result[key] || []).concat(names);
      }
    });
    return result;
  };

  const handleBuildCustom = () => {
    const comps = parseComponents(customInput);
    if (Object.keys(comps).length === 0) {
      setError('Please enter components in format Type:Name e.g. Flow:MyFlow');
      return;
    }
    if (!selectedOrgId && !orgIdParam) {
      setError('Please select an organization first before running manual analysis.');
      return;
    }
    setSourceInfo(''); // user is doing a manual/ad-hoc analysis
    buildGraph(comps);
  };

  if (loading && !graphData) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-af-blue mx-auto"></div>
          <p className="mt-4 text-slate-600 dark:text-slate-400">Building dependency graph from package...</p>
        </div>
      </div>
    );
  }

  if (error && !graphData) {
    return (
      <div className="p-8 max-w-3xl mx-auto">
        <div className="af-panel border-red-300 dark:border-red-800/60 bg-red-50 dark:bg-red-950/30">
          <h3 className="text-red-700 dark:text-red-400 font-semibold">Error</h3>
          <p className="text-red-600 dark:text-red-300 mt-1">{error}</p>
          <button onClick={() => setError(null)} className="mt-3 text-sm underline text-red-700 dark:text-red-400">Dismiss</button>
        </div>
      </div>
    );
  }

  // data may be null here — we always render the selection controls.
  // Results (stats, graph, etc.) are shown only when we have data.
  const data = graphData;

  return (
    <div className="p-8 max-w-7xl mx-auto">
      <div className="mb-8">
        <h1 className="text-3xl font-bold af-gradient-text mb-2">
          🔗 AI Dependency Graph + Auto Package Builder
        </h1>
        <p className="text-slate-600 dark:text-slate-400">
          Automatically discover dependencies from a <strong>real retrieved package.xml</strong> and generate correctly ordered deployment packages.
        </p>
        {sourceInfo && (
          <div className="mt-2 inline-flex items-center gap-2 text-xs px-3 py-1 rounded-full bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-400">
            {sourceInfo}
          </div>
        )}
      </div>

      {/* ========== PRIMARY: Use Retrieved Package (the main improvement) ========== */}
      <div className="af-panel mb-8">
        <div className="flex items-center justify-between mb-4">
          <div>
            <div className="font-semibold text-slate-800 dark:text-slate-100">1. Use a Retrieved Package (recommended)</div>
            <div className="text-xs text-slate-500 dark:text-slate-400">Select an org, then pick a completed retrieval from the list below. Selecting a retrieval immediately parses its package.xml and runs the full dependency check (no extra click needed).</div>
          </div>
          <button
            onClick={() => {
              if (selectedRetrievalId) {
                loadFromRetrieval(selectedRetrievalId);
              }
            }}
            disabled={loading || (!selectedOrgId && !orgIdParam) || !selectedRetrievalId}
            className="af-btn-primary text-sm disabled:opacity-60"
          >
            {loading ? 'Analyzing package...' : (data ? 'Re-run on Selected Retrieval' : 'Analyze Selected Retrieval')}
          </button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Org selector */}
          <div>
            <label className="block text-xs font-medium text-slate-600 dark:text-slate-400 mb-1">Organization</label>
            <select
              value={selectedOrgId}
              onChange={(e) => {
                const v = e.target.value;
                setSelectedOrgId(v);
                setSelectedRetrievalId('');
                setRetrievals([]);
              }}
              className="af-input"
            >
              <option value="">Select org...</option>
              {orgs.map((o: any) => (
                <option key={o.id} value={o.id}>{o.name} ({o.org_type})</option>
              ))}
            </select>
          </div>

          {/* Retrieval selector */}
          <div>
            <label className="block text-xs font-medium text-slate-600 dark:text-slate-400 mb-1">Completed Retrieval (with package.xml)</label>
            <select
              value={selectedRetrievalId}
              onChange={(e) => {
                const newId = e.target.value;
                setSelectedRetrievalId(newId);
                if (newId) {
                  // Selecting a retrieval immediately runs the dependency check on its package.xml
                  // ("select and then proceed")
                  loadFromRetrieval(newId);
                }
              }}
              disabled={!selectedOrgId || retrievals.length === 0}
              className="af-input"
            >
              <option value="">
                {retrievals.length
                  ? 'Choose a retrieval (selecting runs the check)...'
                  : 'No retrievals for this org yet - create one in Retrievals tab'}
              </option>
              {retrievals.map((r: Retrieval) => {
                const when = r.completed_at ? new Date(r.completed_at).toLocaleDateString() : 'In progress';
                const statusBadge = r.status === 'success' ? '✓' : r.status === 'running' ? '⏳' : '⚠️';
                const pkgInfo = r.package_xml ? ' (has package)' : ' (no package yet)';
                return (
                  <option key={r.id} value={r.id} disabled={r.status !== 'success'}>
                    {statusBadge} {when} • {r.id.slice(0,8)} {pkgInfo}
                  </option>
                );
              })}
            </select>
            <div className="text-[10px] text-slate-400 mt-1">Only successful retrievals that contain a package.xml are shown.</div>
          </div>
        </div>

        {retrievalIdParam && !graphData && (
          <div className="mt-3 text-xs text-af-blue">Loading package from URL param...</div>
        )}
      </div>

      {/* ========== SECONDARY: Manual / Ad-hoc (still useful for quick tests) ========== */}
      <div className="af-panel mb-8">
        <div className="flex items-center justify-between mb-3">
          <div>
            <div className="font-semibold text-slate-800 dark:text-slate-100">2. Manual Components (or edit the parsed package above)</div>
            <div className="text-xs text-slate-500 dark:text-slate-400">One line per type: <code className="font-mono">ApexClass:MyClass,OtherClass</code></div>
          </div>
          <button
            onClick={handleBuildCustom}
            disabled={loading || (!selectedOrgId && !orgIdParam)}
            className="af-btn-secondary text-sm"
          >
            {loading ? 'Analyzing...' : 'Analyze These Components'}
          </button>
        </div>
        <textarea
          value={customInput}
          onChange={(e) => setCustomInput(e.target.value)}
          className="af-input font-mono text-sm h-20"
          placeholder={'// Example (one type per line)\n// Flow:My_Approval_Flow\n// ApexClass:MyTriggerHandler,MyService'}
        />
        <div className="mt-1.5 text-[10px] text-slate-400 dark:text-slate-500">
          Salesforce deployment order rule of thumb: CustomMetadata → CustomObject → Apex → Flow → PermissionSet → Profile
        </div>
      </div>

      {/* Inline error if present during interaction (can show even without current graph) */}
      {error && (
        <div className="mb-4 af-panel !p-3 !mb-6 text-sm border border-red-200 dark:border-red-900/50 bg-red-50 dark:bg-red-950/30 text-red-700 dark:text-red-300">
          {error}
          <button className="ml-3 underline" onClick={() => setError(null)}>dismiss</button>
        </div>
      )}

      {!data && (
        <div className="af-panel text-center py-12 mb-8">
          <div className="text-4xl mb-3">📦</div>
          <p className="font-medium text-slate-700 dark:text-slate-200 mb-2">No dependency graph yet.</p>
          <p className="text-sm text-slate-500 dark:text-slate-400 max-w-lg mx-auto">
            Use the <strong>"Use a Retrieved Package (recommended)"</strong> panel above:<br />
            Select an organization, then choose a completed retrieval from the dropdown — selecting it will immediately run the dependency analysis on its real package.xml.
            <br /><br />
            Or, after choosing an org, use the manual components panel and click "Analyze These Components".
          </p>
        </div>
      )}

      {data && (
        <>
          {/* Stats Overview — themed */}
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-8">
            {[
              { label: 'Total Components', value: data.graph.stats.total_nodes },
              { label: 'Changed', value: data.graph.stats.changed_components },
              { label: 'Impacted', value: data.graph.stats.impacted_components },
              { label: 'Missing', value: data.graph.stats.missing_dependencies },
              { label: 'Dependencies', value: data.graph.stats.total_edges },
            ].map((s, idx) => (
              <div key={idx} className="af-card p-4">
                <div className={`text-2xl font-bold text-slate-900 dark:text-white`}>{s.value}</div>
                <div className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">{s.label}</div>
              </div>
            ))}
          </div>

      {/* Missing Dependencies Alert — dark aware */}
      {data.missing_dependencies.length > 0 && (
        <div className="af-panel mb-8 !p-5 border-l-4 border-rose-500 bg-rose-50 dark:bg-rose-950/30">
          <div className="flex items-start gap-3">
            <div className="text-rose-500 mt-0.5">⚠️</div>
            <div className="flex-1">
              <div className="font-semibold text-rose-700 dark:text-rose-400">Missing Dependencies Detected ({data.missing_dependencies.length})</div>
              <div className="text-sm text-rose-600 dark:text-rose-300 mt-1">
                These components are required by your retrieved package but were not included. The AI + rule engine recommends adding them for a successful deployment.
              </div>
              <button
                onClick={autoAddMissing}
                disabled={loading}
                className="mt-3 af-btn-primary bg-rose-600 hover:bg-rose-700 text-sm"
              >
                {loading ? 'Adding...' : '✓ Auto-Add Missing Dependencies (Permission Sets, Custom Metadata, etc.)'}
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* Dependency Graph Visualization — themed */}
        <div className="af-card p-6">
          <h2 className="text-xl font-semibold text-slate-800 dark:text-slate-100 mb-4">Dependency Graph</h2>
          
          <div className="space-y-3 max-h-96 overflow-y-auto pr-1">
            {data.graph.nodes.map((node) => (
              <div key={node.id} className="border border-slate-200 dark:border-white/10 rounded-lg p-3 bg-white dark:bg-slate-800/60 text-slate-800 dark:text-slate-200">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className={`w-3 h-3 rounded-full ${getNodeColor(node)}`}></div>
                    <div>
                      <div className="font-medium text-slate-900 dark:text-white">{node.name}</div>
                      <div className="text-xs text-slate-500 dark:text-slate-400">{node.type}</div>
                    </div>
                  </div>
                  <div className="flex gap-1.5">
                    {node.is_changed && (
                      <span className="px-2 py-0.5 text-[10px] bg-af-blue/10 text-af-blue dark:bg-af-blue/20 rounded">Changed</span>
                    )}
                    {node.is_impacted && (
                      <span className="px-2 py-0.5 text-[10px] bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300 rounded">Impacted</span>
                    )}
                  </div>
                </div>
                
                {data.graph.edges.filter(e => e.source === node.id).length > 0 && (
                  <div className="mt-2 ml-5 text-xs text-slate-600 dark:text-slate-400">
                    <span className="font-medium">Depends on: </span>
                    {data.graph.edges
                      .filter(e => e.source === node.id)
                      .map((edge) => edge.target.split(':')[1] || edge.target)
                      .join(', ')}
                  </div>
                )}
              </div>
            ))}
            {data.graph.nodes.length === 0 && <div className="text-xs text-slate-500">No nodes</div>}
          </div>
        </div>

        {/* Missing Dependencies (right column) — dark aware */}
        <div className="af-card p-6">
          <h2 className="text-xl font-semibold text-slate-800 dark:text-slate-100 mb-4">
            Missing Dependencies ({data.missing_dependencies.length})
          </h2>
          
          <div className="space-y-3 max-h-96 overflow-y-auto pr-1">
            {data.missing_dependencies.map((dep, idx) => (
              <div key={idx} className={`border rounded-lg p-3 text-sm ${getSeverityColor(dep.severity)}`}>
                <div className="flex justify-between items-start gap-2">
                  <div>
                    <div className="font-semibold text-slate-900 dark:text-white">{dep.name}</div>
                    <div className="text-xs opacity-75">{dep.type}</div>
                    <div className="text-xs mt-1.5 opacity-90">{dep.reason}</div>
                    <div className="text-[10px] mt-1 opacity-75">Required by: {dep.required_by.join(', ')}</div>
                  </div>
                  <span className="text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-black/10 dark:bg-white/10 self-start">
                    {dep.severity}
                  </span>
                </div>
              </div>
            ))}
            
            {data.missing_dependencies.length === 0 && (
              <div className="text-center py-10 text-slate-500 dark:text-slate-400">
                <div className="text-3xl mb-2">✅</div>
                <p className="text-sm">No missing dependencies detected. Nice!</p>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Deployment Order — themed */}
      <div className="mt-8 af-card p-6">
        <h2 className="text-xl font-semibold text-slate-800 dark:text-slate-100 mb-1">📦 Recommended Deployment Order</h2>
        <p className="text-xs text-slate-500 dark:text-slate-400 mb-4">Topologically sorted (lowest level dependencies first). This is what makes Salesforce deployments succeed.</p>
        
        <div className="flex flex-wrap gap-2">
          {data.deployment_order.map((component, idx) => (
            <div key={idx} className="flex items-center">
              <div className="px-3 py-1.5 rounded-lg text-sm font-medium bg-slate-100 dark:bg-slate-800 text-slate-800 dark:text-slate-200 border border-slate-200 dark:border-white/10">
                <span className="text-af-blue font-mono text-xs mr-1.5">{idx + 1}.</span>
                {component.split(':')[1] || component}
                <span className="ml-1.5 text-[10px] text-slate-500 dark:text-slate-400">({component.split(':')[0]})</span>
              </div>
              {idx < data.deployment_order.length - 1 && (
                <span className="mx-1 text-slate-300 dark:text-slate-600">→</span>
              )}
            </div>
          ))}
          {data.deployment_order.length === 0 && <span className="text-xs text-slate-400">No order computed</span>}
        </div>
      </div>

      {/* Package XML */}
      {data.package_xml && (
        <div className="mt-8 af-card p-6">
          <div className="flex items-center justify-between mb-3">
            <div>
              <span className="font-semibold text-slate-800 dark:text-slate-100">📄 Auto-generated package.xml</span>
              <span className="ml-2 text-xs text-emerald-600 dark:text-emerald-400">(includes auto-added missing deps + correct order)</span>
            </div>
            <button
              onClick={() => setShowPackageXml(!showPackageXml)}
              className="text-af-blue hover:underline text-sm"
            >
              {showPackageXml ? 'Hide XML' : 'Show XML'}
            </button>
          </div>
          
          {showPackageXml && (
            <pre className="bg-slate-900 text-emerald-200 p-4 rounded-lg overflow-auto text-xs font-mono max-h-72 border border-slate-800">
              <code>{data.package_xml}</code>
            </pre>
          )}
          {!showPackageXml && (
            <div className="text-xs text-slate-500">Click "Show XML" to inspect the generated manifest that you can use directly with sf project deploy or the Deployment tab.</div>
          )}
        </div>
      )}

      {/* Actions */}
      <div className="mt-8 flex flex-wrap gap-3">
        <button
          onClick={() => {
            try { sessionStorage.setItem('cb_last_analysis', data.analysis_id); } catch {}
            alert(`Switch to the "Deployments" tab in the top navigation.\n\nAnalysis ID: ${data.analysis_id}\n\nYou can create a deployment from this analysis (the package.xml with correct ordering + added missing components is already attached).`);
          }}
          className="af-btn-primary"
        >
          🚀 Go to Deployments (use this analysis)
        </button>

        <button
          onClick={() => {
            const blob = new Blob([data.package_xml || ''], { type: 'text/xml' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'package.xml';
            a.click();
          }}
          className="af-btn-secondary"
        >
          Download package.xml
        </button>

        <button
          onClick={downloadDependencyGraphPdf}
          className="af-btn-secondary"
        >
          Download AI Dependency Graph PDF
        </button>

        <button
          onClick={() => {
            if (!data) return;
            setLoading(true);
            fetch('/api/v1/dependency-graph/auto-package', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ analysis_id: data.analysis_id, auto_add_missing: true, include_profiles: true, include_permission_sets: true })
            }).then(r => r.json()).then(d => {
              setGraphData(prev => prev ? { ...prev, package_xml: d.package_xml, deployment_order: d.deployment_order || prev.deployment_order } : prev);
            }).catch(e => setError(String(e))).finally(() => setLoading(false));
          }}
          className="af-btn-secondary"
        >
          Regenerate with full auto-add
        </button>
      </div>

      <div className="mt-4 text-xs text-slate-500 dark:text-slate-400">
        The order above (and inside the generated package.xml) is what prevents the classic “dependent component is not in the package” deployment failures in Salesforce.
      </div>
        </>
      )}
    </div>
  );
};

export default DependencyGraph;

// Made with Bob
