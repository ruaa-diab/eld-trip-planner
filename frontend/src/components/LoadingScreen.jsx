import './LoadingScreen.css'

function Truck() {
  return (
    <svg width="48" height="34" viewBox="0 0 44 32" className="loading__truck-svg" aria-hidden="true">
      <g fill="none" stroke="#F5A524" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="2" y="6" width="24" height="16" rx="1.5" fill="#15253B" />
        <path d="M26 11h8l6 6v5H26z" fill="#15253B" />
        <circle cx="9" cy="25" r="3" fill="#0F1B2D" />
        <circle cx="20" cy="25" r="3" fill="#0F1B2D" />
        <circle cx="35" cy="25" r="3" fill="#0F1B2D" />
      </g>
    </svg>
  )
}

export default function LoadingScreen({ from, to, pickup, cycle, onCancel }) {
  return (
    <main className="page">
      <section className="card loading" aria-busy="true" aria-labelledby="loading-title">
        <div className="badge">Planning trip</div>
        <h2 className="loading__route">
          {from} → {to}
        </h2>
        <div className="loading__meta">
          Pickup in {pickup} • {cycle} h cycle used
        </div>

        <div className="loading__lane" aria-hidden="true">
          <div className="loading__road" />
          <div className="loading__truck">
            <div className="loading__headlight" />
            <Truck />
          </div>
        </div>

        <div className="loading__title" id="loading-title" role="status">
          Planning your trip…
        </div>
        <div className="loading__footer">
          <span>Route, Hours of Service schedule and log sheets are calculated together.</span>
          <button type="button" className="loading__cancel" onClick={onCancel}>
            Cancel
          </button>
        </div>
      </section>
    </main>
  )
}
