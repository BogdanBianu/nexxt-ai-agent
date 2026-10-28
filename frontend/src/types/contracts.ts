// CONTRACTUL TYPESCRIPT AL PLATFORMEI LEXOPS — oglinda exactă a backend/app/contracts/
// Proprietari: Om4 & Om5. Orice modificare aici se face sincron cu backend/app/contracts/.

export type DocType =
  | "POPRIRE_INFIINTARE"
  | "POPRIRE_SISTARE"
  | "POPRIRE_MODIFICARE"
  | "CERERE_INFORMATII"
  | "CERERE_AUTORITATE"
  | "SECHESTRU_INSTITUIRE"
  | "SECHESTRU_RIDICARE"
  | "NOTIFICARE_INSOLVENTA"
  | "CERTIFICAT_MOSTENITOR"
  | "CERERE_GDPR"
  | "NECUNOSCUT";

export type IssuerType = "EXECUTOR" | "ANAF" | "ORGAN_FISCAL_LOCAL" | "POLITIE" | "PARCHET" | "ANSPDCP" | "PERSOANA_FIZICA" | "ALTUL";
export type CreditorType = "INTRETINERE" | "FISCAL" | "COMERCIAL";

export type IncomeCategory =
  | "SALARIU"
  | "PENSIE"
  | "ALOCATIE"
  | "INDEMNIZATIE_COPIL"
  | "DIURNA"
  | "AJUTOR_SOCIAL"
  | "INDEMNIZATIE_BOALA"
  | "ALT_VENIT"
  | "SOLD_ANTERIOR";

export type ClassificationMethod =
  | "HUMAN"
  | "KEYWORD"
  | "PAYER_REGISTRY"
  | "PATTERN"
  | "LLM"
  | "FALLBACK";

export type Severity = "BLOCKING" | "WARNING";
export type ExceptionCode = "E01" | "E02" | "E03" | "E04" | "E05" | "E06" | "E07" | "E08" | "E09";

export type CaseStatus =
  | "RECEIVED"
  | "PROCESSING"
  | "AUTO_PROCESSED"
  | "EXCEPTION_FLAGGED"
  | "LIFTED"
  | "ROUTED_TO_OTHER_MODULE"
  | "FAILED";

export type AgentName =
  | "INTAKE_ROUTER"
  | "EXTRACTION"
  | "RECONCILIATION"
  | "INCOME_CLASSIFIER"
  | "RULE_ENGINE"
  | "ANOMALY"
  | "OUTCOME";

export type AgentStatus = "STARTED" | "PROGRESS" | "COMPLETED" | "SKIPPED" | "FAILED";
export type ModuleStatus = "ACTIVE" | "ROADMAP";

export interface IncomingDocument {
  document_id: string;
  filename: string;
  received_at: string;
  content_type: string;
  text?: string | null;
  pdf_path?: string | null;
}

export interface GarnishmentOrder {
  doc_type: DocType;
  issuer_name: string;
  issuer_type: IssuerType;
  case_number?: string | null;
  issue_date?: string | null;
  debtor_name?: string | null;
  debtor_id?: string | null;
  creditor_name?: string | null;
  creditor_type: CreditorType;
  principal: number;
  enforcement_costs: number;
  total_due: number;
  consignment_iban?: string | null;
  has_signature_and_stamp: boolean;
  references_case_number?: string | null;
  // doar la sechestre: "SECHESTRU_ASIGURATOR_FISCAL" | "SECHESTRU_ASIGURATOR_CIVIL" | "SECHESTRU_ASIGURATOR_PENAL"
  measure_type?: string | null;
  legal_basis?: string | null;
  field_confidence: Record<string, number>;
  extraction_method: string;
}

export interface Customer {
  customer_id: string;
  full_name: string;
  national_id: string;
  is_legal_entity: boolean;
  status: "ACTIV" | "DECEDAT" | "INSOLVENTA";
  address?: string | null;
}

export interface Account {
  iban: string;
  customer_id: string;
  account_type: "CURENT" | "ECONOMII" | "DEPOZIT";
  currency: string;
  opening_balance: number;
  current_balance: number;
}

export interface ActiveGarnishment {
  garnishment_id: string;
  customer_id: string;
  case_number: string;
  issuer_name: string;
  creditor_name: string;
  creditor_type: CreditorType;
  total_due: number;
  amount_recovered: number;
  monthly_periodic_take: number;
  registered_at: string;
  active: boolean;
}

export interface ClassifiedTransaction {
  tx_id: string;
  iban: string;
  booking_date: string;
  amount: number;
  counterparty_name: string;
  description: string;
  category: IncomeCategory;
  method: ClassificationMethod;
  confidence: number;
  rationale: string;
  in_analysis_window: boolean;
}

export interface RuleApplication {
  rule_id: string;
  legal_source: string;
  description: string;
  base_amount: number;
  seizable_amount: number;
  tx_ids: string[];
}

export interface ExceptionFlag {
  code: ExceptionCode;
  severity: Severity;
  agent: AgentName;
  message: string;
  evidence: string[];
  resolved: boolean;
  resolution_note?: string | null;
}

