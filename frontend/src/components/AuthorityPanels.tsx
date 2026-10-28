// Panourile dosarului „Cerere autoritate” (art. 170 CPP), în locul celor de poprire. Proprietar: Om4.
// Aici banca nu blochează bani: comunică date protejate de secretul bancar, deci contează ce s-a cerut,
// dacă cererea e legală și ce anume trimitem înapoi.
import type { ReactNode } from "react";
import { CircleCheck, CircleX, FileSearch, ShieldCheck } from "lucide-react";
import type { Case, IssuerType } from "../types/contracts";
import { formatDate, formatRon, humanize } from "../lib/ui";

const AUTHORITY: Partial<Record<IssuerType, string>> = {
  POLITIE: "Poliție",
  PARCHET: "Organ de urmărire penală",
  ANAF: "ANAF Antifraudă",
};

const ACCOUNT_TYPE: Record<string, string> = { CURENT: "Cont curent", ECONOMII: "Cont de economii", DEPOZIT: "Depozit" };

// Soldurile sunt poziții sintetice „SOLD-…”; restul sunt operațiunile din extras
const operations = (c: Case) => c.classified_transactions.filter((t) => !t.tx_id.startsWith("SOLD-"));
const amlAlerts = (c: Case) => c.exceptions.filter((e) => e.agent === "ANOMALY");
const failed = (c: Case, field: string) => c.exceptions.some((e) => !e.resolved && e.evidence.includes(field));

export function AuthorityKindLine({ data }: { data: Case }) {
  const kind = data.order ? AUTHORITY[data.order.issuer_type] : null;
  return (
    <p className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-sm">
      <span className="inline-flex items-center gap-1.5 rounded-md bg-ink px-2 py-1 text-xs font-bold text-sun">
        <FileSearch size={13} aria-hidden />
        Cerere de informații
      </span>
      <span className="font-medium">Art. 170 Cod procedură penală</span>
      {kind && <span className="text-muted">{kind}</span>}
    </p>
  );
}

function Figure({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="px-5 py-4">
      <dt className="text-sm text-muted">{label}</dt>
      <dd className="display mt-1.5 text-2xl">{value}</dd>
      {note && <dd className="mt-1.5 text-xs text-muted">{note}</dd>}
    </div>
  );
}

export function AuthorityFigures({ data, pending }: { data: Case; pending: boolean }) {
  const show = !pending && !!data.decision;
  const alerts = amlAlerts(data).length;
  return (
    <dl className="grid divide-y divide-line rounded-lg bg-paper ring-1 ring-line sm:grid-cols-4 sm:divide-x sm:divide-y-0">
      <Figure label="Conturi identificate" value={show ? String(data.accounts.length) : "—"} note="Ale persoanei vizate, în Core Banking" />
      <Figure label="Sold raportat" value={show ? formatRon(data.decision?.amount_protected) : "—"} note="Comunicat autorității, nu blocat" />
      <Figure label="Operațiuni în extras" value={show ? String(operations(data).length) : "—"} note="Rulaje anexate răspunsului" />
      <Figure
        label="Sume blocate"
        value={show ? formatRon(0) : "—"}
        note={alerts ? `${alerts} ${alerts === 1 ? "alertă AML" : "alerte AML"} incluse în răspuns` : "Fără sechestru (art. 249 CPP) nu se blochează nimic"}
      />
    </dl>
  );
}

// Punctele numerotate din cerere („1. Lista conturilor…”) și ce răspunde banca la fiecare
function requestedItems(text: string) {
  return text
    .split("\n")
    .map((l) => l.match(/^\s*(\d+)[.)]\s+(.+)/))
    .filter((m): m is RegExpMatchArray => !!m)
    .map((m) => m[2].trim());
}

function answerFor(item: string, data: Case) {
  const t = item.toLowerCase();
  if (/suspect|onpcsb|aml|spălare/.test(t)) {
    const n = amlAlerts(data).length;
    return n ? `${n} ${n === 1 ? "alertă" : "alerte"} AML comunicate` : "Nicio raportare către ONPCSB";
  }
  if (/extras|rulaj|tranzac|operațiun/.test(t)) return `${operations(data).length} operațiuni anexate`;
  if (/cont/.test(t)) return `${data.accounts.length} ${data.accounts.length === 1 ? "cont comunicat" : "conturi comunicate"}`;
  return "Inclus în răspuns";
}

