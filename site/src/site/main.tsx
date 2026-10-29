import { hydrateRoot } from "react-dom/client";
import type { Content } from "@/content/site";
import { App } from "./app";

// The prerendered page, and the words the build wrote beside it.
const root = document.getElementById("app")!;
const page = root.dataset["page"] as keyof Content;
const content = JSON.parse(document.getElementById("words")!.textContent!) as Content[typeof page];

// Brings the page to life without redrawing what is already there.
hydrateRoot(root, <App page={page} content={content} />);
