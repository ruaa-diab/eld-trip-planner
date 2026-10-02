import { useEffect, useRef } from 'react'
import CycleField from './CycleField.jsx'
import DriverDetails, { SAMPLE_DETAILS } from './DriverDetails.jsx'
import PlanningRules from './PlanningRules.jsx'
import RouteFields from './RouteFields.jsx'
import StartFields from './StartFields.jsx'
import './TripForm.css'

// Order used to focus the first field with an error; values are input ids.
const FOCUS_ORDER = [
  ['current_location', 'current_location'],
  ['pickup_location', 'pickup_location'],
  ['dropoff_location', 'dropoff_location'],
  ['current_cycle_used', 'current_cycle_used'],
  ['start_time', 'start_date'],
]

function SectionBadge({ num, children }) {
  return (
    <h2 className="badge badge--numbered form__badge">
      <span className="badge__num">{num}</span>
      {children}
    </h2>
  )
}

/**
 * values: { current_location, pickup_location, dropoff_location, cycle, date, time, details: {...} }
 * errors: { [field]: message, details: { [key]: message } }
 */
export default function TripForm({ values, errors, generalError, onChange, onSubmit }) {
  const formRef = useRef(null)
  const detailErrors = errors.details || {}
  const hasDetailErrors = Object.keys(detailErrors).length > 0

  useEffect(() => {
    const first = FOCUS_ORDER.find(([field]) => errors[field])
    const id = first ? first[1] : hasDetailErrors ? `details-${Object.keys(detailErrors)[0]}` : null
    if (id) formRef.current?.querySelector(`#${id}`)?.focus()
  }, [errors]) // eslint-disable-line react-hooks/exhaustive-deps

  const set = (name, value) => onChange({ ...values, [name]: value })
  const setDetail = (key, value) => onChange({ ...values, details: { ...values.details, [key]: value } })

  return (
    <main className="page">
      <div className="page__inner">
        <div className="form__intro">
          <h1 className="form__title">Plan a trip</h1>
          <p className="form__lead">
            Enter the route and your current cycle. We schedule driving, breaks, fuel and rest under FMCSA Hours of
            Service rules and fill in your daily log sheets.
          </p>
        </div>

        <div className="form__layout">
          <form
            ref={formRef}
            className="card form__card"
            noValidate
            onSubmit={(e) => {
              e.preventDefault()
              onSubmit()
            }}
          >
            {generalError && (
              <div className="form__alert" role="alert">
                <svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true">
                  <circle cx="10" cy="10" r="9" fill="currentColor" />
                  <path d="M10 5.5v5.5M10 14v.5" stroke="#0F1B2D" strokeWidth="2.2" strokeLinecap="round" />
                </svg>
                <div>
                  <strong>We couldn't plan this trip</strong>
                  <div>{generalError}</div>
                </div>
              </div>
            )}

            <SectionBadge num="01">Route</SectionBadge>
            <RouteFields values={values} errors={errors} onChange={set} />

            <div className="lane-line form__divider" aria-hidden="true" />

            <SectionBadge num="02">Hours of Service</SectionBadge>
            <CycleField value={values.cycle} error={errors.current_cycle_used} onChange={(v) => set('cycle', v)} />
            <StartFields date={values.date} time={values.time} error={errors.start_time} onChange={set} />

            <div className="lane-line form__divider form__divider--details" aria-hidden="true" />

            <DriverDetails
              values={values.details}
              errors={detailErrors}
              onChange={setDetail}
              onFillSample={() => onChange({ ...values, details: { ...SAMPLE_DETAILS } })}
              forceOpen={hasDetailErrors}
            />

            <div className="form__actions">
              <button type="submit" className="form__submit">
                Plan trip
                <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
                  <path
                    d="M3 9h11M10 4.5L14.5 9 10 13.5"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2.2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </button>
            </div>
          </form>

          <PlanningRules />
        </div>
      </div>
    </main>
  )
}
