// Antetul dosarului deschis: titlu + alertă, cifrele cheie și fișa dosarului. Proprietar: Om4.
import type { ReactNode } from "react";
import { ArrowDown, ArrowLeft, CircleCheck, Info, OctagonAlert, TriangleAlert } from "lucide-react";
import type { Case, CreditorType } from "../types/contracts";
import { caseTitle, DOC_LABEL, formatDate, formatRon, humanize, STATUS_STYLE } from "../lib/ui";

const MODULE_LABEL: Record<string, string> = {
  autoritati: "Cereri autorități",
  sechestre: "Sechestre asigurătorii",
  insolventa: "Insolvență și succesiuni",
  gdpr: "Cereri GDPR",
};
import { StatusChip } from "./StatusChip";
import { statusLabel } from "../lib/modules";
import { isSeizure } from "../lib/seizure";
import { SeizureKindLine } from "./SeizurePanels";
import { AuthorityKindLine } from "./AuthorityPanels";
import { InsolvencyKindLine } from "./InsolvencyPanels";

const CREDITOR_LABEL: Record<CreditorType, string> = {
  INTRETINERE: "Pensie de întreținere",
  FISCAL: "Creanță fiscală",
  COMERCIAL: "Creanță comercială",
};

interface Props {
  data: Case;
  // true cât timp agenții încă rulează: statusul, alerta și sumele nu se arată încă
  pending: boolean;
  onBack: () => void;
  // Mesaj de confirmare după o decizie a ofițerului
  notice?: string | null;
}

export function CaseHeader({ data, pending, onBack, notice }: Props) {
  const open = pending ? [] : data.exceptions.filter((e) => !e.resolved);
  // Doar atenționări: agenții au terminat, dar ofițerul trebuie să știe (ex. plăți după deschiderea insolvenței)
  const stopped = STATUS_STYLE[data.status].tone === "danger";

  return (
    <div className="pt-6">
      <button onClick={onBack} className="inline-flex items-center gap-1.5 text-sm font-medium text-muted hover:text-ink">
        <ArrowLeft size={16} aria-hidden />
        Toate dosarele
      </button>

      <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-3">
        <h1 className="display text-[2rem]">{caseTitle(data)}</h1>
        {!pending && <StatusChip status={data.status} label={statusLabel(data)} />}
      </div>
      {isSeizure(data) && <SeizureKindLine data={data} />}
      {data.module_id === "autoritati" && <AuthorityKindLine data={data} />}
      {data.module_id === "insolventa" && <InsolvencyKindLine data={data} />}

      {notice && !pending && (
        <div role="status" className="mt-5 flex items-center gap-3 rounded-md border border-ink/20 bg-sun-soft px-5 py-3.5 text-sm">
          <CircleCheck size={18} className="shrink-0" aria-hidden />
          <span className="font-semibold">{notice}</span>
        </div>
      )}

      {!pending && data.status === "ROUTED_TO_OTHER_MODULE" && (
        <div role="status" className="mt-5 flex gap-3.5 rounded-md border border-line-strong bg-canvas px-5 py-4 text-sm">
          <Info size={20} className="mt-px shrink-0" aria-hidden />
          <div>
            <p className="font-bold">Documentul nu este o poprire</p>
            <p className="mt-1">
              Agentul de primire l-a clasificat ca {DOC_LABEL[data.doc_type].toLowerCase()} și l-a redirecționat către{" "}
              {data.module_id && MODULE_LABEL[data.module_id] ? `modulul ${MODULE_LABEL[data.module_id]}` : "alt modul"}, aflat încă în dezvoltare.
              PopririZero nu blochează sume și nu răspunde la acest document.
            </p>
          </div>
        </div>
      )}

      {open.length > 0 && !stopped && (
        <div role="status" className="mt-5 flex gap-3.5 rounded-md border border-danger/40 bg-danger-soft px-5 py-4">
          <TriangleAlert size={20} strokeWidth={2.25} className="mt-0.5 shrink-0 text-danger" aria-hidden />
          <div className="min-w-0">
            <p className="font-bold text-danger-ink">
              {open.length === 1 ? "Procesat automat, cu o atenționare" : `Procesat automat, cu ${open.length} atenționări`}
            </p>
            <ul className="mt-1 space-y-1 text-sm">
              {open.map((e) => (
                <li key={e.code + e.message}>{humanize(e.message)}</li>
              ))}
            </ul>
            <p className="mt-2 text-sm text-danger-ink">Atenționările sunt incluse în răspuns; nu e nevoie de o decizie.</p>
          </div>
        </div>
      )}

      {open.length > 0 && stopped && (
        <div role="alert" className="mt-5 flex gap-3.5 rounded-md border border-danger/40 bg-danger-soft px-5 py-4">
          <OctagonAlert size={20} strokeWidth={2.25} className="mt-0.5 shrink-0 text-danger" aria-hidden />
          <div className="min-w-0">
            <p className="font-bold text-danger-ink">
              {open.length === 1 ? "Procesarea automată a fost oprită" : `Procesarea automată a fost oprită: ${open.length} probleme`}
            </p>
            <ul className="mt-1 space-y-1 text-sm">
              {open.map((e) => (
                <li key={e.code + e.message}>{humanize(e.message)}</li>
              ))}
            </ul>
            <p className="mt-2 text-sm font-semibold text-danger-ink">
              {isSeizure(data) ? "Nu s-a înghețat nicio sumă." : "Nu s-a blocat nicio sumă."} Un ofițer trebuie să verifice dosarul.
            </p>
          </div>
          <a
            href="#workbench"
            onClick={(ev) => {
              ev.preventDefault();
              document.getElementById("workbench")?.scrollIntoView({ behavior: "smooth", block: "start" });
            }}
            className="ml-auto inline-flex h-10 shrink-0 items-center gap-2 self-center rounded-md bg-danger px-4 text-sm font-semibold text-paper transition-[background-color,transform] duration-150 ease-out hover:bg-danger-ink active:scale-[0.97]"
          >
            Verifică acum
            <ArrowDown size={16} aria-hidden />
          </a>
        </div>
      )}
    </div>
  );
}

