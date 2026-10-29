// Butonul „Rulează toate scenariile”: trimite pe rând prin agenți toate scenariile predefinite (S1..S26).
// Pe rând, nu în paralel: registrul de popriri al sesiunii trebuie să le vadă în ordine. Proprietar: Om2.
import { useState } from "react";
import { LoaderCircle, Play } from "lucide-react";
import { api } from "../api/client";
import type { CaseStatus } from "../types/contracts";
import { STATUS_STYLE } from "../lib/ui";

// „S10” după „S9”, nu după „S1”
const order = (id: string) => Number(id.replace(/\D/g, "")) || 0;

interface Result {
  total: number;
  pending: number;
  flagged: number;
  failed: number;
}

export function RunAllScenarios({ onProgress }: { onProgress: () => void }) {
  const [running, setRunning] = useState(false);
  const [current, setCurrent] = useState<{ id: string; index: number; total: number } | null>(null);
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function runAll() {
    setRunning(true);
    setResult(null);
    setError(null);
    try {
      const ids = (await api.listScenarios()).map((s) => s.scenario_id).sort((a, b) => order(a) - order(b));
      const statuses: (CaseStatus | null)[] = [];
      for (const [index, id] of ids.entries()) {
        setCurrent({ id, index: index + 1, total: ids.length });
        statuses.push(await api.createFromScenario(id).then((c) => c.status).catch(() => null));
        onProgress();                          // lista de dosare crește pe măsură ce rulează
      }
      setResult({
        total: ids.length,
        pending: statuses.filter((s) => s === "PENDING_APPROVAL").length,
        flagged: statuses.filter((s) => s && STATUS_STYLE[s].tone === "danger").length,
        failed: statuses.filter((s) => s === null).length,
      });
    } catch {
      setError("Lista de scenarii nu a putut fi încărcată. Verifică dacă serverul rulează.");
    } finally {
      setRunning(false);
      setCurrent(null);
    }
  }

  return (
    <section aria-label="Scenarii predefinite" className="mt-10 rounded-lg bg-canvas px-5 py-4 ring-1 ring-line">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="min-w-0">
          <p className="font-semibold">Scenarii predefinite</p>
          <p aria-live="polite" className="mt-0.5 text-sm text-muted">
            {current ? (
              <>
                Rulez <span className="font-semibold text-ink">{current.id}</span> · {current.index} din {current.total}
              </>
            ) : result ? (
              <>
                {result.total} scenarii rulate: {result.pending} de aprobat, {result.flagged} cu probleme
                {result.failed > 0 && <span className="font-semibold text-danger-ink">, {result.failed} eșuate</span>}.
              </>
            ) : (
              "Trimite prin agenți toate documentele demo (popriri, sechestre, insolvență, GDPR, autorități)."
            )}
          </p>
          {error && (
            <p role="alert" className="mt-1 text-sm text-danger-ink">
              {error}
            </p>
          )}
        </div>
        <button
          onClick={() => void runAll()}
          disabled={running}
          className="inline-flex h-10 shrink-0 items-center gap-2 rounded-md bg-ink px-4 text-sm font-semibold text-paper transition-[background-color,transform] duration-150 ease-out hover:bg-ink/85 active:scale-[0.97] disabled:cursor-not-allowed disabled:bg-ink/40"
        >
          {running ? <LoaderCircle size={16} className="animate-spin" aria-hidden /> : <Play size={16} aria-hidden />}
          {running ? "Se rulează…" : "Rulează toate scenariile"}
        </button>
      </div>
      {current && (
        <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-line" aria-hidden>
          <div
            className="h-full rounded-full bg-ink transition-[width] duration-200 ease-out"
            style={{ width: `${(current.index / current.total) * 100}%` }}
          />
        </div>
      )}
    </section>
  );
}
