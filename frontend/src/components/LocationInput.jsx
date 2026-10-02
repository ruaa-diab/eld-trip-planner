import { useEffect, useId, useRef, useState } from 'react'
import { fetchSuggestions } from '../api.js'

const MIN_CHARS = 3
const DEBOUNCE_MS = 300
const cache = new Map() // text → labels, for the session

function PinIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true" className="suggest__pin">
      <path d="M8 1.5a4.5 4.5 0 0 0-4.5 4.5c0 3.4 4.5 8.5 4.5 8.5s4.5-5.1 4.5-8.5A4.5 4.5 0 0 0 8 1.5z" fill="#F5A524" />
      <circle cx="8" cy="6" r="1.7" fill="#1B2E48" />
    </svg>
  )
}

/** "Rockford, IL" → ["Rockford", "IL"]; "East Rockford, Rockford, IL" → ["East Rockford", "Rockford, IL"]. */
function splitLabel(label) {
  const i = label.indexOf(',')
  return i < 0 ? [label, ''] : [label.slice(0, i), label.slice(i + 1).trim()]
}

/**
 * A location text input with address suggestions (combobox pattern).
 * Typing freely still works; suggestions only help fill the field.
 */
export default function LocationInput({ id, value, onChange, inputProps }) {
  const [query, setQuery] = useState('') // only what the user typed; prefilled values don't trigger lookups
  const [suggestions, setSuggestions] = useState([])
  const [active, setActive] = useState(-1)
  const [open, setOpen] = useState(false)
  const controllerRef = useRef(null)
  const listId = `${useId()}-list`

  useEffect(() => {
    const text = query.trim()
    controllerRef.current?.abort()
    if (text.length < MIN_CHARS) {
      setSuggestions([])
      return undefined
    }
    if (cache.has(text)) {
      setSuggestions(cache.get(text))
      setActive(-1)
      return undefined
    }
    const timer = setTimeout(async () => {
      const controller = new AbortController()
      controllerRef.current = controller
      try {
        const labels = await fetchSuggestions(text, controller.signal)
        cache.set(text, labels)
        setSuggestions(labels)
        setActive(-1)
      } catch {
        // Aborted by a newer keystroke: ignore.
      }
    }, DEBOUNCE_MS)
    return () => clearTimeout(timer)
  }, [query])

  useEffect(() => () => controllerRef.current?.abort(), [])

  const showList = open && suggestions.length > 0

  const pick = (label) => {
    onChange(label)
    setQuery('')
    setSuggestions([])
    setOpen(false)
    setActive(-1)
  }

  const onKeyDown = (e) => {
    if (!showList) return
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActive((a) => (a + 1) % suggestions.length)
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActive((a) => (a <= 0 ? suggestions.length - 1 : a - 1))
    } else if (e.key === 'Enter' && active >= 0) {
      e.preventDefault() // pick instead of submitting the form
      pick(suggestions[active])
    } else if (e.key === 'Escape') {
      e.preventDefault()
      setOpen(false)
      setActive(-1)
    }
  }

  return (
    <div className="suggest">
      <input
        {...inputProps}
        id={id}
        className="input"
        value={value}
        autoComplete="off"
        role="combobox"
        aria-autocomplete="list"
        aria-expanded={showList}
        aria-controls={listId}
        aria-activedescendant={showList && active >= 0 ? `${listId}-${active}` : undefined}
        onChange={(e) => {
          onChange(e.target.value)
          setQuery(e.target.value)
          setOpen(true)
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onKeyDown={onKeyDown}
      />
      {showList && (
        <ul className="suggest__list" id={listId} role="listbox">
          {suggestions.map((label, i) => {
            const [name, sub] = splitLabel(label)
            return (
              <li
                key={label}
                id={`${listId}-${i}`}
                role="option"
                aria-selected={i === active}
                className={i === active ? 'suggest__option suggest__option--active' : 'suggest__option'}
                onMouseDown={(e) => {
                  e.preventDefault() // keep focus; pick before blur closes the list
                  pick(label)
                }}
                onMouseEnter={() => setActive(i)}
              >
                <PinIcon />
                <span>
                  <span className="suggest__name">{name}</span>
                  {sub && <span className="suggest__sub">{sub}</span>}
                </span>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
