import React from "react";
import {
  Download,
  FileText,
  Gauge,
  GitBranch,
  Loader2,
  Network,
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
  getAnalysts,
  getAssignmentInbox,
  getAssignmentOutbox,
  getAuditHistory,
  getAuditTopology,
  getLiveFeedUrl,
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
    label: "Ceiling breach",
    outcome: "Expected non-compliant",
    query: "Verify if a technology software licensing transaction of $1,800,000 USD initiated by Nexus India to an overseas vendor violates internal cross-border limits.",
  },
  {
    label: "Routine vendor payment",
    outcome: "Expected compliant",
    query: "Audit an outbound technology software fee remittance of $400,000 USD from Nexus India to an authorized overseas vendor under the single-transaction licensing ceiling.",
  },
  {
    label: "Beneficiary KYC gap",
    outcome: "Expected action required",
    query: "Review a $750,000 USD cross-border wire transfer from Nexus India to a newly onboarded overseas supplier where beneficiary KYC and originator information must be verified.",
  },
  {
    label: "Anonymous crypto wallet",
    outcome: "Expected action required",
    query: "Evaluate a cross-border cryptocurrency treasury transfer of $900,000 USD initiated by Nexus Global to an anonymous offshore digital wallet with no verified beneficiary identity.",
  },
];

const FILTERS = [
  { id: "ALL", label: "All" },
  { id: "COMPLIANT", label: "Compliant" },
  { id: "NON_COMPLIANT", label: "Non-Compliant" },
  { id: "ACTION_REQUIRED", label: "Action Required" },
];

