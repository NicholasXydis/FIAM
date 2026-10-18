import { Fragment } from "react";
import { FIRST, STAGGER } from "../motion/presets";
import { cn } from "./cn";

// Words that arrive in turn in CSS, so the first frame is complete.
function Words({ text, from }: { text: string; from: number }) {
  return text.split(" ").map((word, i) => (
    <Fragment key={i}>
      {i > 0 && " "}
      <span
        className="inline-block motion-safe:animate-arrive"
        style={{ animationDelay: `${FIRST + (from + i) * STAGGER}s` }}
      >
        {word}
      </span>
    </Fragment>
  ));
}

// What a title says, its one gold phrase if any, and extra classes.
interface Props {
  text: string;
  gold?: string;
  className?: string;
}

// The film's title card: serif words, the gold phrase in italic.
export function Title({ text, gold, className }: Props) {
  return (
    <h1 className={cn("font-display text-title font-normal text-balance", className)}>
      <Words text={text} from={0} />
      {gold && (
        <>
          {" "}
          <em className="text-gold">
            <Words text={gold} from={text.split(" ").length} />
          </em>
        </>
      )}
    </h1>
  );
}
