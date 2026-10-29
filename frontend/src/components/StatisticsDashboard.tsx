// „Statistici & Costuri API”: telemetria AWS Bedrock (cost, cache, tokeni, latență) și ROI față de munca manuală,
// din blocul `ai` al GET /api/metrics. Proprietar: Om2.
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { Bot, Coins, DatabaseZap, Gauge, LoaderCircle, RefreshCw, TrendingUp, UserRound } from "lucide-react";
import { api } from "../api/client";
import type { AiTelemetry, PlatformMetrics } from "../types/contracts";
import { ServerDown } from "./ServerDown";

const num = (n: number, digits = 1) => n.toLocaleString("ro-RO", { maximumFractionDigits: digits });
const usd = (n: number) => `$${n.toFixed(n !== 0 && Math.abs(n) < 0.01 ? 6 : 4)}`;
const eur = (n: number, digits = 2) => `${n.toLocaleString("ro-RO", { minimumFractionDigits: digits, maximumFractionDigits: digits })} €`;
const eurSmall = (n: number) => eur(n, n !== 0 && Math.abs(n) < 0.01 ? 6 : 4);

// 42500 -> „42,5k”, 1250000 -> „1,25M”
function compact(n: number) {
  if (n >= 1_000_000) return `${(n / 1_000_000).toLocaleString("ro-RO", { maximumFractionDigits: 2 })}M`;
  if (n >= 1_000) return `${(n / 1_000).toLocaleString("ro-RO", { maximumFractionDigits: 1 })}k`;
  return String(n);
}

