import React from "react";
import { createRoot } from "react-dom/client";
import {
  Activity,
  ArrowRight,
  BadgeCheck,
  BookOpenCheck,
  BrainCircuit,
  Download,
  FileCheck2,
  LockKeyhole,
  Network,
  SearchCheck,
  ShieldCheck,
  UserRoundCheck,
} from "lucide-react";
import "./styles.css";

function GithubMark({ size = 20 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true" fill="currentColor">
      <path d="M12 .5C5.73.5.75 5.48.75 11.75c0 4.98 3.23 9.19 7.72 10.68.56.1.77-.24.77-.54v-2.03c-3.14.68-3.8-1.34-3.8-1.34-.51-1.31-1.25-1.66-1.25-1.66-1.03-.7.08-.69.08-.69 1.13.08 1.73 1.17 1.73 1.17 1.01 1.72 2.65 1.22 3.3.93.1-.73.39-1.22.71-1.5-2.51-.29-5.15-1.26-5.15-5.59 0-1.24.44-2.24 1.16-3.03-.12-.28-.5-1.43.11-2.99 0 0 .95-.3 3.1 1.16.9-.25 1.86-.38 2.82-.38.96 0 1.92.13 2.82.38 2.15-1.46 3.1-1.16 3.1-1.16.61 1.56.23 2.71.11 2.99.72.79 1.16 1.79 1.16 3.03 0 4.34-2.65 5.3-5.17 5.58.4.35.76 1.03.76 2.08v3.08c0 .3.2.65.78.54 4.48-1.5 7.7-5.7 7.7-10.68C23.25 5.48 18.27.5 12 .5Z" />
    </svg>
  );
}

const transactions = [
  {
    id: "TX_1001",
    route: "Nexus India -> Overseas Vendor",
    amount: "$1.8M",
    limit: "$1.5M",
    status: "NON_COMPLIANT",
    evidence: 67,
  },
  {
    id: "TX_1002",
    route: "Nexus India -> Authorized Vendor",
    amount: "$400K",
    limit: "$1.5M",
    status: "COMPLIANT",
    evidence: 63,
  },
  {
    id: "TX_1008",
    route: "Nexus India -> Overseas Fintech",
    amount: "$4.5M",
    limit: "$1.5M",
    status: "NON_COMPLIANT",
    evidence: 61,
  },
  {
    id: "TX_1005",
    route: "Nexus Global -> Offshore Wallet",
    amount: "$900K",
    limit: "$1.5M",
    status: "ACTION_REQUIRED",
    evidence: 64,
  },
  {
    id: "TX_1004",
    route: "Nexus Tech India -> Parent Entity",
    amount: "$650K",
    limit: "$1.5M",
    status: "COMPLIANT",
    evidence: 66,
  },
];

const pipeline = [
  [SearchCheck, "Parse", "Transaction amount, origin, beneficiary, and intent are extracted from analyst language."],
  [BookOpenCheck, "Retrieve", "Hybrid RAG pulls page-level evidence from RBI, KYC, SEC, and internal policy documents."],
  [Network, "Trace", "NetworkX maps ownership, jurisdiction, and governing policy relationships before the verdict."],
  [BrainCircuit, "Evaluate", "Deterministic guardrails compare requested value, allowed ceiling, and source authority."],
  [FileCheck2, "Certify", "The result becomes a PDF evidence certificate ready for compliance review."],
];

const citations = [
  "foreign_Investement_rbi.pdf - Page 46",
  "nexus_holdings_global_inc.pdf - Page 2",
  "kyc_rbi.pdf - Page 35",
  "credit_Risk_RBI.pdf - Page 15",
];

function Status({ value }) {
  return <span className={`status status-${value.toLowerCase()}`}>{value.replace("_", " ")}</span>;
}

function ComplianceConstellation() {
  return (
    <div className="constellation" aria-label="Animated ComplianceNexus concept visual">
      <div className="orbit orbit-one" />
      <div className="orbit orbit-two" />
      <div className="orbit orbit-three" />
      <div className="pulse-beam beam-one" />
      <div className="pulse-beam beam-two" />
      <div className="pulse-beam beam-three" />
      <div className="core-word">
        <span>COMPLIANCE</span>
        <strong>NEXUS</strong>
      </div>
      <div className="concept-item item-policy"><ShieldCheck size={28} /><span>Policies</span></div>
      <div className="concept-item item-reg"><Activity size={28} /><span>Regulations</span></div>
      <div className="concept-item item-law"><BadgeCheck size={28} /><span>Law</span></div>
      <div className="concept-item item-rules"><LockKeyhole size={28} /><span>Rules</span></div>
      <div className="concept-item item-standards"><FileCheck2 size={28} /><span>Standards</span></div>
      <div className="concept-item item-transparency"><SearchCheck size={28} /><span>Transparency</span></div>
      <div className="concept-item item-lineage"><Network size={28} /><span>Lineage</span></div>
      <div className="concept-item item-cert"><BookOpenCheck size={28} /><span>Citations</span></div>
      <div className="floating-verdict">
        <small>TX_1001</small>
        <strong>NON_COMPLIANT</strong>
        <span>$300K variance detected</span>
      </div>
    </div>
  );
}

