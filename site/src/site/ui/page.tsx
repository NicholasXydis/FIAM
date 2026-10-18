import type { ReactNode } from "react";
import { Background } from "./background";
import { cn } from "./cn";
import { Footer } from "./footer";
import { Header, type Here } from "./header";

// Where a page's card sits: low under its light, or centred.
const PLACES = {
  low: "justify-end pt-[clamp(6rem,30svh,24rem)]",
  centred: "justify-center py-flow",
};

// What frames a page, where its light rests, and where its card sits.
interface Props {
  name: string;
  disclaimer: string;
  here: Here;
  light: readonly [number, number];
  place: keyof typeof PLACES;
  wide?: boolean;
  children: ReactNode;
}

// Every page: skip link, the night behind, header, card, disclaimer.
export function Page({ name, disclaimer, here, light, place, wide = false, children }: Props) {
  return (
    <div className="relative isolate flex min-h-svh flex-col safe-x">
      <a
        href="#main"
        className="absolute -top-25 left-[max(16px,env(safe-area-inset-left,0px))] z-10 inline-flex min-h-touch items-center rounded-full bg-moon px-4 text-film focus:top-3"
      >
        Skip to content
      </a>
      <Background rest={light} />
      <Header name={name} here={here} />
      <main
        id="main"
        className={cn("flex flex-1 flex-col items-center pb-[calc(var(--spacing-flow)*2)] text-center", PLACES[place])}
      >
        <div
          className={cn(
            "@container flex w-full flex-col items-center gap-flow",
            wide ? "max-w-304" : "max-w-[max(60rem,100vmin)]",
          )}
        >
          {children}
        </div>
      </main>
      <Footer disclaimer={disclaimer} />
    </div>
  );
}
