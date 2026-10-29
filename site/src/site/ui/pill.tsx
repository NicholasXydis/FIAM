import type { MouseEvent, ReactNode } from "react";
import { Icon, type IconName } from "./icons";
import { afterPress, plain, wire } from "./press";

// What a pill says, where it goes or what it does, and how it looks.
interface Props {
  label: string;
  icon: IconName;
  href?: string;
  onPress?: () => void;
  // Runs inside the press itself, for what a browser allows only then.
  onTap?: () => void;
  // A toggle's state, for a pill that turns something on and off.
  pressed?: boolean;
  caption?: string;
  trailing?: boolean;
  external?: boolean;
  size?: "big" | "small";
  className?: string;
}

// The site's one button: glass, an icon, words, and ink beneath.
export function Pill(props: Props) {
  const { label, icon, href, onPress, onTap, pressed, caption, trailing = false, external = false } = props;
  const { size = "small", className } = props;
  // The words: a caption over the label, or the label alone.
  const words: ReactNode = caption ? (
    <span className="pill-stack">
      <span className="pill-cap">{caption}</span>
      <span className="pill-label">{label}</span>
    </span>
  ) : (
    <span className="pill-label">{label}</span>
  );
  // The icon before the words, or after them when trailing.
  const face = trailing ? (
    <>
      {words}
      <Icon name={icon} />
    </>
  ) : (
    <>
      <Icon name={icon} />
      {words}
    </>
  );
  // The face twice: once plain, once again in the ink layer.
  const body = (
    <>
      {face}
      <span className="pill-ink" aria-hidden="true">
        {face}
      </span>
    </>
  );
  const classes = ["pill", `pill-${size}`, className].filter(Boolean).join(" ");
  const named = caption ? `${caption} ${label}` : undefined;
  // A link waits for its press, then runs its action or follows itself.
  const go = (e: MouseEvent) => {
    if (external || !plain(e)) return;
    e.preventDefault();
    onTap?.();
    afterPress(onPress ?? (() => location.assign(href!)), onPress ? undefined : href);
  };
  return href ? (
    <a
      ref={wire}
      href={href}
      className={classes}
      aria-label={named}
      onClick={go}
      {...(external && { target: "_blank", rel: "noopener noreferrer" })}
    >
      {body}
    </a>
  ) : (
    <button
      ref={wire}
      type="button"
      className={classes}
      aria-label={named}
      aria-pressed={pressed}
      onClick={() => (onTap?.(), onPress && afterPress(onPress))}
    >
      {body}
    </button>
  );
}
