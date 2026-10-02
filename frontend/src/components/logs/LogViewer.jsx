import { useEffect } from 'react'
import { formatDay, formatMiles, isBlank, parseLocal } from '../../format.js'
import LogSheet from './LogSheet.jsx'

/**
 * Daily log viewer: day navigation + one full sheet.
 * Printing is handled by <PrintLogs>, which renders every day.
 */
export default function LogViewer({ plan, day, onDay, onBack }) {
  const sheets = plan.sheets
  const sheet = sheets[day]
  const last = sheets.length - 1
  const driver = plan.details.driver_name

  useEffect(() => {
    const onKey = (e) => {
      if (e.target.closest?.('input, textarea, select')) return
      if (e.key === 'ArrowLeft' && day > 0) onDay(day - 1)
      if (e.key === 'ArrowRight' && day < last) onDay(day + 1)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [day, last, onDay])

  return (
    <main className="page">
      <div className="page__inner viewer">
        <a
          href="#"
          className="viewer__back"
          onClick={(e) => {
            e.preventDefault()
            onBack()
          }}
        >
          ← Trip results
        </a>
        <div className="viewer__top">
          <div>
            <h1 className="viewer__title">Daily logs</h1>
            <div className="viewer__sub">
              {plan.waypoints[0].label} → {plan.waypoints[2].label}
              {!isBlank(driver) && ` • ${driver.trim()}`}
            </div>
          </div>
          <button type="button" className="viewer__print" onClick={() => window.print()}>
            <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
              <path d="M5 7V2h8v5M5 13H3V7h12v6h-2M5 10h8v6H5z" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
            </svg>
            Print logs
          </button>
        </div>

        <nav className="viewer__nav" aria-label="Log days">
          <button type="button" className="viewer__arrow" aria-label="Previous day" disabled={day === 0} onClick={() => onDay(day - 1)}>
            <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
              <path d="M11 4L6 9l5 5" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
          <div className="viewer__current" aria-live="polite">
            <div className="viewer__current-n">
              Day {day + 1} of {sheets.length}
            </div>
            <div className="viewer__current-date">{formatDay(parseLocal(sheet.date))}</div>
          </div>
          <button type="button" className="viewer__arrow" aria-label="Next day" disabled={day === last} onClick={() => onDay(day + 1)}>
            <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
              <path d="M7 4l5 5-5 5" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
          <div className="viewer__tabs">
            {sheets.map((s, i) => (
              <button
                type="button"
                key={s.date}
                className={i === day ? 'viewer__tab viewer__tab--active' : 'viewer__tab'}
                aria-current={i === day ? 'page' : undefined}
                onClick={() => onDay(i)}
              >
                Day {i + 1} • {formatDay(parseLocal(s.date))} • {formatMiles(s.miles)} mi
              </button>
            ))}
          </div>
        </nav>

        <LogSheet key={sheet.date} sheet={sheet} details={plan.details} isTripStart={day === 0} />
      </div>
    </main>
  )
}

/** Every day, one sheet per printed page. Hidden on screen. */
export function PrintLogs({ plan }) {
  return (
    <div className="print-logs" aria-hidden="true">
      {plan.sheets.map((s, i) => (
        <div className="print-logs__page" key={s.date}>
          <LogSheet sheet={s} details={plan.details} isTripStart={i === 0} />
        </div>
      ))}
    </div>
  )
}
