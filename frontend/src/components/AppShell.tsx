// Layout + bara galbenă LexOps. Modulele stau într-un meniu deschis din logo-ul Raiffeisen. Proprietar: Om4.
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { ChevronDown, CircleAlert, House } from "lucide-react";
import { api } from "../api/client";
import type { CaseSummary, ModuleInfo } from "../types/contracts";
import { moduleOf } from "../lib/modules";
import { STATUS_STYLE } from "../lib/ui";
import logo from "../assets/logo_raiffeisen.png";
import { Mascot } from "./Mascot";

interface Props {
  // Modulul afișat acum; null pe pagina de start
  current: string | null;
  onHome: () => void;
  onModule: (moduleId: string) => void;
  children: ReactNode;
}

function ModuleMenu({ modules, current, onHome, onModule }: { modules: ModuleInfo[] } & Omit<Props, "children">) {
  const [open, setOpen] = useState(false);
  const [review, setReview] = useState<Record<string, number>>({});
  const ref = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  // La fiecare deschidere: câte dosare așteaptă decizia, pe module
  useEffect(() => {
    if (!open) return;
    api
      .listCases()
      .then((cases: CaseSummary[]) => {
        const counts: Record<string, number> = {};
        for (const c of cases) if (STATUS_STYLE[c.status].tone === "danger") counts[moduleOf(c)] = (counts[moduleOf(c)] ?? 0) + 1;
        setReview(counts);
      })
      .catch(() => setReview({}));
    const onDown = (e: MouseEvent) => !ref.current?.contains(e.target as Node) && setOpen(false);
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      setOpen(false);
      triggerRef.current?.focus();
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const go = (fn: () => void) => {
    setOpen(false);
    fn();
  };

  const active = modules.filter((m) => m.status === "ACTIVE");
  const planned = modules.filter((m) => m.status !== "ACTIVE");
  const here = modules.find((m) => m.module_id === current)?.name;

  return (
    <div ref={ref} className="relative flex min-w-0 items-center gap-3">
      <button
        ref={triggerRef}
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
        className="group flex shrink-0 items-center gap-2.5 rounded-md py-1.5 pr-2 pl-1.5 transition-colors duration-150 hover:bg-ink/10 active:scale-[0.98]"
      >
        <img src={logo} alt="Raiffeisen Bank" className="h-8 w-8" />
        <span className="display text-[22px]">LexOps</span>
        <ChevronDown
          size={18}
          strokeWidth={2.5}
          aria-hidden
          className={`transition-transform duration-200 ease-[var(--ease-out-strong)] ${open ? "rotate-180" : ""}`}
        />
      </button>

      {here && (
        <span className="display hidden truncate text-[15px] sm:block">
          <span className="mr-3 text-ink/30" aria-hidden>
            /
          </span>
          {here}
        </span>
      )}

      {open && (
        <div
          role="menu"
          aria-label="Module LexOps"
          className="absolute top-full left-0 z-40 mt-2 w-[min(26rem,calc(100vw-2rem))] origin-top-left animate-menu-in overflow-hidden rounded-lg bg-paper shadow-[0_16px_40px_rgba(0,0,0,0.16)] ring-1 ring-ink/10"
        >
          <button
            role="menuitem"
            onClick={() => go(onHome)}
            aria-current={current === null ? "page" : undefined}
            className={`flex w-full animate-item-in items-center gap-3 border-b border-line px-4 py-3 text-left transition-colors duration-150 hover:bg-canvas ${current === null ? "bg-sun-soft" : ""}`}
          >
            <House size={17} aria-hidden />
            <span className="font-semibold">Pagina de start</span>
          </button>

          <p className="px-4 pt-3 pb-1 text-xs font-semibold text-muted">Module</p>
          {active.map((m, i) => {
            const on = m.module_id === current;
            const n = review[m.module_id] ?? 0;
            return (
              <button
                key={m.module_id}
                role="menuitem"
                onClick={() => go(() => onModule(m.module_id))}
                aria-current={on ? "page" : undefined}
                style={{ animationDelay: `${(i + 1) * 25}ms` }}
                className={`group/item relative flex w-full animate-item-in items-start gap-3 px-4 py-2.5 text-left transition-colors duration-150 hover:bg-canvas ${on ? "bg-sun-soft" : ""}`}
              >
                <span className={`mt-1 h-4 w-1 shrink-0 rounded-full ${on ? "bg-ink" : "bg-transparent group-hover/item:bg-ink/25"}`} aria-hidden />
                <span className="min-w-0 flex-1">
                  <span className="display block text-[15px]">{m.name}</span>
                  <span className="mt-0.5 line-clamp-1 text-xs text-muted">{m.description}</span>
                </span>
                {n > 0 && (
                  <span className="mt-0.5 shrink-0 rounded bg-danger px-1.5 py-0.5 text-xs leading-none font-bold text-paper" title={`${n} de verificat`}>
                    {n}
                  </span>
                )}
              </button>
            );
          })}

          {planned.length > 0 && (
            <div className="mt-1 border-t border-line px-4 py-3">
              <p className="text-xs font-semibold text-muted">În pregătire</p>
              <p className="mt-1 text-sm text-ink/50">{planned.map((m) => m.name).join(", ")}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function AppShell({ current, onHome, onModule, children }: Props) {
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
        <div className="mx-auto flex h-16 max-w-[1440px] items-center justify-between gap-8 px-6 lg:px-10">
          <ModuleMenu modules={modules} current={current} onHome={onHome} onModule={onModule} />

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
      {/* Pe pagina de start Lex stă în hero, lângă titlu */}
      {current !== null && <Mascot />}
    </div>
  );
}
