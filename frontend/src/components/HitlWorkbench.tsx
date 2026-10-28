// Workbench HITL: ofițerul decide pe fiecare excepție și trimite POST /api/cases/{id}/review. Proprietar: Om5 (construit de Om4).
// Backend-ul reface tot pipeline-ul cu decizia ofițerului și întoarce dosarul recalculat.
import { useMemo, useState, type ReactNode } from "react";
import { Check, LoaderCircle, OctagonAlert, Undo2 } from "lucide-react";
import { api } from "../api/client";
import type { Case, ClassifiedTransaction, ExceptionFlag, IncomeCategory, TxOverride } from "../types/contracts";
import { CATEGORY_LABEL, EXCEPTION_LABEL, formatDate, formatRon } from "../lib/ui";

// Excepții pe care backend-ul nu le poate accepta: dosarul trebuie returnat emitentului
const NOT_APPROVABLE: Record<string, string> = {
  E01: "Debitorul nu poate fi identificat cu datele din adresă. Adresa trebuie returnată executorului cu cererea de a corecta CNP-ul sau numele.",
  E02: "Dosarul de executare e deja înregistrat. A doua adresă nu se procesează; executorului i se comunică faptul că poprirea există deja.",
};

type Choice = { kind: "reclassify"; category: IncomeCategory } | { kind: "accept" };

const CATEGORIES = Object.keys(CATEGORY_LABEL) as IncomeCategory[];

function Option({
  name,
  checked,
  onChange,
  title,
  detail,
  children,
}: {
  name: string;
  checked: boolean;
  onChange: () => void;
  title: string;
  detail?: string;
  children?: ReactNode;
}) {
  return (
    <label
      className={`flex cursor-pointer gap-3 rounded-md border px-4 py-3 transition-colors duration-150 ${
        checked ? "border-ink bg-paper" : "border-line bg-paper hover:border-line-strong"
      }`}
    >
      <input type="radio" name={name} checked={checked} onChange={onChange} className="mt-1 h-4 w-4 shrink-0 accent-ink" />
      <span className="min-w-0 flex-1 text-sm">
        <span className="block font-semibold">{title}</span>
        {detail && <span className="mt-0.5 block text-muted">{detail}</span>}
        {children}
      </span>
    </label>
  );
}

function SuspectTx({ tx }: { tx: ClassifiedTransaction }) {
  return (
    <div className="flex items-baseline justify-between gap-4 rounded-md bg-paper px-4 py-3 ring-1 ring-danger/25">
      <div className="min-w-0">
        <div className="font-semibold">{tx.counterparty_name}</div>
        <div className="text-sm text-muted">
          {tx.description}, primit pe {formatDate(tx.booking_date)}
          <span className="block">
            Clasificat acum ca <span className="font-medium text-ink">{CATEGORY_LABEL[tx.category]}</span>
          </span>
        </div>
      </div>
      <div className="display shrink-0 text-base">{formatRon(tx.amount)}</div>
    </div>
  );
}

