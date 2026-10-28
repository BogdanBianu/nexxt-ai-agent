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
  SECHESTRU_INSTITUIRE: "Instituire sechestru",
  SECHESTRU_RIDICARE: "Ridicare sechestru",
  NOTIFICARE_INSOLVENTA: "Notificare insolvență",
  CERTIFICAT_MOSTENITOR: "Certificat de moștenitor",
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

// ── Texte pe înțeles din mesajele brute ale backend-ului ────────────────────────────────
const METHOD_SHORT: Record<string, string> = {
  KEYWORD: "cuvânt-cheie",
  PAYER_REGISTRY: "registru plătitori",
  PATTERN: "tipar",
  LLM: "AI",
  HUMAN: "decizie ofițer",
  FALLBACK: "implicit",
  REGEX: "șabloane",
};

const MODULE_NAME: Record<string, string> = {
  popriri: "PopririZero",
  autoritati: "Cereri autorități",
  sechestre: "Sechestre asigurătorii",
  insolventa: "Insolvență și succesiuni",
  gdpr: "Cereri GDPR",
};

const SINGULAR: [RegExp, string][] = [
  [/\b1 conturi marcate\b/g, "1 cont marcat"],
  [/\b1 conturi active\b/g, "1 cont activ"],
  [/\b1 conturi\b/g, "1 cont"],
  [/\b1 popriri active\b/g, "1 poprire activă"],
  [/\b1 plăți\b/g, "1 plată"],
  [/\b1 popriri suspendate\b/g, "1 poprire suspendată"],
  [/\b1 încasări clasificate\b/g, "1 încasare clasificată"],
  [/\b1 solduri pozitive\b/g, "1 sold pozitiv"],
  [/\b1 anomalii găsite\b/g, "1 anomalie găsită"],
  [/\b1 excepții blocante\b/g, "1 excepție blocantă"],
];

// Traduce enum-urile, formatează sumele și corectează pluralul din mesajele agenților
export function humanize(msg: string | null | undefined): string {
  if (!msg) return "";
  let s = msg.replace(/(\d+(?:\.\d+)?)\s?RON\b/g, (_, n) => formatRon(Number(n)));
  s = s.replace(/→ ([a-z_]+) \(([^)]+)\)/g, (_, id, name) => `→ modulul ${name === "Roadmap" ? (MODULE_NAME[id] ?? id) : name}`);
  s = s.replace(/\b(KEYWORD|PAYER_REGISTRY|PATTERN|LLM|HUMAN|FALLBACK|REGEX)\b/g, (m) => METHOD_SHORT[m] ?? m);
  s = s.replace(/\b[A-Z][A-Z_]{3,}\b/g, (m) => {
    if (m in CATEGORY_LABEL) return CATEGORY_LABEL[m as IncomeCategory];
    if (m in DOC_LABEL) return DOC_LABEL[m as DocType];
    if (m in STATUS_STYLE) return STATUS_STYLE[m as CaseStatus].label;
    return m;
  });
  s = s.replace(/\((E0\d)\)/g, (m, code) => (EXCEPTION_LABEL[code] ? `(${EXCEPTION_LABEL[code]})` : m));
  s = s.replace(/: (VALID|INVALID)\b/g, (_, v) => `: ${v.toLowerCase()}`);
  for (const [re, rep] of SINGULAR) s = s.replace(re, rep);
  return s.replace(/ · /g, ", ");
}

// Titlul unui dosar: debitorul sau, pentru documente fără debitor (ex. cereri de la Poliție), emitentul
export function caseTitle(c: { order?: { debtor_name?: string | null; issuer_name?: string } | null; customer?: { full_name: string } | null; document?: { text?: string | null } }) {
  if (c.order?.debtor_name) return c.order.debtor_name;
  if (c.customer?.full_name) return c.customer.full_name;
  if (c.order?.issuer_name) return c.order.issuer_name;
  const first = c.document?.text?.split("\n").find((l) => l.trim());
  return first?.trim() ?? "Debitor neidentificat";
}
