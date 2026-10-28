// Panoul lateral cu raționamentul detaliat al unui agent. Proprietar: Om4.
// Combină evenimentele agentului (GET /events) cu datele din dosar, explicate pe înțeles pentru un ofițer.
import { useEffect, useRef, useState, type ReactNode } from "react";
import { ArrowLeft, ArrowRight, ChevronDown, OctagonAlert, X } from "lucide-react";
import type { AgentEvent, AgentName, Case, ExceptionFlag } from "../types/contracts";
import { CATEGORY_LABEL, DOC_LABEL, formatDate, formatRon, formatTime, PIPELINE, STATUS_STYLE } from "../lib/ui";

const METHOD_LABEL: Record<string, string> = {
  KEYWORD: "cuvânt-cheie în descriere",
  PAYER_REGISTRY: "registrul de plătitori cunoscuți",
  PATTERN: "tipar recurent în istoric",
  LLM: "model de limbaj (AI)",
  HUMAN: "decizie umană",
  FALLBACK: "regulă implicită",
  REGEX: "extragere după șabloane",
};

const FIELD_LABEL: Record<string, string> = {
  doc_type: "Tip document",
  issuer_name: "Emitent",
  issuer_type: "Tip emitent",
  case_number: "Număr dosar",
  issue_date: "Data emiterii",
  debtor_name: "Nume debitor",
  debtor_id: "CNP debitor",
  creditor_name: "Creditor",
  creditor_type: "Tip creanță",
  principal: "Debit principal",
  enforcement_costs: "Cheltuieli executare",
  total_due: "Total de recuperat",
  consignment_iban: "Cont de consemnare",
  has_signature_and_stamp: "Semnătură și ștampilă",
  references_case_number: "Referință alt dosar",
};

const ISSUER_LABEL: Record<string, string> = {
  EXECUTOR: "Executor judecătoresc",
  ANAF: "ANAF",
  ORGAN_FISCAL_LOCAL: "Organ fiscal local",
  POLITIE: "Poliție",
  PARCHET: "Parchet",
  ALTUL: "Altul",
};

const CREDITOR_LABEL: Record<string, string> = {
  INTRETINERE: "Pensie de întreținere",
  FISCAL: "Creanță fiscală",
  COMERCIAL: "Creanță comercială",
};

// Valoarea unui câmp extras, pe înțeles (enum-uri traduse, date și sume formatate)
function fieldValue(key: string, raw: unknown): string | null {
  if (raw == null || raw === "") return null;
  if (typeof raw === "boolean") return raw ? "Da" : "Nu";
  if (typeof raw === "number") return formatRon(raw);
  const v = String(raw);
  if (key === "doc_type") return DOC_LABEL[v as keyof typeof DOC_LABEL] ?? v;
  if (key === "issuer_type") return ISSUER_LABEL[v] ?? v;
  if (key === "creditor_type") return CREDITOR_LABEL[v] ?? v;
  if (key === "issue_date") return formatDate(v);
  return v;
}

const pct = (n: number) => `${Math.round(n * 100)}%`;

function Confidence({ value }: { value: number }) {
  const low = value < 0.6;
  return (
    <span className="inline-flex items-center gap-2">
      <span className="h-1.5 w-14 overflow-hidden rounded-full bg-line" aria-hidden>
        <span className={`block h-full ${low ? "bg-danger" : "bg-ink"}`} style={{ width: pct(value) }} />
      </span>
      <span className={`w-9 text-right text-xs font-semibold ${low ? "text-danger-ink" : ""}`}>{pct(value)}</span>
    </span>
  );
}

function Block({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="border-t border-line px-6 py-5">
      <h3 className="text-sm font-bold">{title}</h3>
      <div className="mt-3 text-sm leading-relaxed">{children}</div>
    </section>
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-line py-2 last:border-b-0">
      <span className="text-muted">{label}</span>
      <span className="text-right font-medium">{children}</span>
    </div>
  );
}

