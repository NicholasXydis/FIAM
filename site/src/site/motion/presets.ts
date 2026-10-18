import type { Transition } from "motion/react";

// A press: a quick dip and a small overshoot on the way back.
const SNAP: Transition = { type: "spring", stiffness: 520, damping: 26, mass: 0.7 };
// Panels and risen content settle softly, with no overshoot.
export const SETTLE: Transition = { type: "spring", stiffness: 260, damping: 32 };
// The gold light trails the pointer lazily, like a slow camera.
export const TRAIL = { stiffness: 36, damping: 16, mass: 1.4 };
// Words and items arrive in turn, this many seconds apart.
export const STAGGER = 0.09;
// The first word waits this long, so the page has painted.
export const FIRST = 0.25;

// Press feedback for anything tapped, clicked or pressed with Enter.
export const PRESS = { whileTap: { scale: 0.96 }, transition: SNAP };
