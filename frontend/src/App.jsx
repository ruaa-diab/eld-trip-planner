import { useRef, useState } from 'react'
import { ApiError, planTrip, reverseLocation } from './api.js'
import { CYCLE_MAX } from './components/CycleField.jsx'
import { emptyDetails } from './components/DriverDetails.jsx'
import Header from './components/Header.jsx'
import LoadingScreen from './components/LoadingScreen.jsx'
import { nowLocal } from './components/StartFields.jsx'
import TripForm from './components/TripForm.jsx'
import ResultsPage from './components/results/ResultsPage.jsx'
import LogViewer, { PrintLogs } from './components/logs/LogViewer.jsx'
import { parseLocal } from './format.js'

const LOCATION_FIELDS = ['current_location', 'pickup_location', 'dropoff_location']

const ZIP_RE = /^\d{5}(-\d{4})?$/

/**
 * Same rule as the API: a US ZIP (60632 or 60632-1234), or at least 3 characters with at
 * least one letter (never geocode "C" or "123").
 */
export const isUsableLocation = (text) =>
  ZIP_RE.test(text.trim()) || (text.trim().length >= 3 && /\p{L}/u.test(text))

function initialValues() {
  const { date, time } = nowLocal()
  return {
    current_location: '',
    current_coords: null, // { lat, lon } from "Use my current location"; dropped on any edit
    pickup_location: '',
    dropoff_location: '',
    cycle: '',
    date,
    time,
    details: emptyDetails(),
  }
}

/** Client-side checks mirroring the API, so obvious mistakes don't need a round trip. */
function validate(values) {
  const errors = {}
  for (const field of LOCATION_FIELDS) {
    if (!isUsableLocation(values[field])) errors[field] = 'Enter a city or address'
  }
  const cycle = Number(values.cycle)
  if (values.cycle.trim() === '') {
    errors.current_cycle_used = 'Enter the hours already used (0 to 70)'
  } else if (!Number.isFinite(cycle) || cycle < 0 || cycle > CYCLE_MAX) {
    errors.current_cycle_used = 'Enter a number of hours from 0 to 70.'
  }
  if (!values.date || !values.time) errors.start_time = 'Enter the start date and time.'
  return errors
}

function toPayload(values) {
  return {
    current_location: values.current_location.trim(),
    ...(values.current_coords && { current_coords: values.current_coords }),
    pickup_location: values.pickup_location.trim(),
    dropoff_location: values.dropoff_location.trim(),
    current_cycle_used: Number(values.cycle),
    start_time: `${values.date}T${values.time}`,
    details: values.details,
  }
}

const firstMessage = (v) => (Array.isArray(v) ? v[0] : String(v))

/** Turn an ApiError into { fieldErrors, generalError } for the form. */
function errorsFromApi(err, values) {
  if (err.code === 'address_not_found' && Array.isArray(err.fields)) {
    const fieldErrors = {}
    for (const field of err.fields) {
      const text = values[field].trim()
      fieldErrors[field] = err.messages?.[field] || {
        invalid_place: 'Enter a proper city or address',
        outside_us: 'That location is outside the US. Enter a US address.',
        state_mismatch: `Couldn't find '${text}'. Check the city and state.`,
      }[err.reasons?.[field]] || `Couldn't find '${text}'. Check the spelling.`
    }
    // A location that was found but has no truck road nearby also gets a banner.
    const noRoad = Object.values(err.reasons || {}).includes('no_road')
    return { fieldErrors, generalError: noRoad ? 'Check the highlighted location.' : null }
  }
  if (err.code === 'invalid_input' && err.fields && typeof err.fields === 'object') {
    const fieldErrors = {}
    for (const [field, msgs] of Object.entries(err.fields)) {
      if (field === 'details' && msgs && typeof msgs === 'object' && !Array.isArray(msgs)) {
        fieldErrors.details = Object.fromEntries(Object.entries(msgs).map(([k, v]) => [k, firstMessage(v)]))
      } else {
        fieldErrors[field] = firstMessage(msgs)
      }
    }
    return { fieldErrors, generalError: null }
  }
  return { fieldErrors: {}, generalError: err.message }
}

