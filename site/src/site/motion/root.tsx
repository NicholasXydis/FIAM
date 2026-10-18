import { domAnimation, LazyMotion, MotionConfig } from "motion/react";
import type { ReactNode } from "react";

// Motion's DOM features for every part, and reduced motion honoured.
export function Root({ children }: { children: ReactNode }) {
  return (
    <LazyMotion features={domAnimation} strict>
      <MotionConfig reducedMotion="user">{children}</MotionConfig>
    </LazyMotion>
  );
}
