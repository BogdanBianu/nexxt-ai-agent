// Legal Inbox: lista dosarelor + lansatorul de scenarii S1..S8. Proprietar: Om4.
import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowRight, CircleCheck, ChevronDown, OctagonAlert, Plus, Search, X } from "lucide-react";
import { api } from "../api/client";
import type { Case, CaseSummary, ScenarioInfo } from "../types/contracts";
import { ServerDown } from "./ServerDown";
import { UploadDocument } from "./UploadDocument";
import { caseTitle, dayLabel, DOC_LABEL, EXCEPTION_LABEL, formatAgo, formatRon, formatTime, STATUS_STYLE, type StatusTone } from "../lib/ui";

interface Props {
  onOpen: (caseId: string, fresh: boolean) => void;
  // Incrementat din exterior (ex. după un review HITL) ca lista să se reîncarce
  refreshKey?: number;
}

function ScenarioMenu({ onPick, busy }: { onPick: (id: string) => void; busy: boolean }) {
  const [open, setOpen] = useState(false);
  const [scenarios, setScenarios] = useState<ScenarioInfo[]>([]);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api
      .listScenarios()
      .then((list) => setScenarios(list.filter((s) => s.scenario_id !== "S9" && s.scenario_id !== "S10")))
      .catch(() => setScenarios([]));
  }, []);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => {
          if (!scenarios.length) api.listScenarios().then(setScenarios).catch(() => setScenarios([]));
          setOpen((o) => !o);
        }}
        disabled={busy}
        aria-haspopup="menu"
        aria-expanded={open}
        className="inline-flex h-10 items-center gap-2 rounded-md bg-ink pr-3 pl-3.5 text-sm font-semibold text-paper transition-[background-color,transform] duration-150 ease-out hover:bg-ink/85 active:scale-[0.97] disabled:bg-ink/40"
      >
        <Plus size={16} strokeWidth={2.5} aria-hidden />
        {busy ? "Se procesează…" : "Simulează adresă"}
        <ChevronDown size={16} aria-hidden className={`transition-transform duration-150 ${open ? "rotate-180" : ""}`} />
      </button>

      {open && (
        <div role="menu" className="absolute right-0 z-20 mt-2 w-[22rem] overflow-hidden rounded-md bg-paper shadow-[0_8px_24px_rgba(0,0,0,0.12)] ring-1 ring-line">
          <p className="border-b border-line px-4 py-2.5 text-xs text-muted">Alege un scenariu de test. Dosarul trece imediat prin agenți.</p>
          {scenarios.map((s) => (
            <button
              key={s.scenario_id}
              role="menuitem"
              onClick={() => {
                setOpen(false);
                onPick(s.scenario_id);
              }}
              className="flex w-full items-start gap-3 px-4 py-3 text-left hover:bg-canvas focus-visible:bg-canvas"
            >
              <span className="mt-px w-7 shrink-0 text-sm font-bold">{s.scenario_id}</span>
              <span className="text-sm leading-snug font-medium">{s.title}</span>
            </button>
          ))}
          {scenarios.length === 0 && <p className="px-4 py-3 text-sm text-muted">Nu există scenarii disponibile.</p>}
        </div>
      )}
    </div>
  );
}

type Filter = "ALL" | "REVIEW" | "AUTO";

const isReview = (c: CaseSummary) => STATUS_STYLE[c.status].tone === "danger";

const FILTERS: { id: Filter; label: string; test: (c: CaseSummary) => boolean }[] = [
  { id: "ALL", label: "Toate", test: () => true },
  { id: "REVIEW", label: "De verificat", test: isReview },
  { id: "AUTO", label: "Rezolvate automat", test: (c) => c.status === "AUTO_PROCESSED" },
];

const DOT: Record<StatusTone, string> = {
  done: "bg-ink",
  danger: "bg-danger",
  working: "bg-sun ring-1 ring-ink",
  neutral: "bg-line-strong",
};

const QUEUE_MAX = 6;

function problemOf(detail: Case | undefined) {
  const e = detail?.exceptions.find((x) => !x.resolved);
  return e ? (EXCEPTION_LABEL[e.code] ?? e.code) : null;
}

function ReviewCard({ c, detail, onOpen }: { c: CaseSummary; detail?: Case; onOpen: () => void }) {
  const problem = problemOf(detail);
  return (
    <li>
      <button
        onClick={onOpen}
        className="group flex h-full w-full flex-col rounded-lg bg-paper p-4 text-left ring-1 ring-line transition-[box-shadow,transform] duration-150 ease-out hover:ring-ink active:scale-[0.99]"
      >
        <span className="flex items-center justify-between gap-3 text-sm">
          <span className="flex min-w-0 items-center gap-1.5 font-semibold text-danger-ink">
            <OctagonAlert size={15} className="shrink-0 text-danger" aria-hidden />
            <span className="truncate">{problem ?? "Necesită verificare"}</span>
          </span>
          <span className="shrink-0 text-muted">{formatAgo(c.created_at)}</span>
        </span>
        <span className="display mt-3 block text-lg">{c.debtor_name ?? "Debitor neidentificat"}</span>
        <span className="mt-0.5 block truncate text-sm text-muted">
          Dosar {c.case_number ?? "—"}
          {detail?.order?.issuer_name ? `, ${detail.order.issuer_name}` : ""}
        </span>
        <span className="mt-auto flex items-end justify-between gap-3 pt-4">
          <span className="text-sm">
            <span className="block text-muted">Suma în joc</span>
            <span className="font-semibold">{detail?.order ? formatRon(detail.order.total_due) : "—"}</span>
          </span>
          <span className="inline-flex items-center gap-1 text-sm font-semibold">
            Verifică
            <ArrowRight size={15} aria-hidden className="transition-transform duration-150 ease-out group-hover:translate-x-0.5" />
          </span>
        </span>
      </button>
    </li>
  );
}

