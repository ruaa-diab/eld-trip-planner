import { useState } from 'react'

// [API key, label, placeholder]
export const DETAIL_FIELDS = [
  ['driver_name', 'Driver name', 'Full name'],
  ['driver_number', 'Driver number', 'License or employee no.'],
  ['co_driver_name', 'Co-driver', 'None'],
  ['carrier_name', 'Carrier name', 'Legal carrier name'],
  ['main_office_address', 'Main office address', 'Street, city, state'],
  ['home_terminal_address', 'Home terminal address', 'Street, city, state'],
  ['truck_number', 'Truck / tractor number', 'e.g. 2417'],
  ['trailer_number', 'Trailer number', 'e.g. 53-0918'],
  ['shipping_document', 'Shipping document number', 'BOL or manifest no.'],
  ['shipper', 'Shipper', 'Shipper name'],
  ['commodity', 'Commodity', 'e.g. Packaged food'],
]

export const emptyDetails = () => Object.fromEntries(DETAIL_FIELDS.map(([k]) => [k, '']))

export default function DriverDetails({ values, errors, onChange, forceOpen }) {
  const [open, setOpen] = useState(false)
  const isOpen = open || forceOpen

  return (
    <div className="details">
      <button
        type="button"
        className="details__toggle"
        aria-expanded={isOpen}
        aria-controls="details-fields"
        onClick={() => setOpen(!isOpen)}
      >
        <span>
          <span className="details__title">
            Driver &amp; carrier details <span className="details__optional">(optional)</span>
          </span>
          <span className="details__sub">Printed in the header of each log sheet</span>
        </span>
        <svg
          className={isOpen ? 'details__chevron details__chevron--open' : 'details__chevron'}
          width="20"
          height="20"
          viewBox="0 0 20 20"
          aria-hidden="true"
        >
          <path
            d="M5 8l5 5 5-5"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </button>
      {isOpen && (
        <div className="details__grid" id="details-fields">
          {DETAIL_FIELDS.map(([key, label, placeholder]) => (
            <div key={key}>
              <label className="label" htmlFor={`details-${key}`}>
                {label}
              </label>
              <input
                id={`details-${key}`}
                className="input input--compact"
                value={values[key]}
                onChange={(e) => onChange(key, e.target.value)}
                placeholder={placeholder}
                maxLength={200}
                aria-invalid={errors[key] ? 'true' : undefined}
              />
              {errors[key] && <div className="field-error">{errors[key]}</div>}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