function ClosingSection() {
  return (
    <section className="section closing-section" id="demo">
      <div className="closing-motion">
        <span />
        <span />
        <span />
      </div>
      <div className="closing-content">
        <span className="eyebrow">Move Into The Product</span>
        <h2>Move from risk signal to reviewed compliance decision.</h2>
        <p>
          Enter the demo workspace to inspect seeded transactions, compare requested amounts against approved
          ceilings, and review the citation trail behind each compliance outcome.
        </p>
        <div className="hero-actions">
          <a href="/login" className="primary">Login <ArrowRight size={17} /></a>
          <a href="/signup" className="secondary">Sign Up</a>
        </div>
      </div>
    </section>
  );
}

function Footer() {
  return (
    <footer>
      <div>
        <a className="brand" href="/"><ShieldCheck size={20} /> ComplianceNexus</a>
        <p>RAG-powered audit intelligence for cross-border compliance decisions.</p>
      </div>
      <nav>
        <a href="/#flow">Audit Flow</a>
        <a href="/login">Login</a>
        <a href="/signup">Sign Up</a>
      </nav>
      <div className="footer-built">
        <span>Built by Richa Gupta</span>
        <a href="https://github.com/Richa-2005" target="_blank" rel="noreferrer" aria-label="Richa Gupta on GitHub">
          <GithubMark size={20} />
        </a>
      </div>
    </footer>
  );
}

