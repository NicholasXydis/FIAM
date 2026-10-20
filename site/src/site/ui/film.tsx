import { useEffect, useRef, useState } from "react";
import type { Content } from "@/content/site";
import { back, captions, full, fullWay, kept, mount, skip, toggle, watchFull } from "../player";
import { Pill } from "./pill";

// The film over the landing: two videos for changing copy, controls.
export function Film(words: Content["landing"]["film"]) {
  const { label, back: backLabel, skip: skipLabel, play, captions: ccLabel, full: fullLabel } = words;
  const root = useRef<HTMLDivElement>(null);
  const [cc, setCc] = useState(false);
  const [canFull, setCanFull] = useState(false);
  const [isFull, setIsFull] = useState(false);
  // Binds the player here: the captions as last chosen, full screen.
  useEffect(() => {
    setCc(kept());
    const stop = mount(root.current!);
    setCanFull(fullWay() !== null);
    const unwatch = watchFull(setIsFull);
    return () => (unwatch(), stop());
  }, []);
  return (
    <div ref={root} className="film" role="dialog" aria-modal="true" aria-label={label} tabIndex={-1}>
      <canvas className="film-fill" aria-hidden="true" />
      <video className="film-video" playsInline preload="none" disablePictureInPicture aria-hidden="true" />
      <video className="film-video" playsInline preload="none" disablePictureInPicture aria-hidden="true" />
      <div className="film-wait" aria-hidden="true" />
      <p className="film-caption" aria-hidden="true">
        <span />
      </p>
      <div className="film-top">
        <Pill label={backLabel} icon="left" onPress={back} className="film-back" />
        <div className="film-right">
          <Pill label={ccLabel} icon="captions" pressed={cc} onPress={() => setCc(captions(!cc))} className="film-cc" />
          {canFull && (
            <Pill
              label={fullLabel}
              icon={isFull ? "shrink" : "expand"}
              pressed={isFull}
              onTap={full}
              className="film-full"
            />
          )}
          <Pill label={skipLabel} icon="right" trailing onPress={skip} />
        </div>
      </div>
      <div className="film-resume">
        <Pill size="big" label={play} icon="play" onPress={toggle} />
      </div>
    </div>
  );
}
