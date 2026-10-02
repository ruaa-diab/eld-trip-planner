import './Header.css'

export default function Header({ onNewTrip }) {
  return (
    <header className="header">
      <div className="header__bar">
        <a
          href="/"
          className="header__brand"
          onClick={(e) => {
            if (onNewTrip) {
              e.preventDefault()
              onNewTrip()
            }
          }}
        >
          <img className="header__logo" src="/logo.svg" width="36" height="36" alt="" />
          <span className="header__title">ELD Trip Planner</span>
        </a>
        <div className="header__actions">
          <span className="header__pill">Property-carrying • 70 hr / 8 day</span>
          {onNewTrip && (
            <button type="button" className="header__new" onClick={onNewTrip}>
              New trip
            </button>
          )}
        </div>
      </div>
      <div className="header__lane" aria-hidden="true" />
    </header>
  )
}
