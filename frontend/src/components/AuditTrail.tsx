// Jurnalul de audit al dosarului (GET /api/cases/{id}/audit): cine a făcut ce și când. Proprietar: Om4.
import { useEffect, useState } from "react";
import { Bot, Download, UserRound } from "lucide-react";
import { api } from "../api/client";
import type { AgentName, AuditEntry, Case, IncomeCategory } from "../types/contracts";
import { CATEGORY_LABEL, EXCEPTION_LABEL, formatTime, humanize, PIPELINE } from "../lib/ui";

const AGENT_LABEL = Object.fromEntries(PIPELINE.map((p) => [p.agent, p.label])) as Record<AgentName, string>;

const ACTION_LABEL: Record<string, string> = {
  STARTED: "A început",
  PROGRESS: "Pas intermediar",
  COMPLETED: "A finalizat",
  SKIPPED: "Oprit",
  FAILED: "Eșuat",
  RULE_APPLIED: "Regulă aplicată",
  EXCEPTION_RAISED: "Problemă semnalată",
  HITL_REVIEW: "Decizie ofițer",
  CASE_APPROVED: "Aprobat",
  CASE_REJECTED: "Respins",
};

// Intrările care contează pentru un auditor: decizii umane, rezultate, reguli, opriri
const isDecision = (e: AuditEntry) => e.actor.startsWith("user:") || !["STARTED", "PROGRESS"].includes(e.action);

function actorOf(e: AuditEntry) {
  if (e.actor.startsWith("user:")) return { human: true, name: e.actor.slice(5) };
  return { human: false, name: AGENT_LABEL[e.actor as AgentName] ?? e.actor };
}

function describe(e: AuditEntry) {
  const d = e.details;
  if (e.action === "HITL_REVIEW") {
    const overrides = (d.overrides as { tx_id: string; category: IncomeCategory }[] | undefined) ?? [];
    const resolved = (d.resolve_codes as string[] | undefined) ?? [];
    const parts = [
      ...overrides.map((o) => `Reclasificat ${o.tx_id} în ${CATEGORY_LABEL[o.category] ?? o.category}`),
      ...resolved.map((c) => `Acceptat: ${EXCEPTION_LABEL[c] ?? c}`),
    ];
    return `${parts.join("; ")}${typeof d.note === "string" && d.note ? `. Justificare: „${d.note}”` : ""}`;
  }
  if (e.action === "CASE_APPROVED" || e.action === "CASE_REJECTED")
    return typeof d.note === "string" && d.note ? `Motiv: „${d.note}”` : "Propunerea agentului a fost confirmată";
  if (e.action === "EXCEPTION_RAISED" && typeof d.code === "string")
    return `${EXCEPTION_LABEL[d.code] ?? d.code}: ${typeof d.message === "string" ? humanize(d.message) : ""}`;
  if (typeof d.message === "string") return humanize(d.message);
  if (e.action === "RULE_APPLIED" && typeof d.legal_source === "string") return `${d.rule_id ?? ""} ${d.legal_source}`.trim();
  if (typeof d.note === "string") return d.note;
  return Object.keys(d).length ? JSON.stringify(d) : "";
}

function toCsv(caseId: string, rows: AuditEntry[]) {
  const q = (v: string) => `"${v.replace(/"/g, '""')}"`;
  const lines = [["dosar", "timestamp", "actor", "actiune", "detalii"].join(",")];
  for (const e of rows) lines.push([caseId, e.timestamp, e.actor, e.action, describe(e)].map(q).join(","));
  return lines.join("\n");
}

export function AuditTrail({ data }: { data: Case }) {
  const [entries, setEntries] = useState<AuditEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [onlyDecisions, setOnlyDecisions] = useState(false);

  // Dosarul se schimbă după o decizie HITL: reîncărcăm jurnalul
  useEffect(() => {
    setEntries(null);
    api
      .getCaseAudit(data.case_id)
      .then((a) => setEntries([...a].sort((x, y) => x.timestamp.localeCompare(y.timestamp))))
      .catch((e: Error) => setError(e.message));
  }, [data.case_id, data.updated_at]);

  if (error) return <p className="text-sm text-danger-ink">Jurnalul nu a putut fi încărcat: {error}</p>;
  if (!entries) return <p className="text-sm text-muted">Se încarcă jurnalul…</p>;

  const rows = onlyDecisions ? entries.filter(isDecision) : entries;
  const humans = entries.filter((e) => e.actor.startsWith("user:")).length;

  function exportCsv() {
    const blob = new Blob(["﻿" + toCsv(data.case_id, entries!)], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `audit_${data.order?.case_number?.replace("/", "-") ?? data.case_id}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <section aria-label="Jurnal de audit">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted">
          {entries.length} înregistrări, {humans ? `${humans} ${humans === 1 ? "intervenție umană" : "intervenții umane"}` : "fără intervenție umană"}
        </p>
        <div className="flex items-center gap-2">
          <label className="flex cursor-pointer items-center gap-2 text-sm font-medium">
            <input type="checkbox" checked={onlyDecisions} onChange={(e) => setOnlyDecisions(e.target.checked)} className="h-4 w-4 accent-ink" />
            Doar decizii
          </label>
          <button
            onClick={exportCsv}
            className="ml-2 inline-flex h-9 items-center gap-1.5 rounded-md bg-paper px-3 text-sm font-semibold ring-1 ring-line-strong transition-[box-shadow,transform] duration-150 ease-out hover:ring-ink active:scale-[0.97]"
          >
            <Download size={15} aria-hidden />
            Exportă CSV
          </button>
        </div>
      </div>

      <div className="mt-3 overflow-x-auto rounded-lg ring-1 ring-line">
        <table className="w-full min-w-[640px] text-sm">
          <thead className="bg-canvas text-left text-xs font-semibold text-muted">
            <tr>
              <th className="px-4 py-2.5">Ora</th>
              <th className="px-4 py-2.5">Cine</th>
              <th className="px-4 py-2.5">Acțiune</th>
              <th className="px-4 py-2.5">Detalii</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((e, i) => {
              const who = actorOf(e);
              return (
                <tr
                  key={i}
                  className={`border-t border-line align-top ${who.human ? "bg-sun-soft" : e.action === "EXCEPTION_RAISED" ? "bg-danger-soft" : ""}`}
                >
                  <td className="px-4 py-2.5 font-mono text-xs whitespace-nowrap text-muted">{formatTime(e.timestamp)}</td>
                  <td className="px-4 py-2.5 whitespace-nowrap">
                    <span className={`inline-flex items-center gap-1.5 ${who.human ? "font-bold" : "font-medium"}`}>
                      {who.human ? <UserRound size={14} aria-hidden /> : <Bot size={14} className="text-muted" aria-hidden />}
                      {who.name}
                    </span>
                  </td>
                  <td className={`px-4 py-2.5 whitespace-nowrap ${e.action === "EXCEPTION_RAISED" ? "font-semibold text-danger-ink" : who.human ? "font-semibold" : ""}`}>
                    {ACTION_LABEL[e.action] ?? e.action}
                  </td>
                  <td className={`px-4 py-2.5 break-words ${e.action === "EXCEPTION_RAISED" ? "text-danger-ink" : who.human ? "text-ink" : "text-muted"}`}>
                    {describe(e)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
