import { useEffect, useMemo, useRef } from 'react'
import L from 'leaflet'
import { MapContainer, Marker, Polyline, Popup, TileLayer, useMap } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import { formatClock, formatDay } from '../../format.js'
import { STOP_KINDS, stopIconSvg } from './StopIcon.jsx'
import './RouteMap.css'

const TILE_URL = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png'
const ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
const FOCUS_ZOOM = 9
const LEGEND_ORDER = ['start', 'pickup', 'dropoff', 'fuel', 'break_30', 'rest_10', 'restart_34']
const ALWAYS_PRESENT = new Set(['start', 'pickup', 'dropoff'])

/**
 * Stops at identical coordinates (e.g. a break followed by a rest) share one marker.
 * Each group keeps its timeline indexes; the marker shows the longest stop's icon.
 */
function groupByPoint(items) {
  const groups = new Map()
  items.forEach((item, index) => {
    const key = `${item.lat.toFixed(5)},${item.lon.toFixed(5)}`
    if (!groups.has(key)) groups.set(key, { lat: item.lat, lon: item.lon, members: [] })
    groups.get(key).members.push({ ...item, index })
  })
  return [...groups.values()].map((g) => ({
    ...g,
    kind: g.members.reduce((a, b) => (b.durationMin > a.durationMin ? b : a)).kind,
  }))
}

function markerIcon(kind, selected) {
  return L.divIcon({
    html: stopIconSvg(kind, 30),
    className: selected ? 'map-marker map-marker--selected' : 'map-marker',
    iconSize: [30, 30],
    iconAnchor: [15, 15],
    popupAnchor: [0, -14],
  })
}

/** Fits the whole route on load and whenever a new plan arrives. */
function FitRoute({ bounds }) {
  const map = useMap()
  useEffect(() => {
    map.fitBounds(bounds, { padding: [40, 40] })
  }, [map, bounds])
  return null
}

/** Flies to a stop picked in the timeline and opens its popup. */
function FocusSelected({ selected, groups, markerRefs }) {
  const map = useMap()
  useEffect(() => {
    if (!selected || selected.source !== 'timeline') return
    const gi = groups.findIndex((g) => g.members.some((m) => m.index === selected.index))
    if (gi < 0) return
    const { lat, lon } = groups[gi]
    map.flyTo([lat, lon], Math.max(map.getZoom(), FOCUS_ZOOM), { duration: 0.8 })
    map.once('moveend', () => markerRefs.current[gi]?.openPopup())
  }, [selected, groups, map, markerRefs])
  return null
}

function StopPopup({ members }) {
  return (
    <div className="map-popup">
      {members.map((m) => {
        const kind = STOP_KINDS[m.kind]
        return (
          <div className="map-popup__stop" key={m.index}>
            <div className="map-popup__kind" style={{ color: kind.text }}>
              {kind.name}
            </div>
            <div className="map-popup__name">{m.name}</div>
            <div className="map-popup__time">
              {formatDay(m.start)} • {formatClock(m.start)} <span className="map-popup__tag">{m.tag}</span>
            </div>
          </div>
        )
      })}
    </div>
  )
}

function Legend({ items }) {
  const present = new Set(items.map((i) => i.kind))
  return (
    <ul className="map-legend">
      <li>
        <span className="map-legend__route" aria-hidden="true" />
        Route (driving)
      </li>
      {LEGEND_ORDER.map((kind) => {
        const used = present.has(kind) || ALWAYS_PRESENT.has(kind)
        return (
          <li key={kind} className={used ? undefined : 'map-legend__unused'}>
            <span dangerouslySetInnerHTML={{ __html: stopIconSvg(kind, 22) }} />
            {STOP_KINDS[kind].name}
            {!used && ' (not needed)'}
          </li>
        )
      })}
    </ul>
  )
}

/**
 * geometry: [[lat, lon], ...] from the API. items: timeline items (with lat/lon).
 * selected: { index, source } or null. onSelect(index): a marker was clicked.
 */
export default function RouteMap({ geometry, items, selected, onSelect }) {
  const groups = useMemo(() => groupByPoint(items), [items])
  const bounds = useMemo(
    () => L.latLngBounds([...geometry, ...items.map((i) => [i.lat, i.lon])]),
    [geometry, items],
  )
  const markerRefs = useRef([])
  const selectedGroup = groups.findIndex((g) => g.members.some((m) => m.index === selected?.index))

  return (
    <section className="route-map" aria-label="Route map">
      <div className="route-map__canvas">
        <MapContainer bounds={bounds} boundsOptions={{ padding: [40, 40] }} scrollWheelZoom={false}>
          <TileLayer url={TILE_URL} attribution={ATTRIBUTION} className="map-tiles" maxZoom={18} />
          <Polyline positions={geometry} pathOptions={{ color: '#F5A524', weight: 14, opacity: 0.18 }} interactive={false} />
          <Polyline positions={geometry} pathOptions={{ color: '#0F1B2D', weight: 8, opacity: 0.9 }} interactive={false} />
          <Polyline positions={geometry} pathOptions={{ color: '#F5A524', weight: 4 }} interactive={false} />
          {groups.map((g, gi) => (
            <Marker
              key={`${g.lat},${g.lon}`}
              position={[g.lat, g.lon]}
              icon={markerIcon(g.kind, gi === selectedGroup)}
              zIndexOffset={gi === selectedGroup ? 1000 : 0}
              title={g.members.map((m) => `${STOP_KINDS[m.kind].name}: ${m.name}`).join('; ')}
              ref={(el) => (markerRefs.current[gi] = el)}
              eventHandlers={{ click: () => onSelect(g.members[0].index) }}
            >
              <Popup maxWidth={240}>
                <StopPopup members={g.members} />
              </Popup>
            </Marker>
          ))}
          <FitRoute bounds={bounds} />
          <FocusSelected selected={selected} groups={groups} markerRefs={markerRefs} />
        </MapContainer>
      </div>
      <Legend items={items} />
    </section>
  )
}
