// Panourile dosarului „Insolvență și succesiuni”, în locul celor de poprire. Proprietar: Om4.
// Nimic nu se blochează aici: se schimbă cine poate dispune de bani. La succesiune contează cine primește
// cât; la insolvență, ce s-a suspendat, ce conturi s-au marcat și ce plăți au ieșit după deschidere.
import type { ReactNode } from "react";
import { CircleCheck, CircleX, Landmark, Users } from "lucide-react";
import type { Case } from "../types/contracts";
import { formatDate, formatRon, humanize } from "../lib/ui";
import { deathDate, heirs, isSuccession, lateFlags, openingDate, procedure, quotaValue, suspended } from "../lib/insolvency";

const ACCOUNT_TYPE: Record<string, string> = { CURENT: "Cont curent", ECONOMII: "Cont de economii", DEPOZIT: "Depozit" };
const pct = (x: number) => `${(x * 100).toLocaleString("ro-RO", { maximumFractionDigits: 2 })}%`;

export function InsolvencyKindLine({ data }: { data: Case }) {
  const succession = isSuccession(data);
  const p = procedure(data);
  return (
    <p className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-sm">
      <span className="inline-flex items-center gap-1.5 rounded-md bg-ink px-2 py-1 text-xs font-bold text-sun">
        {succession ? <Users size={13} aria-hidden /> : <Landmark size={13} aria-hidden />}
        {succession ? "Succesiune" : p.label}
      </span>
      <span className="font-medium">{succession ? "Codul civil, art. 1132–1133" : "Legea nr. 85/2014"}</span>
      {data.order?.issuer_name && <span className="text-muted">{data.order.issuer_name}</span>}
    </p>
  );
}

function Figure({ label, value, note, alert }: { label: string; value: string; note?: string; alert?: boolean }) {
  return (
    <div className="px-5 py-4">
      <dt className="flex items-center gap-2 text-sm text-muted">
        {alert && <span className="h-2 w-2 rounded-full bg-danger" aria-hidden />}
        {label}
      </dt>
      <dd className={`display mt-1.5 text-2xl ${alert ? "text-danger-ink" : ""}`}>{value}</dd>
      {note && <dd className="mt-1.5 text-xs text-muted">{note}</dd>}
    </div>
  );
}

const total = (c: Case) => c.decision?.amount_protected ?? c.accounts.reduce((s, a) => s + a.current_balance, 0);

export function InsolvencyFigures({ data, pending }: { data: Case; pending: boolean }) {
  const show = !pending;
  const late = lateFlags(data).length;

  if (show && !data.customer) {
    return (
      <div className="rounded-lg bg-canvas px-5 py-4 text-sm">
        <p className="font-bold">{data.order?.debtor_name ?? "Persoana"} nu este client al băncii</p>
        <p className="mt-1 text-muted">{humanize(data.outcome?.summary) || "Banca nu deține conturi ale persoanei din document."}</p>
      </div>
    );
  }

  if (isSuccession(data)) {
    const died = deathDate(data);
    return (
      <dl className="grid divide-y divide-line rounded-lg bg-paper ring-1 ring-line sm:grid-cols-4 sm:divide-x sm:divide-y-0">
        <Figure label="Masa succesorală" value={show ? formatRon(total(data)) : "—"} note="Soldul tuturor conturilor defunctului" />
        <Figure label="Moștenitori" value={String(heirs(data).length)} note="Din certificatul de moștenitor" />
        <Figure label="Data decesului" value={died ? formatDate(died) : "—"} note={data.accounts.length === 1 ? "Un cont al defunctului" : `${data.accounts.length} conturi ale defunctului`} />
        <Figure
          label="Plăți după deces"
          value={show ? String(late) : "—"}
          alert={show && late > 0}
          note={late ? "Nu intră în masa succesorală" : "Contul nu a fost folosit după deces"}
        />
      </dl>
    );
  }

  const opened = openingDate(data);
  return (
    <dl className="grid divide-y divide-line rounded-lg bg-paper ring-1 ring-line sm:grid-cols-4 sm:divide-x sm:divide-y-0">
      <Figure label="Averea din conturi" value={show ? formatRon(total(data)) : "—"} note="Intră în averea debitorului, nu se virează executorilor" />
      <Figure label="Popriri suspendate" value={show ? String(suspended(data).length) : "—"} note="Suspendate de drept (art. 75)" />
      <Figure label="Conturi marcate" value={show ? String(data.accounts.length) : "—"} note={opened ? `Insolvență din ${formatDate(opened)}` : "Marcate INSOLVENTA"} />
      <Figure
        label="Plăți după deschidere"
        value={show ? String(late) : "—"}
        alert={show && late > 0}
        note={late ? "Pot fi anulate (art. 84)" : "Nicio plată după deschidere"}
      />
    </dl>
  );
}