export function CaseInbox({ onOpen, refreshKey = 0 }: Props) {
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [details, setDetails] = useState<Record<string, Case>>({});
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>("ALL");
  const [query, setQuery] = useState("");

  const reload = useCallback(() => {
    api
      .listCases()
      .then((c) => {
        setCases(
          c.filter(
            (item) =>
              item.scenario_id !== "S9" &&
              item.scenario_id !== "S10" &&
              !(item.case_number?.includes("/AI/") || item.case_number?.includes("/P/")),
          ),
        );
        setLoaded(true);
        setError(null);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  useEffect(reload, [reload, refreshKey]);

  // Pentru dosarele blocate avem nevoie de motiv și emitent, care nu sunt în sumar
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

  async function simulate(scenarioId: string) {
    setBusy(true);
    setError(null);
    try {
      const created = await api.createFromScenario(scenarioId);
      onOpen(created.case_id, true);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const sorted = [...cases].sort((a, b) => b.created_at.localeCompare(a.created_at));
  // Coada: cele mai vechi întâi, ca nimic să nu stea uitat
  const queue = sorted.filter(isReview).reverse();

  const q = query.trim().toLowerCase();
  const active = FILTERS.find((f) => f.id === filter)!;
  const rows = sorted.filter(
    (c) => active.test(c) && (!q || [c.debtor_name, c.case_number].some((v) => v?.toLowerCase().includes(q))),
  );
  const groups: { label: string; items: CaseSummary[] }[] = [];
  for (const c of rows) {
    const label = dayLabel(c.created_at);
    const g = groups[groups.length - 1];
    if (g?.label === label) g.items.push(c);
    else groups.push({ label, items: [c] });
  }

  const today = new Date().toLocaleDateString("ro-RO", { weekday: "long", day: "numeric", month: "long" });

  return (
    <div className="pt-10">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm text-muted first-letter:uppercase">{today}</p>
          <h1 className="display mt-1 text-4xl">Popriri</h1>
        </div>
        <div className="flex items-center gap-2">
          <UploadDocument onUploaded={(id) => onOpen(id, true)} />
          <ScenarioMenu onPick={simulate} busy={busy} />
        </div>
      </div>

      {error && !loaded && <ServerDown onRetry={reload} />}

      {error && loaded && (
        <p role="alert" className="mt-6 rounded-md border border-danger/40 bg-danger-soft px-4 py-3 text-sm font-semibold text-danger-ink">
          Acțiunea nu a reușit: {error}
        </p>
      )}

      {loaded && (
        <section aria-labelledby="queue-title" className="mt-8 rounded-lg bg-canvas p-5 lg:p-6">
          <div className="flex flex-wrap items-baseline justify-between gap-3">
            <h2 id="queue-title" className="display flex items-center gap-2.5 text-xl">
              Așteaptă decizia ta
              {queue.length > 0 && <span className="rounded bg-danger px-1.5 py-0.5 text-sm leading-none text-paper">{queue.length}</span>}
            </h2>
            {queue.length > 0 && (
              <p className="text-sm text-muted">Procesarea automată s-a oprit. Nicio sumă nu se blochează până nu decizi.</p>
            )}
          </div>

          {queue.length === 0 ? (
            <p className="mt-3 flex items-center gap-2 text-sm">
              <CircleCheck size={16} aria-hidden />
              Nimic de verificat. Toate popririle primite au fost procesate automat.
            </p>
          ) : (
            <>
              <ul className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                {queue.slice(0, QUEUE_MAX).map((c) => (
                  <ReviewCard key={c.case_id} c={c} detail={details[c.case_id]} onOpen={() => onOpen(c.case_id, false)} />
                ))}
              </ul>
              {queue.length > QUEUE_MAX && (
                <button onClick={() => setFilter("REVIEW")} className="mt-3 text-sm font-semibold underline underline-offset-4">
                  Încă {queue.length - QUEUE_MAX} în tabelul de mai jos
                </button>
              )}
            </>
          )}
        </section>
      )}

      {(loaded || !error) && (
        <>
          <div className="mt-12 flex flex-wrap items-end justify-between gap-4">
            <div className="flex flex-wrap items-end gap-x-8 gap-y-3">
              <h2 className="display text-xl">Toate dosarele</h2>
              <div role="tablist" aria-label="Filtru status" className="flex gap-5">
                {FILTERS.map((f) => {
                  const n = cases.filter(f.test).length;
                  const on = f.id === filter;
                  return (
                    <button
                      key={f.id}
                      role="tab"
                      aria-selected={on}
                      onClick={() => setFilter(f.id)}
                      className={`flex items-center gap-1.5 border-b-2 pb-1 text-sm font-semibold transition-colors duration-150 ${
                        on ? "border-ink" : "border-transparent text-muted hover:text-ink"
                      }`}
                    >
                      {f.label}
                      <span className="text-muted">{n}</span>
                    </button>
                  );
                })}
              </div>
            </div>

            <label className="relative flex w-full items-center sm:w-72">
              <Search size={16} className="pointer-events-none absolute left-3 text-muted" aria-hidden />
              <input
                type="search"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Caută debitor sau nr. dosar"
                aria-label="Caută debitor sau număr dosar"
                className="h-10 w-full rounded-md bg-paper pr-3 pl-9 text-sm ring-1 ring-line-strong outline-none placeholder:text-muted focus:ring-2 focus:ring-ink"
              />
            </label>
          </div>

          <div className="mt-4 overflow-x-auto">
            <table className="w-full min-w-[820px] text-sm">
              <thead>
                <tr className="border-b border-ink text-left text-xs font-semibold text-muted">
                  <th className="py-2.5 pr-4">Debitor</th>
                  <th className="px-4 py-2.5">Nr. dosar</th>
                  <th className="px-4 py-2.5">Status</th>
                  <th className="px-4 py-2.5 text-right">De indisponibilizat</th>
                  <th className="px-4 py-2.5">Primit</th>
                  <th className="w-24" />
                </tr>
              </thead>
              {loaded && rows.length === 0 && (
                <tbody>
                  <tr>
                    <td colSpan={6} className="py-14 text-center">
                      {cases.length === 0 ? (
                        <>
                          <p className="font-semibold">Nicio adresă de poprire primită</p>
                          <p className="mt-1 text-muted">Folosește „Simulează adresă” ca să trimiți un scenariu de test prin agenți.</p>
                        </>
                      ) : (
                        <>
                          <p className="font-semibold">Niciun dosar nu corespunde filtrului</p>
                          <button
                            onClick={() => {
                              setFilter("ALL");
                              setQuery("");
                            }}
                            className="mt-2 inline-flex items-center gap-1 text-sm font-semibold underline underline-offset-4"
                          >
                            <X size={14} aria-hidden />
                            Șterge filtrele
                          </button>
                        </>
                      )}
                    </td>
                  </tr>
                </tbody>
              )}
              {groups.map((g) => (
                <tbody key={g.label}>
                  <tr>
                    <th colSpan={6} scope="rowgroup" className="pt-6 pb-2 text-left text-xs font-semibold first-letter:uppercase">
                      {g.label}
                      <span className="ml-2 font-normal text-muted">{g.items.length}</span>
                    </th>
                  </tr>
                  {g.items.map((c) => {
                    const st = STATUS_STYLE[c.status];
                    const problem = st.tone === "danger";
                    const reason = problem ? problemOf(details[c.case_id]) : null;
                    return (
                      <tr
                        key={c.case_id}
                        onClick={() => onOpen(c.case_id, false)}
                        className="group cursor-pointer border-t border-line transition-colors duration-150 hover:bg-canvas"
                      >
                        <td className="py-3.5 pr-4">
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              onOpen(c.case_id, false);
                            }}
                            className="text-left font-semibold"
                          >
                            {c.debtor_name ?? (details[c.case_id] ? caseTitle(details[c.case_id]) : "…")}
                          </button>
                          <div className="text-xs text-muted">
                            {DOC_LABEL[c.doc_type]}
                            {c.scenario_id ? `, scenariu ${c.scenario_id}` : ""}
                          </div>
                        </td>
                        <td className="px-4 py-3.5 font-mono text-[13px]">{c.case_number ?? "—"}</td>
                        <td className="px-4 py-3.5">
                          <span className={`flex items-center gap-2 font-medium ${problem ? "text-danger-ink" : ""}`}>
                            <span className={`h-2 w-2 shrink-0 rounded-full ${DOT[st.tone]}`} aria-hidden />
                            {st.label}
                          </span>
                          {reason && <div className="pl-4 text-xs text-danger-ink/80">{reason}</div>}
                        </td>
                        <td className="px-4 py-3.5 text-right whitespace-nowrap">
                          {problem ? <span className="text-muted">Blocat</span> : <span className="font-semibold">{c.amount_to_hold != null ? formatRon(c.amount_to_hold) : "—"}</span>}
                        </td>
                        <td className="px-4 py-3.5 whitespace-nowrap">
                          {formatAgo(c.created_at)}
                          <div className="text-xs text-muted">{formatTime(c.created_at).slice(0, 5)}</div>
                        </td>
                        <td className="pr-1 text-right">
                          <span className="inline-flex items-center gap-1 text-sm font-semibold opacity-0 transition-opacity duration-150 group-hover:opacity-100">
                            Deschide
                            <ArrowRight size={14} aria-hidden />
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              ))}
            </table>
          </div>
        </>
      )}
    </div>
  );
}

