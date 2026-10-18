import type { Content } from "@/content/site";
import { Button } from "../ui/button";
import { Eyebrow } from "../ui/eyebrow";
import { Figures } from "../ui/figures";
import { Lead } from "../ui/lead";
import { Page } from "../ui/page";
import { Title } from "../ui/title";

// The film's title card under its light, two ways in, three figures.
export function Landing({ name, disclaimer, eyebrow, title, gold, lead, figures }: Content["landing"]) {
  return (
    <Page name={name} disclaimer={disclaimer} here="landing" light={[0.5, 0.28]} place="low">
      <Eyebrow>{eyebrow}</Eyebrow>
      <Title text={title} gold={gold} />
      <Lead>{lead}</Lead>
      <nav
        aria-label="Ways in"
        className="mt-[calc(var(--spacing-flow)*0.4)] flex flex-wrap justify-center gap-3 @max-[22rem]:w-full @max-[22rem]:flex-col"
      >
        <Button href="/tour/">Tour the project</Button>
        <Button href="/team/" variant="outline" className="[view-transition-name:team]">
          Meet the team
        </Button>
      </nav>
      <Figures items={figures} />
    </Page>
  );
}
