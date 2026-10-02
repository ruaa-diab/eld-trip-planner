export const CYCLE_MAX = 70

/** Hours as a short label: 38 → "38", 20.5 → "20.5", 12.25 → "12.25". */
function formatHours(h) {
  return String(Math.round(h * 100) / 100)
}

export default function CycleField({ value, error, onChange }) {
  const parsed = Number(value)
  const used = value === '' || !Number.isFinite(parsed) ? 0 : Math.min(CYCLE_MAX, Math.max(0, parsed))
  const left = CYCLE_MAX - used

  return (
    <div className="cycle">
      <label className="label cycle__label" htmlFor="current_cycle_used">
        Current cycle used
      </label>
      <p className="cycle__help" id="cycle-help">
        On-duty hours (driving + on duty) logged in the last 8 days, from 0 to 70.
      </p>
      <div className="cycle__controls">
        <div className="cycle__number">
          <input
            id="current_cycle_used"
            name="current_cycle_used"
            type="number"
            inputMode="decimal"
            min="0"
            max={CYCLE_MAX}
            step="0.25"
            className="input mono"
            value={value}
            placeholder="0"
            onChange={(e) => onChange(e.target.value)}
            aria-invalid={error ? 'true' : undefined}
            aria-describedby={error ? 'cycle-help current_cycle_used-error' : 'cycle-help'}
          />
          <span className="cycle__unit" aria-hidden="true">
            hrs
          </span>
        </div>
        <input
          type="range"
          className="cycle__slider"
          min="0"
          max={CYCLE_MAX}
          step="0.5"
          value={used}
          onChange={(e) => onChange(e.target.value)}
          aria-label="Cycle used, hours"
        />
      </div>
      <div className="cycle__bar" aria-hidden="true">
        <div className="cycle__fill" style={{ width: `${(used / CYCLE_MAX) * 100}%` }} />
      </div>
      <div className="cycle__legend">
        <span>
          <strong>{formatHours(used)} h</strong> used
        </span>
        <span className={left < 11 ? 'cycle__left cycle__left--low' : 'cycle__left'}>
          <strong>{formatHours(left)} h</strong> left of 70
        </span>
      </div>
      {error && (
        <div className="field-error" id="current_cycle_used-error">
          {error}
        </div>
      )}
    </div>
  )
}
