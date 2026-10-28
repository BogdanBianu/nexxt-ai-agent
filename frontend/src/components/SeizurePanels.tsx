// Panourile dosarului de sechestru asigurător, în locul celor de poprire. Proprietar: Om4.
// Diferențele față de poprire: plafon în loc de datorie, banii se îngheață în cont (nu se virează),
// felul măsurii (fiscal / civil / penal) schimbă termenii, iar măsura are un ciclu: instituire → ridicare.
import { useEffect, useState, type ReactNode } from "react";
import { ArrowRight, Lock, Scale } from "lucide-react";
import { api } from "../api/client";
import type { Case, CaseSummary } from "../types/contracts";
import { formatDate, formatRon } from "../lib/ui";
import { coverage, isLifting, isSeizure, SEIZURE, seizureKind } from "../lib/seizure";

// Rândul de sub titlu: felul măsurii, temeiul legal și emitentul
export function SeizureKindLine({ data }: { data: Case }) {
  const t = SEIZURE[seizureKind(data)];
  return (
    <p className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-sm">
      <span className="inline-flex items-center gap-1.5 rounded-md bg-ink px-2 py-1 text-xs font-bold text-sun">
        <Scale size={13} aria-hidden />
        {isLifting(data) ? `Ridicare ${t.label.toLowerCase()}` : t.label}
      </span>
      <span className="font-medium">{t.basis}</span>
      {data.order?.issuer_name && <span className="text-muted">emis de {data.order.issuer_name}</span>}
    </p>
  );
}

export function CoverageBar({ share, className = "" }: { share: number; className?: string }) {
  return (
    <div className={`flex h-2 overflow-hidden rounded-sm bg-canvas ring-1 ring-ink/10 ${className}`} aria-hidden>
      <div className="bg-ink" style={{ width: `${share * 100}%` }} />
    </div>
  );
}

function Figure({ label, value, note, icon }: { label: string; value: string; note?: string; icon?: ReactNode }) {
  return (
    <div className="px-5 py-4">
      <dt className="flex items-center gap-2 text-sm text-muted">
        {icon}
        {label}
      </dt>
      <dd className="display mt-1.5 text-2xl">{value}</dd>
      {note && <dd className="mt-1.5 text-xs text-muted">{note}</dd>}
    </div>
  );
}

