import { type ClassValue, clsx } from "clsx";
import { extendTailwindMerge } from "tailwind-merge";

// Merging that knows the theme's sizes, so text-body is not a colour.
const merge = extendTailwindMerge({
  extend: { theme: { text: ["eyebrow", "small", "body", "lead", "title"], spacing: ["flow", "touch"] } },
});

// Joins class names; a later Tailwind class wins over an earlier.
export function cn(...inputs: ClassValue[]) {
  return merge(clsx(inputs));
}
