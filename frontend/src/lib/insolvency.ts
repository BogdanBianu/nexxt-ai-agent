// Datele modulului „Insolvență și succesiuni” pe care contractul nu le are ca atare. Proprietar: Om4.
// Moștenitorii și popririle suspendate vin din regulile aplicate (R-SUC-02, R-INS-01); data deschiderii,
// data decesului și felul procedurii se citesc din textul documentului, ca în backend.
import type { Case } from "../types/contracts";

export const isSuccession = (c: Pick<Case, "doc_type">) => c.doc_type === "CERTIFICAT_MOSTENITOR";

const DATE = String.raw`(\d{2})\.(\d{2})\.(\d{4})`;

function dateIn(text: string, prefix: string) {
  const m = text.match(new RegExp(prefix + DATE, "i"));
  return m ? `${m[3]}-${m[2]}-${m[1]}` : null;
}

export const openingDate = (c: Case) => dateIn(c.document.text ?? "", String.raw`Data deschiderii procedurii:\s*`);
export const deathDate = (c: Case) => dateIn(c.document.text ?? "", String.raw`decedat(?:ă|a)?\s+(?:la|în|in)\s+(?:data\s+de\s+)?`);

export function procedure(c: Case) {
  const t = (c.document.text ?? "").toUpperCase();
  const bankruptcy = /FALIMENT|SIMPLIFICAT|LICHIDATOR/.test(t);
  return {
    bankruptcy,
    label: bankruptcy ? "Faliment" : "Insolvență",
    detail: bankruptcy ? "Procedură simplificată" : "Procedură generală",
    practitioner: bankruptcy ? "Lichidator judiciar" : "Administrator judiciar",
    // „cu acordul …”
    practitionerOf: bankruptcy ? "lichidatorului judiciar" : "administratorului judiciar",
  };
}

// „1/4”, „3/8”, „25%” -> 0.25
export function quotaValue(q: string) {
  const s = q.trim().replace(",", ".");
  if (s.endsWith("%")) return parseFloat(s) / 100;
  const [a, b] = s.split("/").map(Number);
  return b ? a / b : Number.NaN;
}

export interface Heir {
  name: string;
  cnp: string;
  relation: string | null;
  quota: string;
  share: number | null;
}

// Moștenitorii din certificat (cu relația de rudenie), completați cu suma calculată de R-SUC-02 când există
export function heirs(c: Case): Heir[] {
  const fromDoc = [...(c.document.text ?? "").matchAll(/^\s*\d+[.)]\s*([^,\n]+),\s*CNP:?\s*(\d+),\s*([^,\n]+?),\s*cot[ăa]\s*([\d/.,%]+)/gim)].map(
    (m) => ({ name: m[1].trim(), cnp: m[2], relation: m[3].trim(), quota: m[4] }),
  );
  const fromRules = (c.decision?.rules_applied ?? [])
    .filter((r) => r.rule_id === "R-SUC-02")
    .map((r) => {
      const m = r.description.match(/Moștenitor (.+?) \(CNP (\d+)\), cotă ([^.]+)\./);
      return m ? { name: m[1], cnp: m[2], quota: m[3], share: r.seizable_amount } : null;
    })
    .filter((x): x is NonNullable<typeof x> => !!x);

  if (fromRules.length)
    return fromRules.map((h) => ({ ...h, relation: fromDoc.find((d) => d.cnp === h.cnp)?.relation ?? null }));
  return fromDoc.map((d) => ({ ...d, share: null }));
}

export interface SuspendedGarnishment {
  caseNumber: string;
  creditor: string;
  remaining: number;
}

export function suspended(c: Case): SuspendedGarnishment[] {
  return (c.decision?.rules_applied ?? [])
    .filter((r) => r.rule_id === "R-INS-01")
    .map((r) => {
      const m = r.description.match(/Poprire suspendată: dosar (\S+) \((.+)\)\.?$/);
      return { caseNumber: m?.[1] ?? "—", creditor: m?.[2] ?? "—", remaining: r.base_amount };
    });
}

// Plățile după deschiderea procedurii / după deces, semnalate de agentul de anomalii
export const lateFlags = (c: Case) => c.exceptions.filter((e) => e.agent === "ANOMALY");