export default function App() {
  const [screen, setScreen] = useState('form') // form | loading | result | logs
  const [logDay, setLogDay] = useState(0)
  const [values, setValues] = useState(initialValues)
  const [errors, setErrors] = useState({})
  const [generalError, setGeneralError] = useState(null)
  const [focusRequest, setFocusRequest] = useState(0) // bumped when a submit fails, to focus the first error
  const [result, setResult] = useState(null) // { plan, departure }
  const controllerRef = useRef(null)

  // Editing a field clears its error. Editing the current location drops the device position,
  // so a typed address is always geocoded normally.
  const change = (next) => {
    if (next.current_location !== values.current_location && next.current_coords === values.current_coords) {
      next = { ...next, current_coords: null }
    }
    setErrors((prev) => {
      const out = { ...prev }
      for (const field of LOCATION_FIELDS) if (next[field] !== values[field]) delete out[field]
      if (next.cycle !== values.cycle) delete out.current_cycle_used
      if (next.date !== values.date || next.time !== values.time) delete out.start_time
      if (out.details) {
        const details = Object.fromEntries(
          Object.entries(out.details).filter(([k]) => next.details[k] === values.details[k]),
        )
        if (Object.keys(details).length) out.details = details
        else delete out.details
      }
      return out
    })
    setValues(next)
  }

  // "Use my current location": browser position → readable address → field + exact coordinates.
  const [locating, setLocating] = useState(false)
  const locateCurrent = () => {
    const fail = (message) => {
      setLocating(false)
      setErrors((prev) => ({ ...prev, current_location: message }))
    }
    setLocating(true)
    setErrors((prev) => {
      const { current_location: _, ...rest } = prev
      return rest
    })
    navigator.geolocation.getCurrentPosition(
      async ({ coords }) => {
        try {
          const place = await reverseLocation(coords.latitude, coords.longitude)
          setLocating(false)
          setValues((v) => ({ ...v, current_location: place.label, current_coords: { lat: place.lat, lon: place.lon } }))
        } catch (err) {
          fail(err.message || "Couldn't look up your location. Enter it instead.")
        }
      },
      (err) => {
        fail(err.code === err.PERMISSION_DENIED ? 'Location access was blocked' : "Couldn't get your location. Enter it instead.")
      },
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 60000 },
    )
  }

  const backToForm = () => {
    controllerRef.current?.abort()
    controllerRef.current = null
    setScreen('form')
    window.scrollTo(0, 0)
  }

  // New trip: a fresh form with the current time. (Edit trip keeps the values.)
  const newTrip = () => {
    backToForm()
    setValues(initialValues())
    setErrors({})
    setGeneralError(null)
  }

  const submit = async () => {
    const clientErrors = validate(values)
    setGeneralError(null)
    setErrors(clientErrors)
    setFocusRequest((n) => n + 1)
    if (Object.keys(clientErrors).length) return

    const controller = new AbortController()
    controllerRef.current = controller
    setScreen('loading')
    window.scrollTo(0, 0)
    try {
      const data = await planTrip(toPayload(values), controller.signal)
      setResult({ plan: data, departure: parseLocal(`${values.date}T${values.time}`) })
      setScreen('result')
    } catch (err) {
      if (err.name === 'AbortError') return
      const { fieldErrors, generalError: message } =
        err instanceof ApiError ? errorsFromApi(err, values) : { fieldErrors: {}, generalError: err.message }
      setErrors(fieldErrors)
      setFocusRequest((n) => n + 1)
      setGeneralError(message)
      setScreen('form')
    } finally {
      if (controllerRef.current === controller) controllerRef.current = null
    }
  }

  return (
    <>
      <Header onNewTrip={screen === 'form' ? null : newTrip} />
      {screen === 'form' && (
        <TripForm
          values={values}
          errors={errors}
          focusRequest={focusRequest}
          generalError={generalError}
          onChange={change}
          locating={locating}
          onLocate={'geolocation' in navigator ? locateCurrent : null}
          onSubmit={submit}
        />
      )}
      {screen === 'loading' && (
        <LoadingScreen
          from={values.current_location.trim()}
          to={values.dropoff_location.trim()}
          pickup={values.pickup_location.trim()}
          cycle={Number(values.cycle)}
          onCancel={backToForm}
        />
      )}
      {screen === 'result' && result && (
        <ResultsPage
          plan={result.plan}
          departure={result.departure}
          onEdit={backToForm}
          onOpenLogs={(day) => {
            setLogDay(day)
            setScreen('logs')
            window.scrollTo(0, 0)
          }}
        />
      )}
      {screen === 'logs' && result && (
        <LogViewer
          plan={result.plan}
          day={logDay}
          onDay={setLogDay}
          onBack={() => {
            setScreen('result')
            window.scrollTo(0, 0)
          }}
        />
      )}
      {(screen === 'result' || screen === 'logs') && result && <PrintLogs plan={result.plan} />}
    </>
  )
}
