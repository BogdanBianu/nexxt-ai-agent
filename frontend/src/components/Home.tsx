// Pagina de start LexOps: ce așteaptă decizia ofițerului în toate modulele, intrarea în fiecare modul
// și pe scurt cum lucrează agenții. Proprietar: Om4.
import { useCallback, useEffect, useState } from "react";
import { ArrowRight, CircleCheck, OctagonAlert } from "lucide-react";
import { api } from "../api/client";
import type { Case, CaseSummary, ModuleInfo } from "../types/contracts";
import { moduleOf, statusLabel } from "../lib/modules";
import { caseTitle, EXCEPTION_LABEL, formatAgo, PIPELINE, STATUS_STYLE, type StatusTone } from "../lib/ui";
import { ServerDown } from "./ServerDown";
import { UploadDocument } from "./UploadDocument";

interface Props {
  onModule: (moduleId: string) => void;
  onOpen: (caseId: string, fresh: boolean) => void;
}

const isReview = (c: CaseSummary) => STATUS_STYLE[c.status].tone === "danger";
const isToday = (iso: string) => new Date(iso).toDateString() === new Date().toDateString();

const DOT: Record<StatusTone, string> = {
  done: "bg-ink",
  danger: "bg-danger",
  working: "bg-sun ring-1 ring-ink",
  neutral: "bg-line-strong",
};

// Ce face fiecare agent, spus pentru toate modulele, nu doar pentru popriri
const STEP_DETAIL: Record<string, string> = {
  INTAKE_ROUTER: "Recunoaște tipul documentului și îl trimite modulului potrivit.",
  EXTRACTION: "Citește dosarul, emitentul, persoana vizată și sumele.",
  RECONCILIATION: "Găsește clientul și conturile lui în Core Banking.",
  INCOME_CLASSIFIER: "Stabilește natura fiecărei încasări din extras.",
  RULE_ENGINE: "Aplică regulile legale: cât se blochează, ce rămâne protejat.",
  ANOMALY: "Caută tentative de eludare în istoricul tranzacțiilor.",
  OUTCOME: "Execută blocările și redactează răspunsul către emitent.",
};

function Fact({ label, value, alert }: { label: string; value: string; alert?: boolean }) {
  return (
    <span className="block min-w-0">
      <span className="block text-xs text-muted">{label}</span>
      <span className={`mt-0.5 flex items-center gap-1.5 truncate font-semibold ${alert ? "text-danger-ink" : ""}`}>
        {alert && <span className="h-2 w-2 shrink-0 rounded-full bg-danger" aria-hidden />}
        {value}
      </span>
    </span>
  );
}

function ModuleCard({ m, cases, onOpen }: { m: ModuleInfo; cases: CaseSummary[]; onOpen: () => void }) {
  const review = cases.filter(isReview).length;
  const today = cases.filter((c) => isToday(c.created_at)).length;
  const last = cases.reduce<string | null>((a, c) => (!a || c.created_at > a ? c.created_at : a), null);
  return (
    <li>
      <button
        onClick={onOpen}
        className="group flex h-full w-full flex-col rounded-lg bg-paper p-5 text-left ring-1 ring-line transition-[box-shadow,transform] duration-150 ease-out hover:ring-ink active:scale-[0.995] lg:p-6"
      >
        <span className="flex items-center justify-between gap-4">
          <span className="display text-2xl">{m.name}</span>
          <ArrowRight size={18} aria-hidden className="shrink-0 transition-transform duration-150 ease-out group-hover:translate-x-0.5" />
        </span>
        <span className="mt-1.5 block text-sm text-muted">{m.description}</span>
        <span className="mt-auto block pt-5">
          <span className="grid grid-cols-3 gap-4 border-t border-line pt-4 text-sm">
            <Fact label="De verificat" value={String(review)} alert={review > 0} />
            <Fact label="Primite azi" value={String(today)} />
            <Fact label="Ultima intrare" value={last ? formatAgo(last) : "—"} />
          </span>
        </span>
      </button>
    </li>
  );
}

