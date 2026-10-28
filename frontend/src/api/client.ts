// Client API minimal către FastAPI (http://localhost:8000). Proprietari: Om4 & Om5.
import type {
  AgentEvent,
  Case,
  CaseSummary,
  ModuleInfo,
  ReviewAction,
  ScenarioInfo,
} from "../types/contracts";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
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
