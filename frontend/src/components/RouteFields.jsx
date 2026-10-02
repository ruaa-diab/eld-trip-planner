import LocationInput from './LocationInput.jsx'

function CurrentMarker() {
  return (
    <svg width="26" height="26" viewBox="0 0 32 32" aria-hidden="true">
      <path d="M16 3L29 16L16 29L3 16Z" fill="#F5A524" stroke="#0F1B2D" strokeWidth="2" />
      <circle cx="16" cy="16" r="3.5" fill="#0F1B2D" />
    </svg>
  )
}

function ShieldMarker({ letter, path, textY }) {
  return (
    <svg width="28" height="28" viewBox="0 0 32 32" aria-hidden="true">
      <path d={path} fill="#14B8A6" stroke="#0F1B2D" strokeWidth="2.5" />
      <path
        d={path}
        fill="none"
        stroke="#FFFFFF"
        strokeWidth="1.1"
        transform="translate(16 16) scale(0.84) translate(-16 -16)"
      />
      <text x="16" y={textY} textAnchor="middle" fontSize="11" fontWeight="800" fill="#0F1B2D" fontFamily="Overpass">
        {letter}
      </text>
    </svg>
  )
}

const PICKUP_SHIELD = 'M5 4H27Q26 8 28 11Q29 22 16 29Q3 22 4 11Q6 8 5 4Z'
const DROPOFF_SHIELD = 'M4 6Q10 3 16 6Q22 3 28 6L28 14Q28 25 16 30Q4 25 4 14Z'

const FIELDS = [
  {
    name: 'current_location',
    label: 'Current location',
    placeholder: 'City, street address or ZIP',
    marker: <CurrentMarker />,
    markerClass: 'route__marker--current',
  },
  {
    name: 'pickup_location',
    label: 'Pickup location',
    placeholder: 'Shipper address',
    marker: <ShieldMarker letter="P" path={PICKUP_SHIELD} textY="19.5" />,
  },
  {
    name: 'dropoff_location',
    label: 'Dropoff location',
    placeholder: 'Consignee address',
    marker: <ShieldMarker letter="D" path={DROPOFF_SHIELD} textY="20" />,
  },
]

const HINT = 'Street address, business, city & state, or ZIP.'

function LocateButton({ locating, onClick }) {
  return (
    <button
      type="button"
      className="locate"
      onClick={onClick}
      disabled={locating}
      title="Use my current location"
      aria-label={locating ? 'Locating…' : 'Use my current location'}
    >
      {/* The crosshair spins while locating; the button keeps its size. */}
      <svg className={locating ? 'locate__icon locate__icon--busy' : 'locate__icon'} width="20" height="20" viewBox="0 0 20 20" aria-hidden="true">
        <g fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
          <circle cx="10" cy="10" r="5.5" />
          <path d="M10 1.5v3M10 15.5v3M1.5 10h3M15.5 10h3" />
        </g>
        <circle cx="10" cy="10" r="2" fill="currentColor" />
      </svg>
      <span className="visually-hidden" role="status">
        {locating ? 'Locating…' : ''}
      </span>
    </button>
  )
}

/** onLocate: "Use my current location" handler (null when the browser has no geolocation). */
export default function RouteFields({ values, errors, onChange, locating, onLocate }) {
  return (
    <div className="route">
      <div className="route__rail" aria-hidden="true" />
      {FIELDS.map((f) => (
        <div className="route__row" key={f.name}>
          <div className={`route__marker ${f.markerClass || ''}`}>{f.marker}</div>
          <div>
            <label className="label" htmlFor={f.name}>
              {f.label}
            </label>
            <div className={f.name === 'current_location' && onLocate ? 'route__field route__field--locate' : 'route__field'}>
              <LocationInput
                id={f.name}
                value={values[f.name]}
                onChange={(v) => onChange(f.name, v)}
                inputProps={{
                  name: f.name,
                  placeholder: f.placeholder,
                  maxLength: 200,
                  'aria-invalid': errors[f.name] ? 'true' : undefined,
                  'aria-describedby': [`${f.name}-hint`, errors[f.name] && `${f.name}-error`].filter(Boolean).join(' '),
                }}
              />
              {f.name === 'current_location' && onLocate && <LocateButton locating={locating} onClick={onLocate} />}
            </div>
            <div className="route__hint" id={`${f.name}-hint`}>
              {HINT}
            </div>
            {errors[f.name] && (
              <div className="field-error" id={`${f.name}-error`}>
                {errors[f.name]}
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}
