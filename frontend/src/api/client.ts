// Client API minimal către FastAPI (http://localhost:8000). Proprietari: Om4 & Om5.
import type {
  AgentEvent,
  Case,
  CaseSummary,
  ModuleInfo,
  ReviewAction,
  ScenarioInfo,
} from "../types/contracts";

const PRIMARY_API = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";
const FALLBACK_API = "http://127.0.0.1:8765";
let activeApiBase = PRIMARY_API;

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
