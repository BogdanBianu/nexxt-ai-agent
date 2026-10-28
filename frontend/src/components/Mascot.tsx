// Lex, mascota LexOps: un pătrat galben cu ochelari, în colțul din dreapta jos. Sare din când în când
// și spune câte o replică; restul aplicației îi poate da replici prin say() din lib/mascot. Proprietar: Om4.
import { useCallback, useEffect, useRef, useState } from "react";
import { X } from "lucide-react";
import { MASCOT_EVENT } from "../lib/mascot";

const IDLE_LINES = [
  "Alocația copilului nu se atinge. Am verificat de două ori.",
  "Art. 729 CPC îl știu pe de rost. Întreabă-mă orice.",
  "Diurnă de 6.000 de lei? Hmm. Mă uit mai atent.",
  "Trage un PDF aici. Promit că îl citesc tot, cu ochelari cu tot.",
  "Nimic nu se blochează fără să știi tu.",
  "Cafeaua e pe tine, procesarea e pe mine.",
  "Un CNP greșit îl prind din cifra de control.",
  "Sechestrul îngheață, poprirea virează. Nu le încurc.",
  "Dacă ceva nu-mi miroase a bine, mă opresc și te întreb.",
];

const GREETING = "Salut, sunt Lex! Lasă-mi documentele și mă apuc de treabă.";
const SHOW_MS = 6500;
const HOP_MS = 620;

const rand = (min: number, max: number) => min + Math.random() * (max - min);

function Face({ talking }: { talking: boolean }) {
  return (
    <svg viewBox="0 0 64 64" className="h-16 w-16 drop-shadow-[0_6px_10px_rgba(0,0,0,0.15)]" aria-hidden>
      <rect x="4" y="4" width="56" height="56" rx="11" fill="#fff200" stroke="#000" strokeWidth="3" />
      {/* ochelari */}
      <path d="M4 27 h7 M53 27 h7 M29 27 h6" stroke="#000" strokeWidth="3" strokeLinecap="round" />
      <rect x="11" y="19" width="18" height="15" rx="4" fill="#fff" stroke="#000" strokeWidth="3" />
      <rect x="35" y="19" width="18" height="15" rx="4" fill="#fff" stroke="#000" strokeWidth="3" />
      <g className="origin-center animate-blink [transform-box:fill-box]">
        <circle cx="21" cy="27" r="3.2" fill="#000" />
        <circle cx="43" cy="27" r="3.2" fill="#000" />
      </g>
      {talking ? (
        <ellipse cx="32" cy="47" rx="5" ry="3.6" fill="#000" />
      ) : (
        <path d="M25 45 Q32 51 39 45" fill="none" stroke="#000" strokeWidth="3" strokeLinecap="round" />
      )}
    </svg>
  );
}

export function Mascot() {
  const [line, setLine] = useState<string | null>(null);
  const [hopKey, setHopKey] = useState(0);
  const [hopping, setHopping] = useState(false);
  const hideTimer = useRef<number | undefined>(undefined);
  const lastIdle = useRef(-1);

  const hop = useCallback(() => {
    setHopKey((k) => k + 1);
    setHopping(true);
    window.setTimeout(() => setHopping(false), HOP_MS);
  }, []);

  const speak = useCallback(
    (text: string) => {
      hop();
      setLine(text);
      window.clearTimeout(hideTimer.current);
      hideTimer.current = window.setTimeout(() => setLine(null), SHOW_MS);
    },
    [hop],
  );

  const idleLine = useCallback(() => {
    let i = Math.floor(Math.random() * IDLE_LINES.length);
    if (i === lastIdle.current) i = (i + 1) % IDLE_LINES.length;
    lastIdle.current = i;
    return IDLE_LINES[i];
  }, []);

  // Salutul la prima apariție
  useEffect(() => {
    const t = window.setTimeout(() => speak(GREETING), 2500);
    return () => window.clearTimeout(t);
  }, [speak]);

  // Din când în când: o săritură, uneori și o replică
  useEffect(() => {
    let t: number;
    const schedule = () => {
      t = window.setTimeout(() => {
        if (document.visibilityState === "visible") {
          if (Math.random() < 0.6) speak(idleLine());
          else hop();
        }
        schedule();
      }, rand(16000, 28000));
    };
    schedule();
    return () => window.clearTimeout(t);
  }, [speak, hop, idleLine]);

  // Replici trimise de restul aplicației (ex. începutul și finalul unui lot)
  useEffect(() => {
    const onSay = (e: Event) => speak((e as CustomEvent<string>).detail);
    window.addEventListener(MASCOT_EVENT, onSay);
    return () => window.removeEventListener(MASCOT_EVENT, onSay);
  }, [speak]);

  useEffect(() => () => window.clearTimeout(hideTimer.current), []);

  return (
    <div className="pointer-events-none fixed right-5 bottom-5 z-40 flex items-end gap-3 sm:right-8 sm:bottom-8">
      {line && (
        <div
          role="status"
          aria-live="polite"
          className="pointer-events-auto relative mb-6 max-w-[16rem] origin-bottom-right animate-bubble-in rounded-lg bg-paper py-3 pr-9 pl-4 text-sm leading-snug font-medium shadow-[0_12px_32px_rgba(0,0,0,0.14)] ring-1 ring-ink/10"
        >
          {line}
          <button
            onClick={() => setLine(null)}
            aria-label="Închide replica"
            className="absolute top-2 right-2 grid h-6 w-6 place-items-center rounded-md text-muted hover:bg-canvas hover:text-ink"
          >
            <X size={14} aria-hidden />
          </button>
          {/* coada bulei, spre mascotă */}
          <span className="absolute -right-1.5 bottom-4 h-3 w-3 rotate-45 bg-paper ring-1 ring-ink/10 [clip-path:polygon(100%_0,100%_100%,0_0)]" aria-hidden />
        </div>
      )}

      <div className="pointer-events-auto flex flex-col items-center">
        <button
          key={hopKey}
          onClick={() => speak(idleLine())}
          aria-label="Lex, asistentul LexOps: apasă pentru o replică"
          className={`origin-bottom cursor-pointer rounded-xl transition-transform duration-150 hover:-translate-y-0.5 active:scale-95 ${hopping ? "animate-hop" : ""}`}
        >
          <Face talking={!!line} />
        </button>
        <span key={`s${hopKey}`} className={`mt-1 h-1.5 w-11 rounded-full bg-ink/15 ${hopping ? "animate-hop-shadow" : ""}`} aria-hidden />
      </div>
    </div>
  );
}
