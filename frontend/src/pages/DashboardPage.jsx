import React from "react";
import {
  Download,
  FileText,
  Gauge,
  GitBranch,
  Loader2,
  Radio,
  SearchCheck,
  ShieldCheck,
  X,
  Zap,
} from "lucide-react";
import { Status } from "../components/Status";
import {
  authenticateDemo,
  createAuditAssignment,
  evaluateAudit,
  getAssignmentInbox,
  getAuditHistory,
  getAuditTopology,
  getPdfUrl,
  updateAssignment,
} from "../utils/api";

const PERSONAS = {
  analyst: {
    label: "Sarah Jenkins (L1 Analyst)",
    username: "analyst@compliancenexus.com",
  },
  officer: {
    label: "Marcus Vance (L2 Risk Officer)",
    username: "officer@compliancenexus.com",
  },
};

const TABS = [
  { id: "queue", label: "Audit Queue", icon: Gauge },
  { id: "new", label: "New Audit", icon: Zap },
  { id: "graph", label: "Knowledge Graph", icon: GitBranch },
];

const GUIDE_COPY = {
  queue: {
    title: "Review completed and seeded audit decisions.",
    text: "Use this queue to compare remittance values, source policy, verdict status, and the persona that handled the audit. Select any transaction to open the full evidence report and citations.",
  },
  new: {
    title: "Run a fresh compliance evaluation.",
    text: "Start with a sample scenario or write a transaction request. ComplianceNexus parses the request, retrieves policy evidence, evaluates the ceiling, and returns an audit certificate.",
  },
  graph: {
    title: "Inspect the entity-policy topology behind a verdict.",
    text: "This view shows how a transaction connects to subsidiaries, policy documents, risk rules, and breach signals so the compliance decision is traceable instead of opaque.",
  },
};

const SAMPLE_QUERIES = [
  {
    label: "Foreign investment breach",
    outcome: "Expected non-compliant",
    query: "Verify whether a software licensing transaction of $1,800,000 USD initiated by Nexus India to an overseas vendor violates the approved Foreign Investment remittance ceiling.",
  },
  {
    label: "Routine vendor payment",
    outcome: "Expected compliant",
    query: "Evaluate a cross-border technology services payment of $400,000 USD from Nexus India to an authorized overseas vendor under the Foreign Investment policy limit.",
  },
  {
    label: "Large offshore remittance",
    outcome: "Expected non-compliant",
    query: "Audit a $4,500,000 USD remittance from Nexus India to an overseas fintech partner and determine whether RBI KYC and internal ceiling rules are breached.",
  },
  {
    label: "Subsidiary policy check",
    outcome: "Expected compliant",
    query: "Check whether Nexus Global can approve a $900,000 USD subsidiary support transfer when the applicable corporate limit is $1,500,000 USD and source documents are available.",
  },
];

const FILTERS = [
  { id: "ALL", label: "All" },
  { id: "COMPLIANT", label: "Compliant" },
  { id: "NON_COMPLIANT", label: "Non-Compliant" },
  { id: "ACTION_REQUIRED", label: "Action Required" },
];

