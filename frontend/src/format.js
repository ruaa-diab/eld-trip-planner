// Formatting helpers. All times are home terminal time exactly as entered (no time zones).

const WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const pad = (n) => String(n).padStart(2, '0')

/** "2026-10-05T06:00[:00]" or "2026-10-05" → local Date with the same wall-clock values. */
export function parseLocal(s) {
  const [d, t = '00:00'] = s.split('T')
  const [y, mo, day] = d.split('-').map(Number)
  const [h, mi] = t.split(':').map(Number)
  return new Date(y, mo - 1, day, h, mi)
}

/** Whole minutes from a to b. */
export const minutesBetween = (a, b) => Math.round((b - a) / 60000)

export const addDays = (date, n) => new Date(date.getFullYear(), date.getMonth(), date.getDate() + n)

/** "Thu, Oct 1" */
export const formatDay = (d) => `${WEEKDAYS[d.getDay()]}, ${MONTHS[d.getMonth()]} ${d.getDate()}`

/** "Thu, Oct 1, 2026" */
export const formatDayLong = (d) => `${formatDay(d)}, ${d.getFullYear()}`

/** "06:00" (24-hour, as on the log sheets) */
export const formatClock = (d) => `${pad(d.getHours())}:${pad(d.getMinutes())}`

/** Durations in the timeline: 30 → "30 min", 60 → "1 h", 450 → "7 h 30 min". */
export function formatDuration(min) {
  const h = Math.floor(min / 60)
  const m = min % 60
  if (!h) return `${m} min`
  return m ? `${h} h ${m} min` : `${h} h`
}

/** Hours:minutes like the log sheets: 1593 → "26:33", 0 → "0:00". */
export const formatHM = (min) => `${Math.floor(min / 60)}:${pad(min % 60)}`

/** Whole miles with thousands separators: 1037.5 → "1,038". */
export const formatMiles = (mi) => Math.round(mi).toLocaleString('en-US')

export const isBlank = (v) => v == null || String(v).trim() === ''

/** Optional log-sheet fields: a muted "—" when empty. */
export const orDash = (v) => (isBlank(v) ? '—' : String(v).trim())

/** Note after a location name when it was matched as an area, not an exact point. */
export const precisionNote = (precision) =>
  ({ city: '(city center)', county: '(county center)', zip: '(ZIP area)' })[precision] || ''
