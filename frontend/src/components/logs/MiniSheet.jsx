import { formatDay, formatHM, formatMiles, parseLocal } from '../../format.js'
import { MiniGrid, STATUS_ROWS } from './LogGrid.jsx'

const SHORT = { off_duty: 'Off duty', sleeper_berth: 'Sleeper', driving: 'Driving', on_duty: 'On duty' }

/** Results-page preview of one day: grid + four totals + 24:00. Opens the viewer at that day. */
export default function MiniSheet({ sheet, index, onOpen }) {
  const total = Object.values(sheet.totals).reduce((a, b) => a + b, 0)
  return (
    <button type="button" className="mini-sheet" onClick={onOpen} aria-label={`Open day ${index + 1} log sheet`}>
      <span className="mini-sheet__head">
        <span className="mini-sheet__day">
          Day {index + 1} • {formatDay(parseLocal(sheet.date))}
        </span>
        <span className="mini-sheet__miles">{formatMiles(sheet.miles)} mi</span>
      </span>
      <span className="mini-sheet__route">
        {sheet.from} → {sheet.to}
      </span>
      <MiniGrid sheet={sheet} />
      <span className="mini-sheet__totals">
        {STATUS_ROWS.map((r) => (
          <span className="mini-sheet__total" key={r.status}>
            <span className="mini-sheet__total-key">
              <span className="mini-sheet__swatch" style={{ background: r.color }} />
              {SHORT[r.status]}
            </span>
            <strong className="mono">{formatHM(sheet.totals[r.status])}</strong>
          </span>
        ))}
        <span className="mini-sheet__total mini-sheet__total--sum">
          <span>Total</span>
          <strong className="mono">{formatHM(total)}</strong>
        </span>
      </span>
    </button>
  )
}
