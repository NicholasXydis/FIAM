import { m, useInView, useReducedMotion } from "motion/react";
import { type ReactNode, useEffect, useRef, useState } from "react";
import { SETTLE, STAGGER } from "./presets";

// Where content below the fold waits: lowered and soft, never hidden.
const LOW = { y: 18, filter: "blur(6px)", transition: { duration: 0 } };

// What a reveal wraps, its place in a run, and the tag it renders.
interface Props {
  children: ReactNode;
  order?: number;
  className?: string;
  as?: "div" | "li";
}

// Rises into place on scrolling into view; content seen at load stays.
export function Reveal({ children, order = 0, className, as = "div" }: Props) {
  const ref = useRef<HTMLDivElement & HTMLLIElement>(null);
  const reduce = useReducedMotion();
  const seen = useInView(ref, { once: true, margin: "0px 0px -8% 0px" });
  const [waiting, setWaiting] = useState(false);
  // Only what starts below the screen waits, and only once hydrated.
  useEffect(() => {
    const top = ref.current?.getBoundingClientRect().top ?? 0;
    if (!reduce && top > innerHeight) setWaiting(true);
  }, [reduce]);
  const rise = { y: 0, filter: "blur(0px)", transition: { ...SETTLE, delay: order * STAGGER } };
  const Tag = as === "li" ? m.li : m.div;
  return (
    <Tag ref={ref} className={className} {...(waiting && { animate: seen ? rise : LOW })}>
      {children}
    </Tag>
  );
}
