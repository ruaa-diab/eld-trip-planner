import { useRef } from 'react'
import { formatClock, formatDay, formatDayLong, formatMiles, isBlank, parseLocal } from '../../format.js'
import Directions from './Directions.jsx'
import StatSigns from './StatSigns.jsx'
import StopTimeline from './StopTimeline.jsx'
import './ResultsPage.css'

function Subtitle({ plan }) {
  const { details } = plan
  const parts = [`Pickup in ${plan.waypoints[1].label}`]
  if (!isBlank(details.truck_number)) parts.push(`Tractor ${details.truck_number.trim()}`)
  if (!isBlank(details.driver_name)) parts.push(details.driver_name.trim())
  return <div className="results__sub">{parts.join(' • ')}</div>
}

/** Stand-in for the mini log sheet drawn in step 4. */
function SheetPlaceholder({ sheet, index }) {
  return (
    <div className="mini-sheet">
      <div className="mini-sheet__head">
        <span className="mini-sheet__day">
          Day {index + 1} • {formatDay(parseLocal(sheet.date))}
        </span>
        <span className="mini-sheet__miles">{formatMiles(sheet.miles)} mi</span>
      </div>
      <div className="mini-sheet__route">
        {sheet.from} → {sheet.to}
      </div>
      <div className="mini-sheet__placeholder">Log grid and totals (step 4)</div>
    </div>
  )
}

/**
 * plan: the /api/plan-trip response.
 * departure: Date of the start time the driver entered (the API does not echo it).
 */
export default function ResultsPage({ plan, departure, onEdit }) {
  const logsRef = useRef(null)
  const from = plan.waypoints[0].label
  const to = plan.waypoints[2].label

  return (
    <main className="page">
      <div className="results">
        <div className="results__top">
          <div className="results__heading">
            <div className="results__eyebrow">
              Trip plan • departs {formatDayLong(departure)} at {formatClock(departure)}
            </div>
            <h1 className="results__title">
              {from} → {to}
            </h1>
            <Subtitle plan={plan} />
          </div>
          <div className="results__actions">
            <button type="button" className="btn btn--ghost" onClick={onEdit}>
              Edit trip
            </button>
            <button
              type="button"
              className="btn btn--primary"
              onClick={() => logsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })}
            >
              View daily logs
            </button>
          </div>
        </div>

        <StatSigns summary={plan.summary} sheets={plan.sheets} />

        <div className="results__main">
          <div className="results__map placeholder-box">
            <span>Route map (step 3)</span>
          </div>
          <StopTimeline plan={plan} departure={departure} />
        </div>

        <div className="lane-line results__divider" aria-hidden="true" />

        <section ref={logsRef} className="results__logs" aria-labelledby="logs-title">
          <div className="results__logs-head">
            <h2 className="badge badge--numbered" id="logs-title">
              <span className="badge__num">{plan.sheets.length}</span>
              Daily log sheets
            </h2>
          </div>
          <div className="results__sheets">
            {plan.sheets.map((sheet, i) => (
              <SheetPlaceholder key={sheet.date} sheet={sheet} index={i} />
            ))}
          </div>
        </section>

        <Directions directions={plan.directions} />
      </div>
    </main>
  )
}
