// Hero-ul paginii de start: încărcare în lot (stânga) + agenții care lucrează pe fiecare fișier, pe rând (dreapta).
// Fișierele se procesează unul după altul; o eroare nu oprește lotul. La final: câte s-au rezolvat și câte au erori.
// Proprietar: Om4.
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { ArrowRight, Check, FileText, LoaderCircle, Minus, OctagonAlert, RotateCcw, Upload } from "lucide-react";
import { api, uploadDocument } from "../api/client";
import type { AgentEvent, AgentName, Case } from "../types/contracts";
import { say } from "../lib/mascot";
import { caseTitle, EXCEPTION_LABEL, humanize, PIPELINE, STATUS_STYLE } from "../lib/ui";

const MAX_BYTES = 10 * 1024 * 1024;
const REPLAY_MS = 110;
// Cât rămâne vizibil rezultatul unui fișier înainte de swipe
const HOLD_MS = 900;
const SWIPE_MS = 200;

type ItemState = "queued" | "running" | "done" | "error";

interface Item {
  id: string;
  file: File;
  state: ItemState;
  data?: Case;
  // Motivul erorii: problema găsită de agenți sau de ce nu s-a putut citi fișierul
  reason?: string;
}

function rejectReason(f: File) {
  if (!(f.type === "application/pdf" || /\.(pdf|txt)$/i.test(f.name))) return "Format neacceptat (doar PDF sau .txt)";
  if (f.size === 0) return "Fișier gol";
  if (f.size > MAX_BYTES) return "Depășește 10 MB";
  return null;
}

// „S4.pdf” → datele bancare de test ale scenariului S4; altfel backend-ul caută singur clientul
const scenarioOf = (name: string) => name.toUpperCase().match(/(?:^|[^A-Z0-9])(S\d+)(?:[^0-9]|$)/)?.[1] ?? "AUTO";

const hasFiles = (e: DragEvent | React.DragEvent) => Array.from(e.dataTransfer?.types ?? []).includes("Files");

const isProblem = (c: Case) => STATUS_STYLE[c.status].tone === "danger";

function problemOf(c: Case) {
  const e = c.exceptions.find((x) => !x.resolved);
  return e ? (EXCEPTION_LABEL[e.code] ?? e.code) : STATUS_STYLE[c.status].label;
}

// Ce face fiecare agent, pentru orice tip de document
const STEP_HINT: Record<AgentName, string> = {
  INTAKE_ROUTER: "Recunoaște tipul documentului și alege modulul",
  EXTRACTION: "Citește dosarul, emitentul, persoana și sumele",
  RECONCILIATION: "Găsește clientul și conturile în Core Banking",
  INCOME_CLASSIFIER: "Stabilește natura fiecărei încasări",
  RULE_ENGINE: "Aplică regulile legale ale modulului",
  ANOMALY: "Caută tentative de eludare și plăți suspecte",
  OUTCOME: "Execută și redactează răspunsul către emitent",
};

type StepState = "IDLE" | "RUNNING" | "DONE" | "SKIPPED" | "PROBLEM";

function stepStates(events: AgentEvent[], data: Case | undefined, complete: boolean) {
  const last: Partial<Record<AgentName, AgentEvent>> = {};
  for (const e of events) last[e.agent] = e;
  const problems = new Set(complete && data ? data.exceptions.filter((x) => !x.resolved).map((x) => x.agent) : []);
  return PIPELINE.map((p) => {
    const e = last[p.agent];
    let state: StepState = "IDLE";
    if (e) state = e.status === "STARTED" || e.status === "PROGRESS" ? "RUNNING" : e.status === "SKIPPED" ? "SKIPPED" : "DONE";
    if (e?.status === "FAILED" || (state === "DONE" && problems.has(p.agent))) state = "PROBLEM";
    return { ...p, state, message: e ? humanize(e.message) : STEP_HINT[p.agent] };
  });
}

