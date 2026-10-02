const RULES = [
  ['Cycle', '70 hr / 8 days'],
  ['Driving limit', '11 hr per shift'],
  ['Duty window', '14 hr'],
  ['Break', '30 min after 8 hr driving'],
  ['Off-duty reset', '10 consecutive hr'],
  ['Cycle restart', '34 consecutive hr'],
  ['Fueling', 'Every 1,000 mi max'],
  ['Pickup & dropoff', '1 hr on duty each'],
]

const STATUSES = [
  ['off', 'Off duty'],
  ['sleeper', 'Sleeper berth'],
  ['driving', 'Driving'],
  ['on', 'On duty'],
]

export default function PlanningRules() {
  return (
    <aside className="card rules" aria-labelledby="rules-title">
      <h2 className="badge rules__badge" id="rules-title">
        Planning rules
      </h2>
      <dl className="rules__list">
        {RULES.map(([k, v]) => (
          <div className="rules__row" key={k}>
            <dt>{k}</dt>
            <dd>{v}</dd>
          </div>
        ))}
      </dl>
      <h3 className="rules__legend-title">Duty status colors</h3>
      <ul className="rules__legend">
        {STATUSES.map(([key, label]) => (
          <li key={key}>
            <span className={`rules__swatch rules__swatch--${key}`} aria-hidden="true" />
            {label}
          </li>
        ))}
      </ul>
    </aside>
  )
}