function duration(ms: number) {
  if (!ms) return "—";
  return ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toLocaleString("ro-RO", { maximumFractionDigits: 1 })} s`;
}

function Kpi({ icon, label, value, children }: { icon: ReactNode; label: string; value: ReactNode; children?: ReactNode }) {
  return (
    <div className="flex flex-col rounded-lg bg-paper p-5 ring-1 ring-line">
      <p className="flex items-center gap-2 text-sm font-semibold text-muted">
        {icon}
        {label}
      </p>
      <p className="display mt-3 text-[2rem] leading-none tabular-nums">{value}</p>
      <div className="mt-3 space-y-1 text-sm text-muted">{children}</div>
    </div>
  );
}

function Skeleton() {
  return (
    <div aria-busy="true" aria-label="Se încarcă statisticile" className="mt-8 space-y-8">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="h-44 animate-pulse rounded-lg bg-canvas" />
        ))}
      </div>
      <div className="h-64 animate-pulse rounded-lg bg-canvas" />
      <div className="h-48 animate-pulse rounded-lg bg-canvas" />
    </div>
  );
}

function TopKpis({ ai }: { ai: AiTelemetry }) {
  const responses = ai.llm_calls + ai.cache_hits;
  const goodCache = ai.cache_hit_rate > 50;
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <Kpi icon={<Coins size={16} aria-hidden />} label="Cost total AI" value={usd(ai.total_cost_usd)}>
        <p>{eurSmall(ai.total_cost_eur)}</p>
      </Kpi>

      <Kpi
        icon={<DatabaseZap size={16} aria-hidden />}
        label="Eficiență cache SHA-256"
        value={
          <span className="flex items-baseline gap-2">
            {num(ai.cache_hit_rate)}%
            {goodCache && (
              <span className="rounded bg-emerald-50 px-1.5 py-0.5 font-sans text-xs font-bold text-emerald-800 ring-1 ring-emerald-600/30">
                eficient
              </span>
            )}
          </span>
        }
      >
        <p>
          {ai.cache_hits} din {responses} răspunsuri servite din cache
        </p>
        <p>
          <span className="font-semibold text-ink">{usd(ai.cache_savings_usd)}</span> economisiți
        </p>
      </Kpi>

      <Kpi icon={<Gauge size={16} aria-hidden />} label="Volum tokeni & latență" value={compact(ai.input_tokens + ai.output_tokens)}>
        <p>
          {compact(ai.input_tokens)} intrare · {compact(ai.output_tokens)} ieșire
        </p>
        <p>
          <span className="font-semibold text-ink">{duration(ai.avg_llm_latency_ms)}</span> latență medie per apel facturat
        </p>
      </Kpi>

      <Kpi
        icon={<TrendingUp size={16} aria-hidden />}
        label="Multiplicator ROI"
        value={ai.roi_multiple != null ? `${num(ai.roi_multiple)}x` : "N/A"}
      >
        <p>
          <span className="font-semibold text-ink">{num(ai.officer_hours_saved, 2)} h</span> de ofițer economisite
        </p>
        <p>
          <span className="font-semibold text-ink">{eur(ai.net_savings_eur)}</span> economie netă
        </p>
        {ai.roi_multiple == null && <p className="text-xs">Se calculează după primul apel AI facturat.</p>}
      </Kpi>
    </div>
  );
}

function Comparison({ ai, avgProcessingMs }: { ai: AiTelemetry; avgProcessingMs: number }) {
  return (
    <section aria-labelledby="compare-title">
      <h2 id="compare-title" className="display text-2xl">
        Cost AI vs. muncă manuală
      </h2>
      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <div className="rounded-lg bg-canvas p-6 ring-1 ring-line">
          <p className="flex items-center gap-2 font-semibold">
            <UserRound size={18} aria-hidden />
            Procesare tradițională (ofițer bancar)
          </p>
          <dl className="mt-5">
            <dt className="text-sm text-muted">Timp per dosar</dt>
            <dd className="display mt-1 text-3xl tabular-nums">{num(ai.manual_minutes_per_case)} min</dd>
          </dl>
          <p className="mt-5 border-t border-line pt-4 text-sm">
            Cost manual evitat până acum: <span className="font-bold">{eur(ai.manual_cost_avoided_eur)}</span>
          </p>
        </div>

        <div className="rounded-lg bg-sun-soft p-6 ring-1 ring-ink/15">
          <p className="flex items-center gap-2 font-semibold">
            <Bot size={18} aria-hidden />
            Procesare LexOps (AWS Bedrock Nova Pro)
          </p>
          <dl className="mt-5">
            <dt className="text-sm text-muted">Timp per dosar</dt>
            <dd className="display mt-1 text-3xl tabular-nums">{duration(avgProcessingMs)}</dd>
          </dl>
          <p className="mt-5 border-t border-ink/10 pt-4 text-sm">
            Cost AI total până acum: <span className="font-bold">{eurSmall(ai.total_cost_eur)}</span>
          </p>
        </div>
      </div>
      <p className="mt-3 text-xs text-muted">
        Economia de timp se contorizează strict pentru cele {ai.automated_cases} {ai.automated_cases === 1 ? "dosar găsit" : "dosare găsite"} conforme de agenți
        fără intervenția ofițerului (rămâne doar aprobarea finală). Presupuneri: {num(ai.manual_minutes_per_case)} min și{" "}
        {eur(ai.officer_hourly_cost_eur)}/oră pentru un ofițer, configurabile din .env.
      </p>
    </section>
  );
}

function Pricing({ ai }: { ai: AiTelemetry }) {
  return (
    <section aria-labelledby="pricing-title">
      <h2 id="pricing-title" className="display text-2xl">
        Detalii tehnice & tarife Bedrock
      </h2>
      <div className="mt-4 grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <div className="overflow-x-auto rounded-lg ring-1 ring-line">
          <table className="w-full min-w-[480px] text-sm">
            <thead className="bg-canvas text-left text-xs font-semibold text-muted">
              <tr>
                <th className="px-4 py-2.5">Model</th>
                <th className="px-4 py-2.5 text-right">Input / 1K tokeni</th>
                <th className="px-4 py-2.5 text-right">Output / 1K tokeni</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(ai.pricing).map(([model, [input, output]]) => (
                <tr key={model} className="border-t border-line">
                  <td className="px-4 py-2.5 font-mono text-xs">{model}</td>
                  <td className="px-4 py-2.5 text-right tabular-nums">${input}</td>
                  <td className="px-4 py-2.5 text-right tabular-nums">${output}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <dl className="space-y-3 rounded-lg bg-paper p-5 text-sm ring-1 ring-line">
          <div className="flex justify-between gap-4">
            <dt className="text-muted">Apeluri facturate</dt>
            <dd className="font-semibold tabular-nums">{ai.llm_calls}</dd>
          </div>
          <div className="flex justify-between gap-4">
            <dt className="text-muted">Răspunsuri din cache</dt>
            <dd className="font-semibold tabular-nums">{ai.cache_hits}</dd>
          </div>
          <div className="flex justify-between gap-4">
            <dt className="text-muted">Apeluri eșuate (fallback determinist)</dt>
            <dd className={`font-semibold tabular-nums ${ai.failed_calls ? "text-danger-ink" : ""}`}>{ai.failed_calls}</dd>
          </div>
          <div className="flex justify-between gap-4">
            <dt className="text-muted">Timp total în LLM</dt>
            <dd className="font-semibold tabular-nums">{duration(ai.total_llm_latency_ms)}</dd>
          </div>
          <p className="border-t border-line pt-3 text-xs text-muted">Prețuri AWS Bedrock on-demand, lista publică; de reverificat înainte de prezentare.</p>
        </dl>
      </div>
    </section>
  );
}

export function StatisticsDashboard() {
  const [metrics, setMetrics] = useState<PlatformMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    api
      .getMetrics()
      .then((m) => {
        setMetrics(m);
        setError(false);
      })
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, []);

  useEffect(load, [load]);

  return (
    <div className="pt-10">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="display text-[2rem]">Statistici & Costuri API</h1>
          <p className="mt-1 text-muted">
            Telemetrie AWS Bedrock, consum de tokeni și ROI
            {metrics ? ` · ${metrics.total_cases} ${metrics.total_cases === 1 ? "dosar procesat" : "dosare procesate"}` : ""}
          </p>
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="inline-flex h-9 items-center gap-1.5 rounded-md bg-paper px-3 text-sm font-semibold ring-1 ring-line-strong transition-[box-shadow,transform] duration-150 ease-out hover:ring-ink active:scale-[0.97] disabled:opacity-60"
        >
          {loading ? <LoaderCircle size={15} className="animate-spin" aria-hidden /> : <RefreshCw size={15} aria-hidden />}
          Reîmprospătează
        </button>
      </div>

      {error && !metrics ? (
        <div className="mt-8">
          <ServerDown onRetry={load} />
        </div>
      ) : !metrics ? (
        <Skeleton />
      ) : (
        <div className="mt-8 space-y-12">
          <TopKpis ai={metrics.ai} />
          <Comparison ai={metrics.ai} avgProcessingMs={metrics.avg_processing_ms} />
          <Pricing ai={metrics.ai} />
        </div>
      )}
    </div>
  );
}
