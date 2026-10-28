// Pagina de start LexOps: încărcare în lot cu agenții la lucru (hero), apoi baza tuturor dosarelor,
// din toate modulele, cu cele care au erori primele și căutare după CNP, nume, instituție sau dosar. Proprietar: Om4.
import { useCallback, useEffect, useState } from "react";
import { ArrowRight, OctagonAlert, Search, X } from "lucide-react";
import { api } from "../api/client";
import type { Case, CaseSummary, ModuleInfo } from "../types/contracts";
import { moduleOf, statusLabel, typeLabel } from "../lib/modules";
import { caseTitle, EXCEPTION_LABEL, formatAgo, formatTime, STATUS_STYLE, type StatusTone } from "../lib/ui";
import { BatchUpload } from "./BatchUpload";
import { Mascot } from "./Mascot";
import { ServerDown } from "./ServerDown";

interface Props {
  onOpen: (caseId: string, fresh: boolean) => void;
}

const isProblem = (c: CaseSummary) => STATUS_STYLE[c.status].tone === "danger";

const DOT: Record<StatusTone, string> = {
  done: "bg-ink",
  danger: "bg-danger",
  working: "bg-sun ring-1 ring-ink",
  neutral: "bg-line-strong",
};

const plain = (s: string) => s.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase();

// Tot ce poate căuta ofițerul pe un dosar: persoană, CNP/CUI, emitent, creditor, număr de dosar
function haystack(c: CaseSummary, d?: Case) {
  return plain(
    [
      c.debtor_name,
      c.case_number,
      d && caseTitle(d),
      d?.order?.debtor_id,
      d?.customer?.national_id,
      d?.order?.issuer_name,
      d?.order?.creditor_name,
    ]
      .filter(Boolean)
      .join(" "),
  );
}