function Pipeline() {
  return (
    <section className="section pipeline-section" id="flow">
      <div className="section-heading">
        <span className="eyebrow">Audit Engine</span>
        <h2>From analyst query to defensible audit record.</h2>
        <p>
          A natural-language remittance request is converted into structured facts, matched against regulatory
          source material, checked against corporate limits, and preserved as an audit-ready record.
        </p>
      </div>
      <div className="pipeline">
        {pipeline.map(([Icon, label, detail], index) => (
          <div className="pipeline-node" style={{ "--delay": `${index * 0.45}s` }} key={label}>
            <span><Icon size={24} /></span>
            <strong>{label}</strong>
            <p>{detail}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

function Evidence() {
  return (
    <section className="section evidence-section">
      <div className="section-copy">
        <span className="eyebrow">Evidence-Backed Verdict</span>
        <h2 className="typing-title">Every decision shows </h2>
        <h2 className="typing-title">the rule, the number, </h2>
        <h2 className="typing-title">and the document trail.</h2>
        <p>
          Verdicts are generated from extracted transaction values, validated ceiling thresholds, governing
          policy anchors, and page-level citations from the compliance document set.
        </p>
      </div>
      <div className="evidence-ledger">
        <div className="ledger-verdict">
          <span>Verdict</span>
          <strong>NON_COMPLIANT</strong>
          <p>$1,800,000 request exceeds the $1,500,000 approved ceiling by $300,000.</p>
        </div>
        <div className="ledger-rule">
          <span>Primary Mandate</span>
          <strong>Foreign Investment</strong>
          <em>Statutory and internal policy alignment required before release.</em>
        </div>
        {citations.map((citation, index) => (
          <div className="citation-line" style={{ "--delay": `${index * 0.35}s` }} key={citation}>
            <FileCheck2 size={16} />
            <span>{citation}</span>
            <em>locked</em>
          </div>
        ))}
      </div>
    </section>
  );
}

function GraphLineage() {
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

function DashboardPreview() {
  return (
    <section className="section dashboard-section">
      <div className="section-heading compact">
        <span className="eyebrow">Product Preview</span>
        <h2>Monitor transaction history, breach exposure, and evidence exports from one console.</h2>
        <p>
          The dashboard is designed for repeat analyst review: status filtering, audit history, transaction
          deltas, citation inspection, and generated PDF certificates live in the same workflow.
        </p>
      </div>
      <div className="dashboard-shell">
        <div className="dash-top">
          <strong>Compliance Operations Center</strong>
          <span><Activity size={14} /> 124ms avg evaluation</span>
        </div>
        <div className="metric-strip">
          <span><b>8</b> audits seeded</span>
          <span><b>$3.3M</b> blocked exposure</span>
          <span><b>258</b> citations attached</span>
          <span><b>100%</b> PDF traceability</span>
        </div>
        <div className="dash-body">
          <div className="mini-table">
            {transactions.slice(0, 4).map((tx) => (
              <div className="mini-row" key={tx.id}>
                <span className="mono">{tx.id}</span>
                <span>{tx.route}</span>
                <span>{tx.amount}</span>
                <Status value={tx.status} />
              </div>
            ))}
          </div>
          <aside className="drawer-preview">
            <span className="eyebrow">Audit Drawer</span>
            <h3>TX_1001</h3>
            <p>Variance breach confirmed against Foreign Investment mandate.</p>
            <button><Download size={16} /> Export Certificate</button>
          </aside>
        </div>
      </div>
    </section>
  );
}

function App() {
  const path = window.location.pathname;

  if (path === "/login" || path === "/signup") {
    return <AuthPage mode={path === "/signup" ? "signup" : "login"} />;
  }

  return (
    <main>
      <nav className="nav">
        <a className="brand" href="/"><ShieldCheck size={22} /> ComplianceNexus</a>
        <div className="nav-links">
          <a href="#flow">Flow</a>
          <a href="#demo">Demo</a>
          <a href="https://github.com/Richa-2005" target="_blank" rel="noreferrer"><GithubMark size={18} /></a>
        </div>
      </nav>

      <section className="hero">
        <div className="hero-copy">
          <span className="eyebrow"><LockKeyhole size={14} /> RegTech Operations Center</span>
          <h1>Compliance decisions with source-backed proof.</h1>
          <p>
            ComplianceNexus evaluates high-value cross-border remittances against statutory guidance,
            internal corporate policy, and entity lineage. Each verdict is supported by extracted metrics,
            page-level citations, and an exportable evidence certificate.
          </p>
          <ComplianceConstellation />
          <div className="hero-actions">
            <a href="/login" className="primary">Launch Demo Console <ArrowRight size={17} /></a>
            <a href="#flow" className="secondary">Review Audit Flow</a>
          </div>
          <div className="system-strip">
            <span><BadgeCheck size={15} /> FastAPI Online</span>
            <span><SearchCheck size={15} /> Retriever Active</span>
            <span><Network size={15} /> Graph Loaded</span>
            <span><FileCheck2 size={15} /> PDF Ready</span>
          </div>
        </div>
      </section>

      <Pipeline />
      <Evidence />
      <GraphLineage />
      <DashboardPreview />
      <ClosingSection />

      <Footer />
    </main>
  );
}

function AuthPage({ mode }) {
  const isSignup = mode === "signup";

  return (
    <main className="auth-page">
      <nav className="nav">
        <a className="brand" href="/"><ShieldCheck size={22} /> ComplianceNexus</a>
      </nav>

      <section className="auth-layout">
        <div className="auth-panel">
          <span className="eyebrow"><LockKeyhole size={14} /> Secure Access</span>
          <h1>{isSignup ? "Create your ComplianceNexus workspace." : "Enter the compliance console."}</h1>
          <p>
            Use demo access to inspect the analyst workflow immediately, or continue with a standard account form.
          </p>

          <form className="auth-form" onSubmit={(event) => event.preventDefault()}>
            {isSignup && <input type="text" placeholder="Full name" required />}
            <input type="email" placeholder="Work email" required />
            <input type="password" placeholder="Password" required minLength={6} />
            <button type="submit">{isSignup ? "Create Account" : "Login"} <ArrowRight size={17} /></button>
          </form>
          <p className="auth-toggle">
            {isSignup ? "Already have an account? " : "Don't have an account? "}
            <a href={isSignup ? "/login" : "/signup"}>{isSignup ? "Sign in" : "Sign up first"}</a>
          </p>

          <div className="demo-logins">
            <span className="eyebrow">Demo Logins</span>
            <button type="button">
              <UserRoundCheck size={17} />
              Sarah Jenkins
              <em>L1 Analyst</em>
            </button>
            <button type="button">
              <ShieldCheck size={17} />
              Marcus Vance
              <em>L2 Risk Officer</em>
            </button>
          </div>
        </div>

        <aside className="auth-context">
          <h2>Built for regulatory review teams.</h2>
          <p>
            ComplianceNexus gives analysts and risk officers a shared workspace for transaction review,
            citation inspection, entity-policy lineage, and PDF evidence export.
          </p>
          <div className="role-summary">
            <div>
              <span>L1 Analyst</span>
              <ul>
                <li>Reviews newly evaluated remittances</li>
                <li>Opens cited policy pages and source anchors</li>
                <li>Escalates exceptions for legal or L2 review</li>
              </ul>
            </div>
            <div>
              <span>L2 Risk Officer</span>
              <ul>
                <li>Confirms high-risk breach decisions</li>
                <li>Blocks or approves exceptional remittances</li>
                <li>Exports evidence certificates for audit files</li>
              </ul>
            </div>
          </div>
        </aside>
      </section>
    </main>
  );
}

createRoot(document.getElementById("root")).render(<App />);