export function DashboardPage({ role = "analyst" }) {
  const [activeTab, setActiveTab] = React.useState("queue");
  const [activeRole, setActiveRole] = React.useState(role);
  const [tokens, setTokens] = React.useState({});
  const [telemetry, setTelemetry] = React.useState("reconnecting");
  const [audits, setAudits] = React.useState([]);
  const [loadingHistory, setLoadingHistory] = React.useState(true);
  const [filter, setFilter] = React.useState("ALL");
  const [selectedAudit, setSelectedAudit] = React.useState(null);
  const [latestAudit, setLatestAudit] = React.useState(null);
  const [assignments, setAssignments] = React.useState([]);
  const [notice, setNotice] = React.useState("");

  const activeToken = tokens[activeRole] || "";

  React.useEffect(() => {
    let ignore = false;
    setLoadingHistory(true);
    setNotice("");

    Promise.all(
      Object.keys(PERSONAS).map(async (persona) => {
        const auth = await authenticateDemo(persona);
        const history = await getAuditHistory(auth.access_token);
        return { persona, token: auth.access_token, history };
      })
    )
      .then((results) => {
        if (ignore) return;
        const nextTokens = {};
        const merged = [];
        results.forEach((result) => {
          nextTokens[result.persona] = result.token;
          result.history.forEach((record) => merged.push(normalizeAudit(record, result.persona)));
        });
        setTokens(nextTokens);
        setAudits(dedupeAudits(merged));
      })
      .catch(() => {
        if (!ignore) {
          setNotice("Unable to load audit history from localhost:8000.");
          setAudits([]);
        }
      })
      .finally(() => {
        if (!ignore) setLoadingHistory(false);
      });

    return () => {
      ignore = true;
    };
  }, []);

  React.useEffect(() => {
    if (!tokens.analyst) return;
    refreshAssignments(tokens.analyst);
  }, [tokens.analyst]);

  React.useEffect(() => {
    let socket;
    let reconnectTimer;

    function connect() {
      socket = new WebSocket("ws://localhost:8000/ws/live-feed");
      socket.onopen = () => setTelemetry("live");
      socket.onclose = () => {
        setTelemetry("reconnecting");
        reconnectTimer = window.setTimeout(connect, 2500);
      };
      socket.onerror = () => setTelemetry("reconnecting");
    }

    connect();
    return () => {
      window.clearTimeout(reconnectTimer);
      if (socket) socket.close();
    };
  }, []);

  async function handlePersonaChange(nextRole) {
    setActiveRole(nextRole);
    window.history.replaceState({}, "", `/dashboard?role=${nextRole}`);
    if (tokens[nextRole]) return;
    try {
      const auth = await authenticateDemo(nextRole);
      setTokens((current) => ({ ...current, [nextRole]: auth.access_token }));
    } catch {
      setNotice("Unable to refresh persona session.");
    }
  }

  function addAudit(record) {
    const audit = normalizeAudit(record, activeRole);
    setAudits((current) => dedupeAudits([audit, ...current]));
    setLatestAudit(audit);
    setFilter("ALL");
  }

  async function refreshAssignments(token = tokens.analyst) {
    if (!token) return;
    try {
      const inbox = await getAssignmentInbox(token);
      setAssignments(inbox);
    } catch {
      setAssignments([]);
    }
  }

  async function resolveAssignment(assignmentId) {
    if (!tokens.analyst) return;
    try {
      const updated = await updateAssignment(tokens.analyst, assignmentId, { status: "RESOLVED" });
      setAssignments((current) => current.map((item) => (item.id === assignmentId ? updated : item)));
      setNotice("Assignment marked resolved.");
    } catch {
      setNotice("Unable to resolve assignment.");
    }
  }

  const counts = countByStatus(audits);
  const filteredAudits = filter === "ALL" ? audits : audits.filter((audit) => audit.status === filter);

  return (
    <main className="dashboard-page">
      <header className="regtech-nav">
        <a className="regtech-brand" href="/">
          <ShieldCheck size={21} />
          <span>ComplianceNexus RegTech</span>
        </a>

        <div className="nav-actions">
          <TelemetryPill telemetry={telemetry} />
          <select value={activeRole} onChange={(event) => handlePersonaChange(event.target.value)} aria-label="Persona switcher">
            {Object.entries(PERSONAS).map(([key, persona]) => (
              <option value={key} key={key}>{persona.label}</option>
            ))}
          </select>
        </div>
      </header>

      {notice && <div className="dash-notice">{notice}</div>}

      <div className="dashboard-layout">
        <aside className="dashboard-sidebar">
          <nav aria-label="Dashboard sections">
            {TABS.map((tab) => {
              const Icon = tab.icon;
              return (
                <button className={activeTab === tab.id ? "active" : ""} type="button" onClick={() => setActiveTab(tab.id)} key={tab.id}>
                  <Icon size={17} />
                  <span>{tab.label}</span>
                </button>
              );
            })}
          </nav>
          <div className="sidebar-context">
            <span>Active Persona</span>
            <strong>{PERSONAS[activeRole]?.label}</strong>
          </div>
        </aside>

        <div className="dashboard-main">
          <TabGuide activeTab={activeTab} />

          {activeTab === "queue" && (
            <AuditQueue
              audits={filteredAudits}
              assignments={activeRole === "analyst" ? assignments : []}
              counts={counts}
              filter={filter}
              loading={loadingHistory}
              onFilter={setFilter}
              onResolveAssignment={resolveAssignment}
              onSelect={setSelectedAudit}
            />
          )}

          {activeTab === "new" && (
            <NewAuditWorkspace
              token={activeToken}
              latestAudit={latestAudit}
              onAuditComplete={addAudit}
              onNotice={setNotice}
            />
          )}

          {activeTab === "graph" && (
            <KnowledgeGraphWorkspace audits={audits} token={activeToken} />
          )}
        </div>
      </div>

      {selectedAudit && (
        <AuditDetailOverlay
          audit={selectedAudit}
          token={activeToken}
          role={activeRole}
          onAssignmentCreated={() => refreshAssignments()}
          onNotice={setNotice}
          onClose={() => setSelectedAudit(null)}
        />
      )}
    </main>
  );
}

