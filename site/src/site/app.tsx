import type { ReactNode } from "react";
import type { Content } from "@/content/site";
import { Landing } from "./pages/landing";
import { Missing } from "./pages/missing";
import { Team } from "./pages/team";

// Each page by the name its HTML file asks for in data-page.
const PAGES = { landing: Landing, team: Team, missing: Missing };

// One page with its words, the same tree on the server and the client.
export function App<K extends keyof Content>({ page, content }: { page: K; content: Content[K] }) {
  const Page = PAGES[page] as (props: Content[K]) => ReactNode;
  return <Page {...content} />;
}
