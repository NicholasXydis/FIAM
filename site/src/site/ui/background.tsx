import { m, useAnimationFrame, useMotionValue, useReducedMotion, useSpring, useTransform } from "motion/react";
import { useEffect, useRef } from "react";
import { seeded } from "@/shared/math";
import { TRAIL } from "../motion/presets";

// The sky's points in a 1600 by 1000 frame, thinning to the horizon.
const STARS = (() => {
  const random = seeded(2026);
  return Array.from({ length: 150 }, () => ({
    x: +(random() * 1600).toFixed(1),
    y: +(random() ** 1.6 * 860).toFixed(1),
    r: +(0.5 + random() ** 3 * 1.3).toFixed(2),
    o: +(0.15 + random() * 0.55).toFixed(2),
  }));
})();
// Seconds without a pointer before the light drifts on its own.
const IDLE = 3;
// The stars move this share of the light's travel, the other way.
const DEPTH = -0.04;

// The film's night: black, a violet horizon, stars and the gold light.
export function Background({ rest }: { rest: readonly [number, number] }) {
  const reduce = useReducedMotion();
  const aimX = useMotionValue(0);
  const aimY = useMotionValue(0);
  const x = useSpring(aimX, TRAIL);
  const y = useSpring(aimY, TRAIL);
  const skyX = useTransform(x, (v) => v * DEPTH);
  const skyY = useTransform(y, (v) => v * DEPTH);
  const last = useRef(-Infinity);

  // The light follows the pointer on a computer and a finger on a phone.
  useEffect(() => {
    if (reduce) return;
    const follow = (e: PointerEvent) => {
      last.current = performance.now();
      aimX.set(e.clientX - rest[0] * innerWidth);
      aimY.set(e.clientY - rest[1] * innerHeight);
    };
    addEventListener("pointermove", follow, { passive: true });
    addEventListener("pointerdown", follow, { passive: true });
    return () => {
      removeEventListener("pointermove", follow);
      removeEventListener("pointerdown", follow);
    };
  }, [reduce, rest, aimX, aimY]);

  // Left alone, it wanders a slow figure of eight around its place.
  useAnimationFrame((t) => {
    if (reduce || performance.now() - last.current < IDLE * 1000) return;
    const reach = Math.min(innerWidth, innerHeight);
    aimX.set(Math.sin(t / 9000) * reach * 0.16);
    aimY.set(Math.sin(t / 4500) * reach * 0.06);
  });

  return (
    <div aria-hidden="true" className="pointer-events-none fixed inset-0 -z-10 overflow-hidden bg-film">
      <div className="absolute inset-x-[-25%] bottom-[-38%] h-[78%] rounded-[50%] bg-[radial-gradient(closest-side,rgb(169_139_255/0.3),rgb(169_139_255/0.08)_55%,transparent)] motion-safe:animate-breathe" />
      <m.svg
        style={{ x: skyX, y: skyY }}
        className="absolute inset-[-3%] size-[106%]"
        viewBox="0 0 1600 1000"
        preserveAspectRatio="xMidYMid slice"
      >
        {STARS.map((s, i) => (
          <circle key={i} cx={s.x} cy={s.y} r={s.r} fill="var(--color-moon)" opacity={s.o} />
        ))}
      </m.svg>
      <m.div
        style={{ x, y, left: `${rest[0] * 100}%`, top: `${rest[1] * 100}%` }}
        className="absolute size-[clamp(16rem,62vmin,60rem)] -translate-1/2 rounded-full bg-[radial-gradient(closest-side,rgb(242_193_78/0.34),rgb(242_193_78/0.1)_45%,transparent)] will-change-transform"
      >
        <div className="absolute top-1/2 left-1/2 size-1.5 -translate-1/2 rounded-full bg-gold shadow-[0_0_18px_6px_rgb(242_193_78/0.55)]" />
      </m.div>
    </div>
  );
}
