// Încărcarea unei adrese reale (PDF/.txt): buton + dialog cu drag & drop + overlay de drop pe toată pagina. Proprietar: Om4.
// Backend-ul identifică automat în memorie clientul și conturile sale după CNP / nume / numărul dosarului din document.
import { useEffect, useRef, useState, type DragEvent } from "react";
import { FileText, LoaderCircle, Upload, X } from "lucide-react";
import { uploadDocument } from "../api/client";

const MAX_BYTES = 10 * 1024 * 1024;

function validate(file: File): string | null {
  const okType = file.type === "application/pdf" || /\.(pdf|txt)$/i.test(file.name);
  if (!okType) return "Se acceptă doar fișiere PDF sau .txt.";
  if (file.size === 0) return "Fișierul e gol.";
  if (file.size > MAX_BYTES) return "Fișierul depășește 10 MB.";
  return null;
}

const formatSize = (b: number) => (b < 1024 * 1024 ? `${Math.max(1, Math.round(b / 1024))} KB` : `${(b / 1024 / 1024).toFixed(1)} MB`);

function hasFiles(e: DragEvent | globalThis.DragEvent) {
  return Array.from(e.dataTransfer?.types ?? []).includes("Files");
}

interface DialogProps {
  initialFile: File | null;
  onClose: () => void;
  onUploaded: (caseId: string) => void;
}

function UploadDialog({ initialFile, onClose, onUploaded }: DialogProps) {
  const [file, setFile] = useState<File | null>(null);
  const [over, setOver] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    panelRef.current?.focus();
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && !busy && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [busy, onClose]);

  function pick(f: File) {
    const problem = validate(f);
    setError(problem);
    setFile(problem ? null : f);
  }

  useEffect(() => {
    if (initialFile) pick(initialFile);
  }, [initialFile]);

  async function submit() {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const created = await uploadDocument(file, "AUTO");
      onUploaded(created.case_id);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 grid place-items-center p-4" role="dialog" aria-modal="true" aria-labelledby="upload-title">
      <div className="absolute inset-0 bg-ink/30" onClick={() => !busy && onClose()} />
      <div ref={panelRef} tabIndex={-1} className="relative w-full max-w-lg rounded-lg bg-paper shadow-[0_16px_48px_rgba(0,0,0,0.18)] outline-none">
        <div className="flex items-start justify-between gap-4 border-b border-line px-6 py-4">
          <div>
            <h2 id="upload-title" className="display text-xl">
              Încarcă un document
            </h2>
            <p className="mt-0.5 text-sm text-muted">
              Poprire, sechestru, cerere de la autorități sau alt act. Agenții recunosc tipul și găsesc singuri clientul în Core Banking.
            </p>
          </div>
          <button onClick={onClose} disabled={busy} aria-label="Închide" className="grid h-8 w-8 shrink-0 place-items-center rounded-md hover:bg-canvas">
            <X size={18} aria-hidden />
          </button>
        </div>

        <div className="space-y-4 px-6 py-5">
          {!file ? (
            <div
              onDragOver={(e) => {
                if (!hasFiles(e)) return;
                e.preventDefault();
                setOver(true);
              }}
              onDragLeave={() => setOver(false)}
              onDrop={(e) => {
                e.preventDefault();
                setOver(false);
                const f = e.dataTransfer.files[0];
                if (f) pick(f);
              }}
              className={`flex flex-col items-center rounded-lg border-2 border-dashed px-6 py-10 text-center transition-colors duration-150 ${
                over ? "border-ink bg-sun-soft" : "border-line-strong bg-canvas"
              }`}
            >
              <Upload size={28} strokeWidth={1.75} aria-hidden />
              <p className="mt-3 font-semibold">Trage aici documentul</p>
              <p className="mt-0.5 text-sm text-muted">sau</p>
              <button
                onClick={() => inputRef.current?.click()}
                className="mt-2 inline-flex h-9 items-center rounded-md bg-paper px-3.5 text-sm font-semibold ring-1 ring-line-strong transition-[box-shadow,transform] duration-150 ease-out hover:ring-ink active:scale-[0.97]"
              >
                Alege fișier din calculator
              </button>
              <p className="mt-3 text-xs text-muted">PDF sau .txt, maxim 10 MB</p>
            </div>
          ) : (
            <div className="flex items-center gap-3 rounded-lg bg-canvas px-4 py-3">
              <FileText size={22} strokeWidth={1.75} className="shrink-0" aria-hidden />
              <div className="min-w-0 flex-1">
                <div className="truncate font-semibold">{file.name}</div>
                <div className="text-xs text-muted">{formatSize(file.size)} · Clientul va fi căutat automat în baza de date a băncii</div>
              </div>
              {!busy && (
                <button onClick={() => setFile(null)} className="text-sm font-semibold underline underline-offset-4">
                  Schimbă
                </button>
              )}
            </div>
          )}

          <input
            ref={inputRef}
            type="file"
            accept="application/pdf,.pdf,.txt,text/plain"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) pick(f);
              e.target.value = "";
            }}
          />

          {error && (
            <p role="alert" className="rounded-md border border-danger/40 bg-danger-soft px-4 py-3 text-sm text-danger-ink">
              {error}
            </p>
          )}
        </div>

        <div className="flex justify-end gap-2 border-t border-line px-6 py-4">
          <button onClick={onClose} disabled={busy} className="h-10 rounded-md px-4 text-sm font-semibold hover:bg-canvas">
            Renunță
          </button>
          <button
            onClick={submit}
            disabled={!file || busy}
            className="inline-flex h-10 items-center gap-2 rounded-md bg-ink px-4 text-sm font-semibold text-paper transition-[background-color,transform] duration-150 ease-out hover:bg-ink/85 active:scale-[0.97] disabled:cursor-not-allowed disabled:bg-ink/30"
          >
            {busy && <LoaderCircle size={16} className="animate-spin" aria-hidden />}
            {busy ? "Se citește documentul…" : "Procesează documentul"}
          </button>
        </div>
      </div>
    </div>
  );
}

