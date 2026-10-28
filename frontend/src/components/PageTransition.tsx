// Intrarea pe site LexOps, o singură dată la încărcare. Proprietar: Om4.
// Ecran galben → logo-ul Raiffeisen apare → logo-ul devine o fereastră prin care se vede pagina → zoom în fereastră.
// Fereastra e o mască CSS „exclude”: overlay-ul galben are o gaură exact în forma logo-ului.
import { useEffect, useRef } from "react";
import logo from "../assets/logo_raiffeisen.png";

const LOGO_PX = 180;
const EASE_OUT = "cubic-bezier(0.23, 1, 0.32, 1)";
const EASE_IN_OUT = "cubic-bezier(0.77, 0, 0.175, 1)";

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

function setLogoHole(el: HTMLElement) {
  const s = el.style as CSSStyleDeclaration & Record<string, string>;
  s.maskImage = s.webkitMaskImage = `url("${logo}"), linear-gradient(#000 0 0)`;
  s.maskSize = s.webkitMaskSize = `${LOGO_PX}px ${LOGO_PX}px, 100% 100%`;
  s.maskRepeat = s.webkitMaskRepeat = "no-repeat";
  s.maskPosition = s.webkitMaskPosition = "center";
  s.maskComposite = "exclude";
  s.webkitMaskComposite = "xor";
}

export function IntroTransition({ onDone }: { onDone: () => void }) {
  const overlay = useRef<HTMLDivElement>(null);
  const logoRef = useRef<HTMLImageElement>(null);

  useEffect(() => {
    let cancelled = false;
    const o = overlay.current!;
    const img = logoRef.current!;

    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      onDone();
      return;
    }

    (async () => {
      await img.animate(
        [
          { opacity: 0, transform: "scale(0.9)" },
          { opacity: 1, transform: "scale(1)" },
        ],
        { duration: 560, easing: EASE_OUT, fill: "forwards" },
      ).finished;
      await sleep(380);
      if (cancelled) return;

      // Logo-ul devine fereastra prin care se vede pagina
      setLogoHole(o);
      await img.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 300, easing: EASE_OUT, fill: "forwards" }).finished;
      await sleep(160);
      o.style.pointerEvents = "none";

      // Zoom în fereastră; spre final overlay-ul se stinge, ca să nu rămână galben între brațele logo-ului
      await o.animate(
        [
          { transform: "scale(1)", opacity: 1 },
          { transform: "scale(9)", opacity: 1, offset: 0.55 },
          { transform: "scale(26)", opacity: 0 },
        ],
        { duration: 820, easing: EASE_IN_OUT, fill: "forwards" },
      ).finished;
      if (!cancelled) onDone();
    })();

    return () => {
      cancelled = true;
    };
  }, [onDone]);

  return (
    <div ref={overlay} className="fixed inset-0 z-[100] grid place-items-center bg-sun will-change-transform" aria-hidden>
      <img ref={logoRef} src={logo} alt="" className="opacity-0" style={{ width: LOGO_PX, height: LOGO_PX }} />
    </div>
  );
}
