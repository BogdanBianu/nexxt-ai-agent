// Layout + bara galbenă de module LexOps. Proprietar: Om4.
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { CircleAlert } from "lucide-react";
import { api } from "../api/client";
import type { ModuleInfo } from "../types/contracts";

interface Props {
  onHome: () => void;
  children: ReactNode;
}

export function AppShell({ onHome, children }: Props) {
  const [modules, setModules] = useState<ModuleInfo[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api
      .listModules()
      .then((m) => {
        setModules(m);
        setError(null);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  useEffect(load, [load]);

  // Cât timp serverul nu răspunde, verificăm periodic ca indicatorul să dispară singur
  useEffect(() => {
    if (!error) return;
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, [error, load]);

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-30 bg-sun">
        <div className="mx-auto flex h-16 max-w-[1440px] items-center gap-8 px-6 lg:px-10">
          <button onClick={onHome} className="display shrink-0 text-[22px]">
            LexOps
          </button>

          <nav className="flex min-w-0 flex-1 items-center gap-1 overflow-x-auto" aria-label="Module">
            {modules.map((m) => {
              const active = m.status === "ACTIVE";
              return active ? (
                <button
                  key={m.module_id}
                  onClick={onHome}
                  title={m.description}
                  aria-current="page"
                  className="display shrink-0 rounded-md bg-ink px-3.5 py-2 text-sm text-sun"
                >
                  {m.name}
                </button>
              ) : (
                <span
                  key={m.module_id}
                  title={`${m.name}: modul în dezvoltare`}
                  aria-disabled
                  className="display shrink-0 cursor-default px-3 py-2 text-sm text-ink/45"
                >
                  {m.name}
                </span>
              );
            })}
          </nav>

          {error ? (
            <div role="alert" className="flex shrink-0 items-center gap-1.5 rounded-md bg-danger px-3 py-1.5 text-sm font-semibold text-paper">
              <CircleAlert size={16} aria-hidden />
              Serverul nu răspunde
            </div>
          ) : (
            <div className="hidden shrink-0 items-center gap-3 md:flex">
              <div className="text-right text-sm leading-tight">
                <div className="font-semibold">Ofițer juridic</div>
                <div className="text-ink/60">Raiffeisen Bank</div>
              </div>
              <div className="grid h-8 w-8 place-items-center rounded-md bg-ink text-xs font-bold text-sun" aria-hidden>
                OJ
              </div>
            </div>
          )}
        </div>
      </header>

      <main className="mx-auto max-w-[1440px] px-6 pb-16 lg:px-10">{children}</main>
    </div>
  );
}