function Figure({ label, value, note, tone = "plain" }: { label: string; value: string; note?: string; tone?: "plain" | "hold" | "keep" }) {
  const swatch = tone === "hold" ? "bg-ink" : tone === "keep" ? "bg-sun ring-1 ring-ink/15" : "";
  return (
    <div className="rounded-lg bg-paper px-5 py-4 ring-1 ring-line">
      <dt className="flex items-center gap-2 text-sm text-muted">
        {swatch && <span className={`h-2.5 w-2.5 rounded-full ${swatch}`} aria-hidden />}
        {label}
      </dt>
      <dd className="display mt-1.5 text-2xl">{value}</dd>
      {note && <dd className="mt-1.5 text-xs text-muted">{note}</dd>}
    </div>
  );
}

export function CaseFigures({ data, pending }: { data: Case; pending: boolean }) {
  const d = data.decision;
  const show = !pending && d;
  const blocked = !pending && data.exceptions.some((e) => !e.resolved);
  return (
    <dl className="grid gap-3 sm:grid-cols-3">
      <Figure label="Total de recuperat" value={formatRon(data.order?.total_due)} />
      <Figure
        label="Se indisponibilizează"
        tone="hold"
        value={show ? formatRon(d.amount_to_hold) : "—"}
        note={pending ? "Se calculează…" : blocked ? "Nimic blocat până la verificare" : "Transferat în contul de consemnare"}
      />
      <Figure label="Rămâne clientului" tone="keep" value={show ? formatRon(d.amount_protected) : "—"} note={show ? "Protejat conform art. 729 CPC" : undefined} />
    </dl>
  );
}

function Fact({ label, children, wide = false }: { label: string; children: ReactNode; wide?: boolean }) {
  return (
    <div className={`min-w-0 ${wide ? "col-span-2" : ""}`}>
      <dt className="text-xs text-muted">{label}</dt>
      <dd className="mt-0.5 text-sm font-semibold break-words">{children ?? "—"}</dd>
    </div>
  );
}

export function CaseFacts({ data }: { data: Case }) {
  const o = data.order;
  return (
    <section aria-labelledby="facts-title" className="rounded-lg bg-paper ring-1 ring-line">
      <h2 id="facts-title" className="display border-b border-line px-5 py-3.5 text-base">
        Fișa dosarului
      </h2>
      <dl className="grid grid-cols-2 gap-x-6 gap-y-5 px-5 py-5 md:grid-cols-4">
        <Fact label="Număr dosar">{o?.case_number}</Fact>
        <Fact label="Data emiterii">{o?.issue_date ? formatDate(o.issue_date) : null}</Fact>
        <Fact label="Emitent" wide>
          {o?.issuer_name}
        </Fact>
        <Fact label="Creditor" wide>
          {o?.creditor_name}
        </Fact>
        <Fact label="Tip creanță">{o ? CREDITOR_LABEL[o.creditor_type] : null}</Fact>
        <Fact label="CNP debitor">{o?.debtor_id ? <span className="font-mono text-[13px] font-medium">{o.debtor_id}</span> : null}</Fact>
        <Fact label="Debit principal">{o ? formatRon(o.principal) : null}</Fact>
        <Fact label="Cheltuieli executare">{o ? formatRon(o.enforcement_costs) : null}</Fact>
      </dl>
    </section>
  );
}
