import { useEffect, useRef, useState } from "react";
import { useReducedMotion } from "framer-motion";

/**
 * Short count-up for a single already-known numeric value.
 * Skips if reduced motion or value is non-finite.
 */
export function useCountReveal(target: number | null | undefined, durationMs = 520) {
  const reduceMotion = useReducedMotion();
  const [value, setValue] = useState(target ?? 0);
  const started = useRef(false);

  useEffect(() => {
    if (target == null || !Number.isFinite(target)) {
      setValue(0);
      return;
    }
    if (reduceMotion) {
      setValue(target);
      return;
    }
    if (started.current) {
      setValue(target);
      return;
    }
    started.current = true;
    const start = performance.now();
    let raf = 0;
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / durationMs);
      const eased = 1 - Math.pow(1 - t, 3);
      setValue(target * eased);
      if (t < 1) raf = requestAnimationFrame(tick);
      else setValue(target);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, durationMs, reduceMotion]);

  return value;
}

/** Extract first reasonable number from text for optional reveal (UI only). */
export function extractPrimaryNumber(text: string): {
  prefix: string;
  number: number;
  suffix: string;
  raw: string;
} | null {
  const m = text.match(/^(.*?)(\$?-?\d[\d,]*(?:\.\d+)?)(.*)$/);
  if (!m) return null;
  const raw = m[2];
  const num = Number(raw.replace(/[$,]/g, ""));
  if (!Number.isFinite(num) || Math.abs(num) > 1e12) return null;
  // Prefer headlines that lead with a meaningful metric, not tiny indices
  if (m[1].length > 40) return null;
  return { prefix: m[1], number: num, suffix: m[3], raw };
}
