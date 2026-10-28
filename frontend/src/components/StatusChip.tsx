// Eticheta de status a unui dosar. Roșu = problemă, negru = rezolvat. Proprietar: Om4.
import { CircleCheck, CircleDashed, ClipboardCheck, LoaderCircle, OctagonAlert } from "lucide-react";
import type { CaseStatus } from "../types/contracts";
import { STATUS_STYLE, type StatusTone } from "../lib/ui";

const TONE: Record<StatusTone, { className: string; Icon: typeof CircleCheck }> = {
  done: { className: "border-line-strong text-ink", Icon: CircleCheck },
  danger: { className: "border-danger/40 bg-danger-soft text-danger-ink", Icon: OctagonAlert },
  working: { className: "border-ink/20 bg-sun text-ink", Icon: LoaderCircle },
  neutral: { className: "border-line bg-canvas text-muted", Icon: CircleDashed },
  approval: { className: "border-ink/30 bg-sun-soft text-ink", Icon: ClipboardCheck },
};

export function StatusChip({ status, label }: { status: CaseStatus; label?: string }) {
  const s = STATUS_STYLE[status];
  const { className, Icon } = TONE[s.tone];
  return (
    <span className={`inline-flex shrink-0 items-center gap-1.5 rounded border py-0.5 pr-2 pl-1.5 text-xs font-semibold ${className}`}>
      <Icon size={14} strokeWidth={2.25} aria-hidden className={s.tone === "working" ? "animate-spin" : ""} />
      {label ?? s.label}
    </span>
  );
}
