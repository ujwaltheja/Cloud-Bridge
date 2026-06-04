import { useEffect, useState } from 'react'

// ---------------------------------------------------------------------------
// PKCE helpers (Web Crypto API — no external deps)
// ---------------------------------------------------------------------------
function generateCodeVerifier(): string {
  const array = new Uint8Array(32)
  crypto.getRandomValues(array)
  return btoa(String.fromCharCode(...array))
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '')
}

async function generateCodeChallenge(verifier: string): Promise<string> {
  const encoder = new TextEncoder()
  const data = encoder.encode(verifier)
  const digest = await crypto.subtle.digest('SHA-256', data)
  return btoa(String.fromCharCode(...new Uint8Array(digest)))
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '')
}

interface Org {
  id: string
  name: string
  org_type: string
  auth_method: string
  instance_url?: string
  client_id?: string
  client_secret?: string
  last_connection_status?: string
  last_connection_error?: string
  created_at: string
}

function StatusBadge({ status }: { status?: string }) {
  const s = status?.toLowerCase() || 'unknown'
  const cls =
    s === 'success'  ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-400' :
    s === 'error' || s === 'failed' ? 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-400' :
    'bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400'
  return (
    <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${cls}`}>
      {status || 'Never tested'}
    </span>
  )
}

export default function OrgsPage() {
  const [orgs, setOrgs] = useState<Org[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [formMode, setFormMode] = useState<'oauth_web' | 'jwt'>('jwt')
  const [formData, setFormData] = useState<any>({})
  const [submitting, setSubmitting] = useState(false)

  const fetchOrgs = async () => {
    setLoading(true)
    try {
      const res = await fetch('/api/v1/orgs')
      if (res.ok) setOrgs(await res.json())
    } catch (e) { console.error(e) }
    setLoading(false)
  }

  useEffect(() => { fetchOrgs() }, [])

  const startOAuthRedirect = async (orgId: string, clientId: string, clientSecret?: string) => {
    const redirectUri = window.location.origin + '/oauth/callback'
    const verifier = generateCodeVerifier()
    const challenge = await generateCodeChallenge(verifier)
    sessionStorage.setItem('pkce_verifier', verifier)
    const res = await fetch(`/api/v1/orgs/${orgId}/oauth/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        client_id: clientId,
        client_secret: clientSecret || undefined,
        redirect_uri: redirectUri,
        code_challenge: challenge,
        code_challenge_method: 'S256',
      }),
    })
    if (res.ok) {
      const data = await res.json()
      window.location.href = data.authorization_url
    } else {
      alert('Failed to start OAuth: ' + (await res.text()))
      await fetchOrgs()
    }
  }

  const handleAddOrg = async () => {
    setSubmitting(true)
    try {
      const res = await fetch('/api/v1/orgs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...formData, auth_method: formMode }),
      })
      if (res.ok) {
        const org = await res.json()
        setShowForm(false)
        setFormData({})
        if (formMode === 'oauth_web' && org.id && formData.client_id) {
          await startOAuthRedirect(org.id, formData.client_id, formData.client_secret)
        } else {
          await fetchOrgs()
        }
      } else {
        alert('Failed to add org: ' + (await res.text()))
      }
    } catch (e) { alert('Error: ' + e) }
    setSubmitting(false)
  }

  const connectOAuth = async (org: Org) => {
    if (!org.client_id) {
      alert('No Client ID stored for this org. Please delete and re-add it with a Consumer Key.')
      return
    }
    await startOAuthRedirect(org.id, org.client_id, org.client_secret)
  }

  const testConnection = async (id: string) => {
    const res = await fetch(`/api/v1/orgs/${id}/test`, { method: 'POST' })
    if (!res.ok) { alert('Test failed: ' + await res.text()); return }
    const data = await res.json()
    alert(data.success ? 'Connection successful!' : 'Failed: ' + data.message)
    await fetchOrgs()
  }

  const deleteOrg = async (id: string, name: string) => {
    // Use window.confirm to ensure browser compatibility
    const confirmed = window.confirm(`Delete "${name}"? This cannot be undone.`)
    if (!confirmed) {
      console.log('Delete cancelled by user')
      return
    }
    
    console.log(`Deleting org ${id} (${name})...`)
    try {
      const res = await fetch(`/api/v1/orgs/${id}`, { method: 'DELETE' })
      console.log(`Delete response: ${res.status} ${res.statusText}`)
      
      if (res.ok || res.status === 204) {
        console.log('Delete successful, refreshing org list...')
        await fetchOrgs()
        alert(`Successfully deleted "${name}"`)
      } else {
        const errorText = await res.text()
        console.error('Delete failed:', errorText)
        alert('Failed to delete org: ' + errorText)
      }
    } catch (e) {
      console.error('Delete error:', e)
      alert('Error deleting org: ' + e)
    }
  }

  return (
    <div className="max-w-5xl mx-auto px-6 py-10">
      <div className="flex justify-between items-start mb-8">
        <div>
          <h1 className="font-display text-3xl font-bold af-gradient-text">Connected Orgs</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            Authorized Salesforce organizations — connect via JWT or Web OAuth.
          </p>
        </div>
        <button
          onClick={() => setShowForm(!showForm)}
          className={`af-btn-primary ${showForm ? '!bg-slate-500 hover:!bg-slate-600' : ''}`}
        >
          {showForm ? '✕ Cancel' : '+ Add Org'}
        </button>
      </div>

      {showForm && (
        <div className="af-panel mb-8">
          <h2 className="font-semibold text-slate-700 dark:text-slate-200 mb-4">New Organization</h2>
          <div className="flex gap-2 mb-5">
            {(['jwt', 'oauth_web'] as const).map(mode => (
              <button
                key={mode}
                onClick={() => setFormMode(mode)}
                className={`px-4 py-1.5 rounded-lg text-sm font-semibold transition-colors
                  ${formMode === mode ? 'bg-af-blue text-white' : 'af-btn-secondary'}`}
              >
                {mode === 'jwt' ? 'JWT Server-to-Server' : 'Web OAuth'}
              </button>
            ))}
          </div>
          <div className="space-y-3">
            <input placeholder="Org Name (e.g. Dev Sandbox)" className="af-input"
              onChange={(e) => setFormData({ ...formData, name: e.target.value })} />
            <select className="af-input"
              onChange={(e) => setFormData({ ...formData, org_type: e.target.value })}>
              <option value="sandbox">Sandbox</option>
              <option value="production">Production</option>
              <option value="developer">Developer</option>
            </select>
            {formMode === 'jwt' && (
              <>
                <input placeholder="Client ID (Consumer Key)" className="af-input"
                  onChange={(e) => setFormData({ ...formData, client_id: e.target.value })} />
                <input placeholder="Username" className="af-input"
                  onChange={(e) => setFormData({ ...formData, username: e.target.value })} />
                <textarea placeholder="Private Key (PEM)" rows={5}
                  className="af-input font-mono text-xs resize-none"
                  onChange={(e) => setFormData({ ...formData, private_key: e.target.value })} />
              </>
            )}
            {formMode === 'oauth_web' && (
              <>
                <input placeholder="Consumer Key (Client ID)" className="af-input"
                  onChange={(e) => setFormData({ ...formData, client_id: e.target.value })} />
                <input placeholder="Consumer Secret (Client Secret) — leave blank if 'Require Secret' is disabled" className="af-input"
                  type="password"
                  onChange={(e) => setFormData({ ...formData, client_secret: e.target.value || undefined })} />
              </>
            )}
          </div>
          <button onClick={handleAddOrg} disabled={submitting} className="af-btn-primary mt-5">
            {submitting ? 'Connecting…' : 'Add Organization'}
          </button>
        </div>
      )}

      {loading ? (
        <div className="text-slate-400 text-sm py-8 text-center">Loading orgs…</div>
      ) : orgs.length === 0 ? (
        <div className="af-card p-10 text-center">
          <p className="text-slate-400">No orgs connected yet.</p>
          <button onClick={() => setShowForm(true)} className="af-btn-primary mt-4">Connect your first org</button>
        </div>
      ) : (
        <div className="space-y-3">
          {orgs.map((org) => (
            <div key={org.id} className="af-card p-5 flex flex-col sm:flex-row justify-between gap-4">
              <div className="flex-1 min-w-0">
                <div className="font-semibold text-slate-800 dark:text-slate-100">{org.name}</div>
                <div className="text-sm text-slate-500 dark:text-slate-400 mt-0.5">
                  {org.org_type} · {org.auth_method}
                </div>
                <div className="flex items-center gap-2 mt-2">
                  <StatusBadge status={org.last_connection_status} />
                  {org.last_connection_error && (
                    <span className="text-xs text-red-400 truncate max-w-xs">{org.last_connection_error}</span>
                  )}
                </div>
                <div className="af-mono-badge mt-2 inline-block">{org.id}</div>
              </div>
              <div className="flex items-start gap-2 shrink-0">
                {org.auth_method === 'oauth_web' && !org.instance_url ? (
                  <button onClick={() => connectOAuth(org)}
                    className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-af-blue text-white hover:bg-af-blue/90 transition">
                    Connect / Authorize
                  </button>
                ) : (
                  <button onClick={() => testConnection(org.id)} className="af-btn-secondary text-xs">
                    Test Connection
                  </button>
                )}
                <button onClick={() => deleteOrg(org.id, org.name)}
                  className="px-3 py-1.5 rounded-lg text-xs font-medium bg-red-50 text-red-600
                                   hover:bg-red-100 dark:bg-red-900/20 dark:text-red-400
                                   dark:hover:bg-red-900/40 transition">
                  Delete
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