export function Home({ onModule, onOpen }: Props) {
  const [modules, setModules] = useState<ModuleInfo[]>([]);
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [details, setDetails] = useState<Record<string, Case>>({});
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState(false);

  const load = useCallback(() => {
    Promise.all([api.listModules(), api.listCases()])
      .then(([m, c]) => {
        setModules(m);
        setCases(c);
        setLoaded(true);
        setError(false);
      })
      .catch(() => setError(true));
  }, []);

  useEffect(load, [load]);

  // Motivul opririi și numele pentru dosarele fără debitor nu sunt în sumar
  useEffect(() => {
    const missing = cases.filter((c) => (isReview(c) || !c.debtor_name) && !details[c.case_id]);
    if (!missing.length) return;
    Promise.all(missing.map((c) => api.getCase(c.case_id).catch(() => null))).then((list) =>
      setDetails((d) => {
        const next = { ...d };
        for (const x of list) if (x) next[x.case_id] = x;
        return next;
      }),
    );
  }, [cases, details]);

  const today = new Date().toLocaleDateString("ro-RO", { weekday: "long", day: "numeric", month: "long" });
  const active = modules.filter((m) => m.status === "ACTIVE");
  const planned = modules.filter((m) => m.status !== "ACTIVE");
  const moduleName = (id: string) => modules.find((m) => m.module_id === id)?.name ?? id;
  const titleOf = (c: CaseSummary) => c.debtor_name ?? (details[c.case_id] ? caseTitle(details[c.case_id]) : "…");

  const sorted = [...cases].sort((a, b) => b.created_at.localeCompare(a.created_at));
  // Cele mai vechi întâi, ca nimic să nu stea uitat
  const queue = sorted.filter(isReview).reverse();
  const recent = sorted.slice(0, 8);

  return (
    <div className="pt-10">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm text-muted first-letter:uppercase">{today}</p>
          <h1 className="display mt-1 text-4xl">Registratura juridică</h1>
          <p className="mt-2 max-w-[68ch] text-[15px] text-muted">
            Documentele primite de bancă de la executori, instanțe și autorități. Agentul de primire trimite fiecare document modulului potrivit;
            tu intervii doar unde agenții s-au oprit.
          </p>
        </div>
        <UploadDocument onUploaded={(id) => onOpen(id, true)} />
      </div>

      {error && !loaded ? (
        <ServerDown onRetry={load} />
      ) : (
        <>
          <section aria-labelledby="modules-title" className="mt-10">
            <h2 id="modules-title" className="sr-only">
              Module
            </h2>
            <ul className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              {active.map((m) => (
                <ModuleCard key={m.module_id} m={m} cases={cases.filter((c) => moduleOf(c) === m.module_id)} onOpen={() => onModule(m.module_id)} />
              ))}
              {!loaded && [0, 1, 2, 3].map((i) => <li key={i} className="h-[200px] rounded-lg bg-canvas" aria-hidden />)}
            </ul>

            {planned.length > 0 && (
              <div className="mt-6">
                <h3 className="text-sm font-semibold">În pregătire</h3>
                <ul className="mt-2 grid gap-x-8 gap-y-3 text-sm sm:grid-cols-2 lg:grid-cols-3">
                  {planned.map((m) => (
                    <li key={m.module_id}>
                      <span className="font-semibold text-ink/70">{m.name}</span>
                      <span className="block text-muted">{m.description}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </section>

          <div className="mt-14 grid items-start gap-12 lg:grid-cols-[minmax(0,1fr)_380px]">
            <div className="min-w-0 space-y-12">
              <section aria-labelledby="home-queue-title">
                <h2 id="home-queue-title" className="display flex items-center gap-2.5 text-xl">
                  Așteaptă decizia ta
                  {queue.length > 0 && <span className="rounded bg-danger px-1.5 py-0.5 text-sm leading-none text-paper">{queue.length}</span>}
                </h2>
                {loaded && queue.length === 0 ? (
                  <p className="mt-3 flex items-center gap-2 text-sm">
                    <CircleCheck size={16} aria-hidden />
                    Nimic de verificat în niciun modul.
                  </p>
                ) : (
                  <ul className="mt-3 divide-y divide-line rounded-lg ring-1 ring-line">
                    {queue.map((c) => {
                      const e = details[c.case_id]?.exceptions.find((x) => !x.resolved);
                      return (
                        <li key={c.case_id}>
                          <button
                            onClick={() => onOpen(c.case_id, false)}
                            className="group flex w-full items-center gap-4 px-4 py-3.5 text-left transition-colors duration-150 hover:bg-canvas"
                          >
                            <OctagonAlert size={17} className="shrink-0 text-danger" aria-hidden />
                            <span className="min-w-0 flex-1">
                              <span className="block truncate font-semibold">{titleOf(c)}</span>
                              <span className="block truncate text-sm text-danger-ink">
                                {e ? (EXCEPTION_LABEL[e.code] ?? e.code) : "Necesită verificare"}
                              </span>
                            </span>
                            <span className="hidden shrink-0 text-right text-sm sm:block">
                              <span className="block font-medium">{moduleName(moduleOf(c))}</span>
                              <span className="block text-muted">{formatAgo(c.created_at)}</span>
                            </span>
                            <ArrowRight size={16} aria-hidden className="shrink-0 transition-transform duration-150 ease-out group-hover:translate-x-0.5" />
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                )}
              </section>

              <section aria-labelledby="recent-title">
                <h2 id="recent-title" className="display text-xl">
                  Activitate recentă
                </h2>
                {loaded && recent.length === 0 ? (
                  <p className="mt-3 text-sm text-muted">Niciun document primit încă. Încarcă unul sau deschide un modul și simulează un scenariu.</p>
                ) : (
                  <table className="mt-3 w-full text-sm">
                    <thead className="sr-only">
                      <tr>
                        <th>Primit</th>
                        <th>Persoană</th>
                        <th>Modul</th>
                        <th>Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {recent.map((c) => {
                        const st = STATUS_STYLE[c.status];
                        return (
                          <tr
                            key={c.case_id}
                            onClick={() => onOpen(c.case_id, false)}
                            className="cursor-pointer border-t border-line transition-colors duration-150 first:border-ink hover:bg-canvas"
                          >
                            <td className="w-24 py-3 pr-3 whitespace-nowrap text-muted">{formatAgo(c.created_at)}</td>
                            <td className="py-3 pr-3">
                              <button
                                onClick={(ev) => {
                                  ev.stopPropagation();
                                  onOpen(c.case_id, false);
                                }}
                                className="text-left font-semibold"
                              >
                                {titleOf(c)}
                              </button>
                            </td>
                            <td className="hidden py-3 pr-3 whitespace-nowrap text-muted sm:table-cell">{moduleName(moduleOf(c))}</td>
                            <td className="py-3 whitespace-nowrap">
                              <span className={`flex items-center gap-2 font-medium ${st.tone === "danger" ? "text-danger-ink" : ""}`}>
                                <span className={`h-2 w-2 shrink-0 rounded-full ${DOT[st.tone]}`} aria-hidden />
                                {statusLabel(c)}
                              </span>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                )}
              </section>
            </div>

            <aside aria-labelledby="how-title" className="rounded-lg bg-canvas p-5 lg:p-6">
              <h2 id="how-title" className="display text-xl">
                Cum lucrează agenții
              </h2>
              <p className="mt-1 text-sm text-muted">Fiecare document trece prin aceiași șapte pași, în ordine.</p>
              <ol className="mt-5 space-y-4">
                {PIPELINE.map((p, i) => (
                  <li key={p.agent} className="flex gap-3">
                    <span className="grid h-6 w-6 shrink-0 place-items-center rounded-md bg-ink text-xs font-bold text-sun" aria-hidden>
                      {i + 1}
                    </span>
                    <span className="text-sm">
                      <span className="block font-semibold">{p.label}</span>
                      <span className="block text-muted">{STEP_DETAIL[p.agent]}</span>
                    </span>
                  </li>
                ))}
              </ol>
              <p className="mt-6 border-t border-line-strong pt-4 text-sm">
                <span className="font-semibold">La orice problemă, procesarea se oprește.</span> Dosarul ajunge la „Așteaptă decizia ta” și nicio
                sumă nu se blochează până nu decizi.
              </p>
            </aside>
          </div>
        </>
      )}
    </div>
  );
}
