// Decizia finală a angajatului: agenții doar marchează dosarul „conform”, omul aprobă sau respinge. Proprietar: Om2.
// Fără aprobare nu se blochează nimic și nu pleacă niciun răspuns (POST /api/cases/{id}/approve | /reject).
import { useState } from "react";
import { Check, ClipboardCheck, LoaderCircle, X } from "lucide-react";
import { api } from "../api/client";
import type { Case } from "../types/contracts";
import { BLOCKS_MONEY } from "../lib/modules";
import { formatRon, humanize } from "../lib/ui";

const REVIEWER = "Ofițer juridic";

const when = (iso: string) =>
  new Date(iso).toLocaleString("ro-RO", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });

// Ce se întâmplă concret dacă angajatul aprobă
function consequence(data: Case) {
  if (data.proposed_status === "LIFTED") return "Dacă aprobi, poprirea se ridică și banii se deblochează.";
  if (BLOCKS_MONEY.has(data.module_id ?? "popriri") && data.decision)
    return `Dacă aprobi, se blochează ${formatRon(data.decision.amount_to_hold)} și se trimite adresa de răspuns.`;
  return "Dacă aprobi, se trimite adresa de răspuns generată de agent.";
}

function Decided({ data }: { data: Case }) {
  const a = data.approval!;
  const ok = a.decision === "APPROVED";
  return (
    <section aria-label="Decizia finală" className={`rounded-lg px-5 py-4 ring-1 ${ok ? "bg-sun-soft ring-ink/20" : "bg-canvas ring-line"}`}>
      <p className="flex items-center gap-2 font-bold">
        {ok ? <Check size={18} aria-hidden /> : <X size={18} aria-hidden />}
        {ok ? "Aprobat" : "Respins"} de {a.reviewer}
        <span className="font-normal text-muted">· {when(a.timestamp)}</span>
      </p>
      {a.note && <p className="mt-1 text-sm">„{a.note}”</p>}
    </section>
  );
}

export function ApprovalPanel({ data, onDecided }: { data: Case; onDecided: (updated: Case) => void }) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState<"approve" | "reject" | null>(null);
  const [error, setError] = useState<string | null>(null);
  // La dosarele oprite de agent, respingerea e o opțiune secundară, ascunsă până o ceri
  const [rejecting, setRejecting] = useState(false);

  if (data.approval) return <Decided data={data} />;
  const pending = data.status === "PENDING_APPROVAL";
  if (!pending && data.status !== "EXCEPTION_FLAGGED") return null;

  async function decide(kind: "approve" | "reject") {
    if (kind === "reject" && note.trim().length < 3) {
      setError("Scrie motivul respingerii; rămâne în istoricul dosarului.");
      return;
    }
    setBusy(kind);
    setError(null);
    try {
      const body = { reviewer: REVIEWER, note: note.trim() || null };
      onDecided(kind === "approve" ? await api.approveCase(data.case_id, body) : await api.rejectCase(data.case_id, body));
    } catch (e) {
      setError(`Decizia nu a fost salvată: ${(e as Error).message}`);
    } finally {
      setBusy(null);
    }
  }

  const noteField = (
    <label className="block">
      <span className="text-sm font-semibold">{pending ? "Observații" : "Motivul respingerii"}</span>
      <span className="ml-1 text-sm text-muted">{pending ? "(obligatorii doar dacă respingi)" : "(rămâne în istoricul dosarului)"}</span>
      <textarea
        value={note}
        onChange={(e) => setNote(e.target.value)}
        rows={2}
        maxLength={2000}
        placeholder="Ex.: Am verificat adresa originală; ștampila executorului lipsește."
        className="mt-1.5 block w-full resize-y rounded-md border border-line-strong bg-paper px-3 py-2 text-sm outline-none placeholder:text-muted focus:border-ink focus:ring-1 focus:ring-ink"
      />
    </label>
  );

  const rejectButton = (
    <button
      onClick={() => void decide("reject")}
      disabled={!!busy}
      className="inline-flex h-10 items-center gap-2 rounded-md border border-danger/50 bg-paper px-4 text-sm font-semibold text-danger-ink transition-[background-color,transform] duration-150 ease-out hover:bg-danger-soft active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-50"
    >
      {busy === "reject" ? <LoaderCircle size={16} className="animate-spin" aria-hidden /> : <X size={16} aria-hidden />}
      Respinge
    </button>
  );

  const errorLine = error && (
    <p role="alert" className="rounded-md border border-danger/40 bg-danger-soft px-4 py-3 text-sm text-danger-ink">
      {error}
    </p>
  );

  if (!pending) {
    return (
      <section aria-label="Respinge dosarul" className="rounded-lg px-5 py-4 ring-1 ring-line">
        {!rejecting ? (
          <p className="flex flex-wrap items-center justify-between gap-3 text-sm text-muted">
            Documentul nu trebuie procesat deloc? Îl poți respinge direct, fără să rezolvi problemele.
            <button onClick={() => setRejecting(true)} className="font-semibold text-danger-ink underline underline-offset-4">
              Respinge dosarul
            </button>
          </p>
        ) : (
          <div className="space-y-3">
            {noteField}
            {errorLine}
            <div className="flex justify-end gap-2">
              <button onClick={() => setRejecting(false)} className="inline-flex h-10 items-center rounded-md px-3 text-sm font-semibold hover:bg-canvas">
                Renunță
              </button>
              {rejectButton}
            </div>
          </div>
        )}
      </section>
    );
  }

  return (
    <section id="approval" aria-labelledby="approval-title" className="scroll-mt-24 rounded-lg ring-2 ring-ink">
      <div className="border-b border-line bg-sun-soft px-5 py-4">
        <h2 id="approval-title" className="display flex items-center gap-2 text-xl">
          <ClipboardCheck size={20} aria-hidden />
          Decizia ta finală
        </h2>
        <p className="mt-1 text-sm">
          Agenții au găsit dosarul conform criteriilor, dar nu l-au aprobat. Până nu decizi, nu se blochează nimic și nu pleacă niciun răspuns.
        </p>
      </div>
      <div className="space-y-3 p-5">
        {data.outcome?.summary && (
          <p className="text-sm">
            <span className="font-semibold">Propunerea agentului: </span>
            {humanize(data.outcome.summary)}
          </p>
        )}
        <p className="text-sm text-muted">{consequence(data)}</p>
        {noteField}
        {errorLine}
        <div className="flex flex-wrap justify-end gap-2 pt-1">
          {rejectButton}
          <button
            onClick={() => void decide("approve")}
            disabled={!!busy}
            className="inline-flex h-10 items-center gap-2 rounded-md bg-ink px-4 text-sm font-semibold text-paper transition-[background-color,transform] duration-150 ease-out hover:bg-ink/85 active:scale-[0.97] disabled:cursor-not-allowed disabled:bg-ink/30"
          >
            {busy === "approve" ? <LoaderCircle size={16} className="animate-spin" aria-hidden /> : <Check size={16} aria-hidden />}
            Aprobă
          </button>
        </div>
      </div>
    </section>
  );
}
