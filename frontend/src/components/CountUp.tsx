// Figures count up when they scroll into view - the Maha AI site does this
// for its headline stats, and it is the one animation that carries meaning
// here: the eye lands on the number because it moved.
//
// Values arrive as written ("676", "20+", "100%", "0"), so the leading
// number is animated and whatever surrounds it is preserved. A value with
// no digits, or a reader who has asked for reduced motion, gets the final
// text immediately - never a number that animates to the wrong figure.
import { useEffect, useRef, useState } from "react";

const PARTS = /^(\D*)(\d[\d,]*(?:\.\d+)?)(.*)$/s;

function prefersReducedMotion(): boolean {
  return typeof matchMedia === "function"
    && matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export function CountUp({
  value,
  duration = 1100,
  className,
}: {
  value: string;
  duration?: number;
  className?: string;
}) {
  const ref = useRef<HTMLSpanElement>(null);
  const [shown, setShown] = useState(value);
  const parts = value.match(PARTS);

  useEffect(() => {
    // No digits to count, or motion is unwanted: show the real value.
    if (!parts || prefersReducedMotion()) {
      setShown(value);
      return;
    }
    const [, head, digits, tail] = parts;
    const target = Number(digits.replace(/,/g, ""));
    if (!Number.isFinite(target)) {
      setShown(value);
      return;
    }
    const decimals = (digits.split(".")[1] || "").length;
    const grouped = digits.includes(",");
    const render = (n: number) => {
      const fixed = n.toFixed(decimals);
      const withCommas = grouped
        ? Number(fixed).toLocaleString(undefined, {
            minimumFractionDigits: decimals,
            maximumFractionDigits: decimals,
          })
        : fixed;
      return `${head}${withCommas}${tail}`;
    };

    const el = ref.current;
    let raf = 0;
    let cancelled = false;

    const run = () => {
      const start = performance.now();
      const tick = (now: number) => {
        if (cancelled) return;
        const t = Math.min(1, (now - start) / duration);
        // Ease out: fast first, settling onto the figure.
        const eased = 1 - Math.pow(1 - t, 3);
        setShown(render(target * eased));
        if (t < 1) raf = requestAnimationFrame(tick);
        else setShown(value); // land on the value exactly as written
      };
      raf = requestAnimationFrame(tick);
    };

    // The TRUE value stays on screen until the animation actually begins.
    // Starting at zero instead would mean that if the trigger never fires -
    // no IntersectionObserver, a tab that never composites, an observer
    // that misses - the figure sits at 0 forever, showing a wrong number
    // rather than merely a still one. A stat that reads 0 when it is 676 is
    // a data error wearing an animation's clothes.
    if (!el || typeof IntersectionObserver === "undefined") {
      run();
      return () => { cancelled = true; cancelAnimationFrame(raf); };
    }
    const start = () => {
      if (cancelled) return;
      cancelled = false;
      run();
    };
    const obs = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          obs.disconnect();
          clearTimeout(fallback);
          start();
        }
      },
      { rootMargin: "0px 0px -40px 0px" },
    );
    obs.observe(el);
    // Belt and braces: if the observer has not spoken within a second, run
    // anyway. Worst case the count happens off-screen and the reader simply
    // finds the finished figure, which is the correct outcome either way.
    const fallback = window.setTimeout(() => {
      obs.disconnect();
      start();
    }, 1000);
    return () => {
      cancelled = true;
      cancelAnimationFrame(raf);
      clearTimeout(fallback);
      obs.disconnect();
    };
  }, [value, duration]);

  return (
    <span ref={ref} className={className}>
      {shown}
    </span>
  );
}
