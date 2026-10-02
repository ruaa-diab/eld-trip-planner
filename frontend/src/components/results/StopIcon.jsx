// Stop icons from the v3 design: road-sign shapes with a white inner outline and a glyph.
// One SVG definition serves both the timeline (React) and the map markers (Leaflet divIcon HTML).

const PATHS = {
  circle: 'M16 4a12 12 0 1 0 0.01 0Z',
  diamond: 'M16 3L29 16L16 29L3 16Z',
  us: 'M5 4H27Q26 8 28 11Q29 22 16 29Q3 22 4 11Q6 8 5 4Z',
  interstate: 'M4 6Q10 3 16 6Q22 3 28 6L28 14Q28 25 16 30Q4 25 4 14Z',
  square: 'M9 4h14a5 5 0 0 1 5 5v14a5 5 0 0 1-5 5H9a5 5 0 0 1-5-5V9a5 5 0 0 1 5-5Z',
  pentagon: 'M16 3L29 9V28H3V9Z',
  octagon: 'M10.6 3H21.4L29 10.6V21.4L21.4 29H10.6L3 21.4V10.6Z',
}

/** Keyed by API stop type, plus "start" for the current location. */
export const STOP_KINDS = {
  start: { name: 'Current location', path: 'diamond', fill: '#F5A524', fg: '#0F1B2D', text: '#F5A524', glyph: '', ty: 19.5, fs: 9 },
  pickup: { name: 'Pickup', path: 'us', fill: '#14B8A6', fg: '#0F1B2D', text: '#2DD4BF', glyph: 'P', ty: 19.5, fs: 12 },
  dropoff: { name: 'Dropoff', path: 'interstate', fill: '#14B8A6', fg: '#0F1B2D', text: '#2DD4BF', glyph: 'D', ty: 20, fs: 12 },
  fuel: { name: 'Fuel stop', path: 'square', fill: '#14B8A6', fg: '#0F1B2D', text: '#2DD4BF', glyph: 'F', ty: 20, fs: 12 },
  break_30: { name: '30-min break', path: 'circle', fill: '#94A3B8', fg: '#0F1B2D', text: '#CBD5E1', glyph: '30', ty: 20, fs: 11 },
  rest_10: { name: '10-hr rest', path: 'pentagon', fill: '#6366F1', fg: '#FFFFFF', text: '#A5B4FC', glyph: '10', ty: 21.5, fs: 11 },
  restart_34: { name: '34-hr restart', path: 'octagon', fill: '#E5484D', fg: '#FFFFFF', text: '#FF8A8D', glyph: '34', ty: 20, fs: 11 },
}

/** SVG markup for a stop icon (static strings only, no user input). */
export function stopIconSvg(kind, size = 30) {
  const k = STOP_KINDS[kind]
  const d = PATHS[k.path]
  const center = k.glyph
    ? `<text x="16" y="${k.ty}" text-anchor="middle" font-size="${k.fs}" font-weight="800" fill="${k.fg}" font-family="Overpass, sans-serif">${k.glyph}</text>`
    : `<circle cx="16" cy="16" r="3.5" fill="${k.fg}"/>`
  return (
    `<svg width="${size}" height="${size}" viewBox="0 0 32 32" aria-hidden="true" style="display:block">` +
    `<path d="${d}" fill="${k.fill}" stroke="#0F1B2D" stroke-width="2.5"/>` +
    `<path d="${d}" fill="none" stroke="#FFFFFF" stroke-width="1.2" transform="translate(16 16) scale(0.84) translate(-16 -16)"/>` +
    center +
    `</svg>`
  )
}

export default function StopIcon({ kind, size = 30 }) {
  return (
    <span
      className="stop-icon"
      style={{ display: 'block', flex: 'none', width: size, height: size }}
      dangerouslySetInnerHTML={{ __html: stopIconSvg(kind, size) }}
    />
  )
}
