import { formatClock, formatDay, formatDuration, minutesBetween, parseLocal } from '../../format.js'
import StopIcon, { STOP_KINDS } from './StopIcon.jsx'

/**
 * Timeline items: the current location at departure, then every API stop. Between items
 * only driving happens (every non-driving period is a stop), so the gap between one item's
 * end and the next one's start is drive time, and the trip_miles difference is the distance.
 */
export function buildTimeline(plan, departure) {
  const items = [
    { kind: 'start', name: plan.waypoints[0].label, start: departure, end: departure, miles: 0, tag: 'Start' },
  ]
  for (const s of plan.stops) {
    items.push({
      kind: s.type,
      name: s.name,
      start: parseLocal(s.start),
      end: parseLocal(s.end),
      miles: s.trip_miles,
      tag: formatDuration(s.duration_min),
    })
  }
  for (let i = 1; i < items.length; i++) {
    const prev = items[i - 1]
    const driveMin = minutesBetween(prev.end, items[i].start)
    if (driveMin > 0) items[i].driveBefore = { minutes: driveMin, miles: items[i].miles - prev.miles }
  }
  return items
}

export default function StopTimeline({ plan, departure }) {
  const items = buildTimeline(plan, departure)
  const days = plan.summary.days

  return (
    <section className="timeline" aria-labelledby="stops-title">
      <div className="timeline__head">
        <h2 className="badge" id="stops-title">
          Stops
        </h2>
        <span className="timeline__count">
          {items.length} stops • {days} {days === 1 ? 'day' : 'days'}
        </span>
      </div>
      <ol className="timeline__list">
        {items.map((item, i) => {
          const kind = STOP_KINDS[item.kind]
          return (
            <li key={i}>
              {item.driveBefore && (
                <div className="timeline__drive">
                  <span className="timeline__lane" aria-hidden="true" />
                  <span>
                    Drive {formatDuration(item.driveBefore.minutes)} • {Math.round(item.driveBefore.miles).toLocaleString('en-US')} mi
                  </span>
                </div>
              )}
              <div className="timeline__stop">
                <StopIcon kind={item.kind} />
                <span className="timeline__body">
                  <span className="timeline__kind" style={{ color: kind.text }}>
                    {kind.name}
                  </span>
                  <span className="timeline__name">{item.name}</span>
                  <span className="timeline__time">
                    {formatDay(item.start)} • {formatClock(item.start)}
                  </span>
                </span>
                <span className="timeline__tag">{item.tag}</span>
              </div>
            </li>
          )
        })}
      </ol>
      <p className="timeline__note">Times in home terminal time.</p>
    </section>
  )
}