const AUDIT_CACHE_KEY = "compliance-nexus.audit-cache";
const AUDIT_RUN_KEY = "compliance-nexus.active-audit-run";
const AUDIT_RUN_TTL_MS = 12 * 60 * 1000;

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
  const [activeAuditRun, setActiveAuditRun] = React.useState(readActiveAuditRun);
  const [graphAuditId, setGraphAuditId] = React.useState("");
  const [assignments, setAssignments] = React.useState([]);
  const [officerAssignments, setOfficerAssignments] = React.useState([]);
  const [analysts, setAnalysts] = React.useState([]);
  const [notice, setNotice] = React.useState("");

  const activeToken = tokens[activeRole] || "";

  const loadAuditHistories = React.useCallback(async () => {
    const results = await Promise.all(
      Object.keys(PERSONAS).map(async (persona) => {
        const auth = await authenticateDemo(persona);
        const history = await getAuditHistory(auth.access_token);
        return { persona, token: auth.access_token, history };
      })
    );
    const nextTokens = {};
    const merged = [];
    results.forEach((result) => {
      nextTokens[result.persona] = result.token;
      result.history.forEach((record) => merged.push(normalizeAudit(record, result.persona)));
    });
    const normalized = dedupeAudits(merged);
    setTokens(nextTokens);
    setAudits(normalized);
    writeCachedAudits(normalized);
    return normalized;
  }, []);

  React.useEffect(() => {
    let ignore = false;
    setLoadingHistory(true);
    setNotice("");

    const cached = readCachedAudits();
    if (cached.length) setAudits(cached);

    loadAuditHistories()
      .then(() => {
        if (ignore) return;
        setActiveAuditRun(null);
      })
      .catch(() => {
        if (!ignore) {
          setNotice(cached.length ? "Unable to refresh audit history. Showing last loaded records." : "Unable to load audit history from the configured API.");
          if (!cached.length) setAudits([]);
        }
      })
      .finally(() => {
        if (!ignore) setLoadingHistory(false);
      });

    return () => {
      ignore = true;
    };
  }, [loadAuditHistories]);

  React.useEffect(() => {
    if (activeAuditRun) {
      window.localStorage.setItem(AUDIT_RUN_KEY, JSON.stringify(activeAuditRun));
    } else {
      window.localStorage.removeItem(AUDIT_RUN_KEY);
    }
  }, [activeAuditRun]);

  React.useEffect(() => {
    if (!tokens.analyst) return;
    refreshAssignments(tokens.analyst);
  }, [tokens.analyst]);

  React.useEffect(() => {
    if (!tokens.officer) return;
    refreshOfficerAssignments(tokens.officer);
    getAnalysts(tokens.officer).then(setAnalysts).catch(() => setAnalysts([]));
  }, [tokens.officer]);

  React.useEffect(() => {
    let socket;
    let reconnectTimer;

    function connect() {
      socket = new WebSocket(getLiveFeedUrl());
      socket.onopen = () => setTelemetry("live");
      socket.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);
          if (message.event === "AUDIT_EVALUATION_COMPLETE") {
            setNotice(`Audit ${message.transaction_id} completed: ${normalizeStatus(message.status).replace("_", " ")}.`);
            setActiveAuditRun(null);
            loadAuditHistories().catch(() => {});
          }
          if (message.event === "AUDIT_EVALUATION_FAILED") {
            setNotice("Audit evaluation failed before a report could be saved.");
            setActiveAuditRun(null);
          }
        } catch {
          return;
        }
      };
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
    setAudits((current) => {
      const next = dedupeAudits([audit, ...current]);
      writeCachedAudits(next);
      return next;
    });
    setLatestAudit(audit);
    setFilter("ALL");
  }

  function openGraphForAudit(audit) {
    setGraphAuditId(audit.transactionId);
    setSelectedAudit(null);
    setActiveTab("graph");
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

  async function refreshOfficerAssignments(token = tokens.officer) {
    if (!token) return;
    try {
      const outbox = await getAssignmentOutbox(token);
      setOfficerAssignments(outbox);
    } catch {
      setOfficerAssignments([]);
    }
  }

  async function resolveAssignment(assignmentId, resolutionNote) {
    if (!tokens.analyst) return;
    try {
      await updateAssignment(tokens.analyst, assignmentId, { status: "RESOLVED", resolution_note: resolutionNote });
      setAssignments((current) => current.filter((item) => item.id !== assignmentId));
      setNotice("Follow-up submitted to Marcus.");
    } catch {
      setNotice("Unable to resolve assignment.");
    }
  }

  async function closeReturnedAssignment(assignmentId) {
    if (!tokens.officer) return;
    try {
      await updateAssignment(tokens.officer, assignmentId, { status: "CLOSED" });
      setOfficerAssignments((current) => current.filter((item) => item.id !== assignmentId));
      setNotice("Returned follow-up closed.");
    } catch {
      setNotice("Unable to close returned follow-up.");
    }
  }

  function openAuditDetail(audit) {
    setSelectedAudit(audit);
    if (tokens.officer) refreshOfficerAssignments(tokens.officer);
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

      {notice && (
        <div className="dash-notice">
          <span>{notice}</span>
          <button type="button" onClick={() => setNotice("")} aria-label="Dismiss notification">
            <X size={15} />
          </button>
        </div>
      )}

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
              returnedAssignments={activeRole === "officer" ? officerAssignments.filter((assignment) => assignment.status === "RESOLVED") : []}
              counts={counts}
              filter={filter}
              loading={loadingHistory}
              onFilter={setFilter}
              onResolveAssignment={resolveAssignment}
              onCloseReturnedAssignment={closeReturnedAssignment}
              onSelect={openAuditDetail}
            />
          )}

          {activeTab === "new" && (
            <NewAuditWorkspace
              token={activeToken}
              latestAudit={latestAudit}
              activeAuditRun={activeAuditRun}
              onAuditStart={setActiveAuditRun}
              onAuditComplete={addAudit}
              onNotice={setNotice}
            />
          )}

          {activeTab === "graph" && (
            <KnowledgeGraphWorkspace audits={audits} token={activeToken} selectedAuditId={graphAuditId} onSelectedAuditId={setGraphAuditId} activeAuditRun={activeAuditRun} />
          )}
        </div>
      </div>

      {selectedAudit && (
        <AuditDetailOverlay
          audit={selectedAudit}
          token={activeToken}
          role={activeRole}
          onAssignmentCreated={() => refreshAssignments()}
          onOfficerAssignmentsChanged={() => refreshOfficerAssignments()}
          followUps={officerAssignments.filter((assignment) => assignment.transaction_id === selectedAudit.transactionId)}
          analysts={analysts}
          onNotice={setNotice}
          onOpenGraph={openGraphForAudit}
          onCloseReturnedAssignment={closeReturnedAssignment}
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

function AuditQueue({ audits, assignments, returnedAssignments, counts, filter, loading, onFilter, onResolveAssignment, onCloseReturnedAssignment, onSelect }) {
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

      {returnedAssignments.length > 0 && (
        <ReturnedFollowUps assignments={returnedAssignments} onClose={onCloseReturnedAssignment} />
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
  const [resolutionNotes, setResolutionNotes] = React.useState({});

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
            <div className="assignment-resolution">
              <input
                value={resolutionNotes[assignment.id] || ""}
                onChange={(event) => setResolutionNotes((current) => ({ ...current, [assignment.id]: event.target.value }))}
                placeholder="Resolution note"
              />
              <button
                type="button"
                onClick={() => onResolve(assignment.id, resolutionNotes[assignment.id] || "")}
                disabled={!String(resolutionNotes[assignment.id] || "").trim()}
              >
                Submit
              </button>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function ReturnedFollowUps({ assignments, onClose }) {
  return (
    <section className="assignment-inbox returned-work" aria-label="Returned analyst work">
      <div>
        <span className="eyebrow">Returned From L1</span>
        <h2>Analyst follow-ups ready for Marcus</h2>
      </div>
      <div className="followup-list">
        {assignments.slice(0, 5).map((assignment) => (
          <article key={assignment.id} className="resolved">
            <div>
              <strong>{assignment.transaction_id} · {formatAssignmentAction(assignment.action_type)}</strong>
              <Status value={assignment.status} />
            </div>
            <p>{assignment.resolution_note || "No analyst response recorded."}</p>
            <div className="followup-footer">
              <small>{formatDate(assignment.resolved_at || assignment.created_at)}</small>
              <button type="button" onClick={() => onClose(assignment.id)}>Close</button>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function NewAuditWorkspace({ token, latestAudit, activeAuditRun, onAuditStart, onAuditComplete, onNotice }) {
  const [query, setQuery] = React.useState("");
  const loading = Boolean(activeAuditRun);

  async function submitAudit(event) {
    event.preventDefault();
    const trimmed = query.trim();
    if (!trimmed || !token || loading) return;

    onAuditStart({ query: trimmed, startedAt: Date.now() });
    onNotice("");
    try {
      const result = await evaluateAudit(token, trimmed);
      onAuditComplete(result);
      setQuery("");
    } catch {
      onNotice("Audit evaluation failed.");
    } finally {
      onAuditStart(null);
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
          <h2>Try audit scenarios</h2>
          {SAMPLE_QUERIES.map((sample) => (
            <button type="button" onClick={() => setQuery(sample.query)} disabled={loading} key={sample.label}>
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
      <StructuredAuditReport audit={audit} />
      <PdfDownloadButton audit={audit} token={token} label={downloadLabel} />
    </div>
  );
}

function AuditDetailOverlay({ audit, token, role, onAssignmentCreated, onOfficerAssignmentsChanged, followUps, analysts, onNotice, onOpenGraph, onCloseReturnedAssignment, onClose }) {
  return (
    <div className="detail-overlay" role="dialog" aria-modal="true" aria-label="Audit detail">
      <div className="detail-panel">
        <div className="detail-top">
          <div>
            <span className="eyebrow">Audit Detail</span>
            <h2>{audit.transactionId}</h2>
          </div>
          <div className="detail-top-actions">
            <button className="graph-jump" type="button" onClick={() => onOpenGraph(audit)}>
              <Network size={16} />
              Knowledge Graph
            </button>
            <PdfDownloadButton audit={audit} token={token} label="Download PDF" compact />
            <button className="detail-close" type="button" onClick={onClose} aria-label="Close detail">
              <X size={18} />
            </button>
          </div>
        </div>
        <MetricStrip audit={audit} />
        <StructuredAuditReport audit={audit} />
        {role === "officer" && (
          <section className="followup-compose">
            <div>
              <span className="eyebrow">Create L2 Follow-Up</span>
              <h3>Assign analyst work for this audit</h3>
            </div>
            <AuthorityActions
              audit={audit}
              token={token}
              analysts={analysts}
              onAssignmentCreated={onAssignmentCreated}
              onOfficerAssignmentsChanged={onOfficerAssignmentsChanged}
              onNotice={onNotice}
            />
          </section>
        )}
        {role === "officer" && <FollowUpHistory assignments={followUps} onClose={onCloseReturnedAssignment} />}
      </div>
    </div>
  );
}

function StructuredAuditReport({ audit }) {
  const checks = audit.auditChecks || [];
  const evidence = audit.selectedEvidence || [];
  const rationale = audit.auditRationale || {};
  const findings = Array.isArray(rationale.deficiency_findings) ? rationale.deficiency_findings : [];

  return (
    <section className="structured-report" aria-label="Audit report">
      <div className="report-section">
        <span className="report-index">1</span>
        <div>
          <h3>Official Compliance Verdict</h3>
          <Status value={audit.status} />
          <p>{rationale.executive_summary || firstParagraph(audit.verdict) || "No executive summary returned."}</p>
        </div>
      </div>

      <div className="report-section">
        <span className="report-index">2</span>
        <div>
          <h3>Transaction Facts</h3>
          <div className="facts-grid">
            <Fact label="Transaction ID" value={audit.transactionId} />
            <Fact label="Transaction Value" value={audit.amountLabel} />
            <Fact label="Allowed Ceiling" value={audit.ceilingLabel} />
            <Fact label="Delta" value={audit.ceiling > 0 ? formatMoney(audit.delta) : "UNRESOLVED"} />
            <Fact label="Primary Rule Source" value={audit.source} />
          </div>
        </div>
      </div>

      <div className="report-section">
        <span className="report-index">3</span>
        <div>
          <h3>Applicable Rule And Rationale</h3>
          <p>{rationale.rule_application_reasoning || "No rule application rationale recorded."}</p>
        </div>
      </div>

      <div className="report-section">
        <span className="report-index">4</span>
        <div>
          <h3>Deterministic Audit Checks</h3>
          <AuditCheckTable checks={checks} />
        </div>
      </div>

      <div className="report-section">
        <span className="report-index">5</span>
        <div>
          <h3>Primary Evidence Trail</h3>
          <EvidenceGrid evidence={evidence} />
        </div>
      </div>

      <div className="report-section">
        <span className="report-index">6</span>
        <div>
          <h3>Audit Rationale And Action</h3>
          <div className="finding-list">
            {findings.length ? findings.map((finding, index) => (
              <p key={`${finding}-${index}`}>{finding}</p>
            )) : <p>No deterministic compliance deficiency was identified.</p>}
          </div>
          <div className="action-chip">{rationale.recommended_action || "HUMAN_REVIEW"}</div>
        </div>
      </div>

      <div className="report-section">
        <span className="report-index">7</span>
        <div>
          <CitationList citations={audit.citations} />
        </div>
      </div>
    </section>
  );
}

function Fact({ label, value }) {
  return (
    <div>
      <span>{label}</span>
      <strong>{value || "N/A"}</strong>
    </div>
  );
}

function AuditCheckTable({ checks }) {
  if (!checks.length) return <p>No audit checks returned.</p>;

  return (
    <div className="audit-check-table" role="table" aria-label="Deterministic audit checks">
      <div className="check-table-row check-table-head" role="row">
        <span>Check</span>
        <span>Expected</span>
        <span>Actual</span>
        <span>Result</span>
        <span>Evidence</span>
      </div>
      {checks.map((check, index) => (
        <div className="check-table-row" role="row" key={`${check.name}-${index}`}>
          <span>{check.name || "Audit Check"}</span>
          <span>{check.expected || "N/A"}</span>
          <span>{check.actual || "N/A"}</span>
          <span><Status value={check.result || "REVIEW"} /></span>
          <span>{formatEvidenceRefs(check.evidence_items)}</span>
        </div>
      ))}
    </div>
  );
}

function EvidenceGrid({ evidence }) {
  if (!evidence.length) return <p>No selected evidence returned.</p>;

  return (
    <div className="evidence-grid">
      {evidence.slice(0, 6).map((item, index) => (
        <article key={`${item.source_document}-${item.page_number}-${index}`}>
          <strong>{item.source_document || "Evidence"}</strong>
          <span>Page {item.page_number || "unresolved"}</span>
          <p>{trimText(item.snippet || "", 260)}</p>
        </article>
      ))}
    </div>
  );
}

function FollowUpHistory({ assignments, onClose }) {
  return (
    <section className="followup-history">
      <div>
        <span className="eyebrow">L2 Follow-Up History</span>
        <h3>Review notes for this audit</h3>
      </div>
      {assignments.length ? (
        <div className="followup-list">
          {assignments.map((assignment) => (
            <article key={assignment.id} className={assignment.status === "OPEN" ? "" : "resolved"}>
              <div>
                <strong>{formatAssignmentAction(assignment.action_type)}</strong>
                <Status value={assignment.status} />
              </div>
              <p>{assignment.note}</p>
              {assignment.resolution_note && <p className="resolution-text">Analyst response: {assignment.resolution_note}</p>}
              <div className="followup-footer">
                <small>{formatDate(assignment.resolved_at || assignment.created_at)}</small>
                {assignment.status === "RESOLVED" && <button type="button" onClick={() => onClose(assignment.id)}>Close</button>}
              </div>
            </article>
          ))}
        </div>
      ) : (
        <p>No follow-ups created for this audit.</p>
      )}
    </section>
  );
}

function AuthorityActions({ audit, token, analysts, onAssignmentCreated, onOfficerAssignmentsChanged, onNotice }) {
  const [loadingAction, setLoadingAction] = React.useState("");
  const [assigneeEmail, setAssigneeEmail] = React.useState("analyst@compliancenexus.com");
  const [customNote, setCustomNote] = React.useState("");

  async function assign(actionType, note) {
    if (!token) return;
    setLoadingAction(actionType);
    try {
      await createAuditAssignment(token, audit.transactionId, {
        action_type: actionType,
        assignee_email: assigneeEmail,
        note: customNote.trim() || note,
      });
      onNotice("Follow-up assigned.");
      setCustomNote("");
      onAssignmentCreated();
      onOfficerAssignmentsChanged();
    } catch {
      onNotice("Unable to create analyst assignment.");
    } finally {
      setLoadingAction("");
    }
  }

  return (
    <div className="authority-actions" aria-label="L2 risk officer actions">
      <div className="authority-fields">
        <label>
          <span>Assign To</span>
          <select value={assigneeEmail} onChange={(event) => setAssigneeEmail(event.target.value)}>
            {(analysts.length ? analysts : [{ email: "analyst@compliancenexus.com", full_name: "Sarah Jenkins" }]).map((analyst) => (
              <option value={analyst.email} key={analyst.email}>{analyst.full_name || analyst.email}</option>
            ))}
          </select>
        </label>
        <textarea
          value={customNote}
          onChange={(event) => setCustomNote(event.target.value)}
          placeholder="Optional officer note for the analyst..."
        />
      </div>
      <div className="authority-buttons">
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
            {Array.isArray(check.evidence_items) && check.evidence_items.length > 0 && (
              <div className="check-evidence">
                {check.evidence_items.slice(0, 2).map((item, evidenceIndex) => (
                  <small key={`${item.source_document}-${item.page_number}-${evidenceIndex}`}>
                    {item.source_document || "Evidence"} p.{item.page_number || "N/A"}
                  </small>
                ))}
              </div>
            )}
          </div>
        )) : <p>No audit checks returned.</p>}
      </section>
      <section>
        <h3>Primary Evidence Trail</h3>
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

function PdfDownloadButton({ audit, token, label, compact = false }) {
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
    <button className={`pdf-download ${compact ? "compact" : ""}`} type="button" onClick={downloadPdf} disabled={loading || !token}>
      {loading ? <Loader2 className="spin" size={16} /> : <Download size={16} />}
      {label}
    </button>
  );
}

function KnowledgeGraphWorkspace({ audits, token, selectedAuditId, onSelectedAuditId, activeAuditRun }) {
  const [selectedId, setSelectedId] = React.useState(selectedAuditId || "");
  const [topology, setTopology] = React.useState({ nodes: [], links: [] });
  const [loading, setLoading] = React.useState(false);

  React.useEffect(() => {
    if (selectedAuditId) setSelectedId(selectedAuditId);
  }, [selectedAuditId]);

  React.useEffect(() => {
    if (!selectedId && audits.length) {
      setSelectedId(audits[0].transactionId);
      onSelectedAuditId(audits[0].transactionId);
    }
  }, [audits, selectedId]);

  React.useEffect(() => {
    if (!selectedId || !token) {
      setTopology({ nodes: [], links: [] });
      return undefined;
    }

    const controller = new AbortController();
    let ignore = false;
    setLoading(true);
    getAuditTopology(token, selectedId, controller.signal)
      .then((data) => {
        if (!ignore) setTopology(normalizeTopology(data));
      })
      .catch(() => {
        if (!ignore) setTopology((current) => current);
      })
      .finally(() => {
        if (!ignore) setLoading(false);
      });

    return () => {
      ignore = true;
      controller.abort();
    };
  }, [selectedId, token]);

  function selectTransaction(value) {
    setSelectedId(value);
    onSelectedAuditId(value);
  }

  return (
    <section className="graph-page">
      <div className="graph-toolbar">
        <div>
          <span className="eyebrow">Knowledge Graph</span>
          <h1>Transaction topology visualizer</h1>
        </div>
        <label>
          <span>Select Audit Transaction</span>
          <select value={selectedId} onChange={(event) => selectTransaction(event.target.value)}>
            {audits.map((audit) => (
              <option value={audit.transactionId} key={`${audit.persona}-${audit.transactionId}`}>
                {audit.transactionId}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="graph-canvas">
        {activeAuditRun && <div className="graph-busy-note">Audit generation is still running. Existing graph data remains available.</div>}
        {loading && <div className="graph-loading compact"><Loader2 className="spin" size={18} /> Loading graph...</div>}
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
    <svg className="topology-svg" viewBox="0 0 1500 760" role="img" aria-label="Transaction topology map">
      <defs>
        <radialGradient id="nodeGlow" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="rgba(215,168,75,0.12)" />
          <stop offset="100%" stopColor="rgba(215,168,75,0)" />
        </radialGradient>
      </defs>
      <circle cx="750" cy="380" r="300" className="topology-orbit" />
      <circle cx="750" cy="380" r="205" className="topology-orbit muted" />
      {positioned.links.map((link, index) => (
        <g key={`${link.source}-${link.target}-${index}`}>
          <path
            className={`topology-link ${linkColorClass(link)}`}
            d={`M ${link.sourceNode.x} ${link.sourceNode.y} C 750 380, 750 380, ${link.targetNode.x} ${link.targetNode.y}`}
          />
          <text className="topology-link-label" x={link.labelX} y={link.labelY}>{shortEdgeLabel(link.label)}</text>
        </g>
      ))}
      {positioned.nodes.map((node) => (
        <g className="topology-node" transform={`translate(${node.x} ${node.y})`} key={node.id}>
          <circle r="34" className="node-halo" />
          <circle r="18" style={{ "--node-color": nodeColor(node) }} />
          <rect className="node-label-bg" x={-(node.labelWidth || 240) / 2} y={(node.labelY || 52) - 28} width={node.labelWidth || 240} height="62" rx="6" />
          <text y={node.labelY || 52}>{shortLabel(node.id)}</text>
          <text y={(node.labelY || 52) + 19} className="node-type">{node.group}</text>
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
  const nodes = (topology.nodes || []).filter((node) => !isTransactionNode(node));
  const visibleNodeIds = new Set(nodes.map((node) => String(node.id)));
  const links = (topology.links || []).filter((link) => (
    visibleNodeIds.has(String(link.source)) && visibleNodeIds.has(String(link.target))
  ));
  const center = { x: 750, y: 380 };
  const radius = nodes.length > 8 ? 330 : 285;
  const outerNodes = nodes.filter((node) => !String(node.id).toLowerCase().includes("nexus india"));
  const indexed = nodes.map((node) => {
    const isCore = String(node.id).toLowerCase().includes("nexus india");
    if (isCore) return { ...node, x: center.x, y: center.y, labelY: 86, labelWidth: 270 };
    const outerIndex = outerNodes.findIndex((outerNode) => outerNode.id === node.id);
    const angle = -Math.PI / 2 + (outerIndex / Math.max(outerNodes.length, 1)) * Math.PI * 2;
    const x = center.x + Math.cos(angle) * radius;
    const y = center.y + Math.sin(angle) * radius * 0.76;
    return {
      ...node,
      x,
      y,
      labelY: y < center.y ? -72 : 78,
      labelWidth: labelWidthFor(node.id),
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
      .filter((link) => link.sourceNode && link.targetNode)
      .map((link, index) => {
        const sourceIsCore = Math.abs(link.sourceNode.x - center.x) < 8 && Math.abs(link.sourceNode.y - center.y) < 8;
        const targetIsCore = Math.abs(link.targetNode.x - center.x) < 8 && Math.abs(link.targetNode.y - center.y) < 8;
        const anchor = sourceIsCore ? 0.58 : targetIsCore ? 0.42 : 0.5;
        const baseX = link.sourceNode.x + (link.targetNode.x - link.sourceNode.x) * anchor;
        const baseY = link.sourceNode.y + (link.targetNode.y - link.sourceNode.y) * anchor;
        const labelX = baseX + (baseX < center.x ? -56 : 56);
        const labelY = baseY + ((index % 3) - 1) * 32;
        return { ...link, labelX, labelY };
      }),
  };
}

function shortLabel(value) {
  const label = String(value || "");
  return label.length > 28 ? `${label.slice(0, 25)}...` : label;
}

function isTransactionNode(node) {
  const group = String(node.group || "").toUpperCase();
  const id = String(node.id || "").toUpperCase();
  return group === "TRANSACTION" || /^TX_/.test(id);
}

function labelWidthFor(value) {
  const length = String(value || "").length;
  if (length > 24) return 350;
  if (length > 18) return 300;
  return 250;
}

function shortEdgeLabel(value) {
  const label = String(value || "CONNECTED_TO").replaceAll("_", " ");
  return label.length > 20 ? `${label.slice(0, 18)}...` : label;
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

function formatEvidenceRefs(items) {
  if (!Array.isArray(items) || !items.length) return "No evidence attached";
  return items
    .slice(0, 2)
    .map((item) => `${item.source_document || "Evidence"} p.${item.page_number || "N/A"}`)
    .join(", ");
}

function firstParagraph(markdown) {
  return String(markdown || "")
    .split("\n")
    .map((line) => stripMarkdown(line.trim()))
    .find((line) => line && !line.startsWith("#") && !line.startsWith("|") && !line.startsWith(":---")) || "";
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

function readCachedAudits() {
  try {
    const parsed = JSON.parse(window.localStorage.getItem(AUDIT_CACHE_KEY) || "[]");
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function writeCachedAudits(audits) {
  window.localStorage.setItem(AUDIT_CACHE_KEY, JSON.stringify(audits));
}

function readActiveAuditRun() {
  try {
    const parsed = JSON.parse(window.localStorage.getItem(AUDIT_RUN_KEY) || "null");
    if (!parsed?.startedAt || Date.now() - parsed.startedAt > AUDIT_RUN_TTL_MS) {
      window.localStorage.removeItem(AUDIT_RUN_KEY);
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}