// Bara cotelor: fiecare moștenitor are segmentul lui, în nuanțe de negru; partea lipsă rămâne goală, cu roșu
function QuotaBar({ quotas }: { quotas: number[] }) {
  const shades = ["bg-ink", "bg-ink/60", "bg-ink/35", "bg-ink/20"];
  const sum = quotas.reduce((a, b) => a + b, 0);
  return (
    <div className="flex h-3 overflow-hidden rounded-sm ring-1 ring-ink/10" aria-hidden>
      {quotas.map((q, i) => (
        <div key={i} className={`${shades[i % shades.length]} border-r-2 border-paper last:border-r-0`} style={{ width: `${q * 100}%` }} />
      ))}
      {sum < 0.9999 && <div className="bg-danger-soft" style={{ width: `${(1 - sum) * 100}%` }} />}
    </div>
  );
}

function Succession({ data }: { data: Case }) {
  const list = heirs(data);
  const quotas = list.map((h) => quotaValue(h.quota));
  const sum = quotas.reduce((a, b) => a + b, 0);
  const ok = Math.abs(sum - 1) < 0.0001;
  const shades = ["bg-ink", "bg-ink/60", "bg-ink/35", "bg-ink/20"];

  return (
    <section aria-labelledby="heirs-title" className="rounded-lg bg-paper ring-1 ring-line">
      <div className="flex flex-wrap items-baseline justify-between gap-3 border-b border-line px-5 py-3.5">
        <h2 id="heirs-title" className="display text-base">
          Împărțirea pe moștenitori
        </h2>
        <span className={`flex items-center gap-1.5 text-sm font-semibold ${ok ? "" : "text-danger-ink"}`}>
          {ok ? <CircleCheck size={16} aria-hidden /> : <CircleX size={16} className="text-danger" aria-hidden />}
          {ok ? "Cotele însumează 100%" : `Cotele însumează ${pct(sum)}, nu 100%`}
        </span>
      </div>
      <div className="px-5 pt-4">
        <QuotaBar quotas={quotas} />
      </div>
      <table className="mt-2 w-full text-sm">
        <thead className="sr-only">
          <tr>
            <th>Moștenitor</th>
            <th>CNP</th>
            <th>Cotă</th>
            <th>Sumă cuvenită</th>
          </tr>
        </thead>
        <tbody>
          {list.map((h, i) => (
            <tr key={h.cnp} className="border-b border-line last:border-b-0">
              <td className="py-3 pr-3 pl-5">
                <span className="flex items-center gap-2.5">
                  <span className={`h-2.5 w-2.5 shrink-0 rounded-sm ${shades[i % shades.length]}`} aria-hidden />
                  <span>
                    <span className="block font-semibold">{h.name}</span>
                    {h.relation && <span className="block text-muted first-letter:uppercase">{h.relation}</span>}
                  </span>
                </span>
              </td>
              <td className="hidden px-3 py-3 font-mono text-[13px] text-muted sm:table-cell">{h.cnp}</td>
              <td className="px-3 py-3 whitespace-nowrap">
                <span className="font-semibold">{h.quota}</span>
                <span className="ml-1.5 text-muted">{pct(quotaValue(h.quota))}</span>
              </td>
              <td className="py-3 pr-5 pl-3 text-right font-semibold whitespace-nowrap">
                {h.share != null ? formatRon(h.share) : <span className="font-normal text-muted">Nu se calculează</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="border-t border-line px-5 py-3 text-xs text-muted">
        {ok
          ? "Fiecare primește soldul înmulțit cu cota lui; diferența de rotunjire (bani) merge la moștenitorul cu cota cea mai mare."
          : "Plata către moștenitori e oprită până când notarul corectează certificatul sau ofițerul decide."}
      </p>
    </section>
  );
}

function Insolvency({ data }: { data: Case }) {
  const list = suspended(data);
  const opened = openingDate(data);
  return (
    <section aria-labelledby="effects-title" className="rounded-lg bg-paper ring-1 ring-line">
      <h2 id="effects-title" className="display border-b border-line px-5 py-3.5 text-base">
        Efectele deschiderii procedurii
      </h2>
      <ol className="divide-y divide-line">
        <Effect n={1} title="Popriri suspendate" basis="Legea 85/2014, art. 75">
          {list.length ? (
            <ul className="mt-2 space-y-1.5">
              {list.map((g) => (
                <li key={g.caseNumber} className="flex flex-wrap justify-between gap-x-4">
                  <span>
                    Dosar <span className="font-mono text-[13px]">{g.caseNumber}</span>, {g.creditor}
                  </span>
                  <span className="text-muted">
                    rest neîncasat <span className="font-semibold text-ink">{formatRon(g.remaining)}</span>
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <span className="block text-muted">Nu existau popriri active pe debitor.</span>
          )}
          <span className="mt-2 block text-muted">
            {opened ? `Din ${formatDate(opened)}, nu` : "De la deschiderea procedurii, nu"} se mai virează nimic către executori.
          </span>
        </Effect>
        <Effect n={2} title="Conturi marcate INSOLVENTA" basis="Legea 85/2014, art. 84">
          <span className="block text-muted">
            {data.accounts.length} {data.accounts.length === 1 ? "cont" : "conturi"}. Plățile se fac doar cu acordul {procedure(data).practitionerOf}.
          </span>
        </Effect>
        <Effect n={3} title="Plăți după deschidere" basis="Pot fi anulate de judecătorul-sindic" alert={lateFlags(data).length > 0}>
          {lateFlags(data).length ? (
            <ul className="mt-2 space-y-1.5 text-danger-ink">
              {lateFlags(data).map((e, i) => (
                <li key={i}>{humanize(e.message)}</li>
              ))}
            </ul>
          ) : (
            <span className="block text-muted">Nicio plată din cont după deschiderea procedurii.</span>
          )}
        </Effect>
      </ol>
    </section>
  );
}

function Effect({ n, title, basis, alert, children }: { n: number; title: string; basis: string; alert?: boolean; children: ReactNode }) {
  return (
    <li className="flex gap-3 px-5 py-4 text-sm">
      <span
        className={`grid h-6 w-6 shrink-0 place-items-center rounded-md text-xs font-bold ${alert ? "bg-danger text-paper" : "bg-ink text-sun"}`}
        aria-hidden
      >
        {n}
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-baseline justify-between gap-x-4">
          <span className={`font-semibold ${alert ? "text-danger-ink" : ""}`}>{title}</span>
          <span className="text-xs text-muted">{basis}</span>
        </div>
        {children}
      </div>
    </li>
  );
}

export function InsolvencyMain({ data }: { data: Case }) {
  if (!data.customer) return null;
  return isSuccession(data) ? <Succession data={data} /> : <Insolvency data={data} />;
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

export function InsolvencyFacts({ data }: { data: Case }) {
  const o = data.order;
  if (isSuccession(data)) {
    const died = deathDate(data);
    return (
      <section aria-labelledby="ins-facts-title" className="rounded-lg bg-paper ring-1 ring-line">
        <h2 id="ins-facts-title" className="display border-b border-line px-5 py-3.5 text-base">
          Certificatul de moștenitor
        </h2>
        <dl className="grid grid-cols-2 gap-x-6 gap-y-5 px-5 py-5 md:grid-cols-4">
          <Fact label="Număr certificat">{o?.case_number}</Fact>
          <Fact label="Data emiterii">{o?.issue_date ? formatDate(o.issue_date) : null}</Fact>
          <Fact label="Notar public" wide>
            {o?.issuer_name}
          </Fact>
          <Fact label="Defunct" wide>
            {o?.debtor_name}
          </Fact>
          <Fact label="CNP defunct">{o?.debtor_id ? <Mono>{o.debtor_id}</Mono> : null}</Fact>
          <Fact label="Data decesului">{died ? formatDate(died) : null}</Fact>
        </dl>
      </section>
    );
  }
  const p = procedure(data);
  const opened = openingDate(data);
  return (
    <section aria-labelledby="ins-facts-title" className="rounded-lg bg-paper ring-1 ring-line">
      <h2 id="ins-facts-title" className="display border-b border-line px-5 py-3.5 text-base">
        Notificarea de insolvență
      </h2>
      <dl className="grid grid-cols-2 gap-x-6 gap-y-5 px-5 py-5 md:grid-cols-4">
        <Fact label="Număr dosar">{o?.case_number}</Fact>
        <Fact label="Data deschiderii">{opened ? formatDate(opened) : null}</Fact>
        <Fact label="Tribunal" wide>
          {o?.issuer_name}
        </Fact>
        <Fact label="Debitor" wide>
          {o?.debtor_name}
        </Fact>
        <Fact label="CUI">{o?.debtor_id ? <Mono>{o.debtor_id}</Mono> : null}</Fact>
        <Fact label="Procedură">{p.detail}</Fact>
        <Fact label={p.practitioner} wide>
          {o?.creditor_name}
        </Fact>
        <Fact label="Cont unic de insolvență" wide>
          {o?.consignment_iban ? <Mono>{o.consignment_iban}</Mono> : null}
        </Fact>
      </dl>
    </section>
  );
}

// Tab-ul „Conturi”: ce conturi intră în masa succesorală / averea debitorului
export function InsolvencyAccounts({ data }: { data: Case }) {
  const succession = isSuccession(data);
  if (!data.accounts.length) return <p className="text-sm text-muted">Nu există conturi ale persoanei din document.</p>;
  return (
    <section aria-labelledby="ins-accounts-title">
      <h2 id="ins-accounts-title" className="display text-xl">
        {succession ? "Conturile defunctului" : "Conturile debitorului"}
      </h2>
      <div className="mt-4 overflow-x-auto rounded-lg ring-1 ring-line">
        <table className="w-full min-w-[640px] text-sm">
          <thead className="bg-canvas text-left text-muted">
            <tr className="border-b border-line">
              <th className="px-4 py-2.5 font-medium">IBAN</th>
              <th className="px-4 py-2.5 font-medium">Tip</th>
              <th className="px-4 py-2.5 font-medium">Regim</th>
              <th className="px-4 py-2.5 text-right font-medium">Sold</th>
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
                <td className="px-4 py-3">{succession ? "Masă succesorală" : "Marcat INSOLVENTA"}</td>
                <td className="px-4 py-3 text-right font-semibold whitespace-nowrap">
                  {a.currency === "RON" ? formatRon(a.current_balance) : `${a.current_balance} ${a.currency}`}
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className="border-t border-ink">
              <td colSpan={3} className="px-4 py-3 font-semibold">
                {succession ? "Total masă succesorală" : "Total avere în conturi"}
              </td>
              <td className="px-4 py-3 text-right font-bold whitespace-nowrap">{formatRon(total(data))}</td>
            </tr>
          </tfoot>
        </table>
      </div>
    </section>
  );
}