export interface CreditorAllocation {
  case_number: string;
  creditor_name: string;
  creditor_type: CreditorType;
  amount: number;
}

export interface HoldInstruction {
  iban: string;
  amount: number;
  reference: string;
  beneficiary_iban?: string | null;
}

export interface GarnishmentDecision {
  periodic_income: number;
  seizable_periodic: number;
  seizable_other: number;
  exempt_total: number;
  amount_to_hold: number;
  amount_protected: number;
  total_due: number;
  rules_applied: RuleApplication[];
  allocations: CreditorAllocation[];
  hold_instructions: HoldInstruction[];
  rules_version: string;
}

export interface CaseOutcome {
  status: CaseStatus;
  summary: string;
  response_letter_text?: string | null;
  response_letter_pdf?: string | null;
}

export interface TxOverride {
  tx_id: string;
  category: IncomeCategory;
  note?: string | null;
}

export interface ReviewAction {
  reviewer: string;
  overrides: TxOverride[];
  resolve_codes: string[];
  note?: string | null;
  timestamp?: string | null;
}

export interface AgentEvent {
  case_id: string;
  seq: number;
  timestamp: string;
  agent: AgentName;
  status: AgentStatus;
  message: string;
  data: Record<string, unknown>;
}

export interface Case {
  case_id: string;
  module_id?: string | null;
  scenario_id?: string | null;
  status: CaseStatus;
  doc_type: DocType;
  created_at: string;
  updated_at: string;
  document: IncomingDocument;
  order?: GarnishmentOrder | null;
  customer?: Customer | null;
  accounts: Account[];
  active_garnishments: ActiveGarnishment[];
  classified_transactions: ClassifiedTransaction[];
  decision?: GarnishmentDecision | null;
  exceptions: ExceptionFlag[];
  outcome?: CaseOutcome | null;
  reviews: ReviewAction[];
  audit: AuditEntry[];
  llm_usage: LlmUsage;
}

// Telemetria AI a unui dosar, adunată peste toate rulările (inclusiv re-rulările HITL)
export interface LlmUsage {
  calls: number; // apeluri Bedrock facturate
  cache_hits: number; // răspunsuri din cache-ul pe disc (cost 0)
  failed_calls: number; // eșecuri -> fallback determinist
  input_tokens: number;
  output_tokens: number;
  latency_ms: number;
  cost_usd: number;
  cost_eur: number;
  cache_savings_usd: number;
  models: string[];
}

// GET /api/cases/{id}/audit — oglinda AuditEntry din backend/app/contracts
export interface AuditEntry {
  timestamp: string;
  actor: string; // numele agentului sau "user:<nume>"
  action: string;
  details: Record<string, unknown>;
}

export interface CaseSummary {
  case_id: string;
  scenario_id?: string | null;
  module_id?: string | null;
  doc_type: DocType;
  status: CaseStatus;
  debtor_name?: string | null;
  case_number?: string | null;
  amount_to_hold?: number | null;
  open_exceptions: number;
  created_at: string;
}

export interface ModuleInfo {
  module_id: string;
  name: string;
  description: string;
  status: ModuleStatus;
  handled_doc_types: DocType[];
}

export interface ScenarioInfo {
  scenario_id: string;
  title: string;
  description: string;
}

export interface RuleInfo {
  id: string;
  legal_source: string;
  description: string;
  categories: IncomeCategory[];
  creditor_types: CreditorType[];
  quota?: number | null;
  quota_if_creditor: Partial<Record<CreditorType, number>>;
}

// GET /api/rules
export interface RuleBookInfo {
  version: string;
  parameters: Record<string, unknown>;
  periodic_categories: IncomeCategory[];
  rules: RuleInfo[];
}

// GET /api/metrics
export interface PlatformMetrics {
  total_cases: number;
  cases_by_status: Record<string, number>;
  automation_rate: number;
  avg_processing_ms: number;
  total_amount_held: number;
  total_amount_protected: number;
  total_exempt: number;
  exceptions_by_code: Record<string, number>;
  reviews_count: number;
  ai: AiTelemetry;
}

// Blocul `ai` din GET /api/metrics: cost AI vs. cost manual (dashboard-ul Executive Impact)
export interface AiTelemetry {
  llm_calls: number;
  cache_hits: number;
  cache_hit_rate: number; // %
  failed_calls: number;
  input_tokens: number;
  output_tokens: number;
  total_llm_latency_ms: number;
  avg_llm_latency_ms: number;
  total_cost_usd: number;
  total_cost_eur: number;
  avg_cost_per_case_usd: number;
  avg_cost_per_case_eur: number;
  cache_savings_usd: number;
  manual_minutes_per_case: number;
  officer_hourly_cost_eur: number;
  manual_cost_per_case_eur: number;
  automated_cases: number; // închise fără om (AUTO_PROCESSED + LIFTED)
  officer_hours_saved: number;
  manual_cost_avoided_eur: number;
  net_savings_eur: number;
  roi_multiple: number | null; // null cât timp AI-ul a costat 0
  pricing: Record<string, number[]>; // USD / 1K tokeni [input, output]
}
