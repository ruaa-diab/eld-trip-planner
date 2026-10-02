import { isBlank, orDash, formatHM, formatMiles } from '../../format.js'
import { FULL, FullGrid, STATUS_COLOR, minuteX } from './LogGrid.jsx'

// Short words for remark brackets, keyed by the API's remark description.
const BRACKET_WORD = {
  Pickup: 'pickup',
  Dropoff: 'dropoff',
  Fuel: 'fuel',
  '30-min break': 'break',
  '10-hour rest': 'rest',
  '34-hour restart': 'restart',
}

/** Status of the segment running at a minute (for remark color chips). */
function statusAt(sheet, minute) {
  const seg = sheet.segments.find((s) => s.start_min <= minute && minute < s.end_min) || sheet.segments.at(-1)
  return seg.status
}

/**
 * Bracket markers under the grid: a bracket over each stop's time, a single tick where the
 * change has no end on this day (trip start, or a rest running past midnight).
 */
function remarkMarks(sheet, isTripStart) {
  const marks = []
  sheet.remarks.forEach((r, i) => {
    const start = isTripStart && i === 0
    const word = BRACKET_WORD[r.description]
    if (!start && !word) return
    const seg = sheet.segments.find((s) => s.start_min === r.minute)
    const bracket = !start && seg && seg.end_min < 1440
    marks.push({
      x1: minuteX(r.minute),
      x2: bracket ? minuteX(seg.end_min) : null,
      label: start && !word ? r.location : `${r.location} • ${word}`,
    })
  })
  return marks
}

function RemarkBrackets({ marks }) {
  // Tall enough for the longest slanted label (≈7.4 units per character at 60°).
  const longest = Math.max(0, ...marks.map((m) => m.label.length))
  const H = Math.max(60, Math.ceil(34 + longest * 7.4 * Math.sin(Math.PI / 3)))
  return (
    <svg className="log-marks" viewBox={`0 0 ${FULL.width} ${H}`} aria-hidden="true">
      {marks.map((m, i) => (
        <g key={i}>
          {m.x2 == null ? (
            <line x1={m.x1} x2={m.x1} y1={0} y2={12} stroke="#0F1B2D" strokeWidth={3} />
          ) : (
            <path d={`M${m.x1} 0V10H${m.x2}V0`} fill="none" stroke="#0F1B2D" strokeWidth={2} />
          )}
          <text x={m.x1 + 2} y={22} transform={`rotate(60 ${m.x1 + 2} 22)`} className="log-marks__label">
            {m.label}
          </text>
        </g>
      ))}
    </svg>
  )
}

function Line({ value, label, className = '', mono }) {
  const blank = isBlank(value)
  return (
    <div className={`sheet-line ${className}`}>
      <div className={['sheet-line__value', mono && 'mono', blank && 'sheet-line__value--blank'].filter(Boolean).join(' ')}>
        {orDash(value)}
      </div>
      <div className="sheet-line__label">{label}</div>
    </div>
  )
}

function joinPresent(parts) {
  const present = parts.filter((p) => !isBlank(p)).map((p) => p.trim())
  return present.length ? present.join(' • ') : ''
}

/**
 * One day of the Driver's Daily Log.
 * sheet: one entry of the API's `sheets`; details: the API's `details`;
 * isTripStart: true for day 1 (its first remark is the trip start).
 */
