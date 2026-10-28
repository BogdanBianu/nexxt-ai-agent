// Disecția extrasului de cont linie cu linie + regulile aplicate. Proprietar: Om4.
// Fiecare rând are o bară: negru = partea care se oprește (la sechestru: se îngheață), galben = partea protejată.
import { OctagonAlert } from "lucide-react";
import type { Case, RuleApplication } from "../types/contracts";
import { CATEGORY_GROUP, CATEGORY_LABEL, formatDate, formatRon, GROUP_LABEL } from "../lib/ui";

function ruleFor(txId: string, rules: RuleApplication[]) {
  return rules.find((r) => r.tx_ids.includes(txId));
}

// Cota urmăribilă a regulii (ex. 1/3 din salariu → 0.33)
function seizableShare(rule: RuleApplication | undefined) {
  if (!rule || rule.base_amount === 0) return null;
  return rule.seizable_amount / rule.base_amount;
}

function SplitBar({ share }: { share: number }) {
  return (
    <div className="flex h-2 w-full overflow-hidden rounded-sm bg-sun ring-1 ring-ink/10" aria-hidden>
      <div className="bg-ink" style={{ width: `${share * 100}%` }} />
    </div>
  );
}

export function AccountDissection({ data, seizure = false }: { data: Case; seizure?: boolean }) {
  const txs = data.classified_transactions;
  const rules = data.decision?.rules_applied ?? [];
  // Tranzacțiile citate ca dovadă într-o excepție nerezolvată
  const flagged = new Set(data.exceptions.filter((e) => !e.resolved).flatMap((e) => e.evidence));

  return (
    <section aria-labelledby="dissection-title">
      <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-2">
        <h2 id="dissection-title" className="display text-xl">
          Extras de cont
        </h2>
        <div className="flex gap-5 text-sm text-muted">
          <span className="flex items-center gap-2">
            <span className="h-2 w-4 rounded-sm bg-ink" /> {seizure ? "Se îngheață" : "Se oprește"}
          </span>
          <span className="flex items-center gap-2">
            <span className="h-2 w-4 rounded-sm bg-sun ring-1 ring-ink/10" /> Rămâne clientului
          </span>
        </div>
      </div>

      {txs.length === 0 ? (
        <div className="mt-4 rounded-lg border border-dashed border-line-strong px-5 py-8 text-sm">
          <p className="font-medium">Extrasul nu a fost analizat</p>
          <p className="mt-1 text-muted">
            {data.exceptions.length > 0
              ? "Procesarea s-a oprit înainte de clasificarea veniturilor. După rezolvarea problemei de mai sus, dosarul poate fi reprocesat."
              : "Contul nu are încasări în perioada analizată."}
          </p>
        </div>
      ) : (
        <div className="mt-4 overflow-x-auto rounded-lg ring-1 ring-line">
          <table className="w-full min-w-[820px] text-sm">
            <thead className="bg-canvas text-left text-muted">
              <tr className="border-b border-line">
                <th className="px-4 py-2.5 font-medium">Data</th>
                <th className="px-4 py-2.5 font-medium">Plătitor</th>
                <th className="px-4 py-2.5 font-medium">Categorie</th>
                <th className="px-4 py-2.5 font-medium">Temei legal</th>
                <th className="px-4 py-2.5 text-right font-medium">Sumă</th>
                <th className="w-44 px-4 py-2.5 font-medium">{seizure ? "Cotă înghețată" : "Cotă urmăribilă"}</th>
              </tr>
            </thead>
            <tbody>
              {txs.map((tx) => {
                const rule = ruleFor(tx.tx_id, rules);
                const share = seizableShare(rule);
                const isFlagged = flagged.has(tx.tx_id);
                return (
                  <tr
                    key={tx.tx_id}
                    className={`border-b border-line last:border-b-0 ${isFlagged ? "bg-danger-soft" : "hover:bg-canvas/60"} ${tx.in_analysis_window ? "" : "text-muted"}`}
                  >
                    <td className="px-4 py-3 align-top whitespace-nowrap text-muted">{formatDate(tx.booking_date)}</td>
                    <td className="px-4 py-3 align-top">
                      <div className={`font-medium ${isFlagged ? "text-danger-ink" : ""}`}>{tx.counterparty_name}</div>
                      <div className="text-muted">{tx.description}</div>
                    </td>
                    <td className="px-4 py-3 align-top">
                      <div className="flex items-center gap-1.5 font-medium">
                        {CATEGORY_LABEL[tx.category]}
                        {isFlagged && <OctagonAlert size={15} className="text-danger" aria-label="Clasificare contestată de agentul de anomalii" />}
                      </div>
                      <div className="text-xs text-muted" title={tx.rationale}>
                        {seizure ? GROUP_LABEL[CATEGORY_GROUP[tx.category]].replace("oprește", "îngheață") : GROUP_LABEL[CATEGORY_GROUP[tx.category]]}
                      </div>
                    </td>
                    <td className="px-4 py-3 align-top">
                      {rule ? (
                        <>
                          <div>{rule.legal_source}</div>
                          <div className="font-mono text-xs text-muted">{rule.rule_id}</div>
                        </>
                      ) : (
                        <span className="text-muted">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right align-top font-medium whitespace-nowrap">{formatRon(tx.amount)}</td>
                    <td className="px-4 py-3 align-top">
                      {share == null ? (
                        <span className="text-muted">—</span>
                      ) : (
                        <div className="flex items-center gap-3 pt-1.5">
                          <SplitBar share={share} />
                          <span className="w-14 shrink-0 text-right text-xs font-medium">
                            {seizure && share >= 1 ? "Integral" : `${Math.round(share * 100)}%`}
                          </span>
                        </div>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {rules.length > 0 && (
        <>
          <h3 className="display mt-10 text-xl">Reguli aplicate</h3>
          <ul className="mt-4 divide-y divide-line rounded-lg ring-1 ring-line">
            {rules.map((r) => (
              <li key={r.rule_id} className="grid gap-x-6 gap-y-1 px-4 py-3 text-sm md:grid-cols-[12rem_1fr_auto]">
                <div>
                  <div className="font-medium">{r.legal_source}</div>
                  <div className="font-mono text-xs text-muted">{r.rule_id}</div>
                </div>
                <p className="leading-relaxed text-muted">{r.description}</p>
                <div className="whitespace-nowrap md:text-right">
                  <span className="text-muted">din {formatRon(r.base_amount)}</span>
                  <div className="font-semibold">{formatRon(r.seizable_amount)}</div>
                </div>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