function TabGuide({ activeTab }) {
  const guide = GUIDE_COPY[activeTab];
  return (
    <section className="tab-guide">
      <span className="eyebrow">How This Page Works</span>
      <h2>{guide.title}</h2>
      <p>{guide.text}</p>
    </section>
  );
}

function TelemetryPill({ telemetry }) {
  return (
    <div className={`telemetry-pill ${telemetry}`}>
      <Radio size={15} />
      {telemetry === "live" ? "TELEMETRY LIVE" : "RECONNECTING..."}
    </div>
  );
}

function AuditQueue({ audits, assignments, counts, filter, loading, onFilter, onResolveAssignment, onSelect }) {
  return (
    <section className="tab-page audit-queue-page">
      <div className="section-head">
        <div>
          <span className="eyebrow">Audit Queue</span>
          <h1>Transaction audit history</h1>
        </div>
        <div className="filter-pills" aria-label="Audit status filters">
          {FILTERS.map((item) => (
            <button className={filter === item.id ? "active" : ""} type="button" onClick={() => onFilter(item.id)} key={item.id}>
              {item.label} <span>({counts[item.id] || 0})</span>
            </button>
          ))}
        </div>
      </div>

      {assignments.length > 0 && (
        <AssignmentInbox assignments={assignments} onResolve={onResolveAssignment} />
      )}

      <div className="audit-table" role="table" aria-label="Audit records">
        <div className="audit-row audit-head" role="row">
          <span>Transaction ID</span>
          <span>Timestamp</span>
          <span>Persona</span>
          <span>Amount</span>
          <span>Allowed Ceiling</span>
          <span>Source Policy</span>
          <span>Status</span>
        </div>
        {loading ? (
          Array.from({ length: 7 }).map((_, index) => <div className="audit-row skeleton-row" key={index} />)
        ) : audits.length ? (
          audits.map((audit) => (
            <button className="audit-row" type="button" onClick={() => onSelect(audit)} key={`${audit.persona}-${audit.transactionId}`}>
              <span className="mono">{audit.transactionId}</span>
              <span>{formatDate(audit.timestamp)}</span>
              <span>{PERSONAS[audit.persona]?.label || audit.persona}</span>
              <span className="mono">{audit.amountLabel}</span>
              <span className="mono">{audit.ceilingLabel}</span>
              <span className="truncate" title={audit.source}>{audit.source}</span>
              <Status value={audit.status} />
            </button>
          ))
        ) : (
          <div className="empty-grid">No audit records available.</div>
        )}
      </div>
    </section>
  );
}

