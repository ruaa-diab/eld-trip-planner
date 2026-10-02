import { useRef, useState } from 'react'
import { ApiError, planTrip } from './api.js'
import { CYCLE_MAX } from './components/CycleField.jsx'
import { emptyDetails } from './components/DriverDetails.jsx'
import Header from './components/Header.jsx'
import LoadingScreen from './components/LoadingScreen.jsx'
import { nowLocal } from './components/StartFields.jsx'
import TripForm from './components/TripForm.jsx'
import ResultsPage from './components/results/ResultsPage.jsx'
import LogViewer, { PrintLogs } from './components/logs/LogViewer.jsx'
import { parseLocal } from './format.js'

const LOCATION_LABELS = {
  current_location: 'current location',
  pickup_location: 'pickup location',
  dropoff_location: 'dropoff location',
}

function initialValues() {
  const { date, time } = nowLocal()
  return {
    current_location: '',
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
  for (const [field, label] of Object.entries(LOCATION_LABELS)) {
    if (!values[field].trim()) errors[field] = `Enter the ${label}.`
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
      fieldErrors[field] = `Couldn't find '${values[field].trim()}'. Check the spelling.`
    }
    return { fieldErrors, generalError: null }
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
  const [result, setResult] = useState(null) // { plan, departure }
  const controllerRef = useRef(null)

  // Editing a field clears its error.
  const change = (next) => {
    setErrors((prev) => {
      const out = { ...prev }
      for (const field of Object.keys(LOCATION_LABELS)) if (next[field] !== values[field]) delete out[field]
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
          generalError={generalError}
          onChange={change}
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