export function SeizureFigures({ data, pending }: { data: Case; pending: boolean }) {
  const d = data.decision;
  const cap = data.order?.total_due ?? 0;
  const show = !pending && d;
  const blocked = !pending && data.exceptions.some((e) => !e.resolved);
  const frozen = show && !blocked ? d.amount_to_hold : null;
  const share = coverage(frozen, cap);
  const accounts = d?.hold_instructions.map((h) => h.iban) ?? [];

  return (
    <div className="rounded-lg bg-paper ring-1 ring-line">
      <dl className="grid divide-y divide-line sm:grid-cols-3 sm:divide-x sm:divide-y-0">
        <Figure label="Plafonul măsurii" value={formatRon(cap)} note="Se îngheață cel mult până la această sumă" />
        <Figure
          label="Înghețat în cont"
          icon={<Lock size={14} className="text-ink" aria-hidden />}
          value={show ? (blocked ? "—" : formatRon(d.amount_to_hold)) : "—"}
          note={
            pending
              ? "Se calculează…"
              : blocked
                ? "Nimic înghețat până la verificare"
                : "Rămâne în contul clientului; nu se virează nimic"
          }
        />
        <Figure label="Exceptat" value={show ? formatRon(d.amount_protected) : "—"} note={show ? "Protejat de lege (art. 953 CPC)" : undefined} />
      </dl>
      {share != null && (
        <div className="border-t border-line px-5 py-4">
          <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 text-sm">
            <span className="font-semibold">Plafon acoperit {Math.round(share * 100)}%</span>
            <span className="text-muted">
              {share < 1 ? `Încă ${formatRon(cap - (frozen ?? 0))} neacoperiți` : "Plafon atins"}
            </span>
          </div>
          <CoverageBar share={share} className="mt-2" />
          {accounts.length > 0 && (
            <p className="mt-3 text-xs text-muted">
              Înghețat în {accounts.length === 1 ? "contul" : "conturile"}{" "}
              <span className="font-mono text-ink">{accounts.join(", ")}</span>
            </p>
          )}
        </div>
      )}
    </div>
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

const Mono = ({ children }: { children: ReactNode }) => <span className="font-mono text-[13px] font-medium">{children}</span>;

export function SeizureFacts({ data }: { data: Case }) {
  const o = data.order;
  const t = SEIZURE[seizureKind(data)];
  const lifting = isLifting(data);
  return (
    <section aria-labelledby="seizure-facts-title" className="rounded-lg bg-paper ring-1 ring-line">
      <h2 id="seizure-facts-title" className="display border-b border-line px-5 py-3.5 text-base">
        {lifting ? "Decizia de ridicare" : "Actul de sechestru"}
      </h2>
      <dl className="grid grid-cols-2 gap-x-6 gap-y-5 px-5 py-5 md:grid-cols-4">
        <Fact label="Număr dosar">{o?.case_number}</Fact>
        <Fact label="Data emiterii">{o?.issue_date ? formatDate(o.issue_date) : null}</Fact>
        <Fact label="Emitent" wide>
          {o?.issuer_name}
        </Fact>
        <Fact label={t.debtor} wide>
          {o?.debtor_name}
        </Fact>
        <Fact label="CNP / CUI">{o?.debtor_id ? <Mono>{o.debtor_id}</Mono> : null}</Fact>
        {lifting ? (
          <Fact label="Ridică măsura din dosarul">{o?.references_case_number ?? o?.case_number}</Fact>
        ) : (
          <>
            <Fact label="Fel măsură">{t.label}</Fact>
            {o?.legal_basis && (
              <Fact label="Temei legal" wide>
                <span className="font-medium">{o.legal_basis}</span>
              </Fact>
            )}
            <Fact label={t.creditor} wide>
              {o?.creditor_name}
            </Fact>
            <Fact label={t.principal}>{o ? formatRon(o.principal) : null}</Fact>
            <Fact label={t.costs}>{o ? formatRon(o.enforcement_costs) : null}</Fact>
            <Fact label="Cont de consemnare indicat" wide>
              {o?.consignment_iban ? (
                <>
                  <Mono>{o.consignment_iban}</Mono>
                  <span className="mt-0.5 block text-xs font-normal text-muted">
                    Doar indicat în act. Banii se virează aici abia după titlul executoriu.
                  </span>
                </>
              ) : null}
            </Fact>
          </>
        )}
      </dl>
    </section>
  );
}

// Ciclul măsurii: dispusă de emitent → instituită de bancă → ridicată. Leagă actul de instituire de decizia de ridicare.
export function SeizureLifecycle({ data, onOpen }: { data: Case; onOpen: (caseId: string) => void }) {
  const [cases, setCases] = useState<CaseSummary[]>([]);

  useEffect(() => {
    api
      .listCases()
      .then(setCases)
      .catch(() => setCases([]));
  }, [data.case_id, data.updated_at]);

  const o = data.order;
  const lifting = isLifting(data);
  const ref = lifting ? (o?.references_case_number ?? o?.case_number) : o?.case_number;
  const other = cases.find((c) => c.case_id !== data.case_id && isSeizure(c) && isLifting(c) !== lifting && c.case_number === ref);
  const blocked = data.exceptions.some((e) => !e.resolved);
  const frozen = data.decision?.amount_to_hold;

  const steps: { title: string; detail: ReactNode; done: boolean }[] = lifting
    ? [
        {
          title: "Sechestru instituit",
          detail: other ? `Dosarul ${ref}, ${formatDate(other.created_at)}` : `Dosarul ${ref}, înainte de LexOps`,
          done: true,
        },
        { title: "Ridicare dispusă", detail: o?.issue_date ? `Decizie din ${formatDate(o.issue_date)}` : "Decizie primită", done: true },
        {
          title: "Conturi deblocate",
          detail: data.status === "LIFTED" ? `Deblocate pe ${formatDate(data.updated_at)}` : "Așteaptă verificarea",
          done: data.status === "LIFTED",
        },
      ]
    : [
        { title: "Măsură dispusă", detail: o?.issue_date ? `${SEIZURE[seizureKind(data)].issuer}, ${formatDate(o.issue_date)}` : "—", done: true },
        {
          title: "Fonduri înghețate",
          detail: blocked ? "Oprit pentru verificare" : frozen != null ? `${formatRon(frozen)}, ${formatDate(data.updated_at)}` : "—",
          done: !blocked && frozen != null,
        },
        {
          title: other ? "Sechestru ridicat" : "Ridicare",
          detail: other ? `Decizie primită ${formatDate(other.created_at)}` : "La titlul executoriu sau la decizia de ridicare",
          done: !!other,
        },
      ];

  return (
    <section aria-labelledby="lifecycle-title" className="rounded-lg bg-paper px-5 py-4 ring-1 ring-line">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id="lifecycle-title" className="display text-base">
          Ciclul măsurii
        </h2>
        {other && (
          <button
            onClick={() => onOpen(other.case_id)}
            className="inline-flex items-center gap-1 text-sm font-semibold underline-offset-4 hover:underline"
          >
            {lifting ? "Deschide actul de instituire" : "Deschide decizia de ridicare"}
            <ArrowRight size={15} aria-hidden />
          </button>
        )}
      </div>
      <ol className="mt-4 grid gap-4 sm:grid-cols-3">
        {steps.map((s, i) => (
          <li key={s.title} className="flex gap-3">
            <span
              className={`grid h-6 w-6 shrink-0 place-items-center rounded-md text-xs font-bold ${s.done ? "bg-ink text-sun" : "text-muted ring-1 ring-line-strong"}`}
              aria-hidden
            >
              {i + 1}
            </span>
            <span className="min-w-0 text-sm">
              <span className={`block font-semibold ${s.done ? "" : "text-muted"}`}>{s.title}</span>
              <span className="block text-muted">{s.detail}</span>
            </span>
          </li>
        ))}
      </ol>
    </section>
  );
}
