import { useState, useEffect } from 'react'

function App() {
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    fetch(`${import.meta.env.VITE_API_URL}/api/health`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      })
      .then(setResult)
      .catch((e) => setError(e.message))
  }, [])

  return (
    <div style={{ fontFamily: 'monospace', padding: '2rem' }}>
      <h1>ELD Trip Planner</h1>
      <h2>Backend health check</h2>
      {!result && !error && <p>Fetching {import.meta.env.VITE_API_URL}/api/health …</p>}
      {error && <p style={{ color: 'red' }}>Error: {error}</p>}
      {result && <pre style={{ background: '#f0f0f0', padding: '1rem' }}>{JSON.stringify(result, null, 2)}</pre>}
    </div>
  )
}

export default App
