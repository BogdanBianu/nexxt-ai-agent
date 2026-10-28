// Starea „serverul nu răspunde”: explică ce s-a întâmplat, cum se repornește și reîncearcă singură. Proprietar: Om4.
import { useEffect, useState } from "react";
import { LoaderCircle, RotateCw, ServerOff } from "lucide-react";
import { apiBase } from "../api/client";

const RETRY_MS = 5000;

interface Props {
  onRetry: () => void;
  // Reîncercare automată la câteva secunde (implicit da)
  auto?: boolean;
  compact?: boolean;
}

export function ServerDown({ onRetry, auto = true, compact = false }: Props) {
  const [retrying, setRetrying] = useState(false);

  useEffect(() => {
    if (!auto) return;
    const id = setInterval(onRetry, RETRY_MS);
    return () => clearInterval(id);
  }, [auto, onRetry]);

  function retry() {
    setRetrying(true);
    onRetry();
    setTimeout(() => setRetrying(false), 800);
  }

  const button = (
    <button
      onClick={retry}
      className="inline-flex h-10 shrink-0 items-center gap-2 rounded-md bg-ink px-4 text-sm font-semibold text-paper transition-[background-color,transform] duration-150 ease-out hover:bg-ink/85 active:scale-[0.97]"
    >
      {retrying ? <LoaderCircle size={16} className="animate-spin" aria-hidden /> : <RotateCw size={16} aria-hidden />}
      Reîncearcă acum
    </button>
  );

  if (compact) {
    return (
      <div role="alert" className="flex flex-col items-start gap-3 px-5 py-6 text-sm">
        <p className="flex items-center gap-2 font-semibold text-danger-ink">
          <ServerOff size={16} aria-hidden />
          Nu am putut încărca datele de la server.
        </p>
        {button}
      </div>
    );
  }

  return (
    <div role="alert" className="mx-auto mt-16 max-w-xl rounded-lg border border-danger/40 bg-danger-soft px-6 py-6">
      <div className="flex gap-4">
        <ServerOff size={24} className="mt-0.5 shrink-0 text-danger" aria-hidden />
        <div className="min-w-0">
          <h2 className="display text-xl text-danger-ink">Nu ne putem conecta la server</h2>
          <p className="mt-2 text-sm leading-relaxed">
            Backend-ul LexOps nu răspunde la <span className="font-mono text-[13px]">{apiBase()}</span>. Pornește-l dintr-un terminal:
          </p>
          <pre className="mt-3 overflow-x-auto rounded-md bg-paper px-3.5 py-2.5 font-mono text-[12.5px] ring-1 ring-line">
            cd backend{"\n"}../.venv/bin/uvicorn app.main:app --reload --port 8000
          </pre>
          <div className="mt-4 flex flex-wrap items-center gap-3">
            {button}
            {auto && <span className="text-sm text-muted">Reîncercăm automat la fiecare {RETRY_MS / 1000} secunde.</span>}
          </div>
        </div>
      </div>
    </div>
  );
}
