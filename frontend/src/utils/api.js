const API_BASE = "http://localhost:8000";

const demoCredentials = {
  analyst: { username: "analyst@compliancenexus.com", password: "analyst123" },
  officer: { username: "officer@compliancenexus.com", password: "officer123" },
};

export async function authenticateDemo(role) {
  const body = new URLSearchParams(demoCredentials[role] || demoCredentials.analyst);
  const response = await fetch(`${API_BASE}/api/v1/auth/token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });

  if (!response.ok) throw new Error("Demo authentication failed");
  return response.json();
}

export async function getAuditHistory(token) {
  const response = await fetch(`${API_BASE}/api/v1/audits/history`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) throw new Error("Audit history unavailable");
  return response.json();
}

export async function evaluateAudit(token, query) {
  const response = await fetch(`${API_BASE}/api/v1/audits/evaluate`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ query }),
  });
  if (!response.ok) throw new Error("Audit evaluation failed");
  return response.json();
}

export async function getAuditTopology(token, transactionId) {
  const response = await fetch(`${API_BASE}/api/v1/audits/topology/${transactionId}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) throw new Error("Topology unavailable");
  return response.json();
}

export async function createAuditAssignment(token, transactionId, payload) {
  const response = await fetch(`${API_BASE}/api/v1/audits/${transactionId}/assignments`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error("Assignment creation failed");
  return response.json();
}

export async function getAssignmentInbox(token) {
  const response = await fetch(`${API_BASE}/api/v1/audits/assignments/inbox`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) throw new Error("Assignment inbox unavailable");
  return response.json();
}

export async function updateAssignment(token, assignmentId, payload) {
  const response = await fetch(`${API_BASE}/api/v1/audits/assignments/${assignmentId}`, {
    method: "PATCH",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error("Assignment update failed");
  return response.json();
}

export function getPdfUrl(transactionId) {
  return `${API_BASE}/api/v1/audits/${transactionId}/pdf`;
}
