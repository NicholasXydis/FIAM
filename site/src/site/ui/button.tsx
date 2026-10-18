import { cva, type VariantProps } from "class-variance-authority";
import { m } from "motion/react";
import type { ReactNode } from "react";
import { PRESS } from "../motion/presets";
import { cn } from "./cn";

// The site's two looks for a way in: solid moon ink, or a hairline.
const buttonVariants = cva(
  "inline-flex min-h-12 items-center justify-center gap-2 rounded-full px-[1.6em] py-[0.7em] text-body font-medium whitespace-nowrap transition-colors",
  {
    variants: {
      variant: {
        solid: "bg-moon text-film hover:bg-moon/90",
        outline: "border border-hairline bg-film/40 text-moon hover:bg-glass",
      },
    },
    defaultVariants: { variant: "solid" },
  },
);

// What a button links to, its words, and its look.
interface Props extends VariantProps<typeof buttonVariants> {
  href: string;
  children: ReactNode;
  className?: string;
}

// A link shaped as a button, springing back when pressed.
function Button({ href, variant, className, children }: Props) {
  return (
    <m.a href={href} {...PRESS} data-slot="button" className={cn(buttonVariants({ variant }), className)}>
      {children}
    </m.a>
  );
}

export { Button };