function StepMarker({ state, n }: { state: StepState; n: number }) {
  const base = "grid h-5 w-5 shrink-0 place-items-center rounded-full text-[10px] font-bold transition-colors duration-200";
  if (state === "DONE") return <span className={`${base} bg-ink text-paper`}><Check size={11} strokeWidth={3} aria-hidden /></span>;
  if (state === "RUNNING") return <span className={`${base} bg-sun text-ink ring-1 ring-ink`}>{n}</span>;
  if (state === "PROBLEM") return <span className={`${base} bg-danger text-paper`}><OctagonAlert size={11} strokeWidth={3} aria-hidden /></span>;
  if (state === "SKIPPED") return <span className={`${base} border border-dashed border-line-strong text-muted`}><Minus size={10} strokeWidth={3} aria-hidden /></span>;
  return <span className={`${base} border border-line-strong text-muted`}>{n}</span>;
}

function Steps({ events, data, complete }: { events: AgentEvent[]; data?: Case; complete: boolean }) {
  const steps = stepStates(events, data, complete);
  return (
    <ol className="space-y-3">
      {steps.map((s, i) => (
        <li key={s.agent} className="flex gap-3">
          <StepMarker state={s.state} n={i + 1} />
          <div className="min-w-0 flex-1 text-sm leading-snug">
            <span className={`block font-semibold ${s.state === "IDLE" ? "text-muted" : s.state === "PROBLEM" ? "text-danger-ink" : ""}`}>{s.label}</span>
            <span className={`line-clamp-1 ${s.state === "PROBLEM" ? "text-danger-ink" : "text-muted"}`}>{s.message}</span>
          </div>
        </li>
      ))}
    </ol>
  );
}

interface Props {
  onOpen: (caseId: string, fresh: boolean) => void;
  // Lotul s-a terminat: lista de dosare de dedesubt se reîncarcă
  onFinished: () => void;
}

