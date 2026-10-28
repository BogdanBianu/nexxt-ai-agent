// Traseul vertical al celor 7 agenți, alimentat din GET /api/cases/{id}/events. Proprietar: Om4.
// Backend-ul rulează graful sincron, deci la un dosar nou redăm evenimentele pe rând ca să se vadă progresul.
// Pasul care a ridicat o excepție nerezolvată devine roșu, ca problema să se vadă fără să citești.
import { useEffect, useMemo, useRef, useState } from "react";
import { Check, ChevronRight, Minus, OctagonAlert } from "lucide-react";
import { api } from "../api/client";
import type { AgentEvent, AgentName, AgentStatus, Case } from "../types/contracts";
import { PIPELINE } from "../lib/ui";
import { AgentDrawer } from "./AgentDrawer";

const REPLAY_MS = 140;

type StepState = "IDLE" | "RUNNING" | "COMPLETED" | "SKIPPED" | "PROBLEM";

function baseState(status: AgentStatus | undefined): StepState {
  if (!status) return "IDLE";
  if (status === "STARTED" || status === "PROGRESS") return "RUNNING";
  if (status === "FAILED") return "PROBLEM";
  return status;
}

const STATE_WORD: Record<StepState, string> = {
  IDLE: "În așteptare",
  RUNNING: "Lucrează",
  COMPLETED: "Finalizat",
  SKIPPED: "Oprit",
  PROBLEM: "Problemă",
};

const prefersReducedMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

function Marker({ state, index }: { state: StepState; index: number }) {
  const base = "relative z-10 grid h-6 w-6 place-items-center rounded-full text-[11px] font-bold transition-colors duration-200";
  switch (state) {
    case "COMPLETED":
      return (
        <span className={`${base} bg-ink text-paper`}>
          <Check size={13} strokeWidth={2.5} aria-hidden />
        </span>
      );
    case "RUNNING":
      return <span className={`${base} bg-sun text-ink ring-1 ring-ink`}>{index + 1}</span>;
    case "PROBLEM":
      return (
        <span className={`${base} bg-danger text-paper`}>
          <OctagonAlert size={13} strokeWidth={2.5} aria-hidden />
        </span>
      );
    case "SKIPPED":
      return (
        <span className={`${base} border border-dashed border-line-strong bg-paper text-muted`}>
          <Minus size={12} strokeWidth={2.5} aria-hidden />
        </span>
      );
    default:
      return <span className={`${base} border border-line-strong bg-paper text-muted`}>{index + 1}</span>;
  }
}

interface Props {
  caseId: string;
  // true = dosar abia creat → redăm evenimentele; false = le arătăm pe toate imediat
  animate: boolean;
  // Dosarul complet: excepțiile marchează pașii cu probleme, restul alimentează panoul de detalii
  data: Case | null;
  onReplayDone?: () => void;
}

