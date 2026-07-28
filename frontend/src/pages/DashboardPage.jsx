import React from "react";
import {
  ArrowRight,
  BadgeCheck,
  Download,
  FileText,
  GitBranch,
  Loader2,
  LockKeyhole,
  Radio,
  Scale,
  SearchCheck,
  ShieldAlert,
  ShieldCheck,
  UserRoundCheck,
  X,
} from "lucide-react";
import { Status } from "../components/Status";
import { transactions as fallbackTransactions } from "../data/auditData";
import { authenticateDemo, evaluateAudit, getAuditHistory, getAuditTopology, getPdfUrl } from "../utils/api";

function normalizeAudit(record) {
  return {
    id: record.transaction_id || record.id,
    transactionId: record.transaction_id || record.id,
    timestamp: record.created_at || record.timestamp || "Demo seed",
    query: record.query || "Seeded transaction audit",
    amount: Number(record.transaction_value ?? String(record.amount || "0").replace(/[$M,K]/g, "")),
    amountLabel: record.transaction_value ? `$${Number(record.transaction_value).toLocaleString()}` : record.amount,
    ceiling: Number(record.allowed_ceiling ?? String(record.limit || "0").replace(/[$M,K]/g, "")),
    ceilingLabel: record.allowed_ceiling ? `$${Number(record.allowed_ceiling).toLocaleString()}` : record.limit,
    source: record.source_doc || record.source || "Foreign Investment",
    status: record.status || "COMPLIANT",
    citations: record.citations || [],
    pdfPath: record.pdf_path,
    verdict: record.audit_verdict_markdown || "## Official Compliance Verdict\nEvidence-backed decision pending backend connection.",
    delta: record.transaction_value && record.allowed_ceiling
      ? Number(record.transaction_value) - Number(record.allowed_ceiling)
      : 0,
  };
}

const fallbackAudits = fallbackTransactions.map((tx) => normalizeAudit({
  transaction_id: tx.id,
  timestamp: "Demo seed",
  query: `Audit ${tx.route} for ${tx.amount}`,
  transaction_value: tx.amount === "$4.5M" ? 4500000 : tx.amount === "$1.8M" ? 1800000 : tx.amount === "$900K" ? 900000 : 650000,
  allowed_ceiling: 1500000,
  source_doc: tx.source,
  status: tx.status,
  citations: ["foreign_Investement_rbi.pdf - Page 46", "nexus_holdings_global_inc.pdf - Page 2", "kyc_rbi.pdf - Page 35"],
}));

