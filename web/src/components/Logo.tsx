export function Logo({ compact = false }: { compact?: boolean }) {
  return (
    <div className={`brand ${compact ? "brand--compact" : ""}`}>
      <svg
        className="brand__mark"
        viewBox="0 0 32 32"
        role="img"
        aria-label="Asteria"
      >
        <rect
          className="brand__tile"
          x="0.75"
          y="0.75"
          width="30.5"
          height="30.5"
          rx="7"
        />
        <path
          className="brand__graph"
          d="M8.25 24.25 15.15 7.7a.92.92 0 0 1 1.7 0l6.9 16.55M11.25 18.1h9.5"
        />
        <circle className="brand__node brand__node--top" cx="16" cy="7.2" r="2.15" />
        <circle className="brand__node" cx="8.1" cy="24.55" r="1.75" />
        <circle className="brand__node" cx="23.9" cy="24.55" r="1.75" />
        <path
          className="brand__cut"
          d="M13.45 18.1h5.1"
        />
      </svg>
      {!compact && (
        <span className="brand__words">
          <strong>Asteria</strong>
          <small>Research</small>
        </span>
      )}
    </div>
  );
}
