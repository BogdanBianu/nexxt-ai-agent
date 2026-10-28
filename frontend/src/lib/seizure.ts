// Ce face un sechestru asigurător diferit de o poprire: felul măsurii, termenii, plafonul. Proprietar: Om4.
// Felul măsurii vine din order.measure_type; pentru dosarele fără el îl deducem din textul actului
// (penalul primul, pentru că un act penal poate numi ANAF ca parte civilă).
import type { Case, CaseSummary } from "../types/contracts";
import { moduleOf } from "./modules";

export type SeizureKind = "FISCAL" | "CIVIL" | "PENAL";

export interface SeizureTerms {
  label: string;
  issuer: string;
  basis: string;
  debtor: string;
  creditor: string;
  principal: string;
  costs: string;
}

export const SEIZURE: Record<SeizureKind, SeizureTerms> = {
  FISCAL: {
    label: "Sechestru fiscal",
    issuer: "ANAF",
    basis: "Art. 213 Cod procedură fiscală",
    debtor: "Contribuabil",
    creditor: "Autoritate beneficiară",
    principal: "Obligații fiscale estimate",
    costs: "Accesorii estimate",
  },
  CIVIL: {
    label: "Sechestru civil",
    issuer: "Instanță",
    basis: "Art. 952–959 Cod procedură civilă",
    debtor: "Debitor pârât",
    creditor: "Creditor reclamant",
    principal: "Creanță garantată",
    costs: "Cheltuieli judiciare",
  },
  PENAL: {
    label: "Sechestru penal",
    issuer: "Parchet, ANABI",
    basis: "Art. 249–254 Cod procedură penală",
    debtor: "Inculpat",
    creditor: "Parte civilă",
    principal: "Prejudiciu estimat",
    costs: "Cheltuieli judiciare",
  },
};

const plain = (s: string) => s.normalize("NFD").replace(/\p{M}/gu, "").toUpperCase();

const PENAL = /PARCHET|PROCUROR|ANABI|PROCEDURA PENALA|INCULPAT/;
const FISCAL = /PROCEDURA FISCALA|FORMULAR 504|ANTIFRAUDA|DGAF|DGAMC/;

const MEASURE: Record<string, SeizureKind> = {
  SECHESTRU_ASIGURATOR_FISCAL: "FISCAL",
  SECHESTRU_ASIGURATOR_CIVIL: "CIVIL",
  SECHESTRU_ASIGURATOR_PENAL: "PENAL",
};

export function seizureKind(c: Pick<Case, "order" | "document">): SeizureKind {
  const declared = c.order?.measure_type ? MEASURE[c.order.measure_type] : undefined;
  if (declared) return declared;
  const t = plain(c.document?.text ?? "");
  if (c.order?.issuer_type === "PARCHET" || PENAL.test(t)) return "PENAL";
  if (c.order?.issuer_type === "ANAF" || FISCAL.test(t)) return "FISCAL";
  return "CIVIL";
}

export const isSeizure = (c: Pick<CaseSummary, "module_id">) => moduleOf(c) === "sechestre";
export const isLifting = (c: Pick<CaseSummary, "doc_type">) => c.doc_type === "SECHESTRU_RIDICARE" || c.doc_type === "POPRIRE_SISTARE";

// Cât din plafon a fost acoperit de sumele înghețate (0..1)
export function coverage(frozen: number | null | undefined, cap: number | null | undefined) {
  if (!cap || frozen == null) return null;
  return Math.min(1, frozen / cap);
}
