const pad = (n) => String(n).padStart(2, '0')

/** Current browser time as { date: "YYYY-MM-DD", time: "HH:MM" }. */
export function nowLocal() {
  const d = new Date()
  return {
    date: `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`,
    time: `${pad(d.getHours())}:${pad(d.getMinutes())}`,
  }
}

export default function StartFields({ date, time, error, onChange }) {
  const describedBy = ['start-help', error && 'start_time-error'].filter(Boolean).join(' ')
  return (
    <div className="start">
      <div className="start__grid">
        <div>
          <label className="label" htmlFor="start_date">
            Start date
          </label>
          <input
            id="start_date"
            type="date"
            className="input"
            value={date}
            onChange={(e) => onChange('date', e.target.value)}
            aria-invalid={error ? 'true' : undefined}
            aria-describedby={describedBy}
          />
        </div>
        <div>
          <label className="label" htmlFor="start_time">
            Start time
          </label>
          <input
            id="start_time"
            type="time"
            className="input"
            value={time}
            onChange={(e) => onChange('time', e.target.value)}
            aria-invalid={error ? 'true' : undefined}
            aria-describedby={describedBy}
          />
        </div>
      </div>
      <p className="hint" id="start-help">
        Pre-filled with now. Use your home terminal time zone.
      </p>
      {error && (
        <div className="field-error" id="start_time-error">
          {error}
        </div>
      )}
    </div>
  )
}