// Conținutul specific fiecărui agent
function AgentBody({ agent, events, data }: { agent: AgentName; events: AgentEvent[]; data: Case }) {
  const final = [...events].reverse().find((e) => e.status === "COMPLETED" || e.status === "SKIPPED" || e.status === "FAILED");
  const d = (final?.data ?? {}) as Record<string, unknown>;
  const o = data.order;

  switch (agent) {
    case "INTAKE_ROUTER": {
      const file = events.find((e) => e.status === "STARTED")?.data.filename as string | undefined;
      return (
        <>
          <Block title="Ce a primit">
            <p>
              Documentul <span className="font-mono text-[13px]">{file ?? data.document.filename}</span>, sosit pe {formatDate(data.document.received_at)}.
            </p>
          </Block>
          <Block title="Ce a decis">
            <Row label="Tip document">{DOC_LABEL[data.doc_type]}</Row>
            {typeof d.confidence === "number" && (
              <Row label="Încredere">
                <Confidence value={d.confidence} />
              </Row>
            )}
            {typeof d.method === "string" && <Row label="Metodă">{METHOD_LABEL[d.method] ?? d.method}</Row>}
          </Block>
          {typeof d.reason === "string" && (
            <Block title="De ce">
              <p>{d.reason}</p>
            </Block>
          )}
        </>
      );
    }

    case "EXTRACTION":
      if (!o) return null;
      return (
        <>
          <Block title="Ce a extras din adresă">
            <p className="mb-3 text-muted">Fiecare câmp are încrederea cu care a fost citit. Sub 60% e marcat cu roșu.</p>
            {Object.entries(o.field_confidence).map(([k, conf]) => {
              const value = fieldValue(k, (o as unknown as Record<string, unknown>)[k]);
              return (
                <div key={k} className="grid grid-cols-[9rem_1fr_auto] items-baseline gap-3 border-b border-line py-2 last:border-b-0">
                  <span className="text-muted">{FIELD_LABEL[k] ?? k}</span>
                  <span className={`min-w-0 break-words ${value ? "font-medium" : "text-muted"}`}>{value ?? "Nu apare în adresă"}</span>
                  {value ? <Confidence value={conf} /> : <span />}
                </div>
              );
            })}
          </Block>
          <Block title="Cum">
            <p>Metodă: {METHOD_LABEL[o.extraction_method] ?? o.extraction_method}.</p>
          </Block>
        </>
      );

    case "RECONCILIATION": {
      const c = data.customer;
      return (
        <>
          <Block title="Ce a căutat">
            <p>
              Debitorul <span className="font-semibold">{o?.debtor_name ?? "—"}</span> cu CNP{" "}
              <span className="font-mono text-[13px]">{o?.debtor_id ?? "—"}</span> în Core Banking.
            </p>
          </Block>
          {c ? (
            <Block title="Ce a găsit">
              <Row label="Client">{c.full_name}</Row>
              <Row label="ID client">{c.customer_id}</Row>
              <Row label="Status">{c.status}</Row>
              <Row label="Popriri active">{data.active_garnishments.length}</Row>
              <div className="mt-4 space-y-2">
                {data.accounts.map((a) => (
                  <div key={a.iban} className="rounded-lg bg-canvas px-3 py-2.5">
                    <div className="font-mono text-[13px]">{a.iban}</div>
                    <div className="mt-0.5 flex justify-between text-muted">
                      <span>Cont {a.account_type.toLowerCase()}</span>
                      <span className="font-semibold text-ink">{formatRon(a.current_balance)}</span>
                    </div>
                  </div>
                ))}
              </div>
            </Block>
          ) : (
            <Block title="Ce a găsit">
              <p>Debitorul nu a putut fi identificat, deci pașii următori nu au rulat.</p>
            </Block>
          )}
        </>
      );
    }

    case "INCOME_CLASSIFIER":
      return (
        <Block title="Cum a clasificat fiecare încasare">
          <p className="mb-3 text-muted">Natura juridică decide cât se poate opri. Fiecare decizie are metoda și motivul ei.</p>
          <div className="space-y-2.5">
            {data.classified_transactions.map((tx) => (
              <div key={tx.tx_id} className="rounded-lg bg-canvas px-3.5 py-3">
                <div className="flex items-baseline justify-between gap-3">
                  <span className="font-semibold">{tx.counterparty_name}</span>
                  <span className="display shrink-0 text-sm">{formatRon(tx.amount)}</span>
                </div>
                <div className="text-muted">{tx.description}</div>
                <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
                  <span>
                    Clasificat ca <span className="font-semibold">{CATEGORY_LABEL[tx.category]}</span>, prin {METHOD_LABEL[tx.method] ?? tx.method}
                  </span>
                  <Confidence value={tx.confidence} />
                </div>
                <p className="mt-1.5 text-muted">{tx.rationale}</p>
              </div>
            ))}
          </div>
        </Block>
      );

    case "RULE_ENGINE": {
      const dec = data.decision;
      if (!dec) return null;
      return (
        <>
          <Block title="Regulile aplicate">
            <p className="mb-3 text-muted">Calcul determinist, fără AI, versiunea de reguli {dec.rules_version}.</p>
            <div className="space-y-2.5">
              {dec.rules_applied.map((r) => (
                <div key={r.rule_id} className="rounded-lg bg-canvas px-3.5 py-3">
                  <div className="flex items-baseline justify-between gap-3">
                    <span className="font-semibold">{r.legal_source}</span>
                    <span className="font-mono text-xs text-muted">{r.rule_id}</span>
                  </div>
                  <p className="mt-1 text-muted">{r.description}</p>
                  <p className="mt-2">
                    Din {formatRon(r.base_amount)} se pot opri <span className="font-bold">{formatRon(r.seizable_amount)}</span>.
                  </p>
                </div>
              ))}
            </div>
          </Block>
          <Block title="Rezultatul calculului">
            <Row label="Total de recuperat">{formatRon(dec.total_due)}</Row>
            <Row label="Se indisponibilizează">{formatRon(dec.amount_to_hold)}</Row>
            <Row label="Rămâne clientului">{formatRon(dec.amount_protected)}</Row>
          </Block>
        </>
      );
    }

    case "ANOMALY": {
      const mine = data.exceptions.filter((e) => e.agent === "ANOMALY" && !e.resolved);
      const suspects = data.classified_transactions.filter((tx) => mine.some((e) => e.evidence.includes(tx.tx_id)));
      return (
        <>
          <Block title="Ce a verificat">
            <p>Compară încasările din perioada analizată cu istoricul contului, ca să prindă venituri reclasificate după primirea popririi.</p>
            {mine.length === 0 && <p className="mt-3 font-semibold">Nicio tentativă de eludare găsită.</p>}
          </Block>
          {suspects.length > 0 && (
            <Block title={suspects.length === 1 ? "Tranzacția suspectă" : "Tranzacțiile suspecte"}>
              <div className="space-y-2.5">
                {suspects.map((tx) => (
                  <div key={tx.tx_id} className="rounded-lg bg-danger-soft px-3.5 py-3 ring-1 ring-danger/25">
                    <div className="flex items-baseline justify-between gap-3">
                      <span className="font-semibold text-danger-ink">{tx.counterparty_name}</span>
                      <span className="display shrink-0 text-sm">{formatRon(tx.amount)}</span>
                    </div>
                    <div className="text-muted">
                      {tx.description}, {formatDate(tx.booking_date)}
                    </div>
                    <p className="mt-2">
                      Declarată ca <span className="font-semibold">{CATEGORY_LABEL[tx.category]}</span>, deci protejată integral. Dacă e de fapt salariu, se poate opri o treime.
                    </p>
                  </div>
                ))}
              </div>
            </Block>
          )}
          {mine.length > 0 && (
            <Block title="Ce trebuie să faci">
              <ol className="list-decimal space-y-1 pl-5">
                <li>Verifică istoricul plăților de la acest angajator.</li>
                <li>Dacă suma e salariu deghizat, reclasific-o în „Salariu”.</li>
                <li>Dosarul se recalculează și se trimite răspunsul către executor.</li>
              </ol>
            </Block>
          )}
        </>
      );
    }

    case "OUTCOME":
      return (
        <Block title="Decizia finală">
          <Row label="Status">{STATUS_STYLE[data.status].label}</Row>
          <Row label="Scrisoare de răspuns">{data.outcome?.response_letter_text ? "Generată" : "Negenerată"}</Row>
          {data.outcome && <p className="mt-3">{data.outcome.summary}</p>}
        </Block>
      );
  }
}