export default function LogSheet({ sheet, details, isTripStart }) {
  const [yyyy, mm, dd] = sheet.date.split('-')
  const miles = formatMiles(sheet.miles)
  const truckLine = joinPresent([
    !isBlank(details.truck_number) && `Tractor ${details.truck_number.trim()}`,
    !isBlank(details.trailer_number) && `Trailer ${details.trailer_number.trim()}`,
  ].filter(Boolean))
  const shipperLine = joinPresent([details.shipper, details.commodity])
  const rc = sheet.recap

  return (
    <article className="sheet" aria-label={`Drivers Daily Log ${mm}/${dd}/${yyyy}`}>
      <div className="sheet__top">
        <div>
          <div className="sheet__title">Drivers Daily Log</div>
          <div className="sheet__muted">(24 hours)</div>
        </div>
        <div className="sheet__date">
          {[
            [mm, '(month)'],
            [dd, '(day)'],
            [yyyy, '(year)'],
          ].map(([v, label], i) => (
            <div className="sheet__date-part" key={label}>
              {i > 0 && <span className="sheet__date-slash">/</span>}
              <div>
                <div className="sheet__date-value mono">{v}</div>
                <div className="sheet__date-label">{label}</div>
              </div>
            </div>
          ))}
        </div>
        <div className="sheet__copies">
          <strong>Original</strong> – File at home terminal.
          <br />
          <strong>Duplicate</strong> – Driver retains in his/her possession for 8 days.
        </div>
      </div>

      <div className="sheet__fromto">
        <div className="sheet__inline">
          <span className="sheet__inline-label">From:</span>
          <span className="sheet__inline-value">{sheet.from}</span>
        </div>
        <div className="sheet__inline">
          <span className="sheet__inline-label">To:</span>
          <span className="sheet__inline-value">{sheet.to}</span>
        </div>
      </div>

      <div className="sheet__header-grid">
        <div className="sheet__col">
          <div className="sheet__miles">
            <div>
              <div className="sheet__mile-box mono">{miles}</div>
              <div className="sheet-line__label sheet-line__label--center">Total Miles Driving Today</div>
            </div>
            <div>
              <div className="sheet__mile-box mono">{miles}</div>
              <div className="sheet-line__label sheet-line__label--center">Total Mileage Today</div>
            </div>
          </div>
          <Line
            className="sheet-line--center"
            value={truckLine}
            label="Truck/Tractor and Trailer Numbers or License Plate(s)/State (show each unit)"
          />
        </div>
        <div className="sheet__col">
          <Line className="sheet-line--center sheet-line--big" value={details.carrier_name} label="Name of Carrier or Carriers" />
          <Line className="sheet-line--center" value={details.main_office_address} label="Main Office Address" />
          <Line className="sheet-line--center" value={details.home_terminal_address} label="Home Terminal Address" />
        </div>
      </div>

      <div className="sheet__people">
        <Line value={details.driver_name} label="Driver Name" />
        <Line value={details.driver_number} label="Driver Number" mono />
        <Line value={details.co_driver_name} label="Co-Driver" />
      </div>

      <div className="sheet__grid-scroll">
        <div className="sheet__grid-inner">
          <FullGrid sheet={sheet} />
        </div>
      </div>
      <div className="sheet__swipe">Swipe the grid sideways to see the full 24 hours →</div>

      <div className="sheet__remarks-title">Remarks</div>
      <div className="sheet__remarks">
        <RemarkBrackets marks={remarkMarks(sheet, isTripStart)} />
        <ol className="sheet__remark-list">
          {sheet.remarks.map((r, i) => (
            <li key={i} className="sheet__remark">
              <span className="sheet__remark-time mono">{r.time}</span>
              <span className="sheet__remark-text">
                <strong>{r.location}</strong>
                <span className="sheet__remark-desc">
                  <span className="sheet__chip" style={{ background: STATUS_COLOR[statusAt(sheet, r.minute)] }} />
                  {r.description}
                </span>
              </span>
            </li>
          ))}
        </ol>

        <div className="sheet__ship-title">
          Shipping
          <br />
          Documents:
        </div>
        <div className="sheet__ship">
          <Line className="sheet-line--strong-label" value={details.shipping_document} label="DVL or Manifest No. or" mono />
          <Line className="sheet-line--strong-label" value={shipperLine} label="Shipper & Commodity" />
        </div>
      </div>

      <p className="sheet__instructions">
        Enter name of place you reported and where released from work and when and where each change of duty occurred.
        Use time standard of home terminal.
      </p>
      <p className="sheet__tz">Times in home terminal time.</p>

      <div className="recap">
        <div className="recap__today">
          <div className="recap__title">
            Recap:
            <br />
            Complete at end of day
          </div>
          <div>
            <div className="recap__value mono">{formatHM(rc.on_duty_today)}</div>
            <div className="recap__label">On duty hours today, Total lines 3 &amp; 4</div>
          </div>
        </div>

        <div className="recap__box">
          <div className="recap__title">
            70 Hour/
            <br />8 Day
            <br />
            Drivers
          </div>
          {[
            ['A.', rc.a, 'Total hours on duty last 7 days including today.'],
            ['B.', rc.b, 'Total hours available tomorrow 70 hr. minus A*'],
            ['C.', rc.c, 'Total hours on duty last 5 days including today.'],
          ].map(([k, v, label]) => (
            <div key={k}>
              <div className="recap__key">{k}</div>
              <div className="recap__value mono">{formatHM(v)}</div>
              <div className="recap__label">{label}</div>
            </div>
          ))}
        </div>

        <div className="recap__box recap__box--unused">
          <div>
            <div className="recap__title">
              60 Hour/
              <br />7 Day Drivers
            </div>
            <div className="recap__not-used">NOT USED</div>
          </div>
          {[
            ['A.', 'Total hours on duty last 8 days including today.'],
            ['B.', 'Total hours available tomorrow 60 hr. minus A*'],
            ['C.', 'Total hours on duty last 7 days including today.'],
          ].map(([k, label]) => (
            <div key={k}>
              <div className="recap__key">{k}</div>
              <div className="recap__value mono">—</div>
              <div className="recap__label">{label}</div>
            </div>
          ))}
        </div>

        <div className="recap__note">*If you took 34 consecutive hours off duty you have 60/70 hours available</div>
      </div>
    </article>
  )
}
