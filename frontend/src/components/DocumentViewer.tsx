// Adresa primită ↔ răspunsul băncii, una lângă alta. Proprietar: Om5 (construit de Om4).
// În adresă evidențiem valorile pe care agentul de extragere le-a citit, ca ofițerul să vadă sursa fiecărei date.
import { useState, type ReactNode } from "react";
import { Download, FileText, LoaderCircle } from "lucide-react";
import { api } from "../api/client";
import type { Case } from "../types/contracts";
import { formatDate } from "../lib/ui";

const escape = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

// Împarte textul în bucăți și marchează aparițiile valorilor extrase
function highlight(text: string, values: string[]): ReactNode[] {
  const needles = [...new Set(values.filter((v) => v && v.length >= 3))].sort((a, b) => b.length - a.length);
  if (!needles.length) return [text];
  const re = new RegExp(`(${needles.map(escape).join("|")})`, "gi");
  return text.split(re).map((part, i) =>
    i % 2 === 1 ? (
      <mark key={i} className="rounded-sm bg-sun px-0.5 text-ink">
        {part}
      </mark>
    ) : (
      part
    ),
  );
}

function Paper({ children }: { children: ReactNode }) {
  return (
    <div className="max-h-[560px] overflow-y-auto rounded-md bg-paper px-6 py-5 text-[13.5px] leading-relaxed whitespace-pre-wrap ring-1 ring-line">
      {children}
    </div>
  );
}

// Backend-ul e pe alt port, deci atributul `download` e ignorat: luăm fișierul ca blob și îl salvăm noi
async function downloadResponse(data: Case) {
  const res = await fetch(api.responsePdfUrl(data.case_id));
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const blob = await res.blob();
  const ext = blob.type.includes("pdf") ? "pdf" : "txt";
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `raspuns_${data.order?.case_number?.replace("/", "-") ?? data.case_id}.${ext}`;
  a.click();
  URL.revokeObjectURL(url);
}

export function DocumentViewer({ data }: { data: Case }) {
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const o = data.order;
  const letter = data.outcome?.response_letter_text;
  const marks = [o?.case_number, o?.debtor_name, o?.debtor_id, o?.issuer_name, o?.creditor_name, o?.consignment_iban].filter(
    (v): v is string => !!v,
  );

  const missingLetter =
    data.status === "ROUTED_TO_OTHER_MODULE"
      ? "Documentul a fost redirecționat către alt modul; PopririZero nu generează răspuns."
      : data.exceptions.some((e) => !e.resolved)
        ? "Răspunsul către executor se generează după ce rezolvi problemele dosarului."
        : "Pentru acest dosar nu s-a generat un răspuns.";

  return (
    <div className="grid gap-6 xl:grid-cols-2">
      <section aria-labelledby="doc-in-title" className="min-w-0">
        <div className="flex items-end justify-between gap-3">
          <div className="min-w-0">
            <h3 id="doc-in-title" className="display text-lg">
              Adresa primită
            </h3>
            <p className="mt-0.5 flex items-center gap-1.5 truncate text-sm text-muted">
              <FileText size={14} className="shrink-0" aria-hidden />
              {data.document.filename}, {formatDate(data.document.received_at)}
            </p>
          </div>
          {marks.length > 0 && (
            <span className="flex shrink-0 items-center gap-1.5 text-xs text-muted">
              <span className="h-3 w-4 rounded-sm bg-sun" aria-hidden />
              Citit de agent
            </span>
          )}
        </div>
        <div className="mt-3">
          {data.document.text ? (
            <Paper>{highlight(data.document.text, marks)}</Paper>
          ) : (
            <p className="rounded-md border border-dashed border-line-strong px-5 py-8 text-sm text-muted">Textul documentului nu e disponibil.</p>
          )}
        </div>
      </section>

      <section aria-labelledby="doc-out-title" className="min-w-0">
        <div className="flex items-end justify-between gap-3">
          <div>
            <h3 id="doc-out-title" className="display text-lg">
              Răspunsul băncii
            </h3>
            <p className="mt-0.5 text-sm text-muted">Generat automat, către {o?.issuer_name ?? "emitent"}</p>
          </div>
          {letter && (
            <button
              onClick={() => {
                setDownloading(true);
                setDownloadError(null);
                downloadResponse(data)
                  .catch((e: Error) => setDownloadError(e.message))
                  .finally(() => setDownloading(false));
              }}
              disabled={downloading}
              className="inline-flex h-9 shrink-0 items-center gap-1.5 rounded-md bg-ink px-3.5 text-sm font-semibold text-paper transition-[background-color,transform] duration-150 ease-out hover:bg-ink/85 active:scale-[0.97] disabled:bg-ink/40"
            >
              {downloading ? <LoaderCircle size={15} className="animate-spin" aria-hidden /> : <Download size={15} aria-hidden />}
              Descarcă PDF
            </button>
          )}
        </div>
        {downloadError && (
          <p role="alert" className="mt-2 text-sm text-danger-ink">
            PDF-ul nu a putut fi generat ({downloadError}).
          </p>
        )}
        <div className="mt-3">
          {letter ? (
            <Paper>{letter}</Paper>
          ) : (
            <p className="rounded-md border border-dashed border-line-strong px-5 py-8 text-sm">{missingLetter}</p>
          )}
        </div>
      </section>
    </div>
  );
}
