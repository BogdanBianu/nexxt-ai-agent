// Tranziția galbenă LexOps. Proprietar: Om4.
// Intrare pe site: ecran galben → logo-ul Raiffeisen apare → logo-ul devine o fereastră prin care se vede
// pagina → zoom în fereastră. Spre un modul: fundalul galben cu logo intră cu zoom-in →
// numele modulului, foarte gros → numele devine fereastră spre pagina nouă → zoom.
// Fereastra e o mască CSS „exclude”: overlay-ul galben are o gaură exact în forma logo-ului sau a cuvântului.
import { useEffect, useRef } from "react";
import logo from "../assets/logo_raiffeisen.png";

export interface TransitionRequest {
  key: number;
  intro?: boolean;
  // Cuvântul afișat (ex. „Popriri”); fără el, doar logo-ul
  word?: string | null;
  // Chemat când ecranul e complet acoperit: aici se schimbă pagina de dedesubt
  onCovered?: () => void;
}

const LOGO_PX = 180;
const EASE_OUT = "cubic-bezier(0.23, 1, 0.32, 1)";
const EASE_IN_OUT = "cubic-bezier(0.77, 0, 0.175, 1)";

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

function setMask(el: HTMLElement, url: string, w: number, h: number) {
  const s = el.style as CSSStyleDeclaration & Record<string, string>;
  const image = `url("${url}"), linear-gradient(#000 0 0)`;
  const size = `${w}px ${h}px, 100% 100%`;
  s.maskImage = s.webkitMaskImage = image;
  s.maskSize = s.webkitMaskSize = size;
  s.maskRepeat = s.webkitMaskRepeat = "no-repeat";
  s.maskPosition = s.webkitMaskPosition = "center";
  s.maskComposite = "exclude";
  s.webkitMaskComposite = "xor";
}


// Desenăm cuvântul exact cum apare pe ecran, ca masca să se suprapună peste textul negru
async function wordMask(el: HTMLElement) {
  await document.fonts.ready;
  const cs = getComputedStyle(el);
  const rect = el.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  const canvas = document.createElement("canvas");
  canvas.width = Math.ceil(rect.width * dpr);
  canvas.height = Math.ceil(rect.height * dpr);
  const ctx = canvas.getContext("2d")!;
  ctx.scale(dpr, dpr);
  ctx.font = `${cs.fontWeight} ${cs.fontSize} ${cs.fontFamily}`;
  (ctx as CanvasRenderingContext2D & { letterSpacing: string }).letterSpacing = cs.letterSpacing === "normal" ? "0px" : cs.letterSpacing;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillStyle = "#000";
  ctx.fillText(el.textContent ?? "", rect.width / 2, rect.height / 2 + parseFloat(cs.fontSize) * 0.04);
  return { url: canvas.toDataURL(), w: rect.width, h: rect.height };
}

export function PageTransition({ request, onDone }: { request: TransitionRequest; onDone: () => void }) {
  const overlay = useRef<HTMLDivElement>(null);
  const logoRef = useRef<HTMLImageElement>(null);
  const wordRef = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    let cancelled = false;
    const o = overlay.current!;
    const img = logoRef.current!;
    const word = wordRef.current;

    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      request.onCovered?.();
      onDone();
      return;
    }

    const fade = (el: Element, from: number, to: number, ms: number, extra: Keyframe[] = []) =>
      el.animate(extra.length ? extra : [{ opacity: from }, { opacity: to }], { duration: ms, easing: EASE_OUT, fill: "forwards" }).finished;

    // Zoom în fereastră; spre final overlay-ul se stinge, ca să nu rămână galben între litere
    const reveal = () =>
      o.animate(
        [
          { transform: "scale(1)", opacity: 1 },
          { transform: "scale(9)", opacity: 1, offset: 0.55 },
          { transform: "scale(26)", opacity: 0 },
        ],
        { duration: 820, easing: EASE_IN_OUT, fill: "forwards" },
      ).finished;

    (async () => {
      if (request.intro) {
        request.onCovered?.();
        await fade(img, 0, 1, 560, [
          { opacity: 0, transform: "scale(0.9)" },
          { opacity: 1, transform: "scale(1)" },
        ]);
        await sleep(380);
      } else {
        // Fundalul galben cu logo intră peste pagina veche, cu un zoom-in
        img.style.opacity = "1";
        await o.animate(
          [
            { opacity: 0, transform: "scale(1.12)" },
            { opacity: 1, transform: "scale(1)" },
          ],
          { duration: 420, easing: EASE_OUT, fill: "forwards" },
        ).finished;
        if (cancelled) return;
        request.onCovered?.();
        await sleep(140);
        if (word) {
          await Promise.all([
            fade(img, 1, 0, 220, [
              { opacity: 1, transform: "scale(1)" },
              { opacity: 0, transform: "scale(0.85)" },
            ]),
            fade(word, 0, 1, 320, [
              { opacity: 0, transform: "scale(0.94)" },
              { opacity: 1, transform: "scale(1)" },
            ]),
          ]);
          await sleep(260);
        }
      }
      if (cancelled) return;

      // Logo-ul / cuvântul devine fereastra prin care se vede pagina
      if (word && !request.intro) {
        const m = await wordMask(word);
        setMask(o, m.url, m.w, m.h);
        await fade(word, 1, 0, 260);
      } else {
        setMask(o, logo, LOGO_PX, LOGO_PX);
        await fade(img, 1, 0, 300);
      }
      await sleep(160);
      o.style.pointerEvents = "none";
      await reveal();
      if (!cancelled) onDone();
    })();

    return () => {
      cancelled = true;
    };
  }, [request.key]);

  return (
    <div
      ref={overlay}
      className="fixed inset-0 z-[100] grid place-items-center bg-sun will-change-transform"
      // Spre un modul overlay-ul intră din transparent; la intrarea pe site pornește direct galben
      style={{ opacity: request.intro ? 1 : 0 }}
      aria-hidden
    >
      <img ref={logoRef} src={logo} alt="" className="col-start-1 row-start-1 opacity-0" style={{ width: LOGO_PX, height: LOGO_PX }} />
      {request.word && (
        <span
          ref={wordRef}
          className="col-start-1 row-start-1 px-6 text-[clamp(3.25rem,12.5vw,14rem)] leading-none font-black tracking-[-0.045em] whitespace-nowrap opacity-0"
        >
          {request.word.toLocaleUpperCase("ro-RO")}
        </span>
      )}
    </div>
  );
}