function ExceptionCard({ e, data }: { e: ExceptionFlag; data: Case }) {
  // Dovezile sunt ID-uri de tranzacții sau nume de câmpuri; le arătăm pe înțeles când le putem găsi
  const tx = e.evidence.length
    ? e.evidence
        .map((id) => {
          const t = data.classified_transactions.find((x) => x.tx_id === id);
          return t ? `${t.counterparty_name}, ${formatRon(t.amount)}` : FIELD_LABEL[id] ?? id;
        })
        .join("; ")
    : null;
  return (
    <div className="mx-6 mt-5 flex gap-3 rounded-md border border-danger/40 bg-danger-soft px-4 py-3.5">
      <OctagonAlert size={18} className="mt-0.5 shrink-0 text-danger" aria-hidden />
      <div className="min-w-0 text-sm">
        <p className="font-bold text-danger-ink">{e.severity === "BLOCKING" ? "Problemă blocantă" : "Avertisment"}</p>
        <p className="mt-0.5">{e.message}</p>
        {tx && <p className="mt-1.5 text-xs text-muted">Dovezi: {tx}</p>}
      </div>
    </div>
  );
}

interface Props {
  agent: AgentName;
  events: AgentEvent[];
  data: Case;
  onNavigate: (agent: AgentName) => void;
  onClose: () => void;
}

