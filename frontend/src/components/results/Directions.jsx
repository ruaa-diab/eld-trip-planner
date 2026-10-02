import { useState } from 'react'
import { formatDuration } from '../../format.js'

// Route numbers inside ORS road names, e.g. "Jane Addams Memorial Tollway, I 90" → "I-90".
const ROUTE_REF = /^(I|US)[ -]?(\d+[A-Z]?)$/

/** Road labels for one step: its interstate/US numbers, or the plain name if it has none. */
function roadLabels(name) {
  const parts = name.split(',').map((p) => p.trim()).filter(Boolean)
  const refs = parts.map((p) => p.match(ROUTE_REF)).filter(Boolean).map((m) => `${m[1]}-${m[2]}`)
  return refs.length ? refs : [name]
}

/** The 3 roads covering the most distance, listed in route order. */
function mainRoads(directions) {
  const total = new Map()
  const firstSeen = new Map()
  let order = 0
  for (const leg of directions) {
    for (const step of leg.steps) {
      const name = step.name?.trim()
      if (!name || name === '-') continue
      for (const label of roadLabels(name)) {
        total.set(label, (total.get(label) || 0) + step.distance_miles)
        if (!firstSeen.has(label)) firstSeen.set(label, order++)
      }
    }
  }
  // Prefer route numbers; use plain road names only for a route without any.
  const entries = [...total.entries()]
  const refs = entries.filter(([label]) => /^(I|US)-/.test(label))
  return (refs.length ? refs : entries)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 3)
    .map(([name]) => name)
    .sort((a, b) => firstSeen.get(a) - firstSeen.get(b))
}

function formatStepMiles(mi) {
  if (mi < 0.1) return `${Math.round(mi * 5280)} ft`
  return `${mi < 10 ? mi.toFixed(1) : Math.round(mi).toLocaleString('en-US')} mi`
}

export default function Directions({ directions }) {
  const [open, setOpen] = useState(false)
  const stepCount = directions.reduce((n, leg) => n + leg.steps.length, 0)
  const roads = mainRoads(directions)

  return (
    <section className="card directions">
      <button
        type="button"
        className="directions__toggle"
        aria-expanded={open}
        aria-controls="directions-body"
        onClick={() => setOpen(!open)}
      >
        <span className="directions__summary">
          <span className="badge">Turn-by-turn directions</span>
          <span className="directions__meta">
            {stepCount} steps{roads.length ? ` • ${roads.join(', ')}` : ''}
          </span>
        </span>
        <svg
          className={open ? 'directions__chevron directions__chevron--open' : 'directions__chevron'}
          width="20"
          height="20"
          viewBox="0 0 20 20"
          aria-hidden="true"
        >
          <path d="M5 8l5 5 5-5" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>
      {open && (
        <div className="directions__body" id="directions-body">
          {directions.map((leg, i) => (
            <div className="directions__leg" key={i}>
              <h3 className="directions__leg-title">
                {leg.from} → {leg.to}
                <span className="directions__leg-meta">
                  {leg.distance_miles.toLocaleString('en-US')} mi • {formatDuration(leg.duration_min)}
                </span>
              </h3>
              <ol className="directions__steps">
                {leg.steps.map((step, j) => (
                  <li className="directions__step" key={j}>
                    <span className="directions__num" aria-hidden="true">
                      {j + 1}
                    </span>
                    <span className="directions__text">{step.instruction}</span>
                    <span className="directions__dist">{formatStepMiles(step.distance_miles)}</span>
                  </li>
                ))}
              </ol>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}
