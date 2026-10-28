// Helpers vizuale comune (formatare, statusuri, categorii). Proprietar: Om4.
// Paleta e galben / negru / alb: în barele de disecție negru = bani opriți, galben = bani protejați.
import type { AgentName, CaseStatus, DocType, IncomeCategory } from "../types/contracts";

const ron = new Intl.NumberFormat("ro-RO", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
export const formatRon = (n: number | null | undefined) => (n == null ? "—" : `${ron.format(n)} lei`);
export const formatNumber = (n: number) => ron.format(n);

export const formatDate = (iso: string | null | undefined) =>
  iso ? new Date(iso).toLocaleDateString("ro-RO", { day: "2-digit", month: "short" }) : "—";

export const formatTime = (iso: string) =>
  new Date(iso).toLocaleTimeString("ro-RO", { hour: "2-digit", minute: "2-digit", second: "2-digit" });

export type StatusTone = "done" | "danger" | "neutral" | "working";

export const STATUS_STYLE: Record<CaseStatus, { label: string; tone: StatusTone }> = {
  RECEIVED: { label: "Primit", tone: "neutral" },
  PROCESSING: { label: "În procesare", tone: "working" },
  AUTO_PROCESSED: { label: "Procesat automat", tone: "done" },
  EXCEPTION_FLAGGED: { label: "Necesită verificare", tone: "danger" },
  LIFTED: { label: "Poprire ridicată", tone: "neutral" },
  ROUTED_TO_OTHER_MODULE: { label: "Redirecționat", tone: "neutral" },
  FAILED: { label: "Eșuat", tone: "danger" },
};

export type CategoryGroup = "PROTECTED" | "PARTIAL" | "FULL";

export const CATEGORY_GROUP: Record<IncomeCategory, CategoryGroup> = {
  ALOCATIE: "PROTECTED",
  INDEMNIZATIE_COPIL: "PROTECTED",
  DIURNA: "PROTECTED",
  AJUTOR_SOCIAL: "PROTECTED",
  SALARIU: "PARTIAL",
  PENSIE: "PARTIAL",
  INDEMNIZATIE_BOALA: "PARTIAL",
  ALT_VENIT: "FULL",
  SOLD_ANTERIOR: "FULL",
};

export const GROUP_LABEL: Record<CategoryGroup, string> = {
  PROTECTED: "Protejat de lege",
  PARTIAL: "Se oprește o cotă",
  FULL: "Se oprește integral",
};

export const CATEGORY_LABEL: Record<IncomeCategory, string> = {
  SALARIU: "Salariu",
  PENSIE: "Pensie",
  ALOCATIE: "Alocație",
  INDEMNIZATIE_COPIL: "Indemnizație copil",
  DIURNA: "Diurnă",
  AJUTOR_SOCIAL: "Ajutor social",
  INDEMNIZATIE_BOALA: "Indemnizație boală",
  ALT_VENIT: "Alt venit",
  SOLD_ANTERIOR: "Sold anterior",
};

export const PIPELINE: { agent: AgentName; label: string; hint: string }[] = [
  { agent: "INTAKE_ROUTER", label: "Primire", hint: "Ce fel de document e" },
  { agent: "EXTRACTION", label: "Extragere", hint: "Dosar, debitor, sumă" },
  { agent: "RECONCILIATION", label: "Identificare", hint: "Clientul în Core Banking" },
  { agent: "INCOME_CLASSIFIER", label: "Venituri", hint: "Natura fiecărei încasări" },
  { agent: "RULE_ENGINE", label: "Calcul legal", hint: "Art. 729 CPC" },
  { agent: "ANOMALY", label: "Anomalii", hint: "Tentative de eludare" },
  { agent: "OUTCOME", label: "Rezultat", hint: "Răspuns către executor" },
];

export const DOC_LABEL: Record<DocType, string> = {
  POPRIRE_INFIINTARE: "Înființare poprire",
  POPRIRE_SISTARE: "Sistare poprire",
  POPRIRE_MODIFICARE: "Modificare poprire",
  CERERE_INFORMATII: "Cerere informații",
  CERERE_AUTORITATE: "Cerere autoritate",
  CERERE_GDPR: "Cerere GDPR",
  NECUNOSCUT: "Necunoscut",
};

export const formatDateTime = (iso: string) =>
  new Date(iso).toLocaleString("ro-RO", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });

// Numele pe înțeles ale codurilor de excepție (backend/app/contracts/enums.py)
export const EXCEPTION_LABEL: Record<string, string> = {
  E01: "Debitor neidentificat",
  E02: "Dosar duplicat",
  E03: "Venit cu natură neclară",
  E04: "Popriri concurente",
  E05: "Document invalid",
  E06: "Suspiciune de eludare",
  E07: "Sistare fără poprire",
  E08: "Statut special al clientului",
  E09: "Cont de consemnare suspect",
};

// „acum 12 min”, „acum 3 h”, apoi data
export function formatAgo(iso: string, now = Date.now()) {
  const min = Math.floor((now - new Date(iso).getTime()) / 60000);
  if (min < 1) return "chiar acum";
  if (min < 60) return `acum ${min} min`;
  const h = Math.floor(min / 60);
  if (h < 24) return `acum ${h} h`;
  return formatDate(iso);
}

export function dayLabel(iso: string, now = new Date()) {
  const d = new Date(iso);
  const days = Math.round((new Date(now.toDateString()).getTime() - new Date(d.toDateString()).getTime()) / 86400000);
  const date = d.toLocaleDateString("ro-RO", { day: "numeric", month: "long" });
  if (days === 0) return `Astăzi, ${date}`;
  if (days === 1) return `Ieri, ${date}`;
  return d.toLocaleDateString("ro-RO", { weekday: "long", day: "numeric", month: "long" });
}