function AssignmentInbox({ assignments, onResolve }) {
  return (
    <section className="assignment-inbox" aria-label="Analyst assignments">
      <div>
        <span className="eyebrow">Assigned By L2</span>
        <h2>Open analyst follow-ups</h2>
      </div>
      <div className="assignment-list">
        {assignments.map((assignment) => (
          <div className={assignment.status === "OPEN" ? "" : "resolved"} key={assignment.id}>
            <span className="mono">{assignment.transaction_id}</span>
            <strong>{formatAssignmentAction(assignment.action_type)}</strong>
            <p>{assignment.note}</p>
            <button type="button" onClick={() => onResolve(assignment.id)} disabled={assignment.status !== "OPEN"}>
              {assignment.status === "OPEN" ? "Mark Resolved" : "Resolved"}
            </button>
          </div>
        ))}
      </div>
    </section>
  );
}

function NewAuditWorkspace({ token, latestAudit, onAuditComplete, onNotice }) {
  const [query, setQuery] = React.useState("");
  const [loading, setLoading] = React.useState(false);

  async function submitAudit(event) {
    event.preventDefault();
    const trimmed = query.trim();
    if (!trimmed || !token) return;

    setLoading(true);
    onNotice("");
    try {
      const result = await evaluateAudit(token, trimmed);
      onAuditComplete(result);
      setQuery("");
    } catch {
      onNotice("Audit evaluation failed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="tab-page new-audit-page">
      <form className="audit-workspace" onSubmit={submitAudit}>
        <div className="section-head">
          <div>
            <span className="eyebrow">New Audit</span>
            <h1>Multi-agent audit evaluator</h1>
          </div>
          <button type="submit" disabled={loading || !query.trim() || !token}>
            {loading ? <Loader2 className="spin" size={17} /> : <Zap size={17} />}
            Run Multi-Agent Audit
          </button>
        </div>
        <textarea
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Enter a transaction query for the compliance agents..."
          required
        />
        <div className="sample-queries" aria-label="Sample audit prompts">
          {SAMPLE_QUERIES.map((sample) => (
            <button type="button" onClick={() => setQuery(sample.query)} key={sample.label}>
              <span>{sample.label}</span>
              <em>{sample.outcome}</em>
            </button>
          ))}
        </div>
      </form>

      <div className="result-panel">
        {loading && <div className="result-placeholder"><Loader2 className="spin" size={18} /> Running audit...</div>}
        {!loading && latestAudit && <AuditResult audit={latestAudit} token={token} downloadLabel="Download Generated PDF Certificate" />}
        {!loading && !latestAudit && <div className="result-placeholder">Audit results will appear here.</div>}
      </div>
    </section>
  );
}

function AuditResult({ audit, token, downloadLabel }) {
  return (
    <div className="audit-result">
      <MetricStrip audit={audit} />
      <div className="markdown-verdict">{renderMarkdown(audit.verdict)}</div>
      <PdfDownloadButton audit={audit} token={token} label={downloadLabel} />
    </div>
  );
}

function AuditDetailOverlay({ audit, token, role, onAssignmentCreated, onNotice, onClose }) {
  return (
    <div className="detail-overlay" role="dialog" aria-modal="true" aria-label="Audit detail">
      <div className="detail-panel">
        <div className="detail-top">
          <div>
            <span className="eyebrow">Audit Detail</span>
            <h2>{audit.transactionId}</h2>
          </div>
          <button type="button" onClick={onClose} aria-label="Close detail">
            <X size={18} />
          </button>
        </div>
        <MetricStrip audit={audit} />
        <div className="detail-content">
          <section className="report-pane">
            <div className="markdown-verdict">{renderMarkdown(audit.verdict)}</div>
          </section>
          <aside className="citation-pane">
            <StructuredEvidence audit={audit} />
            <CitationList citations={audit.citations} />
          </aside>
        </div>
        <div className="detail-actions">
          {role === "officer" && (
            <AuthorityActions
              audit={audit}
              token={token}
              onAssignmentCreated={onAssignmentCreated}
              onNotice={onNotice}
            />
          )}
          <PdfDownloadButton audit={audit} token={token} label="Download PDF Certificate" />
        </div>
      </div>
    </div>
  );
}

function AuthorityActions({ audit, token, onAssignmentCreated, onNotice }) {
  const [loadingAction, setLoadingAction] = React.useState("");

  async function assign(actionType, note) {
    if (!token) return;
    setLoadingAction(actionType);
    try {
      await createAuditAssignment(token, audit.transactionId, {
        action_type: actionType,
        assignee_email: "analyst@compliancenexus.com",
        note,
      });
      onNotice("Assignment sent to Sarah Jenkins.");
      onAssignmentCreated();
    } catch {
      onNotice("Unable to create analyst assignment.");
    } finally {
      setLoadingAction("");
    }
  }

  return (
    <div className="authority-actions" aria-label="L2 risk officer actions">
      <button
        type="button"
        onClick={() => assign("APPROVE_EXCEPTION", "L2 approved an exception review. Confirm citation coverage and prepare the final evidence certificate.")}
        disabled={Boolean(loadingAction)}
      >
        {loadingAction === "APPROVE_EXCEPTION" ? "Sending..." : "Assign Exception Review"}
      </button>
      <button
        type="button"
        onClick={() => assign("BLOCK_REMITTANCE", "L2 blocked this remittance. Document the breach rationale and attach supporting source citations.")}
        disabled={Boolean(loadingAction)}
      >
        {loadingAction === "BLOCK_REMITTANCE" ? "Sending..." : "Assign Block Follow-Up"}
      </button>
      <button
        type="button"
        onClick={() => assign("REQUEST_EVIDENCE", "L2 requested more evidence. Re-check source pages and confirm the governing policy trail.")}
        disabled={Boolean(loadingAction)}
      >
        {loadingAction === "REQUEST_EVIDENCE" ? "Sending..." : "Request Evidence"}
      </button>
    </div>
  );
}

function MetricStrip({ audit }) {
  return (
    <div className="metric-strip">
      <div>
        <span>Transaction Value</span>
        <strong>{audit.amountLabel}</strong>
      </div>
      <div>
        <span>Allowed Ceiling</span>
        <strong>{audit.ceilingLabel}</strong>
      </div>
      <div>
        <span>Delta</span>
        <strong>{audit.ceiling > 0 ? formatMoney(audit.delta) : "UNRESOLVED"}</strong>
      </div>
      <div>
        <span>Status</span>
        <Status value={audit.status} />
      </div>
    </div>
  );
}

function CitationList({ citations }) {
  return (
    <div className="citation-list">
      <h3>Citations</h3>
      {citations.length ? (
        citations.map((citation, index) => (
          <div key={`${formatCitation(citation)}-${index}`}>
            <FileText size={15} />
            <span>{formatCitation(citation)}</span>
          </div>
        ))
      ) : (
        <p>No citations returned.</p>
      )}
    </div>
  );
}

function StructuredEvidence({ audit }) {
  const evidence = audit.selectedEvidence || [];
  const checks = audit.auditChecks || [];
  const rationale = audit.auditRationale || {};

  return (
    <div className="structured-evidence">
      <section>
        <h3>Audit Checks</h3>
        {checks.length ? checks.map((check, index) => (
          <div className="check-row" key={`${check.name}-${index}`}>
            <strong>{check.name || "Audit Check"}</strong>
            <span>{check.result || "REVIEW"}</span>
            <p>{check.actual || "No actual value recorded."}</p>
          </div>
        )) : <p>No audit checks returned.</p>}
      </section>
      <section>
        <h3>Selected Evidence</h3>
        {evidence.length ? evidence.slice(0, 4).map((item, index) => (
          <div className="evidence-card" key={`${item.source_document}-${item.page_number}-${index}`}>
            <strong>{item.source_document || "Evidence"}</strong>
            <span>Page {item.page_number || "unresolved"}</span>
            <p>{trimText(item.snippet || "", 280)}</p>
          </div>
        )) : <p>No selected evidence returned.</p>}
      </section>
      {rationale.recommended_action && (
        <section>
          <h3>Recommended Action</h3>
          <div className="action-chip">{rationale.recommended_action}</div>
        </section>
      )}
    </div>
  );
}

function PdfDownloadButton({ audit, token, label }) {
  const [loading, setLoading] = React.useState(false);

  async function downloadPdf() {
    if (!token) return;
    setLoading(true);
    try {
      const response = await fetch(getPdfUrl(audit.transactionId), { headers: { Authorization: `Bearer ${token}` } });
      if (!response.ok) throw new Error("PDF unavailable");
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `Compliance_Certificate_${audit.transactionId}.pdf`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } finally {
      setLoading(false);
    }
  }

  return (
    <button className="pdf-download" type="button" onClick={downloadPdf} disabled={loading || !token}>
      {loading ? <Loader2 className="spin" size={16} /> : <Download size={16} />}
      {label}
    </button>
  );
}

function KnowledgeGraphWorkspace({ audits, token }) {
  const [selectedId, setSelectedId] = React.useState("");
  const [topology, setTopology] = React.useState({ nodes: [], links: [] });
  const [loading, setLoading] = React.useState(false);

  React.useEffect(() => {
    if (!selectedId && audits.length) setSelectedId(audits[0].transactionId);
  }, [audits, selectedId]);

  React.useEffect(() => {
    if (!selectedId || !token) {
      setTopology({ nodes: [], links: [] });
      return undefined;
    }

    let ignore = false;
    setLoading(true);
    getAuditTopology(token, selectedId)
      .then((data) => {
        if (!ignore) setTopology(normalizeTopology(data));
      })
      .catch(() => {
        if (!ignore) setTopology({ nodes: [], links: [] });
      })
      .finally(() => {
        if (!ignore) setLoading(false);
      });

    return () => {
      ignore = true;
    };
  }, [selectedId, token]);

  return (
    <section className="graph-page">
      <div className="graph-toolbar">
        <div>
          <span className="eyebrow">Knowledge Graph</span>
          <h1>Transaction topology visualizer</h1>
        </div>
        <label>
          <span>Select Audit Transaction</span>
          <select value={selectedId} onChange={(event) => setSelectedId(event.target.value)}>
            {audits.map((audit) => (
              <option value={audit.transactionId} key={`${audit.persona}-${audit.transactionId}`}>
                {audit.transactionId}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="graph-canvas">
        {loading && <div className="graph-loading"><Loader2 className="spin" size={18} /> Loading graph...</div>}
        {!loading && topology.nodes.length === 0 && <div className="graph-loading">No topology available.</div>}
        <TopologyMap topology={topology} />
        <div className="graph-legend">
          <span><i className="entity" /> Corporate Entity</span>
          <span><i className="policy" /> Policy PDF</span>
          <span><i className="warning" /> Flagged Breach/Warning</span>
        </div>
      </div>
    </section>
  );
}

function TopologyMap({ topology }) {
  const positioned = positionTopology(topology);

  return (
    <svg className="topology-svg" viewBox="0 0 1200 620" role="img" aria-label="Transaction topology map">
      <defs>
        <radialGradient id="nodeGlow" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="rgba(215,168,75,0.22)" />
          <stop offset="100%" stopColor="rgba(215,168,75,0)" />
        </radialGradient>
      </defs>
      <circle cx="600" cy="310" r="230" className="topology-orbit" />
      <circle cx="600" cy="310" r="150" className="topology-orbit muted" />
      {positioned.links.map((link, index) => (
        <g key={`${link.source}-${link.target}-${index}`}>
          <path
            className={`topology-link ${linkColorClass(link)}`}
            d={`M ${link.sourceNode.x} ${link.sourceNode.y} C 600 310, 600 310, ${link.targetNode.x} ${link.targetNode.y}`}
          />
          <text className="topology-link-label">
            <textPath href={`#link-path-${index}`} startOffset="52%">{link.label}</textPath>
          </text>
          <path
            id={`link-path-${index}`}
            d={`M ${link.sourceNode.x} ${link.sourceNode.y} C 600 310, 600 310, ${link.targetNode.x} ${link.targetNode.y}`}
            fill="none"
            stroke="none"
          />
        </g>
      ))}
      {positioned.nodes.map((node) => (
        <g className="topology-node" transform={`translate(${node.x} ${node.y})`} key={node.id}>
          <circle r="42" className="node-halo" />
          <circle r="20" style={{ "--node-color": nodeColor(node) }} />
          <text y="48">{shortLabel(node.id)}</text>
          <text y="66" className="node-type">{node.group}</text>
        </g>
      ))}
    </svg>
  );
}

function normalizeAudit(record, persona) {
  const amount = Number(record.transaction_value ?? record.amount ?? 0);
  const ceiling = Number(record.allowed_ceiling ?? record.ceiling ?? 0);
  const transactionId = String(record.transaction_id || record.id || "");

  return {
    id: record.id || transactionId,
    persona,
    transactionId,
    timestamp: record.created_at || record.timestamp || "",
    query: record.query || "",
    amount,
    ceiling,
    amountLabel: formatMoney(amount),
    ceilingLabel: ceiling > 0 ? formatMoney(ceiling) : "UNRESOLVED",
    source: record.source_doc || record.source || "N/A",
    status: normalizeStatus(record.status),
    citations: parseCitations(record.citations ?? record.citations_json),
    selectedEvidence: parseCitations(record.selected_evidence_items ?? record.selected_evidence_json),
    auditChecks: parseCitations(record.audit_checks ?? record.audit_checks_json),
    auditRationale: parseObject(record.audit_rationale ?? record.audit_rationale_json),
    verdict: record.audit_verdict_markdown || "",
    delta: amount - ceiling,
  };
}

function normalizeStatus(value) {
  const status = String(value || "ACTION_REQUIRED").toUpperCase();
  if (status === "NON COMPLIANT") return "NON_COMPLIANT";
  if (status === "ACTION REQUIRED") return "ACTION_REQUIRED";
  return status;
}

function parseCitations(value) {
  if (!value) return [];
  if (Array.isArray(value)) return value;
  try {
    const parsed = JSON.parse(value);
    return Array.isArray(parsed) ? parsed : [parsed];
  } catch {
    return [value];
  }
}

function parseObject(value) {
  if (!value) return {};
  if (typeof value === "object" && !Array.isArray(value)) return value;
  try {
    const parsed = JSON.parse(value);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : {};
  } catch {
    return {};
  }
}

function trimText(value, maxLength) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  return text.length > maxLength ? `${text.slice(0, maxLength - 3)}...` : text;
}

function dedupeAudits(records) {
  const seen = new Set();
  return records
    .filter((record) => {
      const key = `${record.persona}-${record.transactionId}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
}

function countByStatus(records) {
  return records.reduce(
    (counts, audit) => {
      counts.ALL += 1;
      counts[audit.status] = (counts[audit.status] || 0) + 1;
      return counts;
    },
    { ALL: 0, COMPLIANT: 0, NON_COMPLIANT: 0, ACTION_REQUIRED: 0 }
  );
}

function normalizeTopology(data) {
  return {
    nodes: (data?.nodes || []).map((node) => ({
      ...node,
      id: String(node.id),
      group: String(node.group || "CORPORATE_ENTITY"),
    })),
    links: (data?.edges || data?.links || []).map((edge) => ({
      ...edge,
      source: String(edge.source),
      target: String(edge.target),
      label: edge.label || edge.relation || "CONNECTED_TO",
    })),
  };
}

function positionTopology(topology) {
  const nodes = topology.nodes || [];
  const links = topology.links || [];
  const center = { x: 600, y: 310 };
  const radius = nodes.length > 8 ? 245 : 210;
  const indexed = nodes.map((node, index) => {
    const isCore = index === 0 || String(node.id).toLowerCase().includes("nexus india");
    if (isCore) return { ...node, x: center.x, y: center.y };
    const angle = -Math.PI / 2 + ((index - 1) / Math.max(nodes.length - 1, 1)) * Math.PI * 2;
    return {
      ...node,
      x: center.x + Math.cos(angle) * radius,
      y: center.y + Math.sin(angle) * radius * 0.72,
    };
  });
  const byId = new Map(indexed.map((node) => [node.id, node]));

  return {
    nodes: indexed,
    links: links
      .map((link) => ({
        ...link,
        sourceNode: byId.get(String(link.source)),
        targetNode: byId.get(String(link.target)),
      }))
      .filter((link) => link.sourceNode && link.targetNode),
  };
}

function shortLabel(value) {
  const label = String(value || "");
  return label.length > 22 ? `${label.slice(0, 19)}...` : label;
}

function linkColorClass(link) {
  const label = String(link.label || "").toLowerCase();
  if (label.includes("breach") || label.includes("flag") || label.includes("violate")) return "red";
  if (label.includes("compliant") || label.includes("approved")) return "green";
  return "amber";
}

function nodeColor(node) {
  const group = String(node.group || "").toLowerCase();
  const id = String(node.id || "").toLowerCase();
  if (group.includes("warning") || group.includes("action") || group.includes("breach") || id.includes("action_required")) return "#dc3f4d";
  if (group.includes("policy") || id.endsWith(".pdf") || id.includes("rbi")) return "#d7a84b";
  return "#4e9cff";
}

function renderMarkdown(markdown) {
  const lines = String(markdown || "").split("\n");
  const elements = [];
  let tableRows = [];
  let listItems = [];

  function flushTable() {
    if (!tableRows.length) return;
    const rows = tableRows.filter((row) => !/^\|\s*-/.test(row));
    elements.push(
      <table key={`table-${elements.length}`}>
        <tbody>
          {rows.map((row, index) => (
            <tr key={index}>
              {row.split("|").filter(Boolean).map((cell, cellIndex) => (
                <td key={cellIndex}>{stripMarkdown(cell.trim())}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    );
    tableRows = [];
  }

  function flushList() {
    if (!listItems.length) return;
    elements.push(<ul key={`list-${elements.length}`}>{listItems.map((item, index) => <li key={index}>{stripMarkdown(item)}</li>)}</ul>);
    listItems = [];
  }

  lines.forEach((line) => {
    if (!line.trim()) {
      flushTable();
      flushList();
      return;
    }
    if (line.startsWith("|")) {
      flushList();
      tableRows.push(line);
      return;
    }
    if (line.trim().startsWith("- ")) {
      flushTable();
      listItems.push(line.trim().replace(/^- /, ""));
      return;
    }
    flushTable();
    flushList();
    if (line.startsWith("##")) {
      elements.push(<h3 key={elements.length}>{stripMarkdown(line.replace(/^##\s*/, ""))}</h3>);
    } else {
      elements.push(<p key={elements.length}>{stripMarkdown(line)}</p>);
    }
  });

  flushTable();
  flushList();
  return elements.length ? elements : <p>No verdict returned.</p>;
}

function stripMarkdown(value) {
  return String(value).replace(/\*\*/g, "").replace(/`/g, "");
}

function formatCitation(citation) {
  if (typeof citation === "string") return citation;
  const source = citation.source || citation.document || citation.file || "Evidence";
  const page = citation.page ? `Page ${citation.page}` : "Page unresolved";
  const text = citation.text || citation.snippet || citation.quote || "";
  return text ? `${source} - ${page}: ${text}` : `${source} - ${page}`;
}

function formatMoney(value) {
  const numeric = Number(value || 0);
  return `${numeric < 0 ? "-" : ""}$${Math.abs(numeric).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

function formatDate(value) {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function formatAssignmentAction(value) {
  return String(value || "")
    .toLowerCase()
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}