export function Home({ onOpen }: Props) {
  const [modules, setModules] = useState<ModuleInfo[]>([]);
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [details, setDetails] = useState<Record<string, Case>>({});
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState(false);
  const [query, setQuery] = useState("");

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

  // CNP-ul, emitentul și motivul erorii sunt doar în dosarul complet
  useEffect(() => {
    const missing = cases.filter((c) => !details[c.case_id]);
    if (!missing.length) return;
    Promise.all(missing.map((c) => api.getCase(c.case_id).catch(() => null))).then((list) =>
      setDetails((d) => {
        const next = { ...d };
        for (const x of list) if (x) next[x.case_id] = x;
        return next;
      }),
    );
  }, [cases, details]);

  const moduleName = (id: string) => modules.find((m) => m.module_id === id)?.name ?? id;

  const q = plain(query.trim());
  // Erorile primele, apoi cele mai noi
  const rows = [...cases]
    .sort((a, b) => Number(isProblem(b)) - Number(isProblem(a)) || b.created_at.localeCompare(a.created_at))
    .filter((c) => !q || haystack(c, details[c.case_id]).includes(q));
  const problems = cases.filter(isProblem).length;


  return (
    <div className="pt-10">
      <div className="flex flex-wrap items-end justify-between gap-x-10 gap-y-4">
        <h1 className="display text-[clamp(2rem,4.2vw,3.5rem)] leading-[1.04]">
          <span className="block">Lasă-ne documentele.</span>
          <span className="block">Agenții noștri se ocupă de ele.</span>
        </h1>
        <div className="hidden w-[30rem] shrink-0 sm:block">
          <Mascot inline />
        </div>
      </div>

      <div className="mt-10">
        <BatchUpload onOpen={onOpen} onFinished={load} />
      </div>

      {error && !loaded ? (
        <ServerDown onRetry={load} />
      ) : (
        <section aria-labelledby="all-title" className="mt-16">
          <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-2">
            <h2 id="all-title" className="display text-2xl">
              Toate dosarele
            </h2>
            {loaded && (
              <p className="text-sm text-muted">
                {cases.length} {cases.length === 1 ? "dosar" : "dosare"}
                {problems > 0 && (
                  <>
                    , <span className="font-semibold text-danger-ink">{problems} cu erori</span>, afișate primele
                  </>
                )}
              </p>
            )}
          </div>

          <label className="relative mt-4 flex items-center">
            <Search size={18} className="pointer-events-none absolute left-4 text-muted" aria-hidden />
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Caută după CNP, nume, instituție sau număr de dosar"
              aria-label="Caută după CNP, nume, instituție sau număr de dosar"
              className="h-12 w-full rounded-lg bg-paper pr-11 pl-11 text-[15px] ring-1 ring-line-strong outline-none placeholder:text-muted focus:ring-2 focus:ring-ink [&::-webkit-search-cancel-button]:hidden"
            />
            {query && (
              <button onClick={() => setQuery("")} aria-label="Șterge căutarea" className="absolute right-3 grid h-7 w-7 place-items-center rounded-md hover:bg-canvas">
                <X size={16} aria-hidden />
              </button>
            )}
          </label>

          <div className="mt-4 overflow-x-auto">
            <table className="w-full min-w-[960px] text-sm">
              <thead>
                <tr className="border-b border-ink text-left text-xs font-semibold text-muted">
                  <th className="w-8 py-2.5" aria-label="Eroare" />
                  <th className="py-2.5 pr-4">Persoană</th>
                  <th className="px-4 py-2.5">Instituție emitentă</th>
                  <th className="px-4 py-2.5">Tip</th>
                  <th className="px-4 py-2.5">Nr. dosar</th>
                  <th className="px-4 py-2.5">Status</th>
                  <th className="px-4 py-2.5">Primit</th>
                  <th className="w-8" />
                </tr>
              </thead>
              <tbody>
                {loaded && rows.length === 0 && (
                  <tr>
                    <td colSpan={8} className="py-14 text-center">
                      {cases.length === 0 ? (
                        <>
                          <p className="font-semibold">Niciun dosar încă</p>
                          <p className="mt-1 text-muted">Trage un document în căsuța de mai sus ca să înceapă agenții.</p>
                        </>
                      ) : (
                        <>
                          <p className="font-semibold">Niciun dosar pentru „{query}”</p>
                          <button onClick={() => setQuery("")} className="mt-2 text-sm font-semibold underline underline-offset-4">
                            Șterge căutarea
                          </button>
                        </>
                      )}
                    </td>
                  </tr>
                )}
                {rows.map((c) => {
                  const d = details[c.case_id];
                  const st = STATUS_STYLE[c.status];
                  const problem = isProblem(c);
                  const e = d?.exceptions.find((x) => !x.resolved);
                  const cnp = d?.order?.debtor_id ?? d?.customer?.national_id;
                  return (
                    <tr
                      key={c.case_id}
                      onClick={() => onOpen(c.case_id, false)}
                      className={`group cursor-pointer border-b border-line transition-colors duration-150 ${problem ? "bg-danger-soft/60 hover:bg-danger-soft" : "hover:bg-canvas"}`}
                    >
                      <td className="py-3.5 pl-1">
                        {problem && <OctagonAlert size={17} className="text-danger" aria-label="Are erori" />}
                      </td>
                      <td className="py-3.5 pr-4">
                        <button
                          onClick={(ev) => {
                            ev.stopPropagation();
                            onOpen(c.case_id, false);
                          }}
                          className="text-left font-semibold"
                        >
                          {c.debtor_name ?? (d ? caseTitle(d) : "…")}
                        </button>
                        {cnp && <div className="font-mono text-xs text-muted">{cnp}</div>}
                      </td>
                      <td className="max-w-[18rem] px-4 py-3.5">
                        <span className="line-clamp-2">{d?.order?.issuer_name ?? "—"}</span>
                      </td>
                      <td className="px-4 py-3.5 whitespace-nowrap">
                        <span className="font-medium">{typeLabel(c)}</span>
                        <div className="text-xs text-muted">{moduleName(moduleOf(c))}</div>
                      </td>
                      <td className="px-4 py-3.5 font-mono text-[13px] whitespace-nowrap">{c.case_number ?? "—"}</td>
                      <td className="px-4 py-3.5">
                        <span className={`flex items-center gap-2 font-medium whitespace-nowrap ${problem ? "text-danger-ink" : ""}`}>
                          <span className={`h-2 w-2 shrink-0 rounded-full ${DOT[st.tone]}`} aria-hidden />
                          {statusLabel(c)}
                        </span>
                        {problem && e && <div className="pl-4 text-xs text-danger-ink/80">{EXCEPTION_LABEL[e.code] ?? e.code}</div>}
                      </td>
                      <td className="px-4 py-3.5 whitespace-nowrap">
                        {formatAgo(c.created_at)}
                        <div className="text-xs text-muted">{formatTime(c.created_at).slice(0, 5)}</div>
                      </td>
                      <td className="pr-1 text-right">
                        <ArrowRight size={16} aria-hidden className="inline opacity-0 transition-[opacity,transform] duration-150 group-hover:translate-x-0.5 group-hover:opacity-100" />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}