function Check({ ok, label, detail }: { ok: boolean; label: string; detail?: ReactNode }) {
  return (
    <li className="flex gap-2.5 text-sm">
      {ok ? (
        <CircleCheck size={17} className="mt-px shrink-0" aria-label="Îndeplinit" />
      ) : (
        <CircleX size={17} className="mt-px shrink-0 text-danger" aria-label="Neîndeplinit" />
      )}
      <span>
        <span className={`font-semibold ${ok ? "" : "text-danger-ink"}`}>{label}</span>
        {detail && <span className="block text-muted">{detail}</span>}
      </span>
    </li>
  );
}

export function AuthorityRequest({ data }: { data: Case }) {
  const items = requestedItems(data.document.text ?? "");
  const answered = data.status === "AUTO_PROCESSED";
  const o = data.order;
  return (
    <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,0.8fr)]">
      <section aria-labelledby="requested-title" className="rounded-lg bg-paper ring-1 ring-line">
        <h2 id="requested-title" className="display border-b border-line px-5 py-3.5 text-base">
          Ce a cerut autoritatea
        </h2>
        {items.length ? (
          <ol className="divide-y divide-line">
            {items.map((item, i) => (
              <li key={i} className="grid gap-x-4 gap-y-1 px-5 py-3.5 text-sm sm:grid-cols-[1.5rem_minmax(0,1fr)_auto]">
                <span className="font-bold">{i + 1}.</span>
                <span>{item}</span>
                <span className={`font-semibold whitespace-nowrap sm:text-right ${answered ? "" : "text-muted"}`}>
                  {answered ? answerFor(item, data) : "Nu s-a comunicat"}
                </span>
              </li>
            ))}
          </ol>
        ) : (
          <p className="px-5 py-4 text-sm text-muted">Cererea nu are puncte numerotate; vezi documentul complet în tab-ul Documente.</p>
        )}
      </section>

      <section aria-labelledby="legal-title" className="rounded-lg bg-paper ring-1 ring-line">
        <h2 id="legal-title" className="display flex items-center gap-2 border-b border-line px-5 py-3.5 text-base">
          <ShieldCheck size={17} aria-hidden />
          Ridicarea secretului bancar
        </h2>
        <ul className="space-y-3 px-5 py-4">
          <Check ok={!failed(data, "legal_basis")} label="Temei legal invocat" detail="Art. 170 CPP, ordonanța procurorului sau mandat" />
          <Check ok={!!o?.has_signature_and_stamp} label="Semnătură și ștampilă" />
          <Check ok={!failed(data, "debtor_id")} label="CNP valid" detail={o?.debtor_id ? <span className="font-mono text-[13px]">{o.debtor_id}</span> : undefined} />
          <Check
            ok={!!data.customer && !failed(data, "debtor_name")}
            label="Persoana e client al băncii"
            detail={data.customer ? `${data.customer.full_name}, ${data.accounts.length} ${data.accounts.length === 1 ? "cont" : "conturi"}` : undefined}
          />
        </ul>
        <p className="border-t border-line px-5 py-3 text-xs text-muted">
          {answered ? "Datele pleacă doar cu regim confidențial, către emitentul cererii." : "Nu s-a comunicat nicio dată protejată de secretul bancar."}
        </p>
      </section>
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

export function AuthorityFacts({ data }: { data: Case }) {
  const o = data.order;
  return (
    <section aria-labelledby="authority-facts-title" className="rounded-lg bg-paper ring-1 ring-line">
      <h2 id="authority-facts-title" className="display border-b border-line px-5 py-3.5 text-base">
        Solicitarea
      </h2>
      <dl className="grid grid-cols-2 gap-x-6 gap-y-5 px-5 py-5 md:grid-cols-4">
        <Fact label="Dosar penal">{o?.case_number}</Fact>
        <Fact label="Data emiterii">{o?.issue_date ? formatDate(o.issue_date) : null}</Fact>
        <Fact label="Autoritate" wide>
          {o?.issuer_name}
        </Fact>
        <Fact label="Persoană vizată" wide>
          {o?.debtor_name}
        </Fact>
        <Fact label="Regim">Confidențial, secret bancar</Fact>
        <Fact label="Efect asupra conturilor">Niciunul</Fact>
      </dl>
    </section>
  );
}

