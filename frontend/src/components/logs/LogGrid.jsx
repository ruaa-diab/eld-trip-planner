// The 24-hour duty-status grid, drawn as SVG from the API's sheet segments.
// x = minute / 1440 of the grid width.
import { formatHM } from '../../format.js'
import './logs.css'

// On paper, off duty is a darker slate than the grid rules (#94A3B8) so it never blends in.
export const STATUS_ROWS = [
  { status: 'off_duty', label: ['1. Off Duty'], color: '#64748B' },
  { status: 'sleeper_berth', label: ['2. Sleeper Berth'], color: '#6366F1' },
  { status: 'driving', label: ['3. Driving'], color: '#F5A524' },
  { status: 'on_duty', label: ['4. On Duty', '(not driving)'], color: '#14B8A6' },
]
export const STATUS_COLOR = Object.fromEntries(STATUS_ROWS.map((r) => [r.status, r.color]))
const ROW_INDEX = Object.fromEntries(STATUS_ROWS.map((r, i) => [r.status, i]))

const INK = '#0F1B2D'
const RULE = '#94A3B8'

// Full sheet geometry (viewBox units). The remark brackets use the same x scale.
export const FULL = { labelW: 172, gridW: 864, totalW: 76, headH: 34, rowH: 44 }
FULL.width = FULL.labelW + FULL.gridW + FULL.totalW
export const minuteX = (min, g = FULL) => g.labelW + (min / 1440) * g.gridW

const HOUR_LABELS = Array.from({ length: 25 }, (_, h) =>
  h === 0 || h === 24 ? ['Mid-', 'night'] : h === 12 ? ['Noon'] : [String(h % 12)],
)

/** Horizontal status lines plus a vertical connector at every status change. */
function Segments({ segments, x, rowY, width }) {
  const out = []
  segments.forEach((s, i) => {
    const y = rowY(ROW_INDEX[s.status])
    out.push(
      <line key={`h${i}`} x1={x(s.start_min)} x2={x(s.end_min)} y1={y} y2={y} stroke={STATUS_COLOR[s.status]} strokeWidth={width} strokeLinecap="butt" />,
    )
    const next = segments[i + 1]
    if (next) {
      const xc = x(s.end_min)
      out.push(<line key={`v${i}`} x1={xc} x2={xc} y1={y} y2={rowY(ROW_INDEX[next.status])} stroke={INK} strokeWidth={1.6} />)
    }
  })
  return out
}

