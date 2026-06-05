import React from 'react'
import ReactDOM from 'react-dom/client'
import './index.css'
import App from './App'

const DEFAULT_API_HOST =
  'https://cloud-bridge-himalay-testing.bobathon-us-south-1-bx2-1-eed9cf6127dd1cc2309a78aba5f4061d-0000.us-south.containers.appdomain.cloud'

function normalizeApiBaseUrl(rawUrl: string): string {
  const trimmed = rawUrl.trim()
  if (!trimmed) return ''
  return trimmed
    .replace(/\/+$/, '')
    .replace(/\/api\/v1\/docs$/i, '')
    .replace(/\/api\/v1$/i, '')
}

const apiBaseUrl = normalizeApiBaseUrl(import.meta.env.VITE_API_BASE_URL ?? DEFAULT_API_HOST)

if (apiBaseUrl) {
  const originalFetch = window.fetch.bind(window)
  window.fetch = (input: RequestInfo | URL, init?: RequestInit) => {
    if (typeof input === 'string' && input.startsWith('/api/')) {
      return originalFetch(`${apiBaseUrl}${input}`, init)
    }
    return originalFetch(input, init)
  }
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
