// Compunerea aplicației: lista de dosare ↔ dosarul deschis. Proprietar: Om4 (componentele Om5 se montează în slotul marcat).
import { useCallback, useEffect, useState } from "react";
import { api } from "./api/client";
import { AccountDissection } from "./components/AccountDissection";
import { AgentPipeline } from "./components/AgentPipeline";
import { AppShell } from "./components/AppShell";
import { CaseFacts, CaseFigures, CaseHeader } from "./components/CaseHeader";
import { CaseInbox } from "./components/CaseInbox";
import { SechestreInbox } from "./components/SechestreInbox";
import type { Case } from "./types/contracts";

export default function App() {
  const [activeModule, setActiveModule] = useState<string>("popriri");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [animate, setAnimate] = useState(false);
  const [replayDone, setReplayDone] = useState(false);
  const [current, setCurrent] = useState<Case | null>(null);

  const open = useCallback((caseId: string, fresh: boolean) => {
    setSelectedId(caseId);
    setAnimate(fresh);
    setReplayDone(!fresh);
    window.scrollTo({ top: 0 });
  }, []);

  const home = useCallback(() => {
    setSelectedId(null);
    setCurrent(null);
    window.scrollTo({ top: 0 });
  }, []);

  const onReplayDone = useCallback(() => setReplayDone(true), []);

  useEffect(() => {
    if (!selectedId) return;
    setCurrent(null);
    api.getCase(selectedId).then(setCurrent);
  }, [selectedId]);

  return (
    <AppShell onHome={home} activeModule={activeModule} onSelectModule={setActiveModule}>
      {!selectedId ? (
        activeModule === "sechestre" ? (
          <SechestreInbox onOpen={open} />
        ) : (
          <CaseInbox onOpen={open} />
        )
      ) : (
        <>
          {current && <CaseHeader data={current} pending={!replayDone} onBack={home} />}
          <div className="mt-8 grid items-start gap-8 lg:grid-cols-[minmax(0,1fr)_380px]">
            <div className="min-w-0 space-y-10">
              {current && <CaseFigures data={current} pending={!replayDone} />}
              {current && <CaseFacts data={current} />}
              {current && replayDone && <AccountDissection data={current} />}
              {/* Slot Om5: <HitlWorkbench /> și <DocumentViewer /> */}
            </div>
            <aside className="space-y-6">
              <AgentPipeline caseId={selectedId} animate={animate} data={current} onReplayDone={onReplayDone} />
            </aside>
          </div>
        </>
      )}
    </AppShell>
  );
}
