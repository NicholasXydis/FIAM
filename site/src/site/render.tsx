import { renderToString } from "react-dom/server";
import { CONTENT, type Content } from "@/content/site";
import { App } from "./app";
import { Pill } from "./ui/pill";

// A page's HTML, rendered at build so it arrives complete.
export const render = (page: keyof Content) => renderToString(<App page={page} content={CONTENT[page]} />);

// The page's words as JSON for hydrating, safe inside a script tag.
export const words = (page: keyof Content) => JSON.stringify(CONTENT[page]).replace(/</g, "\\u003c");

// The tour's Back, the site's own pill, rendered once at build.
export const back = () => renderToString(<Pill label="Back" icon="left" href="/" className="tour-back" />);