// Tab-ul „Date comunicate”: exact ce pleacă spre autoritate
export function AuthorityReport({ data }: { data: Case }) {
  const ops = operations(data);
  const flagged = new Set(amlAlerts(data).flatMap((e) => e.evidence));
  return (
    <div className="space-y-10">
      <section aria-labelledby="accounts-title">
        <h2 id="accounts-title" className="display text-xl">
          Conturi comunicate
        </h2>
        {data.accounts.length === 0 ? (
          <p className="mt-3 text-sm text-muted">Nu s-au identificat conturi ale persoanei vizate.</p>
        ) : (
          <div className="mt-4 overflow-x-auto rounded-lg ring-1 ring-line">
            <table className="w-full min-w-[640px] text-sm">
              <thead className="bg-canvas text-left text-muted">
                <tr className="border-b border-line">
                  <th className="px-4 py-2.5 font-medium">IBAN</th>
                  <th className="px-4 py-2.5 font-medium">Tip</th>
                  <th className="px-4 py-2.5 text-right font-medium">Sold la începutul perioadei</th>
                  <th className="px-4 py-2.5 text-right font-medium">Sold curent</th>
                </tr>
              </thead>
              <tbody>
                {data.accounts.map((a) => (
                  <tr key={a.iban} className="border-b border-line last:border-b-0">
                    <td className="px-4 py-3 font-mono text-[13px]">{a.iban}</td>
                    <td className="px-4 py-3">
                      {ACCOUNT_TYPE[a.account_type] ?? a.account_type}
                      <span className="text-muted">, {a.currency}</span>
                    </td>
                    <td className="px-4 py-3 text-right whitespace-nowrap text-muted">
                      {a.currency === "RON" ? formatRon(a.opening_balance) : `${a.opening_balance} ${a.currency}`}
                    </td>
                    <td className="px-4 py-3 text-right font-semibold whitespace-nowrap">
                      {a.currency === "RON" ? formatRon(a.current_balance) : `${a.current_balance} ${a.currency}`}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section aria-labelledby="ops-title">
        <h2 id="ops-title" className="display text-xl">
          Operațiuni anexate
        </h2>
        {ops.length === 0 ? (
          <p className="mt-3 text-sm text-muted">Nu există încasări în perioada analizată; răspunsul comunică doar soldurile.</p>
        ) : (
          <div className="mt-4 overflow-x-auto rounded-lg ring-1 ring-line">
            <table className="w-full min-w-[640px] text-sm">
              <thead className="bg-canvas text-left text-muted">
                <tr className="border-b border-line">
                  <th className="px-4 py-2.5 font-medium">Data</th>
                  <th className="px-4 py-2.5 font-medium">Plătitor</th>
                  <th className="px-4 py-2.5 text-right font-medium">Sumă</th>
                </tr>
              </thead>
              <tbody>
                {ops.map((t) => (
                  <tr key={t.tx_id} className={`border-b border-line last:border-b-0 ${flagged.has(t.tx_id) ? "bg-danger-soft" : ""}`}>
                    <td className="px-4 py-3 whitespace-nowrap text-muted">{formatDate(t.booking_date)}</td>
                    <td className="px-4 py-3">
                      <div className="font-medium">{t.counterparty_name}</div>
                      <div className="text-muted">{t.description}</div>
                    </td>
                    <td className="px-4 py-3 text-right font-semibold whitespace-nowrap">{formatRon(t.amount)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {amlAlerts(data).length > 0 && (
        <section aria-labelledby="aml-title">
          <h2 id="aml-title" className="display text-xl">
            Alerte AML incluse în răspuns
          </h2>
          <ul className="mt-4 space-y-2">
            {amlAlerts(data).map((e, i) => (
              <li key={i} className="rounded-md border border-danger/40 bg-danger-soft px-4 py-3 text-sm text-danger-ink">
                {humanize(e.message)}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