export function AgentDrawer({ agent, events, data, onNavigate, onClose }: Props) {
  const [shown, setShown] = useState(false);
  const [rawOpen, setRawOpen] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);

  const idx = PIPELINE.findIndex((p) => p.agent === agent);
  const node = PIPELINE[idx];
  const prev = PIPELINE[idx - 1];
  const next = PIPELINE[idx + 1];
  const mine = events.filter((e) => e.agent === agent);
  const exc = data.exceptions.filter((e) => e.agent === agent && !e.resolved);
  const last = mine[mine.length - 1];

  useEffect(() => {
    const id = requestAnimationFrame(() => setShown(true));
    panelRef.current?.focus();
    return () => cancelAnimationFrame(id);
  }, []);

  useEffect(() => {
    setRawOpen(false);
    panelRef.current?.scrollTo({ top: 0 });
  }, [agent]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowRight" && next) onNavigate(next.agent);
      if (e.key === "ArrowLeft" && prev) onNavigate(prev.agent);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [next, prev, onClose, onNavigate]);

  return (
    <div className="fixed inset-0 z-50" role="dialog" aria-modal="true" aria-labelledby="drawer-title">
      <div
        onClick={onClose}
        className={`absolute inset-0 bg-ink/30 transition-opacity duration-200 motion-reduce:transition-none ${shown ? "opacity-100" : "opacity-0"}`}
      />
      <div
        ref={panelRef}
        tabIndex={-1}
        className={`absolute inset-y-0 right-0 flex w-full max-w-[560px] flex-col bg-paper shadow-[-16px_0_40px_rgba(0,0,0,0.12)] outline-none transition-transform duration-200 ease-[cubic-bezier(0.25,1,0.5,1)] motion-reduce:transition-none ${
          shown ? "translate-x-0" : "translate-x-full"
        }`}
      >
        <header className="flex items-start justify-between gap-4 border-b border-line px-6 pt-5 pb-4">
          <div>
            <p className="text-sm text-muted">
              Agentul {idx + 1} din {PIPELINE.length}
              {last ? `, ${formatTime(last.timestamp)}` : ""}
            </p>
            <h2 id="drawer-title" className="display mt-1 text-2xl">
              {node.label}
            </h2>
            <p className="mt-0.5 text-sm text-muted">{node.hint}</p>
          </div>
          <button onClick={onClose} aria-label="Închide" className="grid h-8 w-8 place-items-center rounded-md hover:bg-canvas">
            <X size={20} aria-hidden />
          </button>
        </header>

        <div className="flex-1 overflow-y-auto pb-6">
          {exc.map((e) => (
            <ExceptionCard key={e.code + e.message} e={e} data={data} />
          ))}

          {mine.length === 0 ? (
            <p className="px-6 py-8 text-sm text-muted">Acest agent nu a rulat pentru dosarul curent.</p>
          ) : (
            <>
              {last?.status === "SKIPPED" && (
                <p className="mx-6 mt-5 rounded-lg bg-canvas px-4 py-3 text-sm">
                  <span className="font-semibold">Oprit: </span>
                  {last.message}
                </p>
              )}
              <AgentBody agent={agent} events={mine} data={data} />

              <section className="border-t border-line px-6 py-4">
                <button
                  onClick={() => setRawOpen((v) => !v)}
                  aria-expanded={rawOpen}
                  className="flex w-full items-center justify-between text-sm font-semibold"
                >
                  Jurnal tehnic ({mine.length} evenimente)
                  <ChevronDown size={16} aria-hidden className={`transition-transform duration-150 ${rawOpen ? "rotate-180" : ""}`} />
                </button>
                {rawOpen && (
                  <ol className="mt-3 space-y-3">
                    {mine.map((e) => (
                      <li key={e.seq} className="text-xs">
                        <div className="flex gap-2">
                          <span className="font-mono text-muted">{formatTime(e.timestamp)}</span>
                          <span className="font-semibold">{e.status}</span>
                          <span className="min-w-0 break-words">{e.message}</span>
                        </div>
                        {Object.keys(e.data).length > 0 && (
                          <pre className="mt-1.5 overflow-x-auto rounded-md bg-canvas p-2.5 font-mono text-[11px] leading-relaxed text-ink/80">
                            {JSON.stringify(e.data, null, 2)}
                          </pre>
                        )}
                      </li>
                    ))}
                  </ol>
                )}
              </section>
            </>
          )}
        </div>

        <footer className="grid grid-cols-2 border-t border-line">
          <button
            onClick={() => prev && onNavigate(prev.agent)}
            disabled={!prev}
            className="flex items-center gap-2 px-6 py-4 text-left text-sm font-semibold hover:bg-canvas disabled:text-ink/25 disabled:hover:bg-transparent"
          >
            <ArrowLeft size={16} aria-hidden />
            {prev ? prev.label : "Început"}
          </button>
          <button
            onClick={() => next && onNavigate(next.agent)}
            disabled={!next}
            className="flex items-center justify-end gap-2 border-l border-line px-6 py-4 text-right text-sm font-semibold hover:bg-canvas disabled:text-ink/25 disabled:hover:bg-transparent"
          >
            {next ? next.label : "Sfârșit"}
            <ArrowRight size={16} aria-hidden />
          </button>
        </footer>
      </div>
    </div>
  );
}
