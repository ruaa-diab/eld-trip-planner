import { addDays, formatDay, formatHM, formatMiles, formatDuration, parseLocal } from '../../format.js'

const CYCLE_LIMIT_MIN = 70 * 60

function Sign({ title, accent, danger, children, sub }) {
  const cls = ['sign', accent && 'sign--accent', danger && 'sign--danger'].filter(Boolean).join(' ')
  return (
    <div className={cls}>
      <div className="sign__panel">
        <div className="sign__face">
          <div className="sign__title">{title}</div>
          <div className="sign__value">{children}</div>
          {sub}
        </div>
      </div>
      <div className="sign__post" aria-hidden="true" />
    </div>
  )
}

export default function StatSigns({ summary, sheets }) {
  const drivingMin = sheets.reduce((sum, s) => sum + s.totals.driving, 0)
  const first = parseLocal(sheets[0].date)
  const last = parseLocal(sheets[sheets.length - 1].date)
  const range = sheets.length > 1 ? `${formatDay(first)} – ${formatDay(last)}` : formatDay(first)
  const tomorrow = formatDay(addDays(last, 1))
  const cyclePct = Math.min(100, (summary.cycle_after_min / CYCLE_LIMIT_MIN) * 100)

  return (
    <div className="signs-area">
      <div className="signs">
        <Sign title="Total miles" sub={<div className="sign__sub">{formatDuration(drivingMin)} driving</div>}>
          {formatMiles(summary.total_miles)}
        </Sign>

        <Sign title="Days" sub={<div className="sign__sub">{range}</div>}>
          {summary.days}
        </Sign>

        <Sign
          title="Cycle used after"
          sub={
            <div className="sign__bar" role="presentation">
              <div className="sign__fill" style={{ width: `${cyclePct}%` }} />
            </div>
          }
        >
          {formatHM(summary.cycle_after_min)}
          <span className="sign__of"> / 70 h</span>
        </Sign>

        {summary.restart_needed ? (
          <Sign title="Hours tomorrow" danger sub={<div className="sign__sub sign__sub--danger">34-hour restart needed</div>}>
            0:00
          </Sign>
        ) : (
          <Sign
            title="Hours tomorrow"
            accent
            sub={
              <div className="sign__sub">
                70:00 − {formatHM(summary.cycle_after_min)} • {tomorrow}
              </div>
            }
          >
            {formatHM(summary.available_tomorrow_min)}
          </Sign>
        )}
      </div>
    </div>
  )
}