export function AgentPipeline({ caseId, animate, data, onReplayDone }: Props) {
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [shown, setShown] = useState(0);
  const [doneFlag, setDoneFlag] = useState(false);
  const [openAgent, setOpenAgent] = useState<AgentName | null>(null);
  const doneRef = useRef(onReplayDone);
  doneRef.current = onReplayDone;

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setInterval> | undefined;
    setEvents([]);
    setShown(0);
    setDoneFlag(false);
    setOpenAgent(null);

    const finish = () => {
      setDoneFlag(true);
      doneRef.current?.();
    };

    api.getCaseEvents(caseId).then((evs) => {
      if (cancelled) return;
      const sorted = [...evs].sort((a, b) => a.seq - b.seq);
      setEvents(sorted);
      if (!animate || prefersReducedMotion()) {
        setShown(sorted.length);
        finish();
        return;
      }
      let i = 0;
      timer = setInterval(() => {
        i += 1;
        setShown(i);
        if (i >= sorted.length) {
          clearInterval(timer);
          finish();
        }
      }, REPLAY_MS);
    });

    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [caseId, animate]);

  const byAgent = useMemo(() => {
    const m = new Map<AgentName, AgentEvent[]>();
    for (const e of events.slice(0, shown)) m.set(e.agent, [...(m.get(e.agent) ?? []), e]);
    return m;
  }, [events, shown]);

  const open = doneFlag && data ? data.exceptions.filter((e) => !e.resolved) : [];
  const problems = PIPELINE.filter((n) => open.some((e) => e.agent === n.agent)).length;

  return (
    <section aria-labelledby="pipeline-title" className="rounded-lg bg-paper ring-1 ring-line">
      <div className="flex items-baseline justify-between gap-3 border-b border-line px-5 py-4">
        <h2 id="pipeline-title" className="display text-base">
          Agenți
        </h2>
        <span aria-live="polite" className={`text-sm ${problems ? "font-semibold text-danger-ink" : "text-muted"}`}>
          {!doneFlag ? "Procesare în curs…" : problems ? `${problems === 1 ? "O problemă" : `${problems} probleme`} găsite` : "Fără probleme"}
        </span>
      </div>

      <ol className="px-5 pt-5 pb-4">
        {PIPELINE.map((node, idx) => {
          const evs = byAgent.get(node.agent) ?? [];
          const last = evs[evs.length - 1];
          const agentExc = open.filter((e) => e.agent === node.agent);
          const state: StepState = agentExc.length ? "PROBLEM" : baseState(last?.status);
          const clickable = doneFlag && evs.length > 0 && !!data;
          const isLast = idx === PIPELINE.length - 1;
          const nextReached = !isLast && byAgent.has(PIPELINE[idx + 1].agent);

          return (
            <li key={node.agent} className="relative grid grid-cols-[1.5rem_1fr] gap-x-3.5 pb-5 last:pb-0">
              {!isLast && (
                <span aria-hidden className={`absolute top-6 bottom-0 left-[11.5px] w-px ${nextReached ? "bg-ink" : "bg-line"}`} />
              )}
              <Marker state={state} index={idx} />

              <button
                type="button"
                disabled={!clickable}
                onClick={() => setOpenAgent(node.agent)}
                aria-label={clickable ? `${node.label}: vezi raționamentul complet` : undefined}
                className={`group -mx-2 -mt-1 block min-w-0 rounded-lg px-2 py-1 text-left transition-colors duration-150 disabled:cursor-default ${
                  state === "PROBLEM" ? "bg-danger-soft ring-1 ring-danger/25 hover:bg-danger-soft/70" : clickable ? "hover:bg-canvas" : ""
                }`}
              >
                <span className="flex items-baseline justify-between gap-3">
                  <span className={`font-semibold ${state === "IDLE" ? "text-muted" : state === "PROBLEM" ? "text-danger-ink" : ""}`}>{node.label}</span>
                  <span className={`flex shrink-0 items-center gap-1 text-xs ${state === "PROBLEM" ? "font-semibold text-danger-ink" : "text-muted"}`}>
                    {STATE_WORD[state]}
                    {clickable && (
                      <ChevronRight size={14} aria-hidden className="transition-transform duration-150 group-hover:translate-x-0.5" />
                    )}
                  </span>
                </span>

                {agentExc.map((e) => (
                  <span key={e.code + e.message} className="mt-1 block text-sm leading-snug font-medium text-danger-ink">
                    {e.message}
                  </span>
                ))}

                <span className={`mt-0.5 block text-sm leading-snug break-words ${state === "IDLE" ? "text-muted/80" : "text-muted"}`}>
                  {state === "IDLE" ? node.hint : last?.message}
                </span>

                {state === "PROBLEM" && (
                  <span className="mt-2 inline-flex items-center gap-1 text-sm font-bold text-danger-ink underline underline-offset-4">
                    Vezi de ce
                    <ChevronRight size={14} aria-hidden />
                  </span>
                )}
              </button>
            </li>
          );
        })}
      </ol>

      {doneFlag && <p className="border-t border-line px-5 py-3 text-xs text-muted">Apasă pe un agent ca să vezi ce a analizat și de ce a decis așa.</p>}

      {openAgent && data && (
        <AgentDrawer agent={openAgent} events={events} data={data} onNavigate={setOpenAgent} onClose={() => setOpenAgent(null)} />
      )}
    </section>
  );
}