function ExceptionDecision({
  e,
  data,
  choice,
  onChoose,
}: {
  e: ExceptionFlag;
  data: Case;
  choice: Choice | undefined;
  onChoose: (c: Choice) => void;
}) {
  const label = EXCEPTION_LABEL[e.code] ?? e.code;
  const txs = data.classified_transactions.filter((t) => e.evidence.includes(t.tx_id));
  const blocked = NOT_APPROVABLE[e.code];
  const name = `decision-${e.code}`;

  return (
    <fieldset className="rounded-lg bg-canvas p-5">
      <legend className="sr-only">{label}</legend>
      <div className="flex items-center gap-2 font-bold text-danger-ink">
        <OctagonAlert size={17} className="text-danger" aria-hidden />
        {label}
      </div>
      <p className="mt-1 text-sm leading-relaxed">{e.message}</p>

      {txs.length > 0 && (
        <div className="mt-4 space-y-2">
          {txs.map((t) => (
            <SuspectTx key={t.tx_id} tx={t} />
          ))}
        </div>
      )}

      {blocked ? (
        <p className="mt-4 rounded-md border border-line-strong bg-paper px-4 py-3 text-sm">
          <span className="font-semibold">Nu poate fi aprobat din aplicație. </span>
          {blocked}
        </p>
      ) : (
        <div className="mt-4 space-y-2">
          <p className="text-sm font-semibold">Decizia ta</p>
          {txs.length > 0 && (
            <>
              <Option
                name={name}
                checked={choice?.kind === "reclassify" && choice.category === "SALARIU"}
                onChange={() => onChoose({ kind: "reclassify", category: "SALARIU" })}
                title="E salariu: reclasifică și oprește cota legală"
                detail="Suma devine venit periodic; se poate opri până la o treime."
              />
              <Option
                name={name}
                checked={choice?.kind === "reclassify" && choice.category !== "SALARIU"}
                onChange={() => onChoose({ kind: "reclassify", category: "ALT_VENIT" })}
                title="Altă categorie"
                detail="Alege natura juridică corectă a încasării."
              >
                {choice?.kind === "reclassify" && choice.category !== "SALARIU" && (
                  <select
                    value={choice.category}
                    onChange={(ev) => onChoose({ kind: "reclassify", category: ev.target.value as IncomeCategory })}
                    className="mt-2 h-9 w-full rounded-md border border-line-strong bg-paper px-2.5 text-sm"
                  >
                    {CATEGORIES.filter((c) => c !== "SALARIU").map((c) => (
                      <option key={c} value={c}>
                        {CATEGORY_LABEL[c]}
                      </option>
                    ))}
                  </select>
                )}
              </Option>
            </>
          )}
          <Option
            name={name}
            checked={choice?.kind === "accept"}
            onChange={() => onChoose({ kind: "accept" })}
            title={txs.length ? `Clasificarea e corectă, rămâne ${CATEGORY_LABEL[txs[0].category]}` : "Am verificat, continuă procesarea"}
            detail={txs.length ? "Suma rămâne protejată; problema se închide." : "Calculul se face cu datele actuale, conform regulilor legale."}
          />
        </div>
      )}
    </fieldset>
  );
}

interface Props {
  data: Case;
  onUpdated: (c: Case) => void;
}

