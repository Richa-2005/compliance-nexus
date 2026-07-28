export function GraphLineage() {
  return (
    <section className="section graph-section">
      <div className="section-heading">
        <span className="eyebrow">Lineage Inspector</span>
        <h2>Trace how entities, jurisdictions, and policy sources shape each decision.</h2>
        <p>
          NetworkX topology connects parent companies, operating subsidiaries, regulatory PDFs, internal policy
          rules, and external filing references into one explainable compliance map.
        </p>
      </div>
      <div className="graph-stage">
        <svg className="graph-svg" viewBox="0 0 1100 520" role="img" aria-label="Animated compliance graph">
          <path className="graph-link amber" d="M550 78 C480 145 402 184 328 236" />
          <path className="graph-link amber" d="M550 78 C650 145 704 185 774 246" />
          <path className="graph-link red" d="M328 236 C444 310 578 344 754 382" />
          <path className="graph-link green" d="M328 236 C235 315 194 367 155 438" />
          <path className="graph-link muted" d="M774 246 C866 298 918 343 968 410" />
          <path className="graph-link muted" d="M550 78 C546 190 548 279 550 438" />
          {[
            [550, 78, "Nexus Holdings", "entity main"],
            [328, 236, "Nexus India", "entity"],
            [774, 246, "Overseas Vendor", "entity"],
            [754, 382, "Foreign Investment", "policy hot"],
            [155, 438, "RBI KYC", "policy"],
            [550, 438, "Internal Policy", "policy"],
            [968, 410, "SEC Filing", "doc"],
          ].map(([cx, cy, label, klass]) => (
            <g className={`graph-point ${klass}`} key={label}>
              <circle cx={cx} cy={cy} r="31" />
              <text x={cx} y={cy + 58}>{label}</text>
            </g>
          ))}
        </svg>
        <div className="graph-caption">
          <strong>Graph traversal isolates the entity-policy path used for the verdict.</strong>
          <span>Ownership, governing rules, source PDFs, and risk relationships stay visible before the final decision.</span>
        </div>
      </div>
    </section>
  );
}
