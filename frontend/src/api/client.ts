// Client API minimal către FastAPI (http://localhost:8000). Proprietari: Om4 & Om5.
import type {
  AgentEvent,
  AuditEntry,
  Case,
  CaseSummary,
  ModuleInfo,
  ReviewAction,
  ScenarioInfo,
} from "../types/contracts";

const PRIMARY_API = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";
const FALLBACK_API = "http://127.0.0.1:8765";
let activeApiBase = PRIMARY_API;

// Adresa serverului folosită acum (după un eventual fallback); afișată în starea „server oprit”
export const apiBase = () => activeApiBase;

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${activeApiBase}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...init,
    });
  } catch (err) {
    if (activeApiBase === PRIMARY_API) {
      res = await fetch(`${FALLBACK_API}${path}`, {
        headers: { "Content-Type": "application/json" },
        ...init,
      });
      activeApiBase = FALLBACK_API;
    } else {
      throw err;
    }
  }
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}: ${await res.text()}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  listModules: () => json<ModuleInfo[]>("/api/modules"),
  listScenarios: () => json<ScenarioInfo[]>("/api/scenarios"),
  listCases: () => json<CaseSummary[]>("/api/cases"),
  getCase: (caseId: string) => json<Case>(`/api/cases/${caseId}`),
  getCaseEvents: (caseId: string) => json<AgentEvent[]>(`/api/cases/${caseId}/events`),
  getCaseAudit: (caseId: string) => json<AuditEntry[]>(`/api/cases/${caseId}/audit`),
  responsePdfUrl: (caseId: string) => `${activeApiBase}/api/cases/${caseId}/response-pdf`,
  createFromScenario: (scenarioId: string) =>
    json<Case>("/api/cases/from-scenario", {
      method: "POST",
      body: JSON.stringify({ scenario_id: scenarioId }),
    }),
  submitReview: (caseId: string, review: ReviewAction) =>
    json<Case>(`/api/cases/${caseId}/review`, {
      method: "POST",
      body: JSON.stringify(review),
    }),
};

// POST /api/cases/upload (multipart): fără Content-Type explicit, browserul pune boundary-ul singur
export async function uploadDocument(file: File, scenarioId: string): Promise<Case> {
  const form = new FormData();
  form.append("file", file);
  form.append("scenario_id", scenarioId);
  const res = await fetch(`${activeApiBase}/api/cases/upload`, { method: "POST", body: form });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      // răspunsul nu e JSON; păstrăm codul HTTP
    }
    throw new Error(detail);
  }
  return res.json() as Promise<Case>;
}