export function DashboardPage({ role = "analyst" }) {
  const [activeRole, setActiveRole] = React.useState(role);
  const [token, setToken] = React.useState("");
  const [telemetry, setTelemetry] = React.useState("reconnecting");
  const [audits, setAudits] = React.useState(fallbackAudits);
  const [selectedAudit, setSelectedAudit] = React.useState(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState("");
  const isOfficer = activeRole === "officer";

  React.useEffect(() => {
    let ignore = false;
    authenticateDemo(activeRole)
      .then((auth) => {
        if (ignore) return;
        setToken(auth.access_token);
        return getAuditHistory(auth.access_token);
      })
      .then((history) => {
        if (!ignore && history?.length) setAudits(history.map(normalizeAudit));
      })
      .catch(() => {
        if (!ignore) setError("Backend unavailable. Showing seeded dashboard data.");
      });
    return () => {
      ignore = true;
    };
  }, [activeRole]);

  React.useEffect(() => {
    const socket = new WebSocket("ws://localhost:8000/ws/live-feed");
    socket.onopen = () => setTelemetry("live");
    socket.onclose = () => setTelemetry("reconnecting");
    socket.onerror = () => setTelemetry("reconnecting");
    return () => socket.close();
  }, []);

  function switchRole(nextRole) {
    setActiveRole(nextRole);
    window.history.replaceState({}, "", `/dashboard?role=${nextRole}`);
  }

  async function handleEvaluate(query) {
    setLoading(true);
    setError("");
    try {
      const result = await evaluateAudit(token, query);
      const audit = normalizeAudit(result);
      setAudits((current) => [audit, ...current]);
      setSelectedAudit(audit);
    } catch {
      setError("Evaluation could not reach the backend. Keep the backend running on localhost:8000.");
    } finally {
      setLoading(false);
    }
  }

  const visibleAudits = isOfficer ? audits.filter((audit) => audit.status !== "COMPLIANT") : audits;
  const exposure = audits.reduce((sum, audit) => sum + Math.max(0, audit.amount || 0), 0);
  const nonCompliant = audits.filter((audit) => audit.status === "NON_COMPLIANT").length;
  const actionRequired = audits.filter((audit) => audit.status === "ACTION_REQUIRED").length;

  return (
    <main className="dashboard-page">
      <header className="dash-header">
        <a className="brand" href="/"><ShieldCheck size={22} /> ComplianceNexus</a>
        <div className={`telemetry-pill ${telemetry}`}>
          <Radio size={15} />
          {telemetry === "live" ? "TELEMETRY LIVE" : "RECONNECTING..."}
        </div>
        <div className="persona-switcher">
          <button className={activeRole === "analyst" ? "active" : ""} type="button" onClick={() => switchRole("analyst")}>
            <UserRoundCheck size={16} /> Sarah Jenkins <em>L1 Analyst</em>
          </button>
          <button className={activeRole === "officer" ? "active" : ""} type="button" onClick={() => switchRole("officer")}>
            <ShieldAlert size={16} /> Marcus Vance <em>L2 Risk Officer</em>
          </button>
        </div>
      </header>

      <section className="dashboard-role-band">
        <span className="eyebrow">{isOfficer ? "Exception Authority" : "Analyst Review"}</span>
        <h1>{isOfficer ? "Resolve high-risk remittance exceptions." : "Evaluate and review cross-border audit records."}</h1>
        <p>
          {isOfficer
            ? "Non-compliant and action-required audits are prioritized for final sign-off, freeze decisions, and evidence export."
            : "Run a multi-agent audit, review the dense transaction grid, and open the audit inspector without leaving the queue."}
        </p>
        {error && <div className="dash-warning">{error}</div>}
      </section>

      {isOfficer ? (
        <RiskSummary exposure={exposure} nonCompliant={nonCompliant} total={audits.length} actionRequired={actionRequired} />
      ) : (
        <EvaluatorBanner onEvaluate={handleEvaluate} loading={loading} />
      )}

      <AuditGrid audits={visibleAudits} onSelect={setSelectedAudit} isOfficer={isOfficer} />

      <AuditDrawer
        audit={selectedAudit}
        token={token}
        isOfficer={isOfficer}
        onClose={() => setSelectedAudit(null)}
      />
    </main>
  );
}

function EvaluatorBanner({ onEvaluate, loading }) {
  const [query, setQuery] = React.useState("Verify if a technology software licensing transaction of $1,800,000 USD initiated by Nexus India violates internal cross-border limits.");
  return (
    <section className="evaluator-banner">
      <div>
        <span className="eyebrow">Live Multi-Agent Audit</span>
        <h2>Submit a transaction query</h2>
      </div>
      <form onSubmit={(event) => {
        event.preventDefault();
        onEvaluate(query);
      }}>
        <textarea value={query} onChange={(event) => setQuery(event.target.value)} required />
        <button type="submit" disabled={loading}>
          {loading ? <Loader2 className="spin" size={17} /> : <SearchCheck size={17} />}
          Run Multi-Agent Audit
        </button>
      </form>
    </section>
  );
}

function RiskSummary({ exposure, nonCompliant, total, actionRequired }) {
  const ratio = total ? Math.round((nonCompliant / total) * 100) : 0;
  return (
    <section className="risk-summary">
      <div><span>Total Audit Exposure</span><strong>${exposure.toLocaleString()}</strong></div>
      <div><span>Non-Compliance Ratio</span><strong>{ratio}%</strong></div>
      <div><span>Circuit Breakers</span><strong>{actionRequired}</strong></div>
    </section>
  );
}

function AuditGrid({ audits, onSelect, isOfficer }) {
  return (
    <section className="audit-grid-section">
      <div className="tab-intro">
        <h2>{isOfficer ? "Exception Queue" : "Operational Audit Grid"}</h2>
        <p>{isOfficer ? "Filtered to non-compliant and action-required records." : "Fetched from audit history with seeded fallback when the backend is offline."}</p>
      </div>
      <div className="audit-grid">
        <div className="audit-row audit-head">
          <span>Transaction ID</span>
          <span>Timestamp</span>
          <span>Amount ($)</span>
          <span>Allowed Ceiling ($)</span>
          <span>Source Policy</span>
          <span>Status</span>
          <span>Actions</span>
        </div>
        {audits.map((audit) => (
          <button className="audit-row" type="button" onClick={() => onSelect(audit)} key={audit.transactionId}>
            <span className="mono">{audit.transactionId}</span>
            <span>{formatDate(audit.timestamp)}</span>
            <span className="mono">{audit.amountLabel}</span>
            <span className="mono">{audit.ceilingLabel}</span>
            <span>{audit.source}</span>
            <Status value={audit.status} />
            <span>Open Inspector</span>
          </button>
        ))}
      </div>
    </section>
  );
}

function AuditDrawer({ audit, token, isOfficer, onClose }) {
  const [tab, setTab] = React.useState("verdict");
  const [topology, setTopology] = React.useState(null);
  const [loadingGraph, setLoadingGraph] = React.useState(false);

  React.useEffect(() => {
    if (!audit || tab !== "graph") return;
    setLoadingGraph(true);
    getAuditTopology(token, audit.transactionId)
      .then(setTopology)
      .catch(() => setTopology(null))
      .finally(() => setLoadingGraph(false));
  }, [audit, tab, token]);

  if (!audit) return null;

  return (
    <aside className="audit-drawer" aria-label="Audit inspector">
      <div className="drawer-top">
        <div>
          <span className="eyebrow">Audit Inspector</span>
          <h2>{audit.transactionId}</h2>
        </div>
        <button type="button" onClick={onClose} aria-label="Close inspector"><X size={18} /></button>
      </div>

      <div className="drawer-tabs">
        <button className={tab === "verdict" ? "active" : ""} type="button" onClick={() => setTab("verdict")}>Verdict</button>
        <button className={tab === "graph" ? "active" : ""} type="button" onClick={() => setTab("graph")}>Topology</button>
        <button className={tab === "evidence" ? "active" : ""} type="button" onClick={() => setTab("evidence")}>Evidence Vault</button>
      </div>

      {tab === "verdict" && <VerdictTab audit={audit} isOfficer={isOfficer} />}
      {tab === "graph" && <TopologyTab topology={topology} loading={loadingGraph} />}
      {tab === "evidence" && <EvidenceVault audit={audit} />}
    </aside>
  );
}

function VerdictTab({ audit, isOfficer }) {
  const breachedBy = Math.max(0, audit.delta || 0);
  return (
    <div className="drawer-body">
      <div className="metric-callouts">
        <div><span>Variance Delta</span><strong>{breachedBy ? `$${breachedBy.toLocaleString()}` : "$0"}</strong></div>
        <div><span>Source Policy</span><strong>{audit.source}</strong></div>
        <div><span>Status</span><Status value={audit.status} /></div>
      </div>
      <div className="markdown-verdict">
        {renderMarkdown(audit.verdict)}
      </div>
      {isOfficer && (
        <div className="l2-controls">
          <button type="button"><BadgeCheck size={16} /> Sign Off & Approve Exception</button>
          <button type="button"><Scale size={16} /> Freeze Remittance & Escalate</button>
        </div>
      )}
    </div>
  );
}

function TopologyTab({ topology, loading }) {
  if (loading) return <div className="drawer-body skeleton">Loading topology graph...</div>;
  return (
    <div className="drawer-body">
      <div className="topology-canvas">
        <svg viewBox="0 0 520 360" role="img" aria-label="Transaction topology graph">
          {(topology?.edges || [
            { source: "Nexus Holdings", target: "Nexus India", label: "OWNS_100" },
            { source: "Nexus India", target: "Foreign Investment", label: "GOVERNED_BY" },
          ]).map((edge, index) => (
            <line x1={110 + index * 80} y1={90 + index * 45} x2={250 + index * 70} y2={190 + index * 35} key={`${edge.source}-${edge.target}`} />
          ))}
          {(topology?.nodes || [
            { id: "Nexus Holdings", group: "CORPORATE_ENTITY" },
            { id: "Nexus India", group: "CORPORATE_ENTITY" },
            { id: "Foreign Investment", group: "POLICY" },
          ]).slice(0, 8).map((node, index) => {
            const x = 90 + (index % 3) * 165;
            const y = 75 + Math.floor(index / 3) * 120;
            return (
              <g className={`topology-node ${node.group?.toLowerCase() || "entity"}`} key={node.id}>
                <circle cx={x} cy={y} r="26" />
                <text x={x} y={y + 48}>{node.id}</text>
              </g>
            );
          })}
        </svg>
      </div>
      <p className="drawer-note">Nodes represent the transaction-specific entity and policy path returned by the topology endpoint.</p>
    </div>
  );
}

function EvidenceVault({ audit }) {
  const pdfUrl = getPdfUrl(audit.transactionId);
  return (
    <div className="drawer-body">
      <div className="citation-vault">
        {(audit.citations?.length ? audit.citations : ["foreign_Investement_rbi.pdf - Page 46", "nexus_holdings_global_inc.pdf - Page 2"]).map((citation, index) => (
          <div key={`${citation}-${index}`}>
            <FileText size={15} />
            <span>{citation}</span>
          </div>
        ))}
      </div>
      <a className="pdf-download" href={pdfUrl} target="_blank" rel="noreferrer">
        <Download size={16} /> Download Official Compliance PDF
      </a>
      <iframe title="Compliance PDF preview" src={pdfUrl} />
    </div>
  );
}

function renderMarkdown(markdown) {
  return markdown.split("\n").filter(Boolean).map((line, index) => {
    if (line.startsWith("##")) return <h3 key={index}>{line.replace(/^##\s*/, "")}</h3>;
    if (line.startsWith("|")) return <p className="mono" key={index}>{line}</p>;
    return <p key={index}>{line.replace(/\*\*/g, "")}</p>;
  });
}

function formatDate(value) {
  if (!value || value === "Demo seed") return value || "Demo seed";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}
