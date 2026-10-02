import { useMemo, useRef, useState } from 'react'
import { formatClock, formatDayLong, isBlank } from '../../format.js'
import MiniSheet from '../logs/MiniSheet.jsx'
import Directions from './Directions.jsx'
import StatSigns from './StatSigns.jsx'
import RouteMap from './RouteMap.jsx'
import StopTimeline, { buildTimeline } from './StopTimeline.jsx'
import './ResultsPage.css'

function Subtitle({ plan }) {
  const { details } = plan
  const parts = [`Pickup in ${plan.waypoints[1].label}`]
  if (!isBlank(details.truck_number)) parts.push(`Tractor ${details.truck_number.trim()}`)
  if (!isBlank(details.driver_name)) parts.push(details.driver_name.trim())
  return <div className="results__sub">{parts.join(' • ')}</div>
}

/**
 * plan: the /api/plan-trip response.
 * departure: Date of the start time the driver entered (the API does not echo it).
 * onOpenLogs(dayIndex): open the log viewer at that day.
 */
export default function ResultsPage({ plan, departure, onEdit, onOpenLogs }) {
  const mapRef = useRef(null)
  const items = useMemo(() => buildTimeline(plan, departure), [plan, departure])
  // { index, source: 'timeline' | 'map' }; a new object each click so re-clicking re-centers.
  const [selected, setSelected] = useState(null)
  const from = plan.waypoints[0].label
  const to = plan.waypoints[2].label

  const selectFromTimeline = (index) => {
    // On narrow screens the map is above the timeline: bring it into view first.
    const box = mapRef.current?.getBoundingClientRect()
    if (box && (box.top < 0 || box.bottom > window.innerHeight)) {
      mapRef.current.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }
    setSelected({ index, source: 'timeline' })
  }

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
            <button type="button" className="btn btn--primary" onClick={() => onOpenLogs(0)}>
              View daily logs
            </button>
          </div>
        </div>

        <StatSigns summary={plan.summary} sheets={plan.sheets} />

        <div className="results__main">
          <div className="results__map" ref={mapRef}>
            <RouteMap
              geometry={plan.geometry}
              items={items}
              selected={selected}
              onSelect={(index) => setSelected({ index, source: 'map' })}
            />
          </div>
          <StopTimeline items={items} days={plan.summary.days} selected={selected} onSelect={selectFromTimeline} />
        </div>

        <div className="lane-line results__divider" aria-hidden="true" />

        <section className="results__logs" aria-labelledby="logs-title">
          <div className="results__logs-head">
            <h2 className="badge badge--numbered" id="logs-title">
              <span className="badge__num">{plan.sheets.length}</span>
              Daily log sheets
            </h2>
            <a
              href="#"
              className="results__logs-link"
              onClick={(e) => {
                e.preventDefault()
                onOpenLogs(0)
              }}
            >
              Open log viewer →
            </a>
          </div>
          <div className="results__sheets">
            {plan.sheets.map((sheet, i) => (
              <MiniSheet key={sheet.date} sheet={sheet} index={i} onOpen={() => onOpenLogs(i)} />
            ))}
          </div>
        </section>

        <Directions directions={plan.directions} />
      </div>
    </main>
  )
}