/** Full grid: hour header, row labels, 15-minute ticks, status lines, Total Hours column. */
export function FullGrid({ sheet }) {
  const { labelW, gridW, totalW, headH, rowH, width } = FULL
  const gridTop = headH
  const gridH = rowH * 4
  const height = headH + gridH + 34
  const x = (min) => minuteX(min)
  const rowY = (i) => gridTop + rowH * i + rowH / 2

  const ticks = []
  for (let q = 0; q <= 96; q++) {
    const xq = labelW + (q / 96) * gridW
    if (q % 4 === 0) {
      ticks.push(<line key={`hr${q}`} x1={xq} x2={xq} y1={gridTop} y2={gridTop + gridH} stroke={RULE} strokeWidth={1} />)
    } else {
      const len = q % 2 === 0 ? 16 : 9 // half-hour ticks are longer
      for (let r = 0; r < 4; r++) {
        const y0 = gridTop + rowH * r
        ticks.push(<line key={`t${q}-${r}`} x1={xq} x2={xq} y1={y0} y2={y0 + len} stroke={RULE} strokeWidth={1} />)
      }
    }
  }

  return (
    <svg className="log-grid" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Duty status grid, 24 hours">
      {/* Hour header */}
      <rect x={labelW} y={0} width={gridW} height={headH} fill={INK} />
      {HOUR_LABELS.map((lines, h) => {
        const xh = labelW + (h / 24) * gridW
        const anchor = h === 0 ? 'start' : h === 24 ? 'end' : 'middle'
        const xt = h === 0 ? xh + 3 : h === 24 ? xh - 3 : xh
        return (
          <text key={h} x={xt} y={lines.length === 2 ? 14 : 21} textAnchor={anchor} className="log-grid__hour">
            {lines.map((t, i) => (
              <tspan key={i} x={xt} dy={i ? 11 : 0}>
                {t}
              </tspan>
            ))}
          </text>
        )
      })}
      <rect x={labelW + gridW} y={0} width={totalW} height={headH} fill={INK} />
      <text x={labelW + gridW + totalW / 2} y={21} textAnchor="middle" className="log-grid__total-head">
        Total Hours
      </text>

      {/* Row labels with status color bars */}
      {STATUS_ROWS.map((r, i) => {
        const y0 = gridTop + rowH * i
        return (
          <g key={r.status}>
            <rect x={0} y={y0 + 8} width={5} height={rowH - 16} rx={2} fill={r.color} />
            <text x={14} y={y0 + rowH / 2 + (r.label.length === 2 ? -3 : 4)} className="log-grid__row-label">
              {r.label.map((t, j) => (
                <tspan key={j} x={14} dy={j ? 15 : 0}>
                  {t}
                </tspan>
              ))}
            </text>
          </g>
        )
      })}

      {/* Rows, ticks, border */}
      {[1, 2, 3].map((i) => (
        <line key={i} x1={labelW} x2={labelW + gridW} y1={gridTop + rowH * i} y2={gridTop + rowH * i} stroke={RULE} strokeWidth={2} />
      ))}
      {ticks}
      <rect x={labelW} y={gridTop} width={gridW} height={gridH} fill="none" stroke={INK} strokeWidth={2} />

      <Segments segments={sheet.segments} x={x} rowY={rowY} width={4} />

      {/* Total Hours column */}
      {STATUS_ROWS.map((r, i) => {
        const yb = gridTop + rowH * (i + 1) - 7
        const cx = labelW + gridW + totalW / 2
        return (
          <g key={r.status}>
            <text x={cx} y={yb - 4} textAnchor="middle" className="log-grid__total">
              {formatHM(sheet.totals[r.status])}
            </text>
            <line x1={cx - 30} x2={cx + 30} y1={yb} y2={yb} stroke={INK} strokeWidth={1.2} />
          </g>
        )
      })}
      <text x={labelW + gridW + totalW / 2} y={gridTop + gridH + 22} textAnchor="middle" className="log-grid__total">
        {formatHM(Object.values(sheet.totals).reduce((a, b) => a + b, 0))}
      </text>
      <line x1={labelW + gridW + 8} x2={width - 8} y1={gridTop + gridH + 27} y2={gridTop + gridH + 27} stroke={INK} strokeWidth={1.2} />
      <line x1={labelW + gridW + 8} x2={width - 8} y1={gridTop + gridH + 30} y2={gridTop + gridH + 30} stroke={INK} strokeWidth={1.2} />
    </svg>
  )
}

/** Compact grid for the mini sheets: hour lines, 4 rows, status lines. */
export function MiniGrid({ sheet }) {
  const W = 480
  const H = 64
  const rowH = H / 4
  const x = (min) => (min / 1440) * W
  const rowY = (i) => rowH * i + rowH / 2
  return (
    <svg className="mini-grid" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" aria-hidden="true">
      {Array.from({ length: 23 }, (_, h) => (
        <line key={h} x1={x((h + 1) * 60)} x2={x((h + 1) * 60)} y1={0} y2={H} stroke={RULE} strokeWidth={1} vectorEffect="non-scaling-stroke" />
      ))}
      {[1, 2, 3].map((i) => (
        <line key={i} x1={0} x2={W} y1={rowH * i} y2={rowH * i} stroke={RULE} strokeWidth={1} vectorEffect="non-scaling-stroke" />
      ))}
      <Segments segments={sheet.segments} x={x} rowY={rowY} width={4} />
      <rect x={0} y={0} width={W} height={H} fill="none" stroke={INK} strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
    </svg>
  )
}
