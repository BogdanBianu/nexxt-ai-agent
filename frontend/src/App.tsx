// Compunerea aplicației: lista de dosare ↔ dosarul deschis. Proprietar: Om4 (componentele Om5 se montează în slotul marcat).
import { useCallback, useEffect, useState } from "react";
import { api } from "./api/client";
import { AccountDissection } from "./components/AccountDissection";
import { AgentPipeline } from "./components/AgentPipeline";
import { AppShell } from "./components/AppShell";
import { CaseFacts, CaseFigures, CaseHeader } from "./components/CaseHeader";
import { AuditTrail } from "./components/AuditTrail";
import { CaseInbox } from "./components/CaseInbox";
import { DocumentViewer } from "./components/DocumentViewer";
import { HitlWorkbench, ReviewHistory } from "./components/HitlWorkbench";
import { ServerDown } from "./components/ServerDown";
import type { Case } from "./types/contracts";
import { formatRon } from "./lib/ui";

type Tab = "analysis" | "documents" | "audit";

const TABS: { id: Tab; label: string }[] = [
  { id: "analysis", label: "Analiză" },
  { id: "documents", label: "Documente" },
  { id: "audit", label: "Jurnal de audit" },
];

export default function App() {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [animate, setAnimate] = useState(false);
  const [replayDone, setReplayDone] = useState(false);
  const [current, setCurrent] = useState<Case | null>(null);
  const [runKey, setRunKey] = useState(0);
  const [notice, setNotice] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("analysis");

  const open = useCallback((caseId: string, fresh: boolean) => {
    setSelectedId(caseId);
    setAnimate(fresh);
    setReplayDone(!fresh);
    setNotice(null);
    setTab("analysis");
    window.scrollTo({ top: 0 });
  }, []);

  // După decizia ofițerului: dosarul recalculat + redăm agenții care au rulat din nou
  const onReviewed = useCallback((updated: Case) => {
    setCurrent(updated);
    setAnimate(true);
    setReplayDone(false);
    setRunKey((k) => k + 1);
    const still = updated.exceptions.some((e) => !e.resolved);
    setNotice(
      still
        ? "Decizia a fost aplicată, dar dosarul are în continuare probleme deschise."
        : `Decizie aplicată. Dosarul a fost recalculat: se indisponibilizează ${formatRon(updated.decision?.amount_to_hold ?? 0)}.`,
    );
    window.scrollTo({ top: 0, behavior: "smooth" });
  }, []);

  const home = useCallback(() => {
    setSelectedId(null);
    setCurrent(null);
    window.scrollTo({ top: 0 });
  }, []);

  const onReplayDone = useCallback(() => setReplayDone(true), []);

  // Documentele redirecționate (ex. cereri de la Poliție) nu au sume, fișă de poprire sau extras
  const routed = current?.status === "ROUTED_TO_OTHER_MODULE";
  const activeTab: Tab = routed && tab === "analysis" ? "documents" : tab;

  const [caseError, setCaseError] = useState(false);

  const loadCase = useCallback(() => {
    if (!selectedId) return;
    api
      .getCase(selectedId)
      .then((c) => {
        setCurrent(c);
        setCaseError(false);
      })
      .catch(() => setCaseError(true));
  }, [selectedId]);

  useEffect(() => {
    setCurrent(null);
    setCaseError(false);
    loadCase();
  }, [loadCase]);

  return (
    <AppShell onHome={home}>
      {!selectedId ? (
        <CaseInbox onOpen={open} />
      ) : (
        caseError && !current ? (
          <ServerDown onRetry={loadCase} />
        ) : (
          <>
            {current && <CaseHeader data={current} pending={!replayDone} onBack={home} notice={notice} />}
            <div className="mt-8 grid items-start gap-8 lg:grid-cols-[minmax(0,1fr)_380px]">
              <div className="min-w-0 space-y-10">
                {current && !routed && <CaseFigures data={current} pending={!replayDone} />}
                {current && replayDone && <HitlWorkbench data={current} onUpdated={onReviewed} />}
                {current && !routed && <CaseFacts data={current} />}
                {current && replayDone && (
                  <div>
                    <div role="tablist" aria-label="Secțiuni dosar" className="flex gap-6 border-b border-line">
                      {TABS.filter((t) => !(routed && t.id === "analysis")).map((t) => (
                        <button
                          key={t.id}
                          role="tab"
                          aria-selected={activeTab === t.id}
                          onClick={() => setTab(t.id)}
                          className={`-mb-px border-b-2 pb-2.5 text-[15px] font-bold transition-colors duration-150 ${
                            activeTab === t.id ? "border-ink" : "border-transparent text-muted hover:text-ink"
                          }`}
                        >
                          {t.label}
                          {t.id === "audit" && current.audit?.length ? <span className="ml-1.5 font-medium text-muted">{current.audit.length}</span> : null}
                        </button>
                      ))}
                    </div>
                    <div role="tabpanel" className="pt-6">
                      {activeTab === "analysis" && <AccountDissection data={current} />}
                      {activeTab === "documents" && <DocumentViewer data={current} />}
                      {activeTab === "audit" && (
                        <div className="space-y-10">
                          <ReviewHistory data={current} />
                          <AuditTrail data={current} />
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
              <aside className="space-y-6">
                <AgentPipeline caseId={selectedId} animate={animate} data={current} onReplayDone={onReplayDone} runKey={runKey} />
              </aside>
            </div>
          </>
        )
      )}
    </AppShell>
  );
}
