import { useEffect, useRef } from 'react'

export default function OAuthCallback() {
  const called = useRef(false)

  useEffect(() => {
    if (called.current) return   // prevent StrictMode double-fire
    called.current = true

    const searchParams = new URLSearchParams(window.location.search)
    const code = searchParams.get('code')
    const state = searchParams.get('state')

    if (code && state) {
      const verifier = sessionStorage.getItem('pkce_verifier')
      sessionStorage.removeItem('pkce_verifier')
      const redirectUri = window.location.origin + '/oauth/callback'
      fetch(`/api/v1/orgs/oauth/callback?state=${encodeURIComponent(state)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code, redirect_uri: redirectUri, code_verifier: verifier }),
      })
        .then(async res => {
          if (!res.ok) throw new Error(await res.text())
          return res.json()
        })
        .then(data => {
          if (data.success) {
            alert('✅ Organization connected successfully!')
            window.location.href = '/'
          } else {
            alert('Failed to connect org: ' + (data.message || 'Unknown error'))
            window.location.href = '/'
          }
        })
        .catch((err) => { alert('Error completing OAuth: ' + err.message); window.location.href = '/' })
    } else {
      alert('Invalid OAuth callback')
      window.location.href = '/'
    }
  }, [])

  return (
    <div className="min-h-[60vh] flex flex-col items-center justify-center">
      <div className="af-card p-10 text-center max-w-sm">
        <div className="text-4xl mb-4">⟳</div>
        <h1 className="font-display text-2xl font-bold af-gradient-text mb-2">Completing OAuth…</h1>
        <p className="text-slate-400 text-sm">Please wait, do not close this tab.</p>
      </div>
    </div>
  )
}