// Buton + dialog + overlay de drop pe toată pagina. Montat doar pe lista de dosare.
export function UploadDocument({ onUploaded }: { onUploaded: (caseId: string) => void }) {
  const [open, setOpen] = useState(false);
  const [dropped, setDropped] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const depth = useRef(0);

  useEffect(() => {
    if (open) return;
    const enter = (e: globalThis.DragEvent) => {
      if (!hasFiles(e)) return;
      depth.current += 1;
      setDragging(true);
    };
    const leave = () => {
      depth.current = Math.max(0, depth.current - 1);
      if (depth.current === 0) setDragging(false);
    };
    const over = (e: globalThis.DragEvent) => hasFiles(e) && e.preventDefault();
    const drop = (e: globalThis.DragEvent) => {
      if (!hasFiles(e)) return;
      e.preventDefault();
      depth.current = 0;
      setDragging(false);
      const f = e.dataTransfer?.files[0];
      if (f) {
        setDropped(f);
        setOpen(true);
      }
    };
    window.addEventListener("dragenter", enter);
    window.addEventListener("dragleave", leave);
    window.addEventListener("dragover", over);
    window.addEventListener("drop", drop);
    return () => {
      window.removeEventListener("dragenter", enter);
      window.removeEventListener("dragleave", leave);
      window.removeEventListener("dragover", over);
      window.removeEventListener("drop", drop);
    };
  }, [open]);

  return (
    <>
      <button
        onClick={() => {
          setDropped(null);
          setOpen(true);
        }}
        className="inline-flex h-10 items-center gap-2 rounded-md bg-paper px-3.5 text-sm font-semibold ring-1 ring-line-strong transition-[box-shadow,transform] duration-150 ease-out hover:ring-ink active:scale-[0.97]"
      >
        <Upload size={16} aria-hidden />
        Încarcă document
      </button>

      {dragging && !open && (
        <div className="pointer-events-none fixed inset-0 z-40 grid place-items-center bg-sun-soft/90 p-6">
          <div className="flex flex-col items-center rounded-lg border-2 border-dashed border-ink bg-paper px-12 py-10 text-center">
            <Upload size={32} strokeWidth={1.75} aria-hidden />
            <p className="display mt-3 text-2xl">Lasă fișierul aici</p>
            <p className="mt-1 text-sm text-muted">Orice document primit, PDF sau .txt</p>
          </div>
        </div>
      )}

      {open && (
        <UploadDialog
          initialFile={dropped}
          onClose={() => setOpen(false)}
          onUploaded={(id) => {
            setOpen(false);
            onUploaded(id);
          }}
        />
      )}
    </>
  );
}
