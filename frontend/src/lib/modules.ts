// Modulele LexOps văzute de ofițer: nume, texte de pagină, etichete. Proprietar: Om4.
// Agentul de primire decide singur modulul fiecărui document; aici doar îl numim.
import type { CaseSummary, ScenarioInfo } from "../types/contracts";
import { DOC_LABEL, STATUS_STYLE } from "./ui";

// Modulele unde agenții blochează bani; la celelalte coloana de sumă nu are sens
export const BLOCKS_MONEY = new Set(["popriri", "sechestre"]);

// Textele paginii fiecărui modul; un modul nou fără intrare aici primește textele generice
export interface ModuleCopy {
  title: string;
  simulate: string;
  empty: string;
  allClear: string;
}

const GENERIC: ModuleCopy = {
  title: "Dosare",
  simulate: "Simulează document",
  empty: "Niciun document primit",
  allClear: "Nimic de verificat. Toate documentele primite au fost procesate automat.",
};

const MODULE_COPY: Record<string, ModuleCopy> = {
  popriri: {
    title: "Popriri",
    simulate: "Simulează adresă",
    empty: "Nicio adresă de poprire primită",
    allClear: "Nimic de verificat. Toate popririle primite au fost procesate automat.",
  },
  autoritati: {
    title: "Cereri autorități",
    simulate: "Simulează cerere",
    empty: "Nicio cerere de la autorități primită",
    allClear: "Nimic de verificat. Toate cererile primite au primit răspuns automat.",
  },
  sechestre: {
    title: "Sechestre asigurătorii",
    simulate: "Simulează sechestru",
    empty: "Nicio măsură de sechestru primită",
    allClear: "Nimic de verificat. Toate sechestrele primite au fost instituite automat.",
  },
};

export const copyFor = (moduleId: string) => MODULE_COPY[moduleId] ?? GENERIC;

// Dosarele vechi, de dinainte de rutare, nu au modul: sunt popriri
export const moduleOf = (c: Pick<CaseSummary, "module_id">) => c.module_id ?? "popriri";

// Sechestrele folosesc tot tipurile POPRIRE_* din contracte; le numim după modul ca ofițerul să nu le confunde
export function typeLabel(c: Pick<CaseSummary, "module_id" | "doc_type">) {
  if (moduleOf(c) === "sechestre") return c.doc_type === "POPRIRE_SISTARE" ? "Ridicare sechestru" : "Instituire sechestru";
  return DOC_LABEL[c.doc_type];
}

export function statusLabel(c: Pick<CaseSummary, "module_id" | "status">) {
  if (c.status === "LIFTED" && moduleOf(c) === "sechestre") return "Sechestru ridicat";
  return STATUS_STYLE[c.status].label;
}

// Scenariile nu au câmp de modul; tipul se recunoaște după titlu
const SEIZURE = /sechestr/i;
const AUTHORITY = /poliți|parchet|dna|diicot|autorit/i;
export const scenarioModule = (s: ScenarioInfo) =>
  SEIZURE.test(s.title) ? "sechestre" : AUTHORITY.test(s.title) ? "autoritati" : "popriri";