export function BatchUpload({ onOpen, onFinished }: Props) {
  const [items, setItems] = useState<Item[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [shown, setShown] = useState(0);
  const [leaving, setLeaving] = useState(false);
  const [over, setOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const busy = useRef(false);

  const add = useCallback((files: FileList | File[]) => {
    const next = Array.from(files).map<Item>((file, i) => {
      const reason = rejectReason(file);
      return { id: `${Date.now()}-${i}-${file.name}`, file, state: reason ? "error" : "queued", reason: reason ?? undefined };
    });
    if (!next.length) return;
    const ok = next.filter((x) => x.state === "queued").length;
    if (ok) say(ok === 1 ? "Am primit documentul. Mă uit pe el acum." : `Am primit ${ok} documente. Le iau pe rând, una câte una.`);
    // Adăugate în timpul procesării: intră în lotul curent; după rezumat: încep un lot nou
    setItems((list) => (list.some((x) => x.state === "queued" || x.state === "running") ? [...list, ...next] : next));
  }, []);

  const patch = (id: string, p: Partial<Item>) => setItems((list) => list.map((x) => (x.id === id ? { ...x, ...p } : x)));

  // Motorul: ia următorul fișier din coadă, îl încarcă, redă agenții, apoi face swipe la următorul
  useEffect(() => {
    if (busy.current || activeId) return;
    const next = items.find((x) => x.state === "queued");
    if (!next) return;
    busy.current = true;
    setActiveId(next.id);
    setEvents([]);
    setShown(0);
    patch(next.id, { state: "running" });
    uploadDocument(next.file, scenarioOf(next.file.name))
      .then(async (c) => {
        patch(next.id, { data: c });
        const ev = await api.getCaseEvents(c.case_id).catch(() => [] as AgentEvent[]);
        setEvents(ev);
      })
      .catch((e: Error) => {
        patch(next.id, { state: "error", reason: e.message || "Fișierul nu a putut fi citit" });
        setEvents([]);
        setShown(-1);
      });
  }, [items, activeId]);

  const active = items.find((x) => x.id === activeId);
  const complete = !!active?.data && events.length > 0 && shown >= events.length;

  // Redăm evenimentele pe rând
  useEffect(() => {
    if (!events.length || shown >= events.length) return;
    const t = setTimeout(() => setShown((n) => n + 1), REPLAY_MS);
    return () => clearTimeout(t);
  }, [events, shown]);

  // Rezultatul stă puțin pe ecran, apoi swipe și următorul fișier
  useEffect(() => {
    if (!active) return;
    const failedUpload = active.state === "error" && shown === -1;
    if (!complete && !failedUpload) return;
    if (complete && active.data) patch(active.id, isProblem(active.data) ? { state: "error", reason: problemOf(active.data) } : { state: "done" });
    const hold = setTimeout(() => setLeaving(true), HOLD_MS);
    const swap = setTimeout(() => {
      setLeaving(false);
      setActiveId(null);
      busy.current = false;
    }, HOLD_MS + SWIPE_MS);
    return () => {
      clearTimeout(hold);
      clearTimeout(swap);
    };
  }, [complete, shown, active?.id]);

  const finished = items.length > 0 && !activeId && !items.some((x) => x.state === "queued" || x.state === "running");
  const wasFinished = useRef(false);
  useEffect(() => {
    if (finished && !wasFinished.current) {
      onFinished();
      const bad = items.filter((x) => x.state === "error").length;
      const good = items.filter((x) => x.state === "done").length;
      say(
        bad === 0
          ? `Gata! ${good === 1 ? "Documentul e rezolvat" : `Toate cele ${good} sunt rezolvate`} automat. Poți bea cafeaua liniștit.`
          : `Gata! ${good} ${good === 1 ? "rezolvat" : "rezolvate"} automat, ${bad} ${bad === 1 ? "are" : "au"} nevoie de tine.`,
      );
    }
    wasFinished.current = finished;
  }, [finished, onFinished]);

  // Fișierele trase oriunde pe pagina de start ajung în același lot
  useEffect(() => {
    const dragOver = (e: DragEvent) => {
      if (!hasFiles(e)) return;
      e.preventDefault();
      setOver(true);
    };
    const leave = (e: DragEvent) => !e.relatedTarget && setOver(false);
    const drop = (e: DragEvent) => {
      if (!hasFiles(e)) return;
      e.preventDefault();
      setOver(false);
      if (e.dataTransfer?.files.length) add(e.dataTransfer.files);
    };
    window.addEventListener("dragover", dragOver);
    window.addEventListener("dragleave", leave);
    window.addEventListener("drop", drop);
    return () => {
      window.removeEventListener("dragover", dragOver);
      window.removeEventListener("dragleave", leave);
      window.removeEventListener("drop", drop);
    };
  }, [add]);

  const position = active ? items.indexOf(active) + 1 : 0;
  const solved = items.filter((x) => x.state === "done");
  const failed = items.filter((x) => x.state === "error");

  return (
    <section aria-label="Încărcare documente" className="grid gap-4 lg:grid-cols-2">
      {/* Stânga: zona de încărcare, rămâne activă și în timpul procesării */}
      <div
        className={`flex min-h-[26rem] flex-col rounded-xl border-2 border-dashed p-6 transition-[background-color,border-color] duration-200 lg:p-8 ${
          over ? "border-ink bg-sun-soft" : "border-line-strong bg-canvas"
        }`}
      >
        <div className="flex flex-1 flex-col items-center justify-center text-center">
          <span
            className={`grid h-16 w-16 place-items-center rounded-xl bg-paper ring-1 ring-line transition-transform duration-200 ease-[var(--ease-out-strong)] ${over ? "-translate-y-1 scale-105" : ""}`}
          >
            <Upload size={28} strokeWidth={1.75} aria-hidden />
          </span>
          <h2 className="display mt-5 text-2xl">{over ? "Lasă fișierele aici" : "Trage aici documentele primite"}</h2>
          <p className="mt-1.5 max-w-[42ch] text-sm text-muted">
            Popriri, sechestre, cereri de la autorități, notificări de insolvență. Poți pune mai multe deodată; agenții le iau pe rând.
          </p>
          <button
            onClick={() => inputRef.current?.click()}
            className="mt-5 inline-flex h-11 items-center gap-2 rounded-md bg-ink px-5 text-sm font-semibold text-paper transition-[background-color,transform] duration-150 ease-out hover:bg-ink/85 active:scale-[0.97]"
          >
            <FileText size={16} aria-hidden />
            Alege fișiere din calculator
          </button>
          <p className="mt-3 text-xs text-muted">PDF sau .txt, maxim 10 MB fiecare</p>
          <input
            ref={inputRef}
            type="file"
            multiple
            accept="application/pdf,.pdf,.txt,text/plain"
            className="hidden"
            onChange={(e) => {
              if (e.target.files?.length) add(e.target.files);
              e.target.value = "";
            }}
          />
        </div>

        {items.length > 0 && (
          <ul className="mt-6 max-h-40 space-y-1 overflow-y-auto border-t border-line-strong pt-4 text-sm" aria-label="Fișiere în lot">
            {items.map((x) => (
              <li key={x.id} className="flex items-center gap-2.5 animate-rise">
                <span
                  className={`h-2 w-2 shrink-0 rounded-full ${
                    x.state === "done" ? "bg-ink" : x.state === "error" ? "bg-danger" : x.state === "running" ? "bg-sun ring-1 ring-ink" : "bg-line-strong"
                  }`}
                  aria-hidden
                />
                <span className={`min-w-0 flex-1 truncate ${x.state === "queued" ? "text-muted" : "font-medium"}`}>{x.file.name}</span>
                <span className={`shrink-0 text-xs ${x.state === "error" ? "text-danger-ink" : "text-muted"}`}>
                  {x.state === "queued" ? "În așteptare" : x.state === "running" ? "Se verifică…" : x.state === "done" ? "Rezolvat automat" : "Eroare"}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Dreapta: agenții pe fișierul curent; la final, rezumatul lotului */}
      <div className="flex min-h-[26rem] flex-col overflow-hidden rounded-xl bg-paper p-6 ring-1 ring-line lg:p-8">
        {active ? (
          <div key={active.id} className={`flex flex-1 flex-col ${leaving ? "animate-swipe-out" : "animate-swipe-in"}`}>
            <div className="flex items-baseline justify-between gap-4">
              <p className="text-sm text-muted">
                Fișierul {position} din {items.length}
              </p>
              <ProgressDots items={items} activeId={active.id} />
            </div>
            <h2 className="display mt-1 truncate text-2xl">{active.data ? caseTitle(active.data) : active.file.name}</h2>
            <p className="mt-0.5 truncate text-sm text-muted">{active.file.name}</p>

            <div className="mt-6 flex-1">
              {active.state === "error" && !active.data ? (
                <Outcome tone="danger" title="Fișierul nu a putut fi procesat" detail={active.reason} />
              ) : (
                <Steps events={events.slice(0, Math.max(shown, 0))} data={active.data} complete={complete} />
              )}
            </div>

            {complete && active.data && (
              <div className="mt-5 animate-rise">
                {isProblem(active.data) ? (
                  <Outcome tone="danger" title={problemOf(active.data)} detail="Trece la următorul; dosarul te așteaptă în listă." />
                ) : (
                  <Outcome tone="done" title={STATUS_STYLE[active.data.status].label} detail={humanize(active.data.outcome?.summary) || undefined} />
                )}
              </div>
            )}
            {!complete && active.state === "running" && !events.length && (
              <p className="mt-5 flex items-center gap-2 text-sm text-muted">
                <LoaderCircle size={15} className="animate-spin" aria-hidden />
                Se citește documentul…
              </p>
            )}
          </div>
        ) : finished ? (
          <Summary solved={solved} failed={failed} onOpen={onOpen} onClear={() => setItems([])} />
        ) : (
          <Idle />
        )}
      </div>
    </section>
  );
}

function ProgressDots({ items, activeId }: { items: Item[]; activeId: string }) {
  if (items.length < 2) return null;
  return (
    <span className="flex items-center gap-1" aria-hidden>
      {items.slice(0, 12).map((x) => (
        <span
          key={x.id}
          className={`h-1.5 rounded-full transition-[width,background-color] duration-200 ${x.id === activeId ? "w-5 bg-ink" : x.state === "error" ? "w-1.5 bg-danger" : x.state === "done" ? "w-1.5 bg-ink" : "w-1.5 bg-line-strong"}`}
        />
      ))}
    </span>
  );
}

function Outcome({ tone, title, detail }: { tone: "done" | "danger"; title: string; detail?: ReactNode }) {
  return (
    <div className={`flex gap-3 rounded-md px-4 py-3 text-sm ${tone === "danger" ? "border border-danger/40 bg-danger-soft" : "bg-sun-soft"}`}>
      {tone === "danger" ? (
        <OctagonAlert size={18} className="mt-px shrink-0 text-danger" aria-hidden />
      ) : (
        <Check size={18} strokeWidth={2.5} className="mt-px shrink-0" aria-hidden />
      )}
      <div className="min-w-0">
        <p className={`font-bold ${tone === "danger" ? "text-danger-ink" : ""}`}>{title}</p>
        {detail && <p className="mt-0.5 line-clamp-2 text-muted">{detail}</p>}
      </div>
    </div>
  );
}

function Idle() {
  return (
    <div className="flex flex-1 flex-col">
      <p className="text-sm text-muted">Agenții așteaptă</p>
      <h2 className="display mt-1 text-2xl">Niciun document în lucru</h2>
      <p className="mt-0.5 text-sm text-muted">Fiecare document trece prin acești șapte pași, în ordine.</p>
      <div className="mt-6 flex-1">
        <Steps events={[]} complete={false} />
      </div>
    </div>
  );
}

function Summary({ solved, failed, onOpen, onClear }: { solved: Item[]; failed: Item[]; onOpen: Props["onOpen"]; onClear: () => void }) {
  return (
    <div className="flex flex-1 animate-swipe-in flex-col">
      <p className="text-sm text-muted">Lot verificat</p>
      <h2 className="display mt-1 text-2xl">
        {solved.length + failed.length} {solved.length + failed.length === 1 ? "document" : "documente"} procesate
      </h2>

      <dl className="mt-6 grid grid-cols-2 gap-3">
        <div className="rounded-lg bg-sun-soft px-5 py-4">
          <dt className="text-sm">Rezolvate automat</dt>
          <dd className="display mt-1 text-4xl">{solved.length}</dd>
        </div>
        <div className={`rounded-lg px-5 py-4 ${failed.length ? "border border-danger/40 bg-danger-soft" : "bg-canvas"}`}>
          <dt className={`text-sm ${failed.length ? "text-danger-ink" : ""}`}>Cu erori</dt>
          <dd className={`display mt-1 text-4xl ${failed.length ? "text-danger-ink" : ""}`}>{failed.length}</dd>
        </div>
      </dl>

      {failed.length > 0 && (
        <ul className="mt-4 max-h-44 divide-y divide-line overflow-y-auto rounded-md ring-1 ring-line">
          {failed.map((x) => (
            <li key={x.id}>
              <button
                disabled={!x.data}
                onClick={() => x.data && onOpen(x.data.case_id, false)}
                className="group flex w-full items-center gap-3 px-3.5 py-2.5 text-left text-sm transition-colors duration-150 enabled:hover:bg-canvas"
              >
                <OctagonAlert size={15} className="shrink-0 text-danger" aria-hidden />
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-semibold">{x.data ? caseTitle(x.data) : x.file.name}</span>
                  <span className="block truncate text-danger-ink">{x.reason}</span>
                </span>
                {x.data && <ArrowRight size={15} aria-hidden className="shrink-0 transition-transform duration-150 group-hover:translate-x-0.5" />}
              </button>
            </li>
          ))}
        </ul>
      )}

      <div className="mt-auto flex items-center justify-between gap-3 pt-5 text-sm">
        <span className="text-muted">Toate dosarele sunt în lista de mai jos.</span>
        <button onClick={onClear} className="inline-flex items-center gap-1.5 font-semibold underline-offset-4 hover:underline">
          <RotateCcw size={14} aria-hidden />
          Lot nou
        </button>
      </div>
    </div>
  );
}