export function HitlWorkbench({ data, onUpdated }: Props) {
  const open = useMemo(() => data.exceptions.filter((e) => !e.resolved), [data]);
  const [choices, setChoices] = useState<Record<string, Choice>>({});
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const actionable = open.filter((e) => !NOT_APPROVABLE[e.code]);
  const missing = actionable.filter((e) => !choices[e.code]);
  const canSubmit = actionable.length > 0 && missing.length === 0 && note.trim().length >= 3 && !busy;

  async function submit() {
    const overrides: TxOverride[] = [];
    const resolve: string[] = [];
    for (const e of actionable) {
      const c = choices[e.code];
      if (c.kind === "accept") resolve.push(e.code);
      else for (const id of e.evidence) if (data.classified_transactions.some((t) => t.tx_id === id)) overrides.push({ tx_id: id, category: c.category, note });
    }
    setBusy(true);
    setError(null);
    try {
      const updated = await api.submitReview(data.case_id, { reviewer: "Ofițer juridic", overrides, resolve_codes: resolve, note });
      setChoices({});
      setNote("");
      onUpdated(updated);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (open.length === 0) return null;

  return (
    <section id="workbench" aria-labelledby="workbench-title" className="scroll-mt-24 rounded-lg ring-2 ring-ink">
      <div className="border-b border-line px-5 py-4">
        <h2 id="workbench-title" className="display text-xl">
          Verificarea ta
        </h2>
        <p className="mt-1 text-sm text-muted">
          {actionable.length
            ? "Decide pentru fiecare problemă. Agenții refac apoi calculul cu decizia ta."
            : "Problemele acestui dosar nu se pot aproba; vezi mai jos ce trebuie făcut."}
        </p>
      </div>

      <div className="space-y-3 p-5">
        {open.map((e) => (
          <ExceptionDecision
            key={e.code + e.message}
            e={e}
            data={data}
            choice={choices[e.code]}
            onChoose={(c) => setChoices((s) => ({ ...s, [e.code]: c }))}
          />
        ))}

        {actionable.length > 0 && (
          <>
            <label className="block pt-2">
              <span className="text-sm font-semibold">Justificarea deciziei</span>
              <span className="ml-1 text-sm text-muted">(rămâne în istoricul dosarului)</span>
              <textarea
                value={note}
                onChange={(e) => setNote(e.target.value)}
                rows={3}
                placeholder="Ex.: Angajatorul a plătit 6.000 lei salariu lunar în ultimele două luni; suma din octombrie e același salariu."
                className="mt-1.5 block w-full resize-y rounded-md border border-line-strong bg-paper px-3 py-2 text-sm outline-none placeholder:text-muted focus:border-ink focus:ring-1 focus:ring-ink"
              />
            </label>

            {error && (
              <p role="alert" className="rounded-md border border-danger/40 bg-danger-soft px-4 py-3 text-sm text-danger-ink">
                Decizia nu a fost salvată: {error}
              </p>
            )}

            <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
              <p className="text-sm text-muted">
                {missing.length
                  ? `Mai ai de decis pentru ${missing.length === 1 ? "o problemă" : `${missing.length} probleme`}.`
                  : note.trim().length < 3
                    ? "Scrie o justificare scurtă."
                    : "Gata de aplicat."}
              </p>
              <div className="flex gap-2">
                {Object.keys(choices).length > 0 && (
                  <button
                    onClick={() => setChoices({})}
                    className="inline-flex h-10 items-center gap-1.5 rounded-md px-3 text-sm font-semibold hover:bg-canvas"
                  >
                    <Undo2 size={15} aria-hidden />
                    Resetează
                  </button>
                )}
                <button
                  onClick={submit}
                  disabled={!canSubmit}
                  className="inline-flex h-10 items-center gap-2 rounded-md bg-ink px-4 text-sm font-semibold text-paper transition-[background-color,transform] duration-150 ease-out hover:bg-ink/85 active:scale-[0.97] disabled:cursor-not-allowed disabled:bg-ink/30"
                >
                  {busy ? <LoaderCircle size={16} className="animate-spin" aria-hidden /> : <Check size={16} aria-hidden />}
                  {busy ? "Se recalculează…" : "Aplică decizia"}
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </section>
  );
}

// Istoricul deciziilor umane pe dosar
export function ReviewHistory({ data }: { data: Case }) {
  if (!data.reviews.length) return null;
  return (
    <section aria-labelledby="history-title">
      <h2 id="history-title" className="display text-xl">
        Istoric decizii
      </h2>
      <ol className="mt-4 divide-y divide-line rounded-lg ring-1 ring-line">
        {data.reviews.map((r, i) => (
          <li key={i} className="px-4 py-3 text-sm">
            <div className="flex justify-between gap-3">
              <span className="font-semibold">{r.reviewer}</span>
              <span className="text-muted">{r.timestamp ? new Date(r.timestamp).toLocaleString("ro-RO", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }) : ""}</span>
            </div>
            <p className="mt-1 text-muted">
              {[
                ...r.overrides.map((o) => `Reclasificat ${o.tx_id} în ${CATEGORY_LABEL[o.category]}`),
                ...r.resolve_codes.map((c) => `Acceptat: ${EXCEPTION_LABEL[c] ?? c}`),
              ].join("; ")}
            </p>
            {r.note && <p className="mt-1">„{r.note}”</p>}
          </li>
        ))}
      </ol>
    </section>
  );
}
