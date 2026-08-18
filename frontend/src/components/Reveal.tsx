// Scroll-entrance wrapper: fades content up once when it first enters the
// viewport. transform + opacity only (styles in index.css); reduced motion is
// handled by the global override there. Put data-cascade on a child container
// to stagger its children 50ms apart.
import { useEffect, useRef, useState } from "react";
import type { HTMLAttributes } from "react";
import { clsx } from "clsx";

export function Reveal({
  className,
  children,
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  const ref = useRef<HTMLDivElement>(null);
  const [shown, setShown] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el || typeof IntersectionObserver === "undefined") {
      setShown(true);
      return;
    }
    const obs = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          setShown(true);
          obs.disconnect();
        }
      },
      { rootMargin: "0px 0px -60px 0px" },
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, []);

  return (
    <div ref={ref} data-shown={shown || undefined} className={clsx("reveal", className)} {...props}>
      {children}
    </div>
  );
}
