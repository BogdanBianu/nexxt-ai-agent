// Agentul „Explain & Cite” (POST /api/cases/{id}/ask): ofițerul sau juriul întreabă liber de ce dosarul
// a fost soluționat așa, iar răspunsul citează regula (cu articolul de lege), excepția sau tranzacția. Proprietar: Om2.
import { useState, type FormEvent, type KeyboardEvent } from "react";
import { LoaderCircle, OctagonAlert, Receipt, Scale, Send, Sparkles } from "lucide-react";
import { api } from "../api/client";
import type { Case, CaseAnswer, Citation } from "../types/contracts";
import { EXCEPTION_LABEL, formatTime } from "../lib/ui";

// Întrebările propuse depind de modul: fiecare are alt „de ce” tipic
function suggestions(c: Case): string[] {
  const open = c.exceptions.some((e) => !e.resolved);
  const base = open ? ["De ce a ajuns dosarul la un ofițer?"] : [];
  if (c.status === "ROUTED_TO_OTHER_MODULE") return ["De ce nu a fost procesat automat?"];
  switch (c.module_id) {
    case "popriri":
      return [...base, "De ce nu s-au poprit toți banii?", "Ce sume sunt protejate de lege?"];
    case "sechestre":
      return [...base, "De ce s-a înghețat această sumă?", "Ce rămâne protejat?"];
    case "insolventa":
      return c.doc_type === "CERTIFICAT_MOSTENITOR"
        ? [...base, "Cât primește fiecare moștenitor?"]
        : [...base, "Ce se întâmplă cu popririle active?"];
    case "gdpr":
      return [...base, "De ce nu ștergem toate datele clientului?", "Pe ce temei legal s-a răspuns?"];
    default:
      return [...base, "De ce a fost soluționat așa?"];
  }
}

function CitationRow({ c }: { c: Citation }) {
  const icon =
    c.kind === "RULE" ? <Scale size={14} aria-hidden /> : c.kind === "EXCEPTION" ? <OctagonAlert size={14} aria-hidden /> : <Receipt size={14} aria-hidden />;
  const detail = c.kind === "RULE" ? c.legal_source : c.kind === "EXCEPTION" ? (EXCEPTION_LABEL[c.ref] ?? c.text) : c.text;
  return (
    <li className={`flex gap-2 rounded-md px-2.5 py-1.5 text-xs ${c.kind === "EXCEPTION" ? "bg-danger-soft text-danger-ink" : "bg-canvas"}`}>
      <span className="mt-px shrink-0 text-muted">{icon}</span>
      <span className="min-w-0">
        <span className="font-mono font-semibold">{c.ref}</span>
        {detail && <span className={`block break-words ${c.kind === "EXCEPTION" ? "" : "text-muted"}`}>{detail}</span>}
      </span>
    </li>
  );
}

function AnswerCard({ a }: { a: CaseAnswer }) {
  return (
    <article className="space-y-2.5 border-t border-line px-5 py-4">
      <p className="text-sm font-semibold">{a.question}</p>
      <p className="text-sm leading-relaxed break-words whitespace-pre-line">{a.answer}</p>
      {a.citations.length > 0 && (
        <div>
          <h4 className="mb-1.5 text-xs font-semibold text-muted">Surse din dosar</h4>
          <ul className="space-y-1.5">
            {a.citations.map((c, i) => (
              <CitationRow key={`${c.ref}-${i}`} c={c} />
            ))}
          </ul>
        </div>
      )}
      <p className="text-xs text-muted">
        {a.method === "LLM" ? "Formulat de AI din faptele dosarului" : "Compus din regulile dosarului"} · {formatTime(a.answered_at)}
      </p>
    </article>
  );
}

export function CaseCopilot({ data }: { data: Case }) {
  const [question, setQuestion] = useState("");
  const [answers, setAnswers] = useState<CaseAnswer[]>([]);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function ask(text: string) {
    const q = text.trim();
    if (q.length < 3 || pending) return;
    setPending(true);
    setError(null);
    try {
      const a = await api.askCase(data.case_id, { question: q, asked_by: "ofițer" });
      setAnswers((prev) => [a, ...prev]);
      setQuestion("");
    } catch {
      setError("Nu am putut obține un răspuns. Verifică dacă serverul rulează și încearcă din nou.");
    } finally {
      setPending(false);
    }
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    void ask(question);
  }

  // Enter trimite, Shift+Enter rând nou
  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void ask(question);
    }
  }

  return (
    <section aria-labelledby="copilot-title" className="rounded-lg bg-paper ring-1 ring-line">
      <div className="flex items-baseline justify-between gap-3 border-b border-line px-5 py-4">
        <h2 id="copilot-title" className="display flex items-center gap-2 text-base">
          <Sparkles size={16} aria-hidden />
          Întreabă despre dosar
        </h2>
        <span className="text-xs text-muted">cu temei legal</span>
      </div>

      <form onSubmit={onSubmit} className="space-y-3 px-5 py-4">
        <label htmlFor="copilot-question" className="sr-only">
          Întrebarea ta despre dosar
        </label>
        <textarea
          id="copilot-question"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={onKeyDown}
          rows={3}
          maxLength={1000}
          placeholder="Ex.: De ce nu s-au poprit toți banii din cont?"
          className="w-full resize-none rounded-md bg-paper px-3 py-2 text-sm ring-1 ring-line-strong outline-none placeholder:text-muted/80 focus:ring-2 focus:ring-ink"
        />
        <div className="flex flex-wrap gap-1.5">
          {suggestions(data).map((s) => (
            <button
              key={s}
              type="button"
              disabled={pending}
              onClick={() => void ask(s)}
              className="rounded-full bg-canvas px-2.5 py-1 text-xs font-medium ring-1 ring-line transition-colors duration-150 hover:bg-sun-soft hover:ring-ink disabled:opacity-50"
            >
              {s}
            </button>
          ))}
        </div>
        <button
          type="submit"
          disabled={pending || question.trim().length < 3}
          className="inline-flex h-9 items-center gap-1.5 rounded-md bg-ink px-3.5 text-sm font-semibold text-paper transition-[opacity,transform] duration-150 ease-out active:scale-[0.97] disabled:opacity-40"
        >
          {pending ? <LoaderCircle size={15} className="animate-spin" aria-hidden /> : <Send size={15} aria-hidden />}
          {pending ? "Caut în dosar…" : "Întreabă"}
        </button>
        {error && (
          <p role="alert" className="text-sm text-danger-ink">
            {error}
          </p>
        )}
      </form>

      <div aria-live="polite">
        {answers.map((a) => (
          <AnswerCard key={a.answered_at + a.question} a={a} />
        ))}
      </div>
    </section>
  );
}
