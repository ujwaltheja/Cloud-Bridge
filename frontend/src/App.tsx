import { useState, useEffect } from 'react'
import OrgsPage from './pages/Orgs'
import RetrievalsPage from './pages/Retrievals'
import ComparisonsPage from './pages/Comparisons'
import DeploymentsPage from './pages/Deployments'
import ImpactAnalysisPage from './pages/ImpactAnalysis'
import OAuthCallback from './pages/OAuthCallback'
import DependencyGraphPage from './pages/DependencyGraph'

type Page = 'orgs' | 'retrievals' | 'comparisons' | 'deployments' | 'impact-analysis' | 'dependency-graph' | 'oauth-callback' | 'home'

function SunIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24"
      fill="none" stroke="#F59E0B" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="5"/>
      <line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/>
      <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/>
      <line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/>
      <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
    </svg>
  )
}

function MoonIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24"
      fill="none" stroke="#475569" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
    </svg>
  )
}

function SettingsIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24"
      fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="3"/>
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0
      0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0
      0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2
      2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65
      1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0
      1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
    </svg>
  )
}

const NAV_ITEMS: { label: string; page: Page }[] = [
  { label: 'Orgs', page: 'orgs' },
  { label: 'Retrievals', page: 'retrievals' },
  { label: 'Comparisons', page: 'comparisons' },
  { label: 'Deployments', page: 'deployments' },
  { label: 'AI Release Intel', page: 'impact-analysis' },
  { label: 'Dependency Graph', page: 'dependency-graph' },
  { label: 'Status', page: 'home' },
]

function App() {
  const params = new URLSearchParams(window.location.search)
  const pageFromUrl = params.get('page') as Page | null
  const initialPage: Page = params.get('code')
    ? 'oauth-callback'
    : (pageFromUrl && ['orgs','retrievals','comparisons','deployments','impact-analysis','dependency-graph','home'].includes(pageFromUrl) ? pageFromUrl : 'orgs')

  const [currentPage, setCurrentPage] = useState<Page>(initialPage)
  const [dark, setDark] = useState(() => {
    try { return localStorage.getItem('cb_dark') === 'true' } catch { return false }
  })

  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark)
    try { localStorage.setItem('cb_dark', String(dark)) } catch {}
  }, [dark])

  return (
    <div className="min-h-screen bg-af-slate dark:bg-af-darkbg text-slate-800 dark:text-slate-100 transition-colors duration-200 font-sans">

      {/* ── Fixed Header ── */}
      <header className={`fixed top-0 inset-x-0 z-50 h-12 flex items-center gap-6 px-6
                         backdrop-blur border-b border-slate-200 dark:border-white/10
                         dark:bg-af-darkbg/95
                         ${dark ? '' : 'af-header-light'}`}>

        {/* Logo */}
        <a onClick={() => setCurrentPage('home')} className="flex items-center gap-1.5 cursor-pointer select-none shrink-0">
          <span className="font-display font-extrabold text-af-blue text-lg leading-none">Cloud</span>
          <span className="font-display font-light text-slate-700 dark:text-slate-200 text-lg leading-none tracking-wider">Bridge</span>
        </a>

        {/* Nav */}
        <nav className="flex items-center gap-1 flex-1">
          {NAV_ITEMS.map(({ label, page }) => (
            <button
              key={page}
              onClick={() => setCurrentPage(page)}
              className={`px-3 py-1.5 rounded-md text-sm font-semibold transition-colors
                ${currentPage === page
                  ? (dark ? 'text-af-blue bg-af-blue/15' : 'af-tab-active')
                  : 'text-slate-600 dark:text-slate-400 hover:text-af-blue hover:bg-af-blue/5'
                }`}
            >
              {label}
            </button>
          ))}
        </nav>

        {/* Right actions */}
        <div className="flex items-center gap-3 shrink-0">
          <button
            onClick={() => setDark(d => !d)}
            className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 transition"
            title="Toggle theme"
          >
            {dark ? <SunIcon /> : <MoonIcon />}
          </button>
          <button className="flex items-center gap-1.5 text-sm text-slate-500 dark:text-slate-400
                             hover:text-af-blue transition px-2 py-1 rounded-md">
            <SettingsIcon /> Settings
          </button>
        </div>
      </header>

      {/* ── Page content (offset for fixed header) ── */}
      <main className="pt-12">
        {currentPage === 'orgs'            && <OrgsPage />}
        {currentPage === 'retrievals'      && <RetrievalsPage />}
        {currentPage === 'comparisons'     && <ComparisonsPage />}
        {currentPage === 'deployments'     && <DeploymentsPage />}
        {currentPage === 'impact-analysis' && <ImpactAnalysisPage />}
        {currentPage === 'dependency-graph' && <DependencyGraphPage />}
        {currentPage === 'oauth-callback'  && <OAuthCallback />}
        {currentPage === 'home'            && (
          <div className="max-w-4xl mx-auto px-8 py-16">
            <h1 className="font-display text-5xl font-bold af-gradient-text mb-3">
              Cloud Bridge
            </h1>
            <p className="text-slate-500 dark:text-slate-400 text-lg mb-8">
              Salesforce DevOps Platform — Org Management, Metadata Retrieval &amp; Deployment
            </p>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {NAV_ITEMS.filter(n => n.page !== 'home').map(({ label, page }) => (
                <button
                  key={page}
                  onClick={() => setCurrentPage(page)}
                  className="af-card p-5 text-left hover:border-af-blue/40 dark:hover:border-af-blue/30"
                >
                  <div className="text-af-blue font-semibold mb-1">{label}</div>
                  <div className="text-xs text-slate-400">Go to {label} →</div>
                </button>
              ))}
            </div>
          </div>
        )}
      </main>

      {/* ── Footer ── */}
      <footer className="mt-16 py-6 px-6 text-center border-t border-slate-200 dark:border-slate-800">
        <p className="text-xs text-slate-400 dark:text-slate-500">
          Cloud Bridge v0.1.0 · Salesforce DevOps Platform ·{' '}
          <a href="/api/docs" className="text-af-blue hover:underline">API Docs</a>
        </p>
      </footer>
    </div>
  )
}

export default App

