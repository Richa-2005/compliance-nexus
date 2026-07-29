import { Activity, ArrowRight, BadgeCheck, BookOpenCheck, BrainCircuit, Download, FileCheck2, LockKeyhole, Network, SearchCheck } from "lucide-react";
import { citations, transactions } from "../data/auditData";
import { ComplianceConstellation } from "../components/ComplianceConstellation";
import { Footer, BrandNav } from "../components/SiteChrome";
import { GithubMark } from "../components/GithubMark";
import { GraphLineage } from "../components/GraphLineage";
import { Status } from "../components/Status";

const pipeline = [
  [SearchCheck, "Parse", "Transaction amount, origin, beneficiary, and intent are extracted from analyst language."],
  [BookOpenCheck, "Retrieve", "Hybrid RAG pulls page-level evidence from RBI, KYC, SEC, and internal policy documents."],
  [Network, "Trace", "NetworkX maps ownership, jurisdiction, and governing policy relationships before the verdict."],
  [BrainCircuit, "Evaluate", "Deterministic guardrails compare requested value, allowed ceiling, and source authority."],
  [FileCheck2, "Certify", "The result becomes a PDF evidence certificate ready for compliance review."],
];

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

function ClosingSection() {
  return (
    <section className="section closing-section" id="demo">
      <div className="closing-motion"><span /><span /><span /></div>
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

export function LandingPage() {
  return (
    <main>
      <BrandNav>
        <div className="nav-links">
          <a href="#flow">Flow</a>
          <a href="#demo">Demo</a>
          <a href="https://github.com/Richa-2005" target="_blank" rel="noreferrer"><GithubMark size={18} /></a>
        </div>
      </BrandNav>

      <section className="hero hero-expanded">
        <div className="hero-copy">
          <span className="eyebrow"><LockKeyhole size={14} /> RegTech Operations Center</span>
          <h1>Compliance decisions with source-backed proof.</h1>
          <p>
            ComplianceNexus evaluates high-value cross-border remittances against statutory guidance,
            internal corporate policy, and entity lineage. Each verdict is supported by extracted metrics,
            page-level citations, and an exportable evidence certificate.
          </p>
          <div className="hero-actions">
            <a href="/dashboard?role=analyst" className="primary">Launch Demo Console <ArrowRight size={17} /></a>
            <a href="#flow" className="secondary">Review Audit Flow</a>
          </div>
          <div className="system-strip">
            <span><BadgeCheck size={15} /> FastAPI Online</span>
            <span><SearchCheck size={15} /> Retriever Active</span>
            <span><Network size={15} /> Graph Loaded</span>
            <span><FileCheck2 size={15} /> PDF Ready</span>
          </div>
        </div>
        <ComplianceConstellation />
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

export { pipeline };
